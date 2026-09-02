"""Tests for power-session tracking and runtime prediction."""
import time

from app.models import init_db
from app.power import MIN_SESSION_FOR_DRAIN_S, PowerSession, PowerTracker
from app.models import SessionLocal


class FakeController:
    def __init__(self):
        self.connected = False
        self.battery = None

    def get_status(self):
        return {"connected": self.connected}

    def get_telemetry(self):
        return {"battery": self.battery}


def setup_module(module):
    init_db()


def clear_sessions():
    with SessionLocal() as session:
        session.query(PowerSession).delete()
        session.commit()


def test_session_opens_and_closes_with_snapshots():
    clear_sessions()
    ctrl = FakeController()
    tracker = PowerTracker(ctrl, poll_s=999, unreachable_grace_s=0)
    tracker.init()
    tracker.shutdown()  # drive ticks manually

    ctrl.connected, ctrl.battery = True, 88.0
    tracker._tick()  # power-on
    ctrl.battery = 61.0
    tracker._tick()  # refresh cached battery
    ctrl.connected = False
    tracker._tick()  # power-off

    summary = tracker.summary()
    assert len(summary["sessions"]) == 1
    session = summary["sessions"][0]
    assert session["startBattery"] == 88.0
    assert session["endBattery"] == 61.0
    assert session["endedAt"] is not None


def test_drain_rate_and_prediction():
    clear_sessions()
    now = time.time()
    with SessionLocal() as db:
        # Two 2-hour sessions, each draining 40% -> 20 %/h.
        for i in range(2):
            db.add(PowerSession(started_at=now - 7200 * (i + 2),
                                start_battery=90.0,
                                ended_at=now - 7200 * (i + 2) + 7200,
                                end_battery=50.0))
        # A 1-minute blip must not pollute the stats.
        db.add(PowerSession(started_at=now - 100, start_battery=80.0,
                            ended_at=now - 40, end_battery=79.0))
        db.commit()

    ctrl = FakeController()
    tracker = PowerTracker(ctrl, poll_s=999, unreachable_grace_s=0)
    ctrl.connected, ctrl.battery = True, 50.0
    tracker._tick()

    summary = tracker.summary()
    assert summary["avgDrainPctPerHour"] == 20.0
    # 50% at 20 %/h -> 150 minutes left.
    assert summary["predictedMinutesLeft"] == 150
    blip = [s for s in summary["sessions"] if s["durationS"] == 60][0]
    assert blip["drainPctPerHour"] is None


def test_dangling_session_closed_on_init():
    clear_sessions()
    with SessionLocal() as db:
        db.add(PowerSession(started_at=time.time() - 500, start_battery=70.0))
        db.commit()
    tracker = PowerTracker(FakeController(), poll_s=999)
    tracker.init()
    tracker.shutdown()
    sessions = tracker.summary()["sessions"]
    assert sessions[0]["endedAt"] is not None
    assert sessions[0]["endBattery"] is None  # unknown end excluded from drain


def test_power_api():
    from app.app import app
    client = app.test_client()
    data = client.get("/api/robots/bittle-1/power").get_json()
    assert "sessions" in data and "predictedMinutesLeft" in data
    status = client.get("/api/robots/bittle-1/status").get_json()
    assert isinstance(status["startedAt"], float)
