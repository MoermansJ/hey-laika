"""HTTP client for the XIAO ESP32S3 Sense satellite on Laika's head.

The satellite serves, on its own WiFi address (satellite/xiao_sense):
  GET /        status JSON (mic, camera, packets, rssi, led)
  GET /snap    one JPEG frame (QVGA)
  GET /stream  MJPEG (browsers only; the adapter polls /snap instead)
  GET /led     the mood light: ?r=&g=&b=&effect=off|solid|pulse|blink
               &periodMs=&brightness= sets it, no query reads it back

The microphone does not go through here: it streams PCM to ears.py over UDP.
Every call is short-timeout and records the last error instead of raising
into the callers' threads; `enabled` is simply "a host is configured".
"""
import logging
import time

import requests

logger = logging.getLogger(__name__)

LED_EFFECTS = ("off", "solid", "pulse", "blink")


class SatelliteError(RuntimeError):
    """The satellite did not answer (offline, rebooting, wrong address)."""


class SatelliteClient:
    def __init__(self, host: str | None, timeout_s: float = 2.5,
                 session=None, clock=time.time):
        self.host = (host or "").strip()
        self.timeout_s = timeout_s
        self._http = session or requests.Session()
        self._clock = clock
        self.last_ok_at: float | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.host)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}"

    # -- endpoints --

    def status(self) -> dict:
        return self._get("/").json()

    def snapshot(self) -> bytes:
        response = self._get("/snap")
        if not response.content.startswith(b"\xff\xd8"):
            raise SatelliteError("/snap did not return a JPEG")
        return response.content

    def led(self) -> dict:
        return self._get("/led").json()

    def set_led(self, r: int, g: int, b: int, effect: str = "solid",
                period_ms: int = 1500, brightness: int = 255) -> dict:
        if effect not in LED_EFFECTS:
            raise ValueError(f"effect must be one of {LED_EFFECTS}")
        params = {"r": _byte(r), "g": _byte(g), "b": _byte(b), "effect": effect,
                  "periodMs": max(100, min(60000, int(period_ms))),
                  "brightness": _byte(brightness)}
        return self._get("/led", params=params).json()

    # -- reporting --

    def info(self) -> dict:
        return {"host": self.host or None, "enabled": self.enabled,
                "lastOkAt": self.last_ok_at, "lastError": self.last_error}

    # -- internals --

    def _get(self, path: str, params: dict | None = None):
        if not self.enabled:
            raise SatelliteError("SATELLITE_HOST is not set")
        try:
            response = self._http.get(self.base_url + path, params=params,
                                      timeout=self.timeout_s)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.last_error = str(exc)
            raise SatelliteError(f"satellite {path}: {exc}") from exc
        self.last_ok_at = self._clock()
        self.last_error = None
        return response


def _byte(value) -> int:
    return max(0, min(255, int(value)))
