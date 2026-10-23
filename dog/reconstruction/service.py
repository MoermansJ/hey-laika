"""The room as this service currently believes it to be.

One object holds everything a capture touches — the settings, the loaded
model, the newest cloud and the newest frame — behind one lock, because
the HTTP thread, the websocket threads and (later) the capture loop all
read it. Nothing here knows about Flask; `server.py` is the only file that
does, which is what keeps the pipeline testable without a port.

Phase 1 holds exactly one cloud: every capture replaces the last one.
Accumulation across poses is phase 4 (AGENT-28), and it lands here, not in
the viewer.
"""
import logging
import threading
import time

from reconstruction import cloud, depth, fixtures, frames
from reconstruction import settings as settings_module

logger = logging.getLogger(__name__)


class Service:
    """Where frames come from is a *setting*, not a launch flag: the demo
    runs split across Jon's laptop and the PC, and the Tailscale address
    has to be changeable from the tuning panel without a restart."""

    def __init__(self, overrides: dict | None = None,
                 model_factory=depth.build_model,
                 source_factory=frames.FrameSource):
        self.settings, notes = settings_module.resolve(overrides)
        self._source_factory = source_factory
        self._frame_source = None
        self._source_key = None
        self.started_at = time.time()
        self.last_error = None
        self.last_capture = None        # the stats dict of the newest capture
        self.notes = notes
        self._model_factory = model_factory
        self._model = None
        self._model_name = None
        self._cloud = None              # (xyz, colours)
        self._lock = threading.Lock()
        self._capture_lock = threading.Lock()   # one inference at a time
        self._listeners = []            # callables fed every new cloud
        self._loop = None               # the optional interval capture thread
        self._loop_stop = threading.Event()
        self.apply_loop()

    # ---- model -------------------------------------------------------------
    def model(self):
        """The depth model for the current settings, rebuilt when the
        `model` setting changes."""
        with self._lock:
            name = self.settings["model"]
            if self._model is None or self._model_name != name:
                self._model = self._model_factory(name)
                self._model_name = name
                logger.info("Reconstruction: depth model %s", name)
            return self._model

    # ---- frame source ------------------------------------------------------
    def frame_source(self):
        """The adapter client for the current settings, rebuilt when the URL
        or the robot id changes."""
        with self._lock:
            key = (self.settings["frameBaseUrl"], self.settings["robotId"])
            if self._frame_source is None or self._source_key != key:
                self._frame_source = self._source_factory(
                    {"baseUrl": key[0], "robotId": key[1]})
                self._source_key = key
                logger.info("Reconstruction: frames from %s",
                            self._frame_source.snap_url)
            return self._frame_source

    # ---- settings ----------------------------------------------------------
    def update_settings(self, overrides: dict) -> tuple[dict, list[str]]:
        merged = {**self.settings, **(overrides or {})}
        resolved, notes = settings_module.resolve(merged)
        with self._lock:
            self.settings = resolved
            self.notes = notes
        self.apply_loop()
        return resolved, notes

    # ---- capture -----------------------------------------------------------
    def capture(self) -> dict:
        """One frame -> one cloud, replacing the last. Returns the capture's
        stats; the only thing a caller has to catch is FrameError.

        Serialised: a double-clicked button must not start a second
        inference while the first is still on the GPU."""
        with self._capture_lock:
            return self._capture()

    def _capture(self) -> dict:
        started = time.time()
        settings = dict(self.settings)          # one capture, one settings read
        jpeg, origin = self._frame()
        model = self.model()
        disparity, rgb = model.infer(jpeg)
        xyz, colours, stats = cloud.to_points(disparity, rgb, settings)

        capture = {
            "at": time.time(),
            "source": origin,
            "frameBytes": len(jpeg),
            "frameSize": [int(rgb.shape[1]), int(rgb.shape[0])],
            "provider": model.provider,
            "inferenceMs": model.stats["inferenceMs"],
            "totalMs": round((time.time() - started) * 1000.0, 1),
            "cloud": stats,
            "settings": settings,
        }
        with self._lock:
            self._cloud = (xyz, colours)
            self.last_capture = capture
            self.last_error = None
        self._notify(xyz, colours)
        logger.info("Reconstruction: %s -> %d points in %.0f ms (%s)", origin,
                    stats["points"], capture["totalMs"], model.provider)
        return capture

    def _frame(self) -> tuple[bytes, str]:
        """`fresh=1` every time: the button means "look now", not "show me
        what you last saw"."""
        if self.settings["source"] != "adapter":
            return fixtures.person_frame(), "fixture:person"
        source = self.frame_source()
        return source.fetch(fresh=True), source.snap_url

    # ---- the optional loop -------------------------------------------------
    def apply_loop(self) -> None:
        """`captureIntervalS` > 0 arms a background capture loop; 0 (the
        default) means the button is the only trigger. Jon wants to play
        with single captures first, so the loop stays opt-in."""
        wanted = float(self.settings.get("captureIntervalS", 0.0)) > 0.0
        running = self._loop is not None and self._loop.is_alive()
        if wanted and not running:
            self._loop_stop.clear()
            self._loop = threading.Thread(target=self._run_loop, daemon=True,
                                          name="reconstruction-loop")
            self._loop.start()
            logger.info("Reconstruction: capture loop armed at %.1fs",
                        self.settings["captureIntervalS"])
        elif running and not wanted:
            self._loop_stop.set()
            logger.info("Reconstruction: capture loop disarmed")

    def _run_loop(self) -> None:
        while not self._loop_stop.wait(float(self.settings["captureIntervalS"])):
            if float(self.settings.get("captureIntervalS", 0.0)) <= 0.0:
                break
            try:
                self.capture()
            except Exception as error:               # noqa: BLE001 - keep looping
                self.last_error = str(error)
                logger.warning("Reconstruction: loop capture failed (%s)", error)

    def stop(self) -> None:
        self._loop_stop.set()

    @property
    def looping(self) -> bool:
        return self._loop is not None and self._loop.is_alive()             and not self._loop_stop.is_set()

    # ---- readers -----------------------------------------------------------
    def current_cloud(self):
        with self._lock:
            return self._cloud

    def binary_frame(self) -> bytes | None:
        current = self.current_cloud()
        return cloud.to_binary_frame(*current) if current else None

    def state(self) -> dict:
        with self._lock:
            points = self._cloud[0].shape[0] if self._cloud else 0
            return {
                "source": self.settings["source"],
                "frameSource": (self._frame_source.status()
                                if self._frame_source else None),
                "hasCloud": self._cloud is not None,
                "points": int(points),
                "lastCapture": self.last_capture,
                "lastError": self.last_error,
                "settings": dict(self.settings),
                "notes": list(self.notes),
                "looping": self.looping,
                "uptimeS": round(time.time() - self.started_at, 1),
            }

    # ---- listeners (the viewer's socket subscribes here) -------------------
    def subscribe(self, listener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def unsubscribe(self, listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _notify(self, xyz, colours) -> None:
        with self._lock:
            listeners = list(self._listeners)
        if not listeners:
            return
        blob = cloud.to_binary_frame(xyz, colours)
        for listener in listeners:
            try:
                listener(blob)
            except Exception as error:               # noqa: BLE001
                logger.warning("Reconstruction: listener dropped (%s)", error)
                self.unsubscribe(listener)
