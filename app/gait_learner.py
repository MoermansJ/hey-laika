"""Autonomous gait learning from the robot's own IMU.

Learns two things the gyro can actually measure (validated live,
orchestrator docs/reports/CALIBRATION_2026-08-31.md):

- TURN model: per-(direction, angle) gain = actual/commanded rotation,
  measured via 'gp' yaw before/after each closed-loop turn.
- HEADING DRIFT during straight walks: deg/cycle, from yaw delta across
  bounded walks. Walk DISTANCE is deliberately NOT measured — body-frame
  accel + gait vibration + the ~5 Hz gp cap make double-integration
  unworkable on this platform; stride stays externally calibrated.

Driver rules encoded from the calibration session:
- interleave 'kup' between bounded gaits (dropped silently otherwise);
  kup may report failure when already standing — treated as no-op
- kwk* completion echoes are immediate; turns are awaited by polling yaw
  until it settles (g* commands are gait-safe mid-motion)
- yaw: left = +, right = −, raw domain exceeds ±180 → deltas normalized
- every trial is voltage-stamped; the session pauses below the floor
- trials run in small batches; between batches the session parks in
  'awaiting_recenter' until the operator confirms the robot is re-centered
"""
import logging
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


def _norm(delta: float) -> float:
    while delta > 180:
        delta -= 360
    while delta < -180:
        delta += 360
    return delta


class GaitLearner:
    """One learning session at a time; thread-safe status/model reads."""

    def __init__(self, controller, settle_poll_s: float = 1.5,
                 settle_reads: int = 2, max_turn_wait_s: float = 35.0,
                 rearm_wait_s: float = 2.5, walk_s_per_cycle: float = 1.3):
        self.controller = controller
        self.settle_poll_s = settle_poll_s
        self.settle_reads = settle_reads
        self.max_turn_wait_s = max_turn_wait_s
        self.rearm_wait_s = rearm_wait_s
        self.walk_s_per_cycle = walk_s_per_cycle

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

        self._rearm()
        yaw_before = self._read_yaw()
        accepted = self.controller.send_command(command)
        trial["accepted"] = accepted
        if not accepted:
            trial["error"] = "command rejected/dropped"
            return trial

        if kind in ("kwkL", "kwkR"):
            time.sleep(2.0)
            trial["settled"] = self._wait_for_settle(self.max_turn_wait_s)
            yaw_after = self._read_yaw()
            if yaw_before is not None and yaw_after is not None:
                actual = _norm(yaw_after - yaw_before)
                direction = "L" if kind == "kwkL" else "R"
                trial.update({
                    "predicted_deg": arg if direction == "L" else -arg,
                    "actual_deg": round(actual, 1),
                    "error_deg": round(
                        abs(actual - (arg if direction == "L" else -arg)), 1),
                })
                self._update_turn_model(direction, arg, actual)
        elif kind == "kwkF":
            time.sleep(self.walk_s_per_cycle * arg + 3.0)
            self._wait_for_settle(10.0)
            yaw_after = self._read_yaw()
            predicted = STRIDE_FIRST_CYCLE + STRIDE_PER_CYCLE * (arg - 1)
            trial["predicted_distance_m"] = round(predicted, 3)
            trial["distance_note"] = "not measurable proprioceptively"
            if yaw_before is not None and yaw_after is not None:
                drift = _norm(yaw_after - yaw_before)
                trial["heading_drift_deg"] = round(drift, 1)
                self._update_drift_model(arg, drift)
        return trial

    # ---- session ----------------------------------------------------------

    def start(self, sequence: list[str] | None = None, iterations: int = 1,
              batch_size: int = 2) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._reset_state()
            self.pending = (sequence or DEFAULT_SEQUENCE) * iterations
            self.batch_size = max(1, batch_size)
            self.state = "running"
        self._stop.clear()
        self._continue.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def confirm_recenter(self) -> None:
        self._continue.set()

    def stop(self) -> None:
        self._stop.set()
        self._continue.set()

    def _run(self) -> None:
        try:
            batches = [self.pending[i:i + self.batch_size]
                       for i in range(0, len(self.pending), self.batch_size)]
            for index, batch in enumerate(batches):
                if self._stop.is_set():
                    break
                with self._lock:
                    self.current_batch = index + 1
                voltage = self._read_voltage()
                if voltage is not None and voltage < LOW_VOLTAGE_FLOOR:
                    with self._lock:
                        self.state = "paused_low_battery"
                    logger.warning("Gait learning paused: %.2fV < %.2fV floor",
                                   voltage, LOW_VOLTAGE_FLOOR)
                    break
                for command in batch:
                    if self._stop.is_set():
                        break
                    trial = self._run_trial(command)
                    with self._lock:
                        self.trials.append(trial)
                    logger.info("Gait trial: %s", trial)
                if index < len(batches) - 1 and not self._stop.is_set():
                    with self._lock:
                        self.state = "awaiting_recenter"
                    self._continue.wait()
                    self._continue.clear()
                    with self._lock:
                        if not self._stop.is_set():
                            self.state = "running"
            with self._lock:
                if self.state not in ("paused_low_battery",):
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
                "trialsDone": len(self.trials),
                "trialsPending": max(0, len(self.pending) - len(self.trials)),
                "avgTurnErrorDeg": round(
                    sum(t["error_deg"] for t in turn_trials)
                    / len(turn_trials), 1) if turn_trials else None,
                "model": dict(self.model),
            }

    def get_model(self) -> dict:
        with self._lock:
            return {"model": dict(self.model), "trials": list(self.trials)}
