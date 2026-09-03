"""Ultrasonic ranger service: throttling, miss counting, history, the route."""
import pytest

from app.config import Config
from app.ranger import RangerService

RID = Config.ROBOT_ID


class ScriptedController:
    def __init__(self, readings):
        self.readings = list(readings)
        self.calls = []

    def read_range_cm(self, pin):
        self.calls.append(pin)
        return self.readings.pop(0) if self.readings else None


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_reads_are_throttled_and_cached():
    clock = Clock()
    ctrl = ScriptedController([42.0, 43.0])
    ranger = RangerService(ctrl, pin=9, min_interval_s=0.15, clock=clock)
    first = ranger.read()
    clock.now += 0.05
    second = ranger.read()
    clock.now += 0.2
    third = ranger.read()
    assert first["distanceCm"] == 42.0 and first["cached"] is False
    assert second["distanceCm"] == 42.0 and second["cached"] is True
    assert third["distanceCm"] == 43.0 and third["cached"] is False
    assert ctrl.calls == [9, 9]


def test_misses_count_and_history_keeps_none():
    clock = Clock()
    ranger = RangerService(ScriptedController([30.0, None, 31.0]), pin=9, clock=clock)
    for _ in range(3):
        ranger.read()
        clock.now += 1
    status = ranger.status()
    assert status["recent"] == [30.0, None, 31.0]
    assert status["reads"] == 3 and status["misses"] == 1
    assert status["last"]["ok"] is True


def test_validation_pin_is_not_recorded_in_history():
    clock = Clock()
    ranger = RangerService(ScriptedController([12.0, 50.0]), pin=9, clock=clock)
    ranger.read(pin=10)
    clock.now += 1
    ranger.read()
    assert ranger.status()["recent"] == [50.0]


def test_unconfigured_ranger_raises():
    ranger = RangerService(ScriptedController([]), pin=None)
    assert ranger.enabled is False
    with pytest.raises(RuntimeError):
        ranger.read()


@pytest.fixture
def client():
    from app.app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_range_route_reports_reading_and_history(client):
    resp = client.get(f"/api/robots/{RID}/senses/range?pin=9")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pin"] == 9 and body["ok"] is True          # mock returns a number
    assert "readMs" in body and "reads" in body and "recent" in body
    assert client.get(f"/api/robots/{RID}/senses/range?pin=99").status_code == 400
