"""Navigation: the sensor loop, reactive avoidance, click-to-go routes,
sonar sweeps, overrides, and the wiring of errors to the error state.

Layer 1, reactive avoidance, is a thread that reads the ranger at
`sensorHz` while the dog has moved recently. Every reading is recorded in
the sensor log. A reading under `stopCm` during forward motion submits the
`obstacle_stop` behavior at safety priority, puts the obstacle on the map
and raises `nav.blocked`; a running route is preempted by the arbiter and
resumed with a fresh plan once the stop has finished. Avoidance stands
down while the running behavior carries the suppress-avoidance flag (an
override such as a jump), and resumes the moment that behavior ends.

Layers 2 and 3: a route is a generator-backed arbiter behavior. Each leg
turns toward the next waypoint with the firmware's closed-loop turn, then
walks it in bounded bursts. After every burst the IMU yaw replaces the
dead-reckoned heading, a fresh reading ahead goes into the grid, and the
leg is recomputed from the corrected pose; the route is re-planned from
wherever she actually is whenever a burst is blocked.

Layer 4: contradictions, sensor jumps, heading disagreement and failed
commands go through the ErrorHandler (three strikes of one kind escalate)
and the ErrorState pauses the dog and asks the human. The human's answer
comes back through `resolve()`: pin the cells the sensor saw, pin what the
map believed, or "I moved her" (cancel the route; reset the pose from the
Map tab).
"""
import logging
import math
import threading
import time

from app.behavior_store import PRIORITY_AGENT, PRIORITY_MANUAL, PRIORITY_SAFETY
from app.nav_errors import NavError, RecoverableError, UnrecoverableError
from app.sensor_log import classify

logger = logging.getLogger(__name__)

DEFAULTS = {
    "stopCm": 25.0,
    "sensorHz": 6.0,
    "alwaysSample": False,
    "movingWindowS": 3.0,
    "avoidanceEnabled": True,
    "walkSPerCycle": 1.3,
    "walkExtraS": 0.8,
    "turnSPerDeg": 0.05,
    "turnExtraS": 1.5,
    # Turns: "vt" spins in place with the continuous kvt gait while the host
    # watches the IMU and stops with kup (the gait learner's validated
    # turn); "firmware" uses kwkL/R deg, whose completion only arrives when
    # the yaw target is reached, longer than the transport's 20 s window on
    # a slow floor (live, 2026-09-09).
    "turnMode": "vt",
    "vtStopLeadDeg": 5.0,
    "vtPollS": 0.1,
    "vtSettleS": 1.0,
    "maxCyclesPerBurst": 3,
    "maxReplans": 8,
    "maxBlocked": 5,
    "resumeWaitS": 20.0,
    "rangerOnHead": True,
    "sweepAngles": [-90, -60, -30, 0, 30, 60, 90],
    "sweepSettleS": 0.6,
    "sweepAtStart": True,
    "yawDisagreeDeg": 30.0,
    "maxDriftM": 3.0,
    "jumpCm": 100.0,
    "missStreak": 12,
    "lookAheadMarginM": 0.10,
}

NAV_BEHAVIOR = "navigate"
SWEEP_BEHAVIOR = "sonar_sweep"
OVERRIDE_BEHAVIOR = "override"
STOP_BEHAVIOR = "obstacle_stop"


class NavigationRefused(Exception):
    """A request the navigator will not act on right now (409 at the API)."""


class NavigationService:
    def __init__(self, controller, arbiter, senses, ranger, grid, builder, planner,
                 sensor_log, action_log, errors, error_state, trigger=None,
                 config: dict | None = None, battery_reader=None,
                 is_away=lambda: False, clock=time.time, sleep=time.sleep):
        self.controller = controller
        self.arbiter = arbiter
        self.senses = senses
        self.ranger = ranger
        self.grid = grid
        self.builder = builder
        self.planner = planner
        self.sensor_log = sensor_log
        self.action_log = action_log
        self.errors = errors
        self.error_state = error_state
        self.trigger = trigger or (lambda event, payload=None: None)
        self.config = {**DEFAULTS, **(config or {})}
        self._battery = battery_reader or (lambda: None)
        self._is_away = is_away
        self._clock = clock
        self._sleep = sleep

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self.state = "idle"
        self.target: dict | None = None
        self.route: dict | None = None
        self.finished: dict | None = None
        self.last_block: dict | None = None
        self.last_sweep: dict | None = None
        self.blocked_count = 0
        self.replans = 0
        self._pan = 0.0
        self._last_motion_cmd: str | None = None
        self._last_motion_at: float | None = None
        self._last_reading: dict | None = None
        self._miss_streak = 0
        self._loop_thread = None
        self.stats = {"ticks": 0, "stops": 0, "suppressed": 0, "resumes": 0,
                      "sweeps": 0, "routes": 0, "arrivals": 0,
                      "recoverable": 0, "escalated": 0}

        self.errors.on_escalate = self._on_escalate
        self.error_state.on_resolve = self._apply_resolution
        self.senses.hold_sniffer = lambda: self.active

    # ---- lifecycle ---------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.state in ("planning", "moving", "blocked")

    def init(self) -> None:
        self.grid.load()
        self.builder.start_flusher()
        self.sensor_log.init()
        self.errors.init()
        self._loop_thread = threading.Thread(target=self._loop, daemon=True)
        self._loop_thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self.builder.stop()
        self.sensor_log.shutdown()

    def instrument(self, controller) -> None:
        """Wrap send_command: every motion command lands in the action log
        with the sensor snapshot of that instant (composes with the other
        wrappers, each wraps the previous)."""
        original = controller.send_command

        def logged(command: str) -> bool:
            kind, _ = classify(command)
            snapshot = self._snapshot() if kind != "other" else None
            ok = original(command)
            if kind == "other":
                return ok
            try:
                self.action_log.record(command, snapshot,
                                       source=self.arbiter.current_behavior() or "direct")
                if ok and kind in ("advance", "turn"):
                    self._last_motion_cmd = command
                    self._last_motion_at = self._clock()
            except Exception:
                logger.exception("Action log failed on %r", command)
            return ok

        controller.send_command = logged

    def _snapshot(self) -> dict:
        pose = self.senses.pose()
        last = self._last_reading or {}
        return {**pose, "rangeCm": last.get("rangeCm"), "battery": self._safe_battery()}

    def _safe_battery(self):
        try:
            return self._battery()
        except Exception:
            return None

    # ---- layer 1: the sensor and avoidance loop ----------------------------

    def _loop(self) -> None:
        while not self._stop.wait(1.0 / max(0.5, float(self.config["sensorHz"]))):
            try:
                self._tick()
            except Exception:
                logger.exception("Navigation sensor tick failed")

    def _moving(self) -> bool:
        last = getattr(self.controller, "last_motion_at", None)
        return last is not None and \
            self._clock() - last < float(self.config["movingWindowS"])

    def _tick(self) -> None:
        if not (self._moving() or self.active or self.config["alwaysSample"]):
            return
        self.stats["ticks"] += 1
        reading = self.sample()
        self._check_avoidance(reading)

    def sample(self) -> dict:
        """One reading from the ranger plus everything else she knows now;
        recorded in the sensor log."""
        raw = None
        if self.ranger is not None and self.ranger.enabled:
            try:
                raw = self.ranger.read()
            except Exception as exc:
                logger.warning("Ranger read failed: %s", exc)
        pose = self.senses.pose()
        reading = {"rangeCm": raw.get("distanceCm") if raw else None,
                   "rangeOk": bool(raw and raw.get("ok")),
                   "cached": bool(raw and raw.get("cached")),
                   "gated": bool(raw and raw.get("gated")),
                   "x": pose["x"], "y": pose["y"], "heading": pose["heading"],
                   "driftM": pose["driftM"], "yaw": pose.get("yaw"),
                   "battery": self._safe_battery(),
                   "command": getattr(self.controller, "last_command", None),
                   "behavior": self.arbiter.current_behavior(), "panDeg": self._pan}
        recorded = self.sensor_log.record(reading)
        previous = self._last_reading
        self._last_reading = recorded
        if raw and not raw.get("cached"):
            self._miss_streak = 0 if raw.get("ok") else self._miss_streak + 1
            self._check_anomaly(previous, recorded)
        return recorded

    def _check_anomaly(self, previous: dict | None, reading: dict) -> None:
        jump = float(self.config["jumpCm"])
        if previous and previous.get("rangeCm") is not None \
                and reading.get("rangeCm") is not None \
                and not self._moving() \
                and abs(reading["rangeCm"] - previous["rangeCm"]) > jump:
            self._handle(RecoverableError(
                "sensor_anomaly",
                f"range jumped {previous['rangeCm']} -> {reading['rangeCm']} cm while still",
                {"previous": previous["rangeCm"], "now": reading["rangeCm"]}))
        elif self._miss_streak == int(self.config["missStreak"]) and self._moving():
            self._handle(RecoverableError(
                "sensor_anomaly", f"{self._miss_streak} echoes missed in a row while moving",
                {"missStreak": self._miss_streak}))

    def _forward_motion_recent(self) -> bool:
        cmd, at = self._last_motion_cmd, self._last_motion_at
        if not cmd or at is None or self._clock() - at > float(self.config["movingWindowS"]):
            return False
        kind, gait = classify(cmd)
        return kind == "turn" or (kind == "advance" and not (gait or "").startswith("bk"))

    def _check_avoidance(self, reading: dict) -> None:
        if not self.config["avoidanceEnabled"] or self.ranger is None or not self.ranger.enabled:
            return
        if reading.get("cached") or reading.get("rangeCm") is None:
            return
        if reading["rangeCm"] > float(self.config["stopCm"]):
            return
        if self.arbiter.avoidance_suppressed():
            self.stats["suppressed"] += 1
            return
        if not self._forward_motion_recent():
            return
        result = self.arbiter.submit(
            STOP_BEHAVIOR, source="safety", priority=PRIORITY_SAFETY,
            cause={"type": "nav.avoidance", "rangeCm": reading["rangeCm"]})
        if result.get("status") == "rejected":
            return
        self.stats["stops"] += 1
        pose = {"x": reading["x"], "y": reading["y"], "heading": reading["heading"]}
        self.builder.integrate(reading["rangeCm"], pose, self._pan)
        self.last_block = {"at": self._clock(), "rangeCm": reading["rangeCm"],
                           "x": reading["x"], "y": reading["y"],
                           "heading": reading["heading"]}
        with self._lock:
            if self.active:
                self.state = "blocked"
                self.blocked_count += 1
        self.trigger("nav.blocked", {"obstacleCm": reading["rangeCm"],
                                     "x": reading["x"], "y": reading["y"]})

    # ---- layers 2 and 3: targets and routes --------------------------------

    def set_target(self, x: float, y: float, source: str = "manual") -> dict:
        if self.error_state.blocked:
            raise NavigationRefused("an error is waiting for a human answer")
        if self._is_away():
            raise NavigationRefused("away mode: the home map is not in use")
        with self._lock:
            if self.active:
                self._cancel_run()
            self.target = {"x": float(x), "y": float(y), "source": source,
                           "setAt": self._clock()}
            self.route = None
            self.finished = None
            self.state = "planning"
            self.blocked_count = 0
            self.replans = 0
        self.stats["routes"] += 1
        priority = PRIORITY_AGENT if source == "agent" else PRIORITY_MANUAL
        return self._submit_route(source, priority)

    def _submit_route(self, source: str, priority: int) -> dict:
        result = self.arbiter.submit_generator(
            NAV_BEHAVIOR, self._route_steps, source=source, priority=priority,
            cause={"type": "nav.target", "target": dict(self.target or {})},
            on_end=self._on_route_end)
        if result.get("status") == "rejected":
            with self._lock:
                self.state = "idle"
                self.finished = {"state": "rejected", "detail": result.get("reason"),
                                 "at": self._clock()}
        return {**result, "target": dict(self.target or {}), "state": self.state}

    def cancel(self) -> dict:
        with self._lock:
            was = self.state
            self.target = None
            self.route = None
            if self.active:
                self.state = "cancelled"
                self.finished = {"state": "cancelled", "at": self._clock()}
            stopped = self._cancel_run()
        return {"was": was, "state": self.state, "stopped": stopped}

    def _cancel_run(self) -> bool:
        if self.arbiter.current_behavior() == NAV_BEHAVIOR:
            return bool(self.arbiter.stop_current().get("stopped"))
        return False

    def _route_steps(self):
        target = self.target
        if target is None:
            return
        with self._lock:
            self.state = "moving"
        if self.config["sweepAtStart"] and self.config["rangerOnHead"] \
                and self.ranger is not None and self.ranger.enabled:
            yield from self._sweep_steps()
        replans = 0
        while self.target is target:
            pose = self.senses.pose()
            plan = self.planner.plan((pose["x"], pose["y"]), (target["x"], target["y"]))
            if not plan["ok"]:
                self._finish("unreachable", plan["reason"])
                self.trigger("nav.unreachable", {"reason": plan["reason"]})
                yield {"status": "failed", "detail": plan["reason"], "settleS": 0}
                return
            with self._lock:
                self.route = {"waypoints": plan["waypoints"], "plannedAt": self._clock(),
                              "legIndex": 0, "explored": plan.get("explored")}
                self.replans = replans
            replans += 1
            blocked = False
            for index, waypoint in enumerate(plan["waypoints"]):
                with self._lock:
                    if self.route is not None:
                        self.route["legIndex"] = index
                outcome = yield from self._leg_steps(waypoint)
                if outcome == "blocked":
                    blocked = True
                    break
                if outcome == "failed":
                    self._finish("failed", "a step failed and could not be recovered")
                    yield {"status": "failed", "detail": "unrecovered step", "settleS": 0}
                    return
            if not blocked:
                yield {"command": "kup", "settleS": 1.0}
                pose = self.senses.pose()
                self._finish("arrived", f"at ({pose['x']}, {pose['y']})")
                self.stats["arrivals"] += 1
                self.trigger("nav.arrived", {"x": pose["x"], "y": pose["y"]})
                return
            if replans > int(self.config["maxReplans"]):
                self._finish("unreachable", "re-planned too many times")
                self.trigger("nav.unreachable", {"reason": "re-planned too many times"})
                yield {"status": "failed", "detail": "too many replans", "settleS": 0}
                return

    def _leg_steps(self, waypoint):
        while True:
            pose = self.senses.pose()
            leg = self.planner.leg(pose, waypoint)
            if leg["arrived"]:
                return "arrived"
            if leg["turnDeg"]:
                outcome = yield from self._turn_steps(leg["turnDeg"])
                if outcome == "failed":
                    return "failed"
                if outcome == "interrupted":
                    return "blocked" if self.state == "blocked" else "failed"
                self._after_motion()
                continue
            ahead = self._look_ahead()
            if ahead is not None and ahead <= float(self.config["stopCm"]):
                self._block_here(ahead)
                return "blocked"
            cycles = min(int(leg["cycles"]), int(self.config["maxCyclesPerBurst"]))
            if ahead is not None:
                room = ahead / 100.0 - float(self.config["stopCm"]) / 100.0 \
                    - float(self.config["lookAheadMarginM"])
                cycles = min(cycles, max(1, self.planner.cycles_for(max(0.0, room))))
            if cycles <= 0:
                return "arrived"
            step = {"command": f"kwkF {cycles}",
                    "settleS": float(self.config["walkSPerCycle"]) * cycles
                    + float(self.config["walkExtraS"])}
            yield step
            if step.get("failed"):
                if self._handle(RecoverableError(
                        "action_failed", f"{step['command']} was not accepted",
                        {"command": step["command"]}))["action"] != "retry":
                    return "failed"
                continue
            self.errors.clear("action_failed")
            self._after_motion()
            if self.state == "blocked":
                return "blocked"

    def _turn_steps(self, turn_deg: float):
        """Turn toward the leg. Returns "ok", "failed" or "interrupted".

        vt mode: start the continuous turn-in-place gait, accumulate the
        IMU yaw until the target (minus a stop lead for momentum) is swept,
        then kup. The stop is in a finally block: no exit path, including
        an arbiter preemption arriving between yields, leaves her spinning.
        Firmware mode is the one-command kwkL/R deg turn."""
        if self.config["turnMode"] != "vt":
            step = {"command": self.planner.turn_command(turn_deg),
                    "settleS": self._turn_settle(turn_deg)}
            yield step
            if step.get("failed"):
                if self._handle(RecoverableError(
                        "action_failed", f"{step['command']} was not accepted",
                        {"command": step["command"]}))["action"] != "retry":
                    return "failed"
                return "ok"
            self.errors.clear("action_failed")
            return "ok"
        start = self.senses.read_yaw()
        if start is None:
            if self._handle(RecoverableError(
                    "sensor_anomaly", "IMU yaw unreadable before a turn",
                    {"turnDeg": turn_deg}))["action"] != "retry":
                return "failed"
            return "ok"
        direction = "L" if turn_deg > 0 else "R"
        step = {"command": f"kvt{direction}", "settleS": 0.2}
        yield step
        if step.get("failed"):
            self.controller.send_command("kup")
            if self._handle(RecoverableError(
                    "action_failed", f"{step['command']} was not accepted",
                    {"command": step["command"]}))["action"] != "retry":
                return "failed"
            return "ok"
        self.errors.clear("action_failed")
        total, last = 0.0, start
        lead = float(self.config["vtStopLeadDeg"])
        deadline = self._clock() + min(45.0, abs(turn_deg) / 6.0 + 12.0)
        interrupted = False
        try:
            while self._clock() < deadline:
                if self.arbiter.interrupt_requested():
                    interrupted = True
                    break
                yaw = self.senses.read_yaw()
                if yaw is not None:
                    total += (yaw - last + 180.0) % 360.0 - 180.0
                    last = yaw
                    if abs(total) >= abs(turn_deg) - lead:
                        break
                self._sleep(float(self.config["vtPollS"]))
        finally:
            self.controller.send_command("kup")
        self.senses.fuse_yaw()      # the shadow did not model the spin
        yield {"settleS": float(self.config["vtSettleS"])}
        return "interrupted" if interrupted else "ok"

    def _turn_settle(self, turn_deg: float) -> float:
        return abs(turn_deg) * float(self.config["turnSPerDeg"]) + float(self.config["turnExtraS"])

    def _block_here(self, range_cm: float) -> None:
        pose = self.senses.pose()
        self.last_block = {"at": self._clock(), "rangeCm": range_cm, "x": pose["x"],
                           "y": pose["y"], "heading": pose["heading"]}
        with self._lock:
            self.blocked_count += 1
        self.trigger("nav.blocked", {"obstacleCm": range_cm, "x": pose["x"], "y": pose["y"]})

    def _look_ahead(self) -> float | None:
        reading = self.sample()
        if reading.get("rangeCm") is None:
            return None
        pose = {"x": reading["x"], "y": reading["y"], "heading": reading["heading"]}
        self._integrate(reading["rangeCm"], pose)
        return reading["rangeCm"]

    def _after_motion(self) -> None:
        fused = self.senses.fuse_yaw()
        if fused is not None:
            if abs(fused["correctionDeg"]) > float(self.config["yawDisagreeDeg"]):
                self._handle(RecoverableError(
                    "localization_drift",
                    f"IMU heading differs from dead reckoning by {fused['correctionDeg']} deg",
                    fused))
            else:
                self.errors.clear("localization_drift")
        pose = self.senses.pose()
        if pose["driftM"] > float(self.config["maxDriftM"]):
            self._handle(UnrecoverableError(
                "lost", f"dead-reckoning uncertainty reached {pose['driftM']} m",
                {"pose": pose}))
            return
        self._look_ahead()

    def _integrate(self, range_cm: float, pose: dict) -> dict:
        result = self.builder.integrate(range_cm, pose, self._pan)
        if result["contradictions"]:
            self._handle(RecoverableError(
                "map_contradiction",
                f"{len(result['contradictions'])} cell(s) disagree with the map",
                {"cells": result["contradictions"], "rangeCm": range_cm, "pose": pose}))
        else:
            self.errors.clear("map_contradiction")
        return result

    def _handle(self, error: NavError) -> dict:
        result = self.errors.handle(error)
        if result["action"] == "retry":
            self.stats["recoverable"] += 1
        else:
            self.stats["escalated"] += 1
        return result

    def _on_escalate(self, error: UnrecoverableError, error_id) -> None:
        with self._lock:
            if self.active:
                self.state = "error"
                self.finished = {"state": "error", "detail": error.message,
                                 "errorId": error_id, "at": self._clock()}
        self.error_state.enter(error, error_id)

    def _finish(self, state: str, detail: str | None = None) -> None:
        with self._lock:
            self.state = state
            self.finished = {"state": state, "detail": detail, "at": self._clock()}
            if state in ("arrived", "unreachable", "failed"):
                self.target = None

    def _on_route_end(self, status: str, detail: str) -> None:
        with self._lock:
            if self.error_state.blocked or self.state == "error":
                return
            if status == "interrupted" and self.state == "blocked" and self.target is not None:
                if self.blocked_count > int(self.config["maxBlocked"]):
                    self._finish("unreachable", "blocked too many times")
                    self.trigger("nav.unreachable", {"reason": "blocked too many times"})
                    return
                threading.Thread(target=self._resume_after_stop, daemon=True).start()
                return
            if status == "interrupted" and self.active:
                self.state = "cancelled"
                self.finished = {"state": "cancelled", "detail": detail, "at": self._clock()}
                self.target = None
            elif status == "failed" and self.active:
                self._finish("failed", detail)

    def _resume_after_stop(self) -> None:
        deadline = self._clock() + float(self.config["resumeWaitS"])
        while self._clock() < deadline:
            if self.arbiter.current_behavior() is None:
                break
            self._sleep(0.2)
        with self._lock:
            if self.state != "blocked" or self.target is None or self.error_state.blocked:
                return
            self.state = "planning"
            target = self.target
        self.stats["resumes"] += 1
        priority = PRIORITY_AGENT if target["source"] == "agent" else PRIORITY_MANUAL
        self._submit_route(target["source"], priority)

    # ---- sweeps --------------------------------------------------------------

    def sweep(self, source: str = "manual") -> dict:
        if not self.config["rangerOnHead"]:
            raise NavigationRefused("the ranger does not pan with the head (NAV_RANGER_ON_HEAD)")
        if self.ranger is None or not self.ranger.enabled:
            raise NavigationRefused("ULTRASONIC_PIN is not set")
        if self.error_state.blocked:
            raise NavigationRefused("an error is waiting for a human answer")
        return self.arbiter.submit_generator(
            SWEEP_BEHAVIOR, self._sweep_steps, source=source,
            priority=PRIORITY_AGENT if source == "agent" else PRIORITY_MANUAL,
            cause={"type": "nav.sweep"})

    def _sweep_steps(self):
        pose = self.senses.pose()
        readings = []
        try:
            for angle in list(self.config["sweepAngles"]):
                self._pan = float(angle)
                yield {"command": f"m 0 {int(angle)}", "settleS": float(self.config["sweepSettleS"])}
                reading = self.sample()
                readings.append((float(angle), reading.get("rangeCm")))
        finally:
            self._pan = 0.0
        yield {"command": "m 0 0", "settleS": float(self.config["sweepSettleS"])}
        result = self.builder.integrate_sweep(readings, pose)
        self.stats["sweeps"] += 1
        self.last_sweep = {"at": self._clock(), "pose": pose, **result,
                           "readings": [{"panDeg": a, "rangeCm": d} for a, d in readings]}
        if result["contradictions"]:
            self._handle(RecoverableError(
                "map_contradiction",
                f"sweep: {len(result['contradictions'])} cell(s) disagree with the map",
                {"cells": result["contradictions"], "pose": pose}))
        self.trigger("map.updated", {"version": self.grid.version})

    # ---- overrides -------------------------------------------------------------

    def override(self, behavior: str | None = None, command: str | None = None,
                 source: str = "manual", settle_s: float = 3.0) -> dict:
        cause = {"type": "nav.override", "behavior": behavior, "command": command}
        if behavior:
            return self.arbiter.submit(behavior, source=source, priority=PRIORITY_MANUAL,
                                       cause=cause, suppress_avoidance=True)
        if command:
            if not command.startswith("k"):
                raise ValueError("override commands are skills ('k...')")
            steps = [{"command": command, "settleS": float(settle_s)}]
            return self.arbiter.submit_generator(
                OVERRIDE_BEHAVIOR, lambda: iter(steps), source=source,
                priority=PRIORITY_MANUAL, cause=cause, suppress_avoidance=True)
        raise ValueError("'behavior' or 'command' required")

    # ---- human answers -----------------------------------------------------------

    def _apply_resolution(self, choice: str, error: dict) -> dict:
        cells = (error.get("context") or {}).get("cells") or []
        applied = {"choice": choice, "cells": 0, "resumed": False}
        if choice in ("trust_sensor", "trust_map") and cells:
            applied["cells"] = self.builder.apply_correction(
                cells, "sensor" if choice == "trust_sensor" else "map")
        with self._lock:
            target = self.target
            if choice == "manual":
                self.target = None
                self.route = None
                self.state = "idle"
                self.finished = {"state": "cancelled", "detail": "moved by hand",
                                 "at": self._clock()}
                target = None
            elif target is not None:
                self.state = "planning"
        if target is not None:
            priority = PRIORITY_AGENT if target["source"] == "agent" else PRIORITY_MANUAL
            self._submit_route(target["source"], priority)
            applied["resumed"] = True
        elif self.state == "error":
            with self._lock:
                self.state = "idle"
        return applied

    # ---- reporting ---------------------------------------------------------------

    def configure(self, updates: dict) -> dict:
        numeric = ("stopCm", "sensorHz", "movingWindowS", "walkSPerCycle", "walkExtraS",
                   "turnSPerDeg", "turnExtraS", "maxCyclesPerBurst", "maxReplans",
                   "maxBlocked", "sweepSettleS", "yawDisagreeDeg", "maxDriftM",
                   "jumpCm", "missStreak", "lookAheadMarginM")
        for key in numeric:
            if key in updates and isinstance(updates[key], (int, float)) and updates[key] >= 0:
                self.config[key] = type(DEFAULTS[key])(updates[key])
        for key in ("avoidanceEnabled", "alwaysSample", "rangerOnHead", "sweepAtStart"):
            if key in updates:
                self.config[key] = bool(updates[key])
        if isinstance(updates.get("sweepAngles"), list):
            angles = [float(a) for a in updates["sweepAngles"]
                      if isinstance(a, (int, float)) and -90 <= a <= 90]
            if angles:
                self.config["sweepAngles"] = angles
        return self.status()

    def status(self) -> dict:
        with self._lock:
            target = dict(self.target) if self.target else None
            route = dict(self.route) if self.route else None
            finished = dict(self.finished) if self.finished else None
        pose = self.senses.pose()
        remaining = None
        if target is not None:
            remaining = round(math.hypot(target["x"] - pose["x"], target["y"] - pose["y"]), 2)
        return {"state": self.state, "active": self.active, "target": target,
                "route": route, "remainingM": remaining, "finished": finished,
                "pose": pose, "blockedCount": self.blocked_count, "replans": self.replans,
                "lastBlock": self.last_block, "lastSweep": self.last_sweep,
                "avoidance": {"enabled": bool(self.config["avoidanceEnabled"]),
                              "stopCm": self.config["stopCm"],
                              "suppressed": self.arbiter.avoidance_suppressed(),
                              "rangerEnabled": bool(self.ranger is not None and self.ranger.enabled),
                              "moving": self._moving(),
                              "stops": self.stats["stops"]},
                "sensors": {"latest": self._last_reading, **self.sensor_log.status()},
                "map": self.builder.status(),
                "errors": {**self.error_state.status(), "handler": self.errors.status()},
                "config": dict(self.config), "stats": dict(self.stats),
                "away": bool(self._is_away())}

    def map_json(self) -> dict:
        pose = self.senses.pose()
        with self._lock:
            target = dict(self.target) if self.target else None
            route = dict(self.route) if self.route else None
        return {**self.grid.to_json(), "pose": pose, "target": target,
                "route": route, "state": self.state, "lastBlock": self.last_block}
