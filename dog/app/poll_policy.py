"""Adaptive dog-facing polling (owner request 2026-09-01).

When the dog is parked in an idle posture (rest on all fours, sit, lie
down), routine pings — the telemetry 'P' poll and the battery event poll —
stretch by a configurable multiplier. Posture comes from observing the
command stream (the same choke point the odometry shadow taps), NOT from
last_command, which routine non-motion traffic (XWd, XWs) would clobber.

The 20 s WS keepalive is deliberately NOT governed here: the firmware
drops clients silent for 40 s, so it cannot safely stretch.
"""
import threading

DEFAULTS = {
    "telemetryTtlS": 40.0,
    "batteryPollS": 40.0,
    "idleMultiplier": 3.0,
    "idlePostures": ["rest", "sit", "lnd"],
}

# Command prefixes that represent motion/posture (skills, joints, frames).
_MOTION_PREFIXES = ("k", "m", "i", "M", "I", "L")


class PollPolicy:
    def __init__(self, config: dict | None = None):
        self._lock = threading.Lock()
        self.config = {**DEFAULTS, **(config or {})}
        self._last_posture_cmd: str | None = None

    # ---- posture tracking --------------------------------------------------

    def observe_command(self, command: str) -> None:
        command = (command or "").strip()
        if command and command.startswith(_MOTION_PREFIXES):
            with self._lock:
                self._last_posture_cmd = command

    def is_idle(self) -> bool:
        with self._lock:
            cmd = self._last_posture_cmd
            postures = list(self.config["idlePostures"])
        if not cmd:
            return False
        name = cmd[1:] if cmd[0] in "kK" else cmd
        name = name.strip().lower()
        return any(name == p.lower() or name.startswith(p.lower())
                   for p in postures)

    def factor(self) -> float:
        return float(self.config["idleMultiplier"]) if self.is_idle() else 1.0

    # ---- effective intervals (injected as callables) -----------------------

    def telemetry_ttl(self) -> float:
        return float(self.config["telemetryTtlS"]) * self.factor()

    def battery_interval(self) -> float:
        return float(self.config["batteryPollS"]) * self.factor()

    # ---- config API --------------------------------------------------------

    def configure(self, updates: dict) -> dict:
        with self._lock:
            for key in ("telemetryTtlS", "batteryPollS", "idleMultiplier"):
                if key in updates and isinstance(updates[key], (int, float)) \
                        and updates[key] > 0:
                    self.config[key] = float(updates[key])
            postures = updates.get("idlePostures")
            if isinstance(postures, str):
                postures = [p.strip() for p in postures.split(",") if p.strip()]
            if isinstance(postures, list) and postures:
                self.config["idlePostures"] = [str(p) for p in postures]
        return self.status()

    def status(self) -> dict:
        idle = self.is_idle()
        with self._lock:
            config = dict(self.config)
            last = self._last_posture_cmd
        return {
            "config": config,
            "idle": idle,
            "lastPostureCommand": last,
            "effectiveTelemetryTtlS": round(self.telemetry_ttl(), 1),
            "effectiveBatteryPollS": round(self.battery_interval(), 1),
            "keepaliveS": 20,  # fixed: firmware 40 s client-silence timeout
        }
