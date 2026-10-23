"""Where a frame comes from: the adapter's cached JPEG, or a file.

The adapter already polls the XIAO's `/snap` and caches the newest frame
(`dog/app/eyes.py`), and exposes it at
`GET /api/robots/<robot_id>/eyes/snap`, which the orchestrator relays on
:8080. This service reads *that*, never the satellite directly: the XIAO
serves one camera and one microphone off one small radio, and the
satellite README records `/snap` returning 500 when the camera is
contended. One poller, one cache, many readers.

`fresh=True` adds `?fresh=1`, which makes the adapter take a new picture
instead of handing over the cached one — what the manual capture button
wants. The base URL is configurable because the demo runs split: the
orchestrator on Jon's laptop, this service on the PC, joined over
Tailscale.
"""
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULTS = {
    "baseUrl": "http://localhost:8080",   # orchestrator; :15001 hits the adapter
    "robotId": "bittle-1",
    "timeoutS": 8.0,
}


class FrameError(RuntimeError):
    """The frame could not be fetched. Carries the URL that failed."""


class FrameSource:
    def __init__(self, config: dict | None = None):
        self.config = {**DEFAULTS, **(config or {})}
        self.last_error = None
        self.stats = {"fetches": 0, "fetchMs": None, "bytes": None,
                      "lastAt": None}

    @property
    def snap_url(self) -> str:
        base = str(self.config["baseUrl"]).rstrip("/")
        return f"{base}/api/robots/{self.config['robotId']}/eyes/snap"

    def fetch(self, fresh: bool = True) -> bytes:
        """One JPEG from the adapter's cache. Raises FrameError, never a
        bare requests exception, so callers log one shape of failure."""
        import requests

        url = self.snap_url + ("?fresh=1" if fresh else "")
        started = time.time()
        try:
            response = requests.get(url, timeout=float(self.config["timeoutS"]))
            response.raise_for_status()
        except Exception as error:                   # noqa: BLE001 - one shape out
            self.last_error = f"{type(error).__name__}: {error}"
            logger.warning("Frame fetch failed (%s): %s", url, self.last_error)
            raise FrameError(f"{url}: {self.last_error}") from error

        body = response.content
        if not body.startswith(b"\xff\xd8"):
            self.last_error = f"{url} did not return a JPEG"
            raise FrameError(self.last_error)

        self.last_error = None
        self.stats = {"fetches": self.stats["fetches"] + 1,
                      "fetchMs": round((time.time() - started) * 1000.0, 1),
                      "bytes": len(body), "lastAt": time.time()}
        return body

    def status(self) -> dict:
        return {"snapUrl": self.snap_url, "lastError": self.last_error,
                **self.stats}


def from_file(path: str | Path) -> bytes:
    """A saved frame. Step 1a proves the model on one of these before any
    hardware is involved."""
    body = Path(path).read_bytes()
    if not body.startswith(b"\xff\xd8"):
        raise FrameError(f"{path} is not a JPEG")
    return body
