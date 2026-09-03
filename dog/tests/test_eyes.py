"""Eyes: person events from scripted detections, rate limiting, the clear
event, status, the real ONNX detector when the model file exists, and the
Flask routes without a satellite."""
import io
from pathlib import Path

import pytest

from app.config import Config
from app.eyes import EyesService, YoloOnnxDetector, _nms, _payload

RID = Config.ROBOT_ID


def make_jpeg(width=320, height=240, colour=(114, 114, 114)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, format="JPEG")
    return buf.getvalue()


class FakeSatellite:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.snaps = 0

    def snapshot(self):
        self.snaps += 1
        return b"\xff\xd8frame%d" % self.snaps

    def info(self):
        return {"host": "sat", "enabled": self.enabled}


class FakeBinder:
    def __init__(self):
        self.events = []

    def trigger(self, event, data=None):
        self.events.append((event, data))
        return []


class ScriptedDetector:
    def __init__(self, script):
        self.script = list(script)
        self.loaded = True

    def detect(self, jpeg):
        return self.script.pop(0) if self.script else []

    def info(self):
        return {"model": "scripted", "loaded": True}


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


PERSON = {"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.6, "confidence": 0.9}
SMALL = {"x": 0.1, "y": 0.1, "w": 0.05, "h": 0.1, "confidence": 0.5}


def make(script, clock=None, **kw):
    clock = clock or Clock()
    binder = FakeBinder()
    eyes = EyesService(FakeSatellite(), binder, detector=ScriptedDetector(script),
                       clock=clock, sleep=lambda s: None, **kw)
    return eyes, binder, clock


def test_person_event_carries_largest_box_and_offset():
    eyes, binder, _ = make([[SMALL, PERSON]])
    persons = eyes.capture() and eyes.status()["persons"]
    assert len(persons) == 2
    event, payload = binder.events[0]
    assert event == "vision.person"
    assert payload["count"] == 2 and payload["w"] == 0.2
    assert payload["offset"] == pytest.approx(0.4)     # centre x 0.7 -> +0.4
    assert payload["area"] == pytest.approx(0.12)


def test_person_events_are_rate_limited_then_clear_fires_once():
    clock = Clock()
    eyes, binder, _ = make([[PERSON], [PERSON], [PERSON], [], [], [], []],
                           clock=clock, event_interval_s=1.0, lost_after_s=2.0)
    for step in (0.0, 0.3, 1.1):
        clock.now = 1000.0 + step
        eyes.capture()
    assert [e for e, _ in binder.events] == ["vision.person", "vision.person"]
    clock.now = 1001.5
    eyes.capture()                                    # nobody, but not yet lost
    assert len(binder.events) == 2
    clock.now = 1003.2
    eyes.capture()
    assert binder.events[-1][0] == "vision.clear"
    clock.now = 1004.0
    eyes.capture()
    assert [e for e, _ in binder.events].count("vision.clear") == 1
    assert eyes.stats["personEvents"] == 2 and eyes.stats["clearEvents"] == 1


def test_status_reports_frames_fps_and_detector():
    clock = Clock()
    eyes, _, _ = make([[], [], []], clock=clock)
    for step in (0.0, 0.25, 0.5):
        clock.now = 1000.0 + step
        eyes.capture()
    status = eyes.status()
    assert status["frames"] == 3 and status["streaming"] is True
    assert status["fps"] == pytest.approx(0.6)        # 3 frames in a 5 s window
    assert status["detector"]["model"] == "scripted"
    assert status["personCount"] == 0 and status["enabled"] is False  # init() not called
    jpeg, at = eyes.frame()
    assert jpeg.startswith(b"\xff\xd8") and at == 1000.5


def test_unconfigured_eyes_cannot_be_enabled():
    eyes = EyesService(FakeSatellite(enabled=False), FakeBinder())
    assert eyes.enabled is False
    with pytest.raises(RuntimeError):
        eyes.set_enabled(True)


def test_nms_drops_overlapping_boxes():
    import numpy as np

    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=float)
    scores = np.array([0.9, 0.8, 0.7])
    assert _nms(boxes, scores, 0.5) == [0, 2]


def test_payload_prefers_area_over_confidence():
    payload = _payload([{**SMALL, "confidence": 0.99}, PERSON])
    assert payload["confidence"] == 0.9 and payload["count"] == 2


MODEL = Path(Config.EYES_MODEL)


@pytest.mark.skipif(not MODEL.is_file(), reason="run dog/tools/export_yolo.py first")
def test_real_detector_runs_on_a_blank_frame():
    detector = YoloOnnxDetector(MODEL, confidence=0.45)
    assert detector.available is True and detector.loaded is False
    persons = detector.detect(make_jpeg())
    assert persons == [] and detector.loaded is True
    assert detector.info()["inputSize"] == [320, 320]


@pytest.mark.skipif(not MODEL.is_file(), reason="run dog/tools/export_yolo.py first")
def test_real_detector_finds_the_fixture_person_with_json_safe_boxes():
    import json

    jpeg = (Path(__file__).parent / "fixtures" / "person.jpg").read_bytes()
    persons = YoloOnnxDetector(MODEL, confidence=0.45).detect(jpeg)
    assert persons, "no person found in tests/fixtures/person.jpg"
    json.dumps(_payload(persons))                      # plain floats, no numpy
    assert all(0 <= p["x"] <= 1 and 0 < p["w"] <= 1 for p in persons)


def test_missing_model_reports_unavailable():
    detector = YoloOnnxDetector("nowhere/yolo.onnx")
    assert detector.available is False
    with pytest.raises(FileNotFoundError):
        detector.detect(make_jpeg())


# ---- routes (no SATELLITE_HOST under test: everything reports disabled) ----

@pytest.fixture
def client():
    from app.app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_eyes_and_mood_routes_without_a_satellite(client):
    eyes = client.get(f"/api/robots/{RID}/eyes").get_json()
    assert eyes["enabled"] is False and eyes["configured"] is False
    assert client.get(f"/api/robots/{RID}/eyes/snap").status_code == 404
    assert client.get(f"/api/robots/{RID}/satellite").status_code == 409
    assert client.post(f"/api/robots/{RID}/eyes/config",
                       json={"enabled": True}).status_code == 409
    mood = client.get(f"/api/robots/{RID}/mood").get_json()
    assert mood["enabled"] is False and "happy" in mood["moods"]
    assert client.post(f"/api/robots/{RID}/mood", json={"mood": "happy"}).status_code == 409


def test_detect_route_validates_upload(client):
    assert client.post(f"/api/robots/{RID}/eyes/detect").status_code == 400
    resp = client.post(f"/api/robots/{RID}/eyes/detect",
                       data={"file": (io.BytesIO(b"not a jpeg"), "x.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 400


@pytest.mark.skipif(not MODEL.is_file(), reason="run dog/tools/export_yolo.py first")
def test_detect_route_runs_the_model(client):
    resp = client.post(f"/api/robots/{RID}/eyes/detect",
                       data={"file": (io.BytesIO(make_jpeg()), "blank.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["persons"] == [] and body["inferenceMs"] >= 0
    snap = client.get(f"/api/robots/{RID}/eyes/snap")
    assert snap.status_code == 200 and snap.mimetype == "image/jpeg"
