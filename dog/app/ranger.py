"""Ultrasonic ranger: one-shot firmware reads (`XU`, one-pin Grove ranger on
the UART socket) with the bookkeeping a live readout needs.

Every read is a firmware round trip under the controller lock (~50-90 ms
over WiFi), so GUI polling is throttled here rather than trusted: reads
closer together than `min_interval_s` return the cached value. Misses
(`-1`, no echo inside the ~2 m window) are counted, never retried — the
validation notes (NAVIGATION_MAPPING_BRIEF addendum 2026-09-03) show they
come from the target, not the sensor.
"""
import threading
import time
from collections import deque


class RangerService:
    def __init__(self, controller, pin: int | None, min_interval_s: float = 0.15,
                 history: int = 60, clock=time.time):
        self.controller = controller
        self.pin = pin
        self.min_interval_s = min_interval_s
        self._clock = clock
        self._lock = threading.Lock()
        self._recent: deque = deque(maxlen=history)
        self._last: dict | None = None
        self.stats = {"reads": 0, "misses": 0, "lastReadMs": None}

    @property
    def enabled(self) -> bool:
        return bool(self.pin)

    def read(self, pin: int | None = None) -> dict:
        pin = pin or self.pin
        if not pin:
            raise RuntimeError("ULTRASONIC_PIN is not set")
        now = self._clock()
        with self._lock:
            last = self._last
            if (last and last["pin"] == pin
                    and now - last["at"] < self.min_interval_s):
                return {**last, "cached": True}
            started = time.time()
            distance = self.controller.read_range_cm(pin)
            read_ms = round((time.time() - started) * 1000)
            self.stats["reads"] += 1
            self.stats["lastReadMs"] = read_ms
            if distance is None:
                self.stats["misses"] += 1
            if pin == self.pin:
                self._recent.append(distance)
            self._last = {"pin": pin, "distanceCm": distance,
                          "ok": distance is not None, "at": now,
                          "readMs": read_ms}
            return {**self._last, "cached": False}

    def status(self) -> dict:
        with self._lock:
            recent = list(self._recent)
            last = dict(self._last) if self._last else None
        return {"enabled": self.enabled, "pin": self.pin,
                "minIntervalS": self.min_interval_s, "last": last,
                "recent": recent, **self.stats}
