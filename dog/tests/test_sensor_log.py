"""Sensor readings and action outcomes: buffering, flushing, export."""
from app.models import init_db
from app.sensor_log import (ACTION_FIELDS, ActionLog, SensorLog, classify,
                            readings_csv)


def setup_module(module):
    init_db()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_hundred_readings_buffer_without_loss_and_flush_to_disk():
    clock = Clock()
    log = SensorLog(flush_s=999, history=1000, persist=True, clock=clock)
    log.init()
    for i in range(100):
        clock.now += 0.1
        log.record({"rangeCm": float(i), "rangeOk": True, "x": i / 100, "y": 0.0,
                    "heading": 0.0, "driftM": 0.0, "battery": 80.0,
                    "command": "kwkF 1", "behavior": "navigate"})
    assert log.stats["recorded"] == 100
    assert log.latest()["rangeCm"] == 99.0
    assert len(log.recent(1000)) == 100
    assert log.rate_hz() == 10.0
    assert log.flush() == 100
    assert log.flush() == 0
    # The app's own loop shares this database; keep to this test's clock.
    stored = [r for r in log.stored(since=1000.0 + 9.05, limit=5000) if r["t"] < 2000]
    assert len(stored) == 10 and stored[0]["rangeCm"] == 99.0
    status = log.status()
    assert status["flushed"] >= 100 and status["pending"] == 0 and status["dropped"] == 0
    csv_text = readings_csv(stored[:2])
    assert csv_text.splitlines()[0].startswith("t,rangeCm,rangeOk,x,y")
    assert len(csv_text.splitlines()) == 3


def test_memory_only_log_keeps_the_ring():
    log = SensorLog(history=5, persist=False)
    for i in range(8):
        log.record({"rangeCm": i})
    assert [r["rangeCm"] for r in log.recent(10)] == [7, 6, 5, 4, 3]
    assert log.flush() == 8 and log.status()["persist"] is False


def test_classify_commands():
    assert classify("kwkF 3") == ("advance", "wkF")
    assert classify("kbkF 1") == ("advance", "bkF")
    assert classify("kwkL 45") == ("turn", "wkL")
    assert classify("kvtR") == ("turn", "vtR")
    assert classify("kjmp") == ("skill", "jmp")
    assert classify("m 0 45") == ("joint", None)
    assert classify("b 14 8") == ("other", None)


def test_action_log_records_outcomes_and_exports():
    clock = Clock()
    log = ActionLog(persist=True, clock=clock)
    action_id = log.record("kwkF 3", {"x": 0.1, "y": 0.2, "heading": 3.0, "yaw": 2.5,
                                      "rangeCm": 80.0, "battery": 77.0},
                           source="navigate", target_m=0.324)
    assert isinstance(action_id, int)
    clock.now += 4.0
    log.outcome(action_id, "blocked", "wall at 20 cm")
    rows = log.export(since=999.0)
    row = [r for r in rows if r["id"] == action_id][0]
    assert row["kind"] == "advance" and row["gait"] == "wkF"
    assert row["outcome"] == "blocked" and row["endedAt"] == 1004.0
    assert row["targetM"] == 0.324 and row["source"] == "navigate"
    csv_text = log.export_csv(since=999.0)
    assert csv_text.splitlines()[0] == ",".join(ACTION_FIELDS)
    assert "kwkF 3" in csv_text
    assert log.recent(1)[0]["outcome"] == "blocked"
    assert log.status()["recorded"] == 1 and log.status()["outcomes"] == 1
