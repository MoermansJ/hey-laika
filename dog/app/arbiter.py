"""The behavior arbiter: single owner of all robot motion.

Every behavior source (lifecycle events, manual GUI, agents, safety
responses) submits here. Priority convention: LOWER number wins
(1 safety · 2 manual · 3 agent · 4 lifecycle · 5 idle).

Semantics:
- Idle arbiter: submission executes immediately.
- Busy: a strictly higher-priority submission preempts an interruptible
  current behavior AT THE NEXT STEP BOUNDARY; non-interruptible behaviors
  finish first (the submission waits at the front of the queue).
- Equal/lower priority queues (bounded, max 3) or is explicitly rejected —
  never silently dropped.
- Per-behavior cooldowns reject rapid re-triggers.
- Every run and transition lands in the store's run log and is pushed to
  listeners (activity log / STOMP via the app layer).
- Provenance: every submission carries a `cause` dict (raw event + matched
  binding, or manual/agent origin) that lands in the run log; interrupted
  runs record `preempted_by` — the preemptor's run id, or "manual_stop".
"""
import logging
import threading
import time
import uuid

logger = logging.getLogger(__name__)

QUEUE_MAX = 3


class Arbiter:
    def __init__(self, controller, store, on_change=None,
                 sleep_fn=time.sleep):
        self.controller = controller
        self.store = store
        self.on_change = on_change or (lambda status: None)
        self._sleep = sleep_fn

        self._lock = threading.RLock()
        self._work = threading.Condition(self._lock)
        self._queue: list[dict] = []      # sorted: (priority, seq)
        self._current: dict | None = None
        self._interrupt = False
        self._interrupted_by: str | None = None  # preemptor run id | "manual_stop"
        self._seq = 0
        self._last_start: dict[str, float] = {}
        self._stop_thread = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ---- public API --------------------------------------------------------

    def submit(self, behavior_name: str, source: str = "manual",
               priority: int = 2, cause: dict | None = None) -> dict:
        from app.metrics import metrics

        behavior = self.store.behavior(behavior_name)
        if behavior is None:
            metrics.inc("behavior.rejected")
            return {"status": "rejected", "reason": "behavior not found"}
        with self._lock:
            cooldown = behavior.get("cooldownS") or 0
            last = self._last_start.get(behavior_name, 0)
            if cooldown and time.time() - last < cooldown:
                metrics.inc("behavior.rejected")
                return {"status": "rejected", "reason": "cooldown"}
            # Duplicate suppression: same behavior already running or queued.
            if self._current and self._current["behavior"] == behavior_name:
                metrics.inc("behavior.rejected")
                return {"status": "rejected", "reason": "already running"}
            if any(s["behavior"] == behavior_name for s in self._queue):
                metrics.inc("behavior.rejected")
                return {"status": "rejected", "reason": "already queued"}
            if len(self._queue) >= QUEUE_MAX:
                metrics.inc("behavior.rejected")
                return {"status": "rejected", "reason": "queue full"}
            metrics.inc("behavior.submitted")
            metrics.inc(f"behavior.priority.{priority}")

            self._seq += 1
            submission = {"behavior": behavior_name, "source": source,
                          "priority": priority, "seq": self._seq,
                          "cause": cause or {"type": source},
                          "run_id": str(uuid.uuid4())}
            self._queue.append(submission)
            self._queue.sort(key=lambda s: (s["priority"], s["seq"]))

            preempting = (self._current is not None
                          and priority < self._current["priority"]
                          and self._current.get("interruptible", True))
            if preempting:
                self._interrupt = True
                self._interrupted_by = submission["run_id"]
                metrics.inc("behavior.preemptions")
            self._work.notify_all()
            position = self._queue.index(submission)
            return {"status": "preempting" if preempting else
                    ("executing" if self._current is None and position == 0
                     else "queued"),
                    "position": position}

    def stop_current(self) -> dict:
        with self._lock:
            if self._current is None:
                return {"stopped": False, "reason": "nothing running"}
            self._interrupt = True
            self._interrupted_by = "manual_stop"
            self._work.notify_all()
            return {"stopped": True, "behavior": self._current["behavior"]}

    def status(self) -> dict:
        with self._lock:
            current = None
            if self._current:
                current = {k: self._current[k] for k in
                           ("behavior", "source", "priority")}
                current["step"] = self._current.get("step", 0)
                current["stepTotal"] = self._current.get("stepTotal", 0)
                current["cause"] = self._current.get("cause")
                current["runId"] = self._current.get("run_id")
            queued = [{**{k: s[k] for k in ("behavior", "source", "priority")},
                       "cause": s.get("cause"), "runId": s.get("run_id")}
                      for s in self._queue]
        return {"current": current, "queued": queued,
                "recentRuns": self.store.recent_runs(10)}

    def shutdown(self) -> None:
        with self._lock:
            self._stop_thread = True
            self._interrupt = True
            self._work.notify_all()

    # ---- executor ----------------------------------------------------------

    def _run(self) -> None:
        while True:
            with self._lock:
                while not self._queue and not self._stop_thread:
                    self._work.wait()
                if self._stop_thread:
                    return
                submission = self._queue.pop(0)
                behavior = self.store.behavior(submission["behavior"])
                if behavior is None:
                    continue
                submission["interruptible"] = behavior.get("interruptible", True)
                submission["stepTotal"] = len(behavior["steps"])
                submission["step"] = 0
                self._current = submission
                self._interrupt = False
                self._interrupted_by = None
                self._last_start[behavior["name"]] = time.time()
            self._execute(submission, behavior)

    def _execute(self, submission: dict, behavior: dict) -> None:
        run_id = self.store.log_start(behavior["name"], submission["source"],
                                      submission["priority"],
                                      cause=submission["cause"],
                                      run_id=submission["run_id"])
        self._notify()
        status, detail = "complete", ""
        try:
            for index, step in enumerate(behavior["steps"]):
                with self._lock:
                    if self._interrupt and submission["interruptible"]:
                        status, detail = "interrupted", "preempted/stopped"
                        break
                    submission["step"] = index + 1
                sent = self.controller.send_command(step["command"])
                if not sent and step["command"] != "kup":
                    logger.warning("Behavior %s step failed: %s",
                                   behavior["name"], step["command"])
                    detail = f"step {index + 1} failed: {step['command']}"
                self._sleep(float(step.get("settleS", 1.0)))
                self._notify()
        except Exception as exc:
            logger.exception("Behavior %s crashed", behavior["name"])
            status, detail = "failed", str(exc)
        finally:
            with self._lock:
                preempted_by = (self._interrupted_by
                                if status == "interrupted" else None)
                self._current = None
                self._interrupt = False
                self._interrupted_by = None
            self.store.log_end(run_id, status, detail,
                               preempted_by=preempted_by)
            self._notify()

    def _notify(self) -> None:
        try:
            self.on_change(self.status())
        except Exception:
            logger.exception("Arbiter on_change listener failed")
