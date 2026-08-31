"""Autonomous gait learning from the robot's own IMU.

Learns what the gyro can actually measure (validated live, see
orchestrator docs/reports/CALIBRATION_2026-08-31.md):

- TURN model: per-(direction, angle) gain = actual/commanded rotation,
  measured via 'gp' yaw before/after each closed-loop turn.
- HEADING DRIFT during straight walks: deg/cycle, from yaw delta across
  bounded walks. Walk DISTANCE is deliberately NOT measured — body-frame
  accel + gait vibration + the ~5 Hz gp cap make double-integration
  unworkable on this platform; stride stays externally calibrated.

Self-recentering (optional): the learner dead-reckons its pose (turns are
arcs — radius by angle — walks are strides along the mean heading) and
after each trial turns toward home with feedback-corrected turns, walks
back, and restores heading. Pose error accumulates and the robot cannot
sense the arena edge, so every `verify_every` trials the session still
parks in 'awaiting_recenter' for a human drift check, and it parks
immediately if the pose estimate strays too far from home.

Driver rules encoded from the calibration session:
- interleave 'kup' between bounded gaits (dropped silently otherwise);
  kup may report failure when already standing — treated as no-op
- kwk* completion echoes are immediate; turns are awaited by polling yaw
  until it settles (g* commands are gait-safe mid-motion)
- yaw: left = +, right = −, raw domain exceeds ±180 → deltas normalized
- turn commands ≤ ~30° are unreliable — feedback turns clamp low
- every trial is voltage-stamped; the session pauses below the floor
"""
import logging
import math
import re
import threading
import time

logger = logging.getLogger(__name__)

_FLOAT_RE = re.compile(r"-?\d+\.?\d*")
_VOLTAGE_RE = re.compile(r"Voltage:\s*([0-9]+(?:\.[0-9]+)?)")

# Below this pack voltage precision trials are meaningless (torque sag).
LOW_VOLTAGE_FLOOR = 6.9

DEFAULT_SEQUENCE = [
    "kwkL 45", "kwkR 45",
    "kwkL 90", "kwkR 90",
    "kwkL 30", "kwkR 30",
    "kwkF 3", "kwkF 6",
]

# Calibrated stride model (gym mat) — prediction only, not learned here.
STRIDE_FIRST_CYCLE = 0.100
STRIDE_PER_CYCLE = 0.112

# Feedback-turn tuning: small commanded angles are unreliable, so accept a
# heading tolerance rather than chasing precision with sloppy tiny turns.
TURN_TOLERANCE_DEG = 12.0
TURN_CMD_MIN = 20
TURN_CMD_MAX = 100
TURN_MAX_STEPS = 3

# If the pose estimate strays this far from home, stop trusting it.
POSE_DIVERGENCE_M = 0.7
HOME_CLOSE_ENOUGH_M = 0.08


def _norm(delta: float) -> float:
    while delta > 180:
        delta -= 360
    while delta < -180:
        delta += 360
    return delta


def _turn_radius_m(angle_deg: float, gait: str = "wk") -> float:
    """Arc radius by commanded angle: ~0.33m at 90°, ~0.5m at ≤30° for the
    walking turn; the vt (turn-in-place) gait shuffles nearly on the spot."""
    if gait == "vt":
        return 0.05
    a = max(30.0, min(90.0, abs(angle_deg)))
    return 0.5 - (a - 30.0) / 60.0 * 0.17


class GaitLearner:
    """One learning session at a time; thread-safe status/model reads."""

    def __init__(self, controller, settle_poll_s: float = 1.5,
                 settle_reads: int = 2, max_turn_wait_s: float = 35.0,
                 rearm_wait_s: float = 2.5, walk_s_per_cycle: float = 1.3,
                 post_turn_wait_s: float = 2.0, walk_extra_s: float = 3.0):
        self.controller = controller
        self.settle_poll_s = settle_poll_s
        self.settle_reads = settle_reads
        self.max_turn_wait_s = max_turn_wait_s
        self.rearm_wait_s = rearm_wait_s
        self.walk_s_per_cycle = walk_s_per_cycle
        self.post_turn_wait_s = post_turn_wait_s
        self.walk_extra_s = walk_extra_s
        # Host-closed-loop turn-in-place: poll fast (each gp ~0.2-0.4s) and
        # stop slightly early to absorb momentum + stop latency (~9.4°/s spin).
        self.vt_poll_s = 0.1
        self.vt_stop_lead_deg = 5.0

        self._lock = threading.Lock()
        self._continue = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._reset_state()

    def _reset_state(self) -> None:
        self.state = "idle"  # idle|running|awaiting_recenter|paused_low_battery|done|stopped|error
        self.trials: list[dict] = []
        self.pending: list[str] = []
        self.current_batch = 0
        self.recenter_mode = "manual"
        self.verify_every = 3
        self.arena_half_m = 0.5
        # Pose estimate: x/y meters from home, heading deg (0 = start facing,
        # left positive). Forward unit vector for heading h: (-sin h, cos h).
        self._x = self._y = self._heading = 0.0
        self.model = {
            "turn_gains": {},          # e.g. {"L45": 1.02, "R90": 0.97}
            "turn_gain_left": None,    # aggregate EMA per direction
            "turn_gain_right": None,
            "heading_drift_deg_per_cycle": None,
            "stride_first_cycle": STRIDE_FIRST_CYCLE,
            "stride_per_cycle": STRIDE_PER_CYCLE,
        }

    # ---- sensors ----------------------------------------------------------

    def _read_yaw(self, tries: int = 4) -> float | None:
        for _ in range(tries):
            lines = self.controller.query("gp")
            if lines:
                for line in "\n".join(lines).splitlines():
                    if "ICM" in line or "MCU" in line:
                        floats = _FLOAT_RE.findall(line)
                        if len(floats) >= 6:
                            return float(floats[3])
            time.sleep(0.3)
        return None

    def _read_voltage(self) -> float | None:
        lines = self.controller.query("P")
        if lines:
            match = _VOLTAGE_RE.search("\n".join(lines))
            if match:
                return float(match.group(1))
        return None

    def _rearm(self) -> None:
        # kup is a no-op (and may 'fail') when already standing — ignore result.
        self.controller.send_command("kup")
        time.sleep(self.rearm_wait_s)

    def _wait_for_settle(self, deadline_s: float) -> bool:
        """Poll yaw until it stops changing; True if settled before deadline."""
        last = None
        stable = 0
        start = time.time()
        while time.time() - start < deadline_s:
            yaw = self._read_yaw(tries=2)
            if yaw is not None and last is not None and \
                    abs(_norm(yaw - last)) < 2.0:
                stable += 1
                if stable >= self.settle_reads:
                    return True
            else:
                stable = 0
            last = yaw
            time.sleep(self.settle_poll_s)
        return False

    # ---- pose dead reckoning ----------------------------------------------

    def _advance_pose_arc(self, delta_deg: float, radius_m: float) -> None:
        if abs(delta_deg) < 0.5:
            return
        chord = 2 * radius_m * math.sin(math.radians(abs(delta_deg)) / 2)
        bearing = math.radians(self._heading + delta_deg / 2)
        self._x += -chord * math.sin(bearing)
        self._y += chord * math.cos(bearing)
        self._heading = _norm(self._heading + delta_deg)

    def _advance_pose_walk(self, distance_m: float, drift_deg: float) -> None:
        bearing = math.radians(self._heading + drift_deg / 2)
        self._x += -distance_m * math.sin(bearing)
        self._y += distance_m * math.cos(bearing)
        self._heading = _norm(self._heading + drift_deg)

    def _home_distance(self) -> float:
        return math.hypot(self._x, self._y)

    # ---- measured motion primitives (update pose; return measurement) -----

    def _measured_turn(self, direction: str, angle: int,
                       gait: str = "wk") -> float | None:
        self._rearm()
        before = self._read_yaw()
        if not self.controller.send_command(f"k{gait}{direction} {angle}"):
            return None
        time.sleep(self.post_turn_wait_s)
        self._wait_for_settle(self.max_turn_wait_s)
        after = self._read_yaw()
        if before is None or after is None:
            return None
        actual = _norm(after - before)
        self._advance_pose_arc(actual, _turn_radius_m(angle, gait))
        return actual

    def _measured_walk(self, cycles: int) -> float | None:
        self._rearm()
        before = self._read_yaw()
        if not self.controller.send_command(f"kwkF {cycles}"):
            return None
        time.sleep(self.walk_s_per_cycle * cycles + self.walk_extra_s)
        self._wait_for_settle(10.0)
        after = self._read_yaw()
        distance = STRIDE_FIRST_CYCLE + STRIDE_PER_CYCLE * (cycles - 1)
        drift = _norm(after - before) if before is not None and \
            after is not None else 0.0
        self._advance_pose_walk(distance, drift)
        return drift if before is not None and after is not None else None

    def _vt_turn(self, direction: str, target_deg: float) -> float | None:
        """Host-closed-loop turn-in-place: start the continuous kvt gait,
        integrate yaw while it spins (~9.4°/s live), stop with kup when the
        target is crossed. Validated live 2026-08-31: kvt takes NO angle
        argument on B10_251121 — it spins until interrupted. The stop is in
        a finally block: no code path may leave the robot spinning."""
        self._rearm()
        last = self._read_yaw()
        if last is None:
            return None
        if not self.controller.send_command(f"kvt{direction}"):
            return None
        total = 0.0
        deadline = time.time() + min(45.0, abs(target_deg) / 6.0 + 12.0)
        try:
            while time.time() < deadline:
                yaw = self._read_yaw(tries=1)
                if yaw is not None:
                    total += _norm(yaw - last)
                    last = yaw
                    if abs(total) >= abs(target_deg) - self.vt_stop_lead_deg:
                        break
                time.sleep(self.vt_poll_s)
        finally:
            self.controller.send_command("kup")
        time.sleep(self.rearm_wait_s)
        final = self._read_yaw()
        if final is not None:
            total += _norm(final - last)
        self._advance_pose_arc(total, _turn_radius_m(target_deg, "vt"))
        return total

    def _turn_by(self, target_delta_deg: float, gait: str = "vt") -> None:
        """Feedback-corrected turn to a relative heading — the mapping
        primitive. Recentering uses host-closed-loop turn-in-place so the
        correction itself barely displaces the robot."""
        remaining = _norm(target_delta_deg)
        for _ in range(TURN_MAX_STEPS):
            if abs(remaining) <= TURN_TOLERANCE_DEG:
                return
            direction = "L" if remaining > 0 else "R"
            if gait == "vt":
                actual = self._vt_turn(direction, remaining)
            else:
                command = int(min(TURN_CMD_MAX,
                                  max(TURN_CMD_MIN, abs(remaining))))
                actual = self._measured_turn(direction, command, gait=gait)
            if actual is None:
                return
            remaining = _norm(remaining - actual)

    def _goto(self, tx: float, ty: float,
              final_heading: float | None = None) -> None:
        """Dead-reckon to a target point, optionally facing final_heading.

        Iterative: corrections themselves move the robot, so each round
        re-aims from the updated pose. Aiming uses turn-in-place, so this
        converges to within roughly a stride of the target.
        """
        for _ in range(3):
            dx, dy = tx - self._x, ty - self._y
            distance = math.hypot(dx, dy)
            if distance < HOME_CLOSE_ENOUGH_M:
                break
            # Bearing of the target vector in our convention.
            bearing = math.degrees(math.atan2(-dx, dy))
            self._turn_by(_norm(bearing - self._heading))
            dx, dy = tx - self._x, ty - self._y
            distance = math.hypot(dx, dy)
            if distance < HOME_CLOSE_ENOUGH_M:
                break
            cycles = max(1, min(6, round((distance - STRIDE_FIRST_CYCLE)
                                         / STRIDE_PER_CYCLE) + 1))
            if self._measured_walk(cycles) is None:
                break
        if final_heading is not None:
            self._turn_by(_norm(final_heading - self._heading))

    def _auto_recenter(self) -> None:
        self._goto(0.0, 0.0, final_heading=0.0)

    _DIAGONALS = (45.0, 135.0, -45.0, -135.0)

    def _prepare_trial(self, command: str) -> bool:
        """Stage the trial so its predicted footprint stays on the arena.

        Turns launch from home with the arc's chord aimed at a diagonal
        (maximum room from center); walks are staged half the walk length
        behind home along a diagonal so they pass through the middle.
        Returns False (trial unsafe) if the footprint cannot fit at all.
        """
        parts = command.split()
        kind = parts[0]
        arg = int(parts[1]) if len(parts) > 1 else 1
        # Component-wise safe reach from center; 1.3/1.2 factors absorb the
        # known overshoot and stride variance conservatively.
        half = self.arena_half_m - 0.08
        if kind in ("kwkL", "kwkR"):
            delta = arg if kind == "kwkL" else -arg
            # 1.3 on the swept angle absorbs the known momentum overshoot;
            # empirical 90° chords are ~0.57m and must pass the 0.5m arena.
            swept = min(abs(delta) * 1.3, 179.0)
            chord = 2 * _turn_radius_m(arg) * math.sin(math.radians(swept) / 2)
            if chord > half * 1.41:
                return False
            # Chord bearing ≈ heading + delta/2; pick the diagonal needing
            # the least pre-rotation from the current heading.
            diag = min(self._DIAGONALS,
                       key=lambda c: abs(_norm(c - delta / 2 - self._heading)))
            self._goto(0.0, 0.0, final_heading=_norm(diag - delta / 2))
        elif kind == "kwkF":
            distance = (STRIDE_FIRST_CYCLE
                        + STRIDE_PER_CYCLE * (arg - 1)) * 1.2
            if distance > 2 * half * 1.41:
                return False
            diag = min(self._DIAGONALS,
                       key=lambda c: abs(_norm(c - self._heading)))
            rad = math.radians(diag)
            self._goto((distance / 2) * math.sin(rad),
                       -(distance / 2) * math.cos(rad), final_heading=diag)
        return True

    # ---- model updates ----------------------------------------------------

    @staticmethod
    def _ema(old: float | None, new: float, alpha: float = 0.3) -> float:
        return new if old is None else (1 - alpha) * old + alpha * new

    def _update_turn_model(self, direction: str, angle: int,
                           actual: float) -> None:
        signed_expected = angle if direction == "L" else -angle
        gain = actual / signed_expected if signed_expected else 0.0
        key = f"{direction}{angle}"
        with self._lock:
            self.model["turn_gains"][key] = round(
                self._ema(self.model["turn_gains"].get(key), gain), 4)
            agg = "turn_gain_left" if direction == "L" else "turn_gain_right"
            self.model[agg] = round(self._ema(self.model[agg], gain), 4)

    def _update_drift_model(self, cycles: int, yaw_delta: float) -> None:
        drift = yaw_delta / cycles
        with self._lock:
            self.model["heading_drift_deg_per_cycle"] = round(
                self._ema(self.model["heading_drift_deg_per_cycle"], drift), 2)

    # ---- trial execution --------------------------------------------------

    def _run_trial(self, command: str) -> dict:
        trial = {"command": command, "at": time.time(),
                 "voltage": self._read_voltage()}
        parts = command.split()
        kind = parts[0]
        arg = int(parts[1]) if len(parts) > 1 else 1

        if kind in ("kwkL", "kwkR"):
            direction = "L" if kind == "kwkL" else "R"
            actual = self._measured_turn(direction, arg)
            if actual is None:
                trial["error"] = "turn failed or yaw unreadable"
                return trial
            expected = arg if direction == "L" else -arg
            trial.update({"predicted_deg": expected,
                          "actual_deg": round(actual, 1),
                          "error_deg": round(abs(actual - expected), 1)})
            self._update_turn_model(direction, arg, actual)
        elif kind == "kwkF":
            drift = self._measured_walk(arg)
            predicted = STRIDE_FIRST_CYCLE + STRIDE_PER_CYCLE * (arg - 1)
            trial["predicted_distance_m"] = round(predicted, 3)
            trial["distance_note"] = "not measurable proprioceptively"
            if drift is not None:
                trial["heading_drift_deg"] = round(drift, 1)
                self._update_drift_model(arg, drift)
        return trial

    # ---- session ----------------------------------------------------------

    def start(self, sequence: list[str] | None = None, iterations: int = 1,
              batch_size: int = 2, recenter: str = "manual",
              verify_every: int = 3, arena_half_m: float = 0.5) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._reset_state()
            self.pending = (sequence or DEFAULT_SEQUENCE) * iterations
            self.batch_size = max(1, batch_size)
            self.recenter_mode = recenter if recenter in ("auto", "manual") \
                else "manual"
            self.verify_every = max(1, verify_every)
            self.arena_half_m = max(0.3, float(arena_half_m))
            self.state = "running"
        self._stop.clear()
        self._continue.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def confirm_recenter(self) -> None:
        """Operator confirms the robot is at home — trust resets with it."""
        self._x = self._y = self._heading = 0.0
        self._continue.set()

    def stop(self) -> None:
        self._stop.set()
        self._continue.set()

    def _pause_for_human(self) -> None:
        with self._lock:
            self.state = "awaiting_recenter"
        self._continue.wait()
        self._continue.clear()
        with self._lock:
            if not self._stop.is_set():
                self.state = "running"

    def _run(self) -> None:
        try:
            done_since_verify = 0
            for index, command in enumerate(self.pending):
                if self._stop.is_set():
                    break
                with self._lock:
                    self.current_batch = index // self.batch_size + 1
                voltage = self._read_voltage()
                if voltage is not None and voltage < LOW_VOLTAGE_FLOOR:
                    with self._lock:
                        self.state = "paused_low_battery"
                    logger.warning("Gait learning paused: %.2fV < %.2fV floor",
                                   voltage, LOW_VOLTAGE_FLOOR)
                    return
                if self.recenter_mode == "auto" and \
                        not self._prepare_trial(command):
                    trial = {"command": command, "at": time.time(),
                             "skipped": "footprint exceeds arena bounds"}
                    with self._lock:
                        self.trials.append(trial)
                    logger.warning("Gait trial skipped as unsafe: %s", command)
                    continue
                trial = self._run_trial(command)
                with self._lock:
                    self.trials.append(trial)
                logger.info("Gait trial: %s", trial)
                done_since_verify += 1

                last = index == len(self.pending) - 1
                if self.recenter_mode == "auto":
                    if last:
                        self._auto_recenter()
                    diverged = self._home_distance() > POSE_DIVERGENCE_M
                    if not last and (diverged or
                                     done_since_verify >= self.verify_every):
                        if diverged:
                            logger.warning("Pose estimate diverged (%.2fm); "
                                           "requesting human recenter",
                                           self._home_distance())
                        else:
                            self._auto_recenter()
                        self._pause_for_human()
                        done_since_verify = 0
                elif not last and (index + 1) % self.batch_size == 0:
                    self._pause_for_human()
            with self._lock:
                self.state = "stopped" if self._stop.is_set() else "done"
        except Exception:
            logger.exception("Gait learning session crashed")
            with self._lock:
                self.state = "error"

    # ---- introspection ----------------------------------------------------

    def get_status(self) -> dict:
        with self._lock:
            turn_trials = [t for t in self.trials if "error_deg" in t]
            return {
                "state": self.state,
                "batch": self.current_batch,
                "recenterMode": self.recenter_mode,
                "trialsDone": len(self.trials),
                "trialsPending": max(0, len(self.pending) - len(self.trials)),
                "avgTurnErrorDeg": round(
                    sum(t["error_deg"] for t in turn_trials)
                    / len(turn_trials), 1) if turn_trials else None,
                "poseEstimate": {"x": round(self._x, 3),
                                 "y": round(self._y, 3),
                                 "headingDeg": round(self._heading, 1)},
                "model": dict(self.model),
            }

    def get_model(self) -> dict:
        with self._lock:
            return {"model": dict(self.model), "trials": list(self.trials)}
