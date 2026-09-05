"""Battery saver: four tiers that trade liveliness for runtime.

  active    everything on
  eco       battery <= 30 % or quiet 5 min: camera to 1 fps, LED dimmed to
            40 %, WiFi sniffer off
  doze      battery <= 15 % or quiet 15 min: lie down and switch the servos
            off (the `power_nap` behavior), camera paused, LED at 10 %
  critical  battery <= 8 %: doze at safety priority, motion requests refused
            with a spoken reason, "please charge me" said once

Anything that shows someone is there wakes her back to active: a wake phrase,
a person in view, a leash event, an IMU exception (lifted, knocked), a manual
command from the console. A battery-forced tier only lifts when the level
climbs back above the threshold plus a hysteresis band (charging), or on a
manual override from the console. The microphone stays on in every tier so
"Hey Laika" always works.

Independently of the tiers, the sensor gate: the camera, the ranger and the
WiFi sniffer run only while she is moving (a motion command in the last
`stationaryAfterS` seconds). Stationary, only the ears and the speaker stay
live, so "Hey Laika" still works and she still answers. `sensorsWhenStationary`
turns the gate off.

What each tier saves comes from the parts list: holding servos are the
biggest draw and go to zero after `d`; the satellite's camera and WiFi bursts
(peaks ~340 mA) shrink with fewer frames; the LED is up to 60 mA at full
white. The mood light, the eyes and the sniffer expose the knobs this uses.
"""
import json
import logging
import threading
import time

from app.models import SessionLocal, Setting

logger = logging.getLogger(__name__)

TIERS = ("active", "eco", "doze", "critical")
SETTINGS_KEY = "power.saver"
DEFAULT_CONFIG = {
    "ecoPct": 30.0, "dozePct": 15.0, "criticalPct": 8.0, "hysteresisPct": 5.0,
    "ecoIdleS": 300.0, "dozeIdleS": 900.0,
    "ecoFps": 1.0, "ecoLedDim": 0.4, "dozeLedDim": 0.1,
    "sensorsWhenStationary": 0.0, "stationaryAfterS": 20.0,
}
WAKE_EVENTS = ("voice.wake", "voice.phrase", "voice.intent", "conversation.listen",
               "vision.person", "leash.near", "leash.warn", "leash.far", "leash.lost",
               "exception.report")
SAY_CRITICAL = "My battery is low. Please charge me."
SAY_REFUSE = "My battery is too low to move. Please charge me first."


class PowerSaver:
    def __init__(self, binder, eyes, mood, senses, battery_reader, idle_seconds,
                 speak=None, tick_s: float = 5.0, clock=time.time, enabled: bool = True,
                 ranger=None, motion_at=None):
        self.binder = binder
        self.eyes = eyes
        self.mood = mood
        self.senses = senses
        self.ranger = ranger
        self.motion_at = motion_at or (lambda: None)   # -> epoch of the last motion command
        self.moving = True
        self.sensors_gated = False
        self.battery_reader = battery_reader      # -> pct | None
        self.idle_seconds = idle_seconds          # -> seconds since the last motion
        self.speak = speak or (lambda text: None)
        self.tick_s = tick_s
        self._clock = clock
        self.enabled = enabled
        self.config = dict(DEFAULT_CONFIG)
        self.tier = "active"
        self.since = clock()
        self.reasons: list[str] = []
        self.manual: str | None = None
        self._last_activity = clock()
        self._activity_reason = "start"
        self._base_fps = getattr(eyes, "fps", None)
        self._paused_eyes = False
        self._said_critical = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.stats = {"transitions": 0, "wakes": 0, "lastWake": None, "lastBattery": None}

    # -- lifecycle --

    def init(self) -> None:
        self._load_config()
        self.binder.listeners.append(self.on_event)
        if self.enabled:
            threading.Thread(target=self._loop, daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.tick_s):
            try:
                self.evaluate()
            except Exception:
                logger.exception("Power saver tick failed")

    # -- activity: anything that means someone is there --

    def on_event(self, event: str, payload: dict | None = None) -> None:
        if event in WAKE_EVENTS:
            self.note_activity(event)

    def note_activity(self, reason: str = "command") -> None:
        self._last_activity = self._clock()
        self._activity_reason = reason
        if self.tier != "active" and self.manual is None and not self._battery_forced():
            self.stats["wakes"] += 1
            self.stats["lastWake"] = reason
            self._apply("active", [f"woken by {reason}"])

    def motion_allowed(self) -> str | None:
        """None when the dog may move; otherwise the sentence to say instead."""
        return SAY_REFUSE if self.tier == "critical" else None

    # -- the decision --

    def evaluate(self) -> dict:
        battery = self._battery()
        idle = self._idle()
        target, reasons = self._target(battery, idle)
        if target != self.tier:
            self._apply(target, reasons)
        self._gate_sensors()
        return self.status()

    # -- the sensor gate: sensors follow motion, ears and speaker do not --

    def motion_seconds(self) -> float | None:
        try:
            at = self.motion_at()
        except Exception:
            at = None
        return None if at is None else max(0.0, self._clock() - at)

    def _gate_sensors(self) -> None:
        if self.config.get("sensorsWhenStationary"):
            moving = True
        else:
            since = self.motion_seconds()
            moving = since is not None and since < self.config["stationaryAfterS"]
        if moving == self.moving and (self.sensors_gated == (not moving) or moving):
            return
        self.moving = moving
        if self.tier in ("doze", "critical"):
            return                                  # the tier already has them off
        if moving:
            self._eyes(fps=self._base_fps if self.tier == "active" else self.config["ecoFps"], running=True)
            self._sniffer(self.tier == "active")
            self._ranger(True)
            self.sensors_gated = False
        else:
            self._eyes(running=False)
            self._sniffer(False)
            self._ranger(False)
            self.sensors_gated = True
        logger.info("Power saver: sensors %s (%s)", "on" if moving else "paused",
                    "moving" if moving else "stationary")

    def _ranger(self, on: bool) -> None:
        if self.ranger is not None and hasattr(self.ranger, "gated"):
            self.ranger.gated = not on

    def _target(self, battery, idle) -> tuple[str, list[str]]:
        if self.manual:
            return self.manual, ["manual override"]
        c = self.config
        reasons = []
        tier = "active"
        if battery is not None:
            if battery <= c["criticalPct"]:
                return "critical", [f"battery {battery:.0f} %"]
            if battery <= c["dozePct"]:
                tier, reasons = "doze", [f"battery {battery:.0f} %"]
            elif battery <= c["ecoPct"]:
                tier, reasons = "eco", [f"battery {battery:.0f} %"]
        if idle >= c["dozeIdleS"] and tier != "doze":
            tier, reasons = "doze", reasons + [f"quiet {int(idle // 60)} min"]
        elif idle >= c["ecoIdleS"] and tier == "active":
            tier, reasons = "eco", [f"quiet {int(idle // 60)} min"]
        # Hysteresis: a battery-forced tier holds until the level climbs back
        # above its threshold plus the band (the pack is being charged).
        if battery is not None and self._battery_forced():
            rank = {t: i for i, t in enumerate(TIERS)}
            if rank[tier] < rank[self.tier]:
                threshold = {"eco": c["ecoPct"], "doze": c["dozePct"], "critical": c["criticalPct"]}[self.tier]
                if battery < threshold + c["hysteresisPct"]:
                    return self.tier, self.reasons
        return tier, reasons

    def _battery_forced(self) -> bool:
        return any(r.startswith("battery") for r in self.reasons)

    # -- applying a tier --

    def _apply(self, tier: str, reasons: list[str]) -> None:
        with self._lock:
            previous = self.tier
            self.tier = tier
            self.since = self._clock()
            self.reasons = list(reasons)
            self.stats["transitions"] += 1
        logger.info("Power saver: %s -> %s (%s)", previous, tier, ", ".join(reasons) or "-")
        c = self.config
        try:
            if tier == "active":
                self._eyes(fps=self._base_fps, running=self.moving)
                self._dim(1.0)
                self._sniffer(self.moving)
                self._ranger(self.moving)
                self._said_critical = False
            elif tier == "eco":
                self._eyes(fps=c["ecoFps"], running=self.moving)
                self._dim(c["ecoLedDim"])
                self._sniffer(False)
                self._ranger(self.moving)
            elif tier == "doze":
                self._eyes(running=False)
                self._dim(c["dozeLedDim"])
                self._sniffer(False)
                self.binder.trigger("power.doze", {"reasons": reasons})
            elif tier == "critical":
                self._eyes(running=False)
                self._dim(c["dozeLedDim"])
                self._sniffer(False)
                self.binder.trigger("power.critical", {"reasons": reasons})
                if not self._said_critical:
                    self._said_critical = True
                    try:
                        self.speak(SAY_CRITICAL)
                    except Exception as exc:
                        logger.info("Power saver: could not speak (%s)", exc)
        except Exception:
            logger.exception("Power saver: applying %s failed", tier)

    def _eyes(self, fps=None, running: bool | None = None) -> None:
        if self.eyes is None or not getattr(self.eyes, "_enabled", True):
            return
        if fps is not None and hasattr(self.eyes, "set_fps"):
            self.eyes.set_fps(fps)
        if running is False and self.eyes.enabled:
            self.eyes.set_enabled(False)
            self._paused_eyes = True
        elif running is True and self._paused_eyes:
            self.eyes.set_enabled(True)
            self._paused_eyes = False
        if running is True:
            self.sensors_gated = False

    def _dim(self, factor: float) -> None:
        if self.mood is not None and hasattr(self.mood, "set_dim"):
            self.mood.set_dim(factor)

    def _sniffer(self, on: bool) -> None:
        if self.senses is not None and hasattr(self.senses, "enabled"):
            self.senses.enabled = on

    # -- readings --

    def _battery(self):
        try:
            battery = self.battery_reader()
        except Exception:
            battery = None
        self.stats["lastBattery"] = battery
        return battery

    def _idle(self) -> float:
        try:
            motion_idle = float(self.idle_seconds())
        except Exception:
            motion_idle = 0.0
        return min(motion_idle, self._clock() - self._last_activity)

    # -- settings and overrides --

    def override(self, tier: str | None) -> dict:
        if tier is not None and tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS} or null for automatic")
        self.manual = tier
        if tier is None:
            self.reasons = []            # let the next evaluation decide afresh
        return self.evaluate()

    def configure(self, updates: dict) -> dict:
        bounds = {"ecoPct": (0, 100), "dozePct": (0, 100), "criticalPct": (0, 100),
                  "hysteresisPct": (0, 30), "ecoIdleS": (30, 86400), "dozeIdleS": (60, 86400),
                  "ecoFps": (0.2, 10), "ecoLedDim": (0, 1), "dozeLedDim": (0, 1),
                  "sensorsWhenStationary": (0, 1), "stationaryAfterS": (3, 3600)}
        new = dict(self.config)
        for key, value in (updates or {}).items():
            if key not in bounds:
                raise ValueError(f"unknown setting '{key}'")
            lo, hi = bounds[key]
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number")
            if not lo <= value <= hi:
                raise ValueError(f"{key} must be between {lo} and {hi}")
            new[key] = value
        if not new["criticalPct"] <= new["dozePct"] <= new["ecoPct"]:
            raise ValueError("thresholds must satisfy criticalPct <= dozePct <= ecoPct")
        if not new["ecoIdleS"] <= new["dozeIdleS"]:
            raise ValueError("ecoIdleS must not exceed dozeIdleS")
        self.config = new
        self._save_config()
        self.moving = not self.moving           # force the gate to re-evaluate
        return self.evaluate()

    def _load_config(self) -> None:
        try:
            with SessionLocal() as session:
                row = session.get(Setting, SETTINGS_KEY)
            if row is not None:
                data = json.loads(row.value or "{}")
                self.config.update({k: float(v) for k, v in data.items() if k in DEFAULT_CONFIG})
        except Exception:
            logger.exception("Power saver: settings not loaded")

    def _save_config(self) -> None:
        try:
            with SessionLocal() as session:
                row = session.get(Setting, SETTINGS_KEY) or Setting(key=SETTINGS_KEY)
                row.value = json.dumps(self.config)
                session.add(row)
                session.commit()
        except Exception:
            logger.exception("Power saver: settings not saved")

    # -- reporting --

    def status(self) -> dict:
        motion = self.motion_seconds()
        return {"enabled": self.enabled, "tier": self.tier, "tiers": list(TIERS),
                "moving": self.moving, "sensorsGated": self.sensors_gated,
                "motionS": None if motion is None else round(motion, 1),
                "sinceS": round(self._clock() - self.since, 1), "reasons": list(self.reasons),
                "manual": self.manual, "battery": self.stats["lastBattery"],
                "idleS": round(self._idle(), 1), "lastActivity": self._activity_reason,
                "config": dict(self.config), "defaults": dict(DEFAULT_CONFIG), **self.stats}
