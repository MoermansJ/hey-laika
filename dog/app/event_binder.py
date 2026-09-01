"""Lifecycle event sources → binding lookup → arbiter submission.

Events (MVP): robot.online, idle.timeout, battery.low, exception.report,
plus manual/agent invokes that call the arbiter directly.

Idle-clock subtlety: the arbiter's own behaviors move the robot and stamp
controller.last_motion_at, which must NOT reset the idle ladder (or
sitting would forever postpone lying down). The binder only treats
motion as external activity when the arbiter was idle at the time.
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)


class EventBinder:
    def __init__(self, arbiter, store, controller,
                 tick_s: float = 5.0, battery_poll_s: float = 20.0):
        self.arbiter = arbiter
        self.store = store
        self.controller = controller
        self.tick_s = tick_s
        self.battery_poll_s = battery_poll_s

        self._idle_anchor = time.time()
        self._seen_motion_at = None
        self._fired_idle: set[float] = set()
        self._fired_battery: set[float] = set()
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._idle_loop, daemon=True).start()
        threading.Thread(target=self._battery_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    # ---- event entry points ------------------------------------------------

    def on_online(self) -> None:
        self.trigger("robot.online")

    def handle_output_line(self, line: str) -> None:
        """Unsolicited firmware output (controller hook)."""
        if line.startswith("EXCEPTION_REPORT"):
            parts = line.split()
            code = parts[1] if len(parts) > 1 else "?"
            logger.info("Firmware exception report: %s", line)
            self.trigger("exception.report", {"code": code})

    def trigger(self, event: str, data: dict | None = None) -> list[dict]:
        """Look up enabled bindings for the event; submit matches."""
        results = []
        for binding in self.store.bindings(event=event, enabled_only=True):
            if not self._filter_matches(binding.get("filter"), data):
                continue
            result = self.arbiter.submit(
                binding["behavior"], source=f"event.{event}",
                priority=binding["priority"],
                cause=self._cause(event, data, binding))
            results.append({"behavior": binding["behavior"], **result})
        return results

    @staticmethod
    def _filter_matches(filter_spec, data) -> bool:
        if not filter_spec:
            return True
        data = data or {}
        return all(str(data.get(k)) == str(v) for k, v in filter_spec.items())

    @staticmethod
    def _cause(event: str, payload: dict | None, binding: dict) -> dict:
        """Provenance: the raw trigger AND the binding that processed it."""
        return {"type": "event", "event": event, "payload": payload,
                "bindingId": binding.get("id"),
                "filter": binding.get("filter")}

    # ---- idle ladder -------------------------------------------------------

    def _idle_loop(self) -> None:
        while not self._stop.wait(self.tick_s):
            try:
                self._idle_tick()
            except Exception:
                logger.exception("Idle tick failed")

    def _idle_tick(self) -> None:
        motion_at = getattr(self.controller, "last_motion_at", None)
        arbiter_busy = self.arbiter.status()["current"] is not None
        if motion_at != self._seen_motion_at:
            self._seen_motion_at = motion_at
            if not arbiter_busy:
                # External motion (GUI, agent bypass, etc.) — reset ladder.
                self._idle_anchor = time.time()
                self._fired_idle.clear()
                return
        idle_s = time.time() - self._idle_anchor
        for binding in self.store.bindings(event="idle.timeout",
                                           enabled_only=True):
            threshold = float((binding.get("filter") or {}).get("seconds", 0))
            if threshold and idle_s >= threshold and \
                    threshold not in self._fired_idle:
                self._fired_idle.add(threshold)
                self.arbiter.submit(
                    binding["behavior"], source="event.idle.timeout",
                    priority=binding["priority"],
                    cause=self._cause("idle.timeout",
                                      {"seconds": threshold,
                                       "idleS": round(idle_s, 1)}, binding))

    def reset_idle(self) -> None:
        """External signal that activity happened (e.g. manual invoke)."""
        self._idle_anchor = time.time()
        self._fired_idle.clear()

    # ---- battery -----------------------------------------------------------

    def _battery_loop(self) -> None:
        while not self._stop.wait(self.battery_poll_s):
            try:
                telemetry = self.controller.get_telemetry()
                battery = telemetry.get("battery")
                if battery is None:
                    continue
                for binding in self.store.bindings(event="battery.low",
                                                   enabled_only=True):
                    pct = float((binding.get("filter") or {}).get("pct", 0))
                    if not pct:
                        continue
                    if battery <= pct and pct not in self._fired_battery:
                        self._fired_battery.add(pct)
                        self.arbiter.submit(
                            binding["behavior"], source="event.battery.low",
                            priority=binding["priority"],
                            cause=self._cause("battery.low",
                                              {"battery": battery, "pct": pct},
                                              binding))
                    elif battery > pct + 5:
                        self._fired_battery.discard(pct)  # re-arm on recharge
            except Exception:
                logger.exception("Battery tick failed")
