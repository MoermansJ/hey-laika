"""Tests for the adapter metrics layer."""
import time

from app.metrics import Metrics, instrument_controller, metrics as global_metrics


class SlowController:
    def __init__(self, ok=True):
        self.ok = ok
        self.commands = []

    def send_command(self, command):
        self.commands.append(command)
        return self.ok


def test_observe_windows_and_counters():
    m = Metrics()
    m.observe("ws.command", 120.0, ok=True)
    m.observe("ws.command", 80.0, ok=False)
    snap = m.snapshot()
    assert snap["counters"]["ws.command.count"] == 2
    assert snap["counters"]["ws.command.errors"] == 1
    window = snap["window1h"]["ws.command"]
    assert window["count"] == 2
    assert window["errors"] == 1
    assert window["avgMs"] == 100.0
    assert window["maxMs"] == 120.0


def test_counters_survive_flush_and_reload():
    m = Metrics()
    m.init()
    m.inc("test.persist", 3)
    m.flush()
    reloaded = Metrics()
    reloaded.init()
    assert reloaded.snapshot()["counters"]["test.persist"] >= 3


def test_instrument_controller_times_commands():
    m_ctrl = SlowController(ok=True)
    # instrument_controller records into the module singleton; grab a
    # baseline so the assertion is delta-based.
    before = global_metrics.snapshot()["counters"].get("ws.command.count", 0)
    instrument_controller(m_ctrl)
    assert m_ctrl.send_command("ksit") is True
    assert m_ctrl.commands == ["ksit"]
    after = global_metrics.snapshot()["counters"]["ws.command.count"]
    assert after == before + 1


def test_metrics_endpoint_serves_snapshot():
    from app.app import app
    client = app.test_client()
    client.get("/api/health")  # generate at least one observed request
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.get_json()
    assert data["robotId"] == "bittle-1"
    assert "counters" in data and "window1h" in data
    http_keys = [k for k in data["counters"] if k.startswith("http.")]
    assert http_keys, "HTTP hook recorded nothing"
    # /metrics itself must not be counted.
    assert not any("/metrics" in k for k in data["counters"])
