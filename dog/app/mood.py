"""Mood light: the chainable RGB LED on the satellite shows what Laika is
doing (NAVIGATION_MAPPING_BRIEF §Vision satellite: "mood / leash zone").

Two layers, both mirrored to the LED through satellite.set_led:
  base   the standing mood (idle, a leash zone, low battery, or whatever the
         GUI pinned); survives until replaced
  flash  a short-lived mood layered on top (wake word heard, person seen,
         the dog spoke); reverts to the base when its timer runs out

Events reach this module through EventBinder.listeners, so the mapping
below runs for every event whether or not a behavior is bound to it. The
LED is cosmetic: a satellite that does not answer is recorded, never raised.
A resync loop re-sends the state every 30 s so a rebooted satellite (LED
off at boot) catches up without anyone noticing.
"""
import logging
import threading
import time

from app.satellite import LED_EFFECTS, SatelliteError

logger = logging.getLogger(__name__)

# name -> (r, g, b, effect, periodMs, brightness)
MOODS = {
    "off":         (0,   0,   0,   "off",   1500, 255),
    "idle":        (255, 140, 40,  "solid", 1500, 40),    # warm, dim
    "heard":       (0,   120, 255, "pulse", 900,  255),   # legacy blue; wake is green now
    "wake":        (0,   255, 40,  "solid", 1500, 255),   # wake phrase heard
    "wake_greet":  (0,   255, 40,  "pulse", 700,  255),   # ...and it was a greeting
    "listening":   (0,   255, 40,  "pulse", 700,  255),   # recording the request (the spinner)
    "thinking":    (160, 0,   255, "pulse", 700,  255),
    "speaking":    (0,   255, 170, "pulse", 450,  255),
    "happy":       (0,   255, 40,  "solid", 1500, 255),
    "person":      (0,   210, 255, "solid", 1500, 200),   # someone in view
    "alert":       (255, 160, 0,   "solid", 1500, 255),
    "warn":        (255, 90,  0,   "blink", 700,  255),   # leash stretching
    "lost":        (255, 0,   0,   "blink", 350,  255),   # leash at its end
    "low_battery": (255, 0,   0,   "pulse", 2500, 255),
    "rainbow":     (0,   0,   0,   "rainbow", 600, 255),  # host-stepped, periodMs per colour
}

# The rainbow is stepped from here (one /led call per colour) rather than in
# the satellite sketch: no XIAO reflash needed, and 600 ms steps are a
# handful of tiny requests per second. Firmware-native smoothing is queued
# in FIRMWARE_QUEUE.md.
MANUAL_HOLD_S = 60.0        # a GUI/API pin outranks camera and framework events this long

RAINBOW = ((255, 0, 0), (255, 110, 0), (255, 220, 0), (0, 200, 0),
           (0, 90, 255), (60, 0, 200), (170, 0, 255))

# event -> (mood, seconds); None seconds = becomes the base mood
EVENT_MOODS = {
    "robot.online":     ("happy", 4.0),
    "voice.phrase":     ("wake", 2.5),
    "voice.wake":       ("wake", 2.5),
    "vision.person":    ("person", 1.5),
    "vision.clear":     (None, None),
    "exception.report": ("alert", 3.0),
    "leash.near":       ("idle", None),
    "leash.warn":       ("warn", None),
    "leash.far":        ("lost", None),
    "leash.lost":       ("lost", None),
    "battery.low":      ("low_battery", None),
    "idle.timeout":     ("idle", None),
}

# voice.phrase picks its mood from the intent; anything not listed is "wake".
INTENT_MOODS = {"greet": "wake_greet"}

# GUI badge kinds -> the mood whose colour and effect they must share, so a
# badge on screen and the LED on the head always agree (single source).
BADGES = {"wake": "wake", "wakeGreet": "wake_greet", "listening": "listening",
          "thinking": "thinking", "speaking": "speaking", "person": "person",
          "online": "happy", "alert": "alert", "warn": "warn", "lost": "lost",
          "lowBattery": "low_battery"}


class MoodService:
    def __init__(self, satellite, enabled: bool = True, base: str = "idle",
                 resync_s: float = 30.0, clock=time.time):
        self.satellite = satellite
        self._enabled = enabled and satellite.enabled
        self.resync_s = resync_s
        self._clock = clock
        self._lock = threading.Lock()
        self._base = dict(_mood_spec(base), name=base)
        self._flash: dict | None = None
        self._hold: dict | None = None
        self._flash_timer: threading.Timer | None = None
        self._manual_until = 0.0
        self.dim = 1.0                      # battery saver scales every brightness
        self._stop = threading.Event()
        self.stats = {"sets": 0, "failures": 0, "lastError": None,
                      "lastEvent": None, "lastSetAt": None}

    @property
    def enabled(self) -> bool:
        return self._enabled

    # -- lifecycle --

    def init(self) -> None:
        if not self.enabled:
            return
        self._apply(self._base)          # paint the base mood now, not in 30 s
        threading.Thread(target=self._resync_loop, daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            if self._flash_timer:
                self._flash_timer.cancel()

    # -- public --

    def set(self, mood: str, manual: bool = True) -> dict:
        """Pin a named mood as the base (clears any running flash). A pin from
        the GUI or API holds off event-driven flashes for MANUAL_HOLD_S: with
        someone in front of the camera, vision.person re-flashed cyan every
        1.5 s and every click looked ignored (2026-09-04)."""
        spec = dict(_mood_spec(mood), name=mood)
        with self._lock:
            self._base = spec
            self._clear_flash_locked()
            if manual:
                self._manual_until = self._clock() + MANUAL_HOLD_S
        self._apply(self._current())
        return self.status()

    def set_color(self, r: int, g: int, b: int, effect: str = "solid",
                  period_ms: int = 1500, brightness: int = 255) -> dict:
        """Pin a custom colour as the base (the GUI's colour picker)."""
        if effect not in LED_EFFECTS:
            raise ValueError(f"effect must be one of {LED_EFFECTS}")
        spec = {"name": "custom", "r": int(r), "g": int(g), "b": int(b),
                "effect": effect, "periodMs": int(period_ms),
                "brightness": int(brightness)}
        with self._lock:
            self._base = spec
            self._clear_flash_locked()
            self._manual_until = self._clock() + MANUAL_HOLD_S
        self._apply(self._current())
        return self.status()

    def flash(self, mood: str, seconds: float) -> dict:
        """Show a mood for `seconds`, then fall back to the base."""
        spec = dict(_mood_spec(mood), name=mood)
        with self._lock:
            self._clear_flash_locked()
            self._flash = {**spec, "until": self._clock() + seconds}
            self._flash_timer = threading.Timer(seconds, self._end_flash)
            self._flash_timer.daemon = True
            self._flash_timer.start()
        self._apply(self._current())
        return self.status()

    def hold(self, mood: str) -> dict:
        """Show a mood on top of everything until release(): the conversation's
        listening / thinking / speaking states, which have no fixed length."""
        spec = dict(_mood_spec(mood), name=mood)
        with self._lock:
            self._hold = spec
        self._apply(spec)
        return self.status()

    def release(self) -> dict:
        with self._lock:
            self._hold = None
        self._apply(self._current())
        return self.status()

    def on_event(self, event: str, payload: dict | None = None) -> None:
        """EventBinder listener: map framework events to moods."""
        if not self.enabled or event not in EVENT_MOODS:
            return
        mood, seconds = EVENT_MOODS[event]
        if event == "voice.phrase":
            mood = INTENT_MOODS.get((payload or {}).get("intent"), mood)
        self.stats["lastEvent"] = event
        if self._clock() < self._manual_until:
            return
        if mood is None:
            with self._lock:
                self._clear_flash_locked()
            self._apply(self._base)
        elif seconds is None:
            self.set(mood, manual=False)
        else:
            self.flash(mood, seconds)

    def sync(self) -> bool:
        """Re-send the current state (satellite reboot, GUI refresh)."""
        return self._apply(self._current())

    # -- reporting --

    def status(self) -> dict:
        with self._lock:
            base = dict(self._base)
            flash = dict(self._flash) if self._flash else None
            hold = dict(self._hold) if self._hold else None
        current = hold or flash or base
        return {"enabled": self.enabled, "moods": list(MOODS),
                "palette": {name: _mood_spec(name) for name in MOODS},
                "badges": dict(BADGES),
                "effects": list(LED_EFFECTS),
                "mood": current["name"], "base": base["name"],
                "hold": hold["name"] if hold else None,
                "dim": self.dim,
                "flash": ({"name": flash["name"],
                           "remainingS": round(max(0.0, flash["until"] - self._clock()), 1)}
                          if flash else None),
                "color": {k: current[k] for k in
                          ("r", "g", "b", "effect", "periodMs", "brightness")},
                "satellite": self.satellite.info(), **self.stats}

    # -- internals --

    def _current(self) -> dict:
        with self._lock:
            return dict(self._hold or self._flash or self._base)

    def _clear_flash_locked(self) -> None:
        if self._flash_timer:
            self._flash_timer.cancel()
        self._flash_timer = None
        self._flash = None

    def _end_flash(self) -> None:
        with self._lock:
            self._flash = None
            self._flash_timer = None
        self._apply(self._current())

    def _apply(self, spec: dict) -> bool:
        if not self.enabled:
            return False
        if spec["effect"] == "rainbow":
            return self._start_rainbow(spec)
        self._stop_rainbow()
        return self._send(spec["r"], spec["g"], spec["b"], spec["effect"],
                          spec["periodMs"], spec["brightness"])

    def set_dim(self, factor: float) -> dict:
        """Scale all brightness by 0..1 without touching the moods themselves."""
        self.dim = max(0.0, min(1.0, float(factor)))
        self._apply(self._current())
        return self.status()

    def _send(self, r, g, b, effect, period_ms, brightness) -> bool:
        if self.dim < 1.0 and brightness:
            brightness = max(1, int(round(brightness * self.dim)))
        try:
            self.satellite.set_led(r, g, b, effect, period_ms, brightness)
        except SatelliteError as exc:
            self.stats["failures"] += 1
            self.stats["lastError"] = str(exc)
            return False
        self.stats["sets"] += 1
        self.stats["lastSetAt"] = self._clock()
        self.stats["lastError"] = None
        return True

    # -- rainbow: host-stepped colour cycle --

    def _start_rainbow(self, spec: dict) -> bool:
        with self._lock:
            self._rainbow_gen = getattr(self, "_rainbow_gen", 0) + 1
            gen = self._rainbow_gen
            self._rainbow_index = 0
        ok = self.rainbow_step(gen)
        threading.Thread(target=self._rainbow_loop, args=(gen, spec["periodMs"] / 1000.0),
                         daemon=True).start()
        return ok

    def _stop_rainbow(self) -> None:
        with self._lock:
            self._rainbow_gen = getattr(self, "_rainbow_gen", 0) + 1

    def rainbow_step(self, gen: int | None = None) -> bool:
        """Send the next rainbow colour; False once the cycle was superseded."""
        with self._lock:
            if gen is not None and gen != getattr(self, "_rainbow_gen", 0):
                return False
            index = getattr(self, "_rainbow_index", 0)
            self._rainbow_index = (index + 1) % len(RAINBOW)
            brightness = self._current_spec_locked()["brightness"]
        r, g, b = RAINBOW[index]
        return self._send(r, g, b, "solid", 1500, brightness)

    def _rainbow_loop(self, gen: int, period_s: float) -> None:
        while not self._stop.wait(period_s):
            if not self.rainbow_step(gen):
                return

    def _current_spec_locked(self) -> dict:
        return self._flash or self._base

    def _resync_loop(self) -> None:
        while not self._stop.wait(self.resync_s):
            try:
                self._resync_once()
            except Exception:
                logger.exception("Mood resync failed")

    def _resync_once(self) -> None:
        current = self._current()
        if current["effect"] == "rainbow":
            return                       # the cycle repaints every step anyway
        try:
            shown = self.satellite.led()
        except SatelliteError as exc:
            self.stats["lastError"] = str(exc)
            return
        if any(shown.get(k) != current[k] for k in ("r", "g", "b", "effect")):
            self._apply(current)


def _mood_spec(name: str) -> dict:
    if name not in MOODS:
        raise ValueError(f"unknown mood '{name}' (one of {', '.join(MOODS)})")
    r, g, b, effect, period_ms, brightness = MOODS[name]
    return {"r": r, "g": g, "b": b, "effect": effect, "periodMs": period_ms,
            "brightness": brightness}
