"""Eyes: JPEG frames from the satellite camera -> YOLOv8-nano person
detection on the host -> `vision.person` / `vision.clear` events.

Pipeline (NAVIGATION_MAPPING_BRIEF.md §Vision satellite):

  satellite /snap at EYES_FPS  ->  YoloOnnxDetector (onnxruntime, CPU; the
  runtime is already in the image for whisper's VAD, the weights come from
  dog/tools/export_yolo.py)  ->  persons as normalised boxes  ->  the
  largest one becomes the event payload:
    {count, x, y, w, h, offset, area, confidence}
  `offset` is the box centre relative to the frame centre, -1 (far left)
  .. +1 (far right): the steering signal follow-me needs. `vision.person`
  repeats at most once per `event_interval_s` while someone is in view;
  `vision.clear` fires once when nobody has been seen for `lost_after_s`.

The latest JPEG is cached so the GUI can show the picture through the
adapter (/eyes/snap) without every browser tab hitting the satellite. The
detector is injectable so tests run without the model file.
"""
import io
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PERSON_CLASS = 0


class YoloOnnxDetector:
    """YOLOv8 ONNX (any imgsz) through onnxruntime; loads on first use."""

    def __init__(self, model_path: str | Path, confidence: float = 0.45,
                 iou: float = 0.5):
        self.model_path = Path(model_path)
        self.model_name = self.model_path.name
        self.confidence = confidence
        self.iou = iou
        self.loaded = False
        self.available = self.model_path.is_file()
        self._session = None
        self._input_name = None
        self._input_size = (320, 320)   # (width, height), read from the model
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._session is None:
                import onnxruntime as ort

                if not self.available:
                    raise FileNotFoundError(
                        f"{self.model_path} missing; run dog/tools/export_yolo.py")
                started = time.time()
                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                self._session = ort.InferenceSession(
                    str(self.model_path), options, providers=["CPUExecutionProvider"])
                meta = self._session.get_inputs()[0]
                self._input_name = meta.name
                shape = meta.shape
                if len(shape) == 4 and all(isinstance(d, int) for d in shape[2:]):
                    self._input_size = (shape[3], shape[2])
                self.loaded = True
                logger.info("Eyes: %s loaded in %.1fs (input %sx%s)", self.model_name,
                            time.time() - started, *self._input_size)
            return self._session

    def detect(self, jpeg: bytes) -> list[dict]:
        import numpy as np
        from PIL import Image

        session = self._load()
        image = Image.open(io.BytesIO(jpeg)).convert("RGB")
        width, height = image.size
        tensor, scale, pad_x, pad_y = _letterbox(image, self._input_size)
        (output,) = session.run(None, {self._input_name: tensor})
        rows = output[0].T                          # (N, 4 + classes)
        scores = rows[:, 4 + PERSON_CLASS]
        keep = scores >= self.confidence
        boxes, scores = rows[keep, :4], scores[keep]
        if len(boxes) == 0:
            return []
        xyxy = np.column_stack([boxes[:, 0] - boxes[:, 2] / 2, boxes[:, 1] - boxes[:, 3] / 2,
                                boxes[:, 0] + boxes[:, 2] / 2, boxes[:, 1] + boxes[:, 3] / 2])
        detections = []
        for index in _nms(xyxy, scores, self.iou):
            x1 = max(0.0, (xyxy[index, 0] - pad_x) / scale)
            y1 = max(0.0, (xyxy[index, 1] - pad_y) / scale)
            x2 = min(float(width), (xyxy[index, 2] - pad_x) / scale)
            y2 = min(float(height), (xyxy[index, 3] - pad_y) / scale)
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append({"x": round(float(x1) / width, 4),
                               "y": round(float(y1) / height, 4),
                               "w": round(float(x2 - x1) / width, 4),
                               "h": round(float(y2 - y1) / height, 4),
                               "confidence": round(float(scores[index]), 3)})
        return detections

    def info(self) -> dict:
        return {"model": self.model_name, "path": str(self.model_path),
                "available": self.available, "loaded": self.loaded,
                "confidence": self.confidence,
                "inputSize": list(self._input_size)}


def _letterbox(image, size):
    import numpy as np
    from PIL import Image

    target_w, target_h = size
    width, height = image.size
    scale = min(target_w / width, target_h / height)
    new_w, new_h = max(1, round(width * scale)), max(1, round(height * scale))
    resized = image.resize((new_w, new_h), Image.BILINEAR)
    canvas = Image.new("RGB", (target_w, target_h), (114, 114, 114))
    pad_x, pad_y = (target_w - new_w) // 2, (target_h - new_h) // 2
    canvas.paste(resized, (pad_x, pad_y))
    array = np.asarray(canvas, dtype=np.float32) / 255.0
    tensor = np.ascontiguousarray(array.transpose(2, 0, 1)[None])
    return tensor, scale, pad_x, pad_y


def _nms(boxes, scores, iou_threshold):
    import numpy as np

    order = np.argsort(-scores)
    kept = []
    while len(order):
        first = order[0]
        kept.append(int(first))
        if len(order) == 1:
            break
        rest = order[1:]
        ix1 = np.maximum(boxes[first, 0], boxes[rest, 0])
        iy1 = np.maximum(boxes[first, 1], boxes[rest, 1])
        ix2 = np.minimum(boxes[first, 2], boxes[rest, 2])
        iy2 = np.minimum(boxes[first, 3], boxes[rest, 3])
        inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
        area_first = (boxes[first, 2] - boxes[first, 0]) * (boxes[first, 3] - boxes[first, 1])
        area_rest = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        iou = inter / np.maximum(area_first + area_rest - inter, 1e-6)
        order = rest[iou <= iou_threshold]
    return kept


class EyesService:
    def __init__(self, satellite, event_binder, detector=None, fps: float = 4.0,
                 enabled: bool = True, event_interval_s: float = 1.0,
                 lost_after_s: float = 2.0, clock=time.time, sleep=time.sleep):
        self.satellite = satellite
        self.binder = event_binder
        self.detector = detector
        self.fps = max(0.2, min(10.0, fps))
        self.event_interval_s = event_interval_s
        self.lost_after_s = lost_after_s
        self._clock = clock
        self._sleep = sleep
        self._enabled = enabled and satellite.enabled
        self._running = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._frame_at: float | None = None
        self._persons: list[dict] = []
        self._last_person_at: float | None = None
        self._last_event_at = 0.0
        self._cleared = True
        self._frame_times: list[float] = []
        self.stats = {"frames": 0, "detections": 0, "errors": 0,
                      "lastError": None, "inferenceMs": None,
                      "personEvents": 0, "clearEvents": 0}

    # -- lifecycle --

    def init(self) -> None:
        if not self._enabled:
            return
        self._running.set()
        threading.Thread(target=self._loop, daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()

    @property
    def enabled(self) -> bool:
        return self._enabled and self._running.is_set()

    def set_fps(self, fps: float) -> None:
        """Change the grab rate at run time (the battery saver drops it)."""
        self.fps = max(0.2, min(10.0, float(fps)))

    def set_enabled(self, enabled: bool) -> None:
        """Pause/resume frame grabbing (the satellite stays reachable)."""
        if not self._enabled:
            raise RuntimeError("SATELLITE_HOST is not set")
        if enabled:
            self._running.set()
        else:
            self._running.clear()

    # -- frames --

    def frame(self) -> tuple[bytes | None, float | None]:
        with self._lock:
            return self._frame, self._frame_at

    def capture(self) -> bytes:
        """Fetch one frame from the satellite now and run it through."""
        jpeg = self.satellite.snapshot()
        self.process(jpeg)
        return jpeg

    def process(self, jpeg: bytes) -> list[dict]:
        """Detect persons in one JPEG; cache it; emit events. Synchronous."""
        now = self._clock()
        with self._lock:
            self._frame, self._frame_at = jpeg, now
            self._frame_times = [t for t in self._frame_times if now - t < 5.0] + [now]
        self.stats["frames"] += 1
        persons: list[dict] = []
        if self.detector is not None:
            started = time.time()
            persons = self.detector.detect(jpeg)
            self.stats["inferenceMs"] = round((time.time() - started) * 1000)
        with self._lock:
            self._persons = persons
        if persons:
            self.stats["detections"] += 1
            self._last_person_at = now
            self._cleared = False
            if now - self._last_event_at >= self.event_interval_s:
                self._last_event_at = now
                self.stats["personEvents"] += 1
                self.binder.trigger("vision.person", _payload(persons))
        elif (not self._cleared and self._last_person_at is not None
              and now - self._last_person_at >= self.lost_after_s):
            self._cleared = True
            self.stats["clearEvents"] += 1
            self.binder.trigger("vision.clear", {"lastSeenS": round(now - self._last_person_at, 1)})
        return persons

    # -- reporting --

    def status(self) -> dict:
        now = self._clock()
        with self._lock:
            frame_at = self._frame_at
            persons = list(self._persons)
            recent = [t for t in self._frame_times if now - t < 5.0]
        measured = round(len(recent) / 5.0, 1) if len(recent) > 1 else 0.0
        return {
            "enabled": self.enabled,
            "configured": self._enabled,
            "targetFps": self.fps,
            "fps": measured,
            "streaming": frame_at is not None and now - frame_at < 3.0,
            "lastFrameAgeS": round(now - frame_at, 1) if frame_at else None,
            "persons": persons,
            "personCount": len(persons),
            "lastPersonAgeS": (round(now - self._last_person_at, 1)
                               if self._last_person_at else None),
            "detector": self.detector.info() if self.detector else None,
            "satellite": self.satellite.info(),
            **self.stats,
        }

    # -- internals --

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self._running.is_set():
                self._sleep(0.25)
                continue
            period = 1.0 / self.fps            # re-read: set_fps changes it live
            started = self._clock()
            try:
                self.capture()
            except Exception as exc:
                self.stats["errors"] += 1
                self.stats["lastError"] = str(exc)
                self._sleep(2.0)
                continue
            self._sleep(max(0.0, period - (self._clock() - started)))


def _payload(persons: list[dict]) -> dict:
    largest = max(persons, key=lambda p: p["w"] * p["h"])
    centre_x = largest["x"] + largest["w"] / 2
    return {"count": len(persons), **largest,
            "offset": round((centre_x - 0.5) * 2, 3),
            "area": round(largest["w"] * largest["h"], 4)}


def build_detector(model_path: str, confidence: float):
    return YoloOnnxDetector(model_path, confidence=confidence)
