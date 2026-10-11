"""AGENT-04: the adapter side of the orchestrator's ArbiterClient contract.

The Java ArbiterClient submits via POST /arbiter/invoke, reads the run back via
GET /behavior/run-log/<run_id>, so the submit result must carry the run id and
an agent's declared goal must survive into the run's provenance."""
import time

import pytest

from app.arbiter import Arbiter
from app.behavior_store import PRIORITY_AGENT
from app.config import Config


class _Store:
    def __init__(self):
        self.runs = []

    def behavior(self, name):
        return {"id": name, "name": name, "description": "",
                "steps": [{"command": "kbalance", "settleS": 0.0}],
                "interruptible": True, "cooldownS": 0}

    def log_start(self, name, source, priority, cause=None, run_id=None):
        self.runs.append({"id": run_id, "behavior": name, "cause": cause,
                          "status": "running"})
        return run_id

    def log_end(self, run_id, status, detail="", preempted_by=None):
        next(r for r in self.runs if r["id"] == run_id)["status"] = status

    def recent_runs(self, limit=10):
        return list(reversed(self.runs))[:limit]


class _Controller:
    last_motion_at = 0.0

    def send_command(self, command):
        return True

    def get_telemetry(self):
        return {}


def test_submit_result_carries_the_run_id_the_run_log_uses():
    store = _Store()
    arb = Arbiter(_Controller(), store, sleep_fn=lambda s: time.sleep(min(s, 0.02)))
    try:
        result = arb.submit("look_up", source="agent", priority=PRIORITY_AGENT,
                            cause={"type": "agent", "decisionId": "d-1"})
        assert result["status"] in ("executing", "queued")
        assert result["runId"]
        end = time.time() + 3
        while time.time() < end and not store.runs:
            time.sleep(0.01)
        assert store.runs and store.runs[0]["id"] == result["runId"]
    finally:
        arb.shutdown()


def test_rejected_submit_has_no_run_id():
    store = _Store()
    store.behavior = lambda name: None
    arb = Arbiter(_Controller(), store, sleep_fn=lambda s: time.sleep(min(s, 0.02)))
    try:
        result = arb.submit("missing", source="agent", priority=PRIORITY_AGENT)
        assert result["status"] == "rejected"
        assert "runId" not in result
    finally:
        arb.shutdown()


@pytest.fixture
def appmod():
    import app.app as module
    module.app.config["TESTING"] = True
    return module


def test_invoke_puts_agent_goal_in_cause(appmod, monkeypatch):
    seen = {}

    def fake_submit(name, source, priority, cause):
        seen.update(name=name, source=source, priority=priority, cause=cause)
        return {"status": "queued", "position": 0, "runId": "run-42"}

    monkeypatch.setattr(appmod.arbiter, "submit", fake_submit)
    resp = appmod.app.test_client().post(
        f"/api/robots/{Config.ROBOT_ID}/arbiter/invoke",
        json={"behavior": "look_up", "source": "agent", "priority": 3,
              "decisionId": "d-7", "goal": "look_upward"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["runId"] == "run-42"
    assert body["status"] == "queued"
    assert seen["cause"] == {"type": "agent", "decisionId": "d-7",
                             "goal": "look_upward"}
    assert seen["priority"] == 3


def test_invoke_without_goal_keeps_previous_agent_cause(appmod, monkeypatch):
    seen = {}
    monkeypatch.setattr(appmod.arbiter, "submit",
                        lambda name, source, priority, cause:
                        seen.update(cause=cause) or {"status": "queued"})
    appmod.app.test_client().post(
        f"/api/robots/{Config.ROBOT_ID}/arbiter/invoke",
        json={"behavior": "look_up", "source": "agent", "decisionId": "d-8"})
    assert seen["cause"] == {"type": "agent", "decisionId": "d-8"}


def test_run_log_entry_endpoint_returns_the_run(appmod):
    run_id = appmod.behavior_store.log_start(
        "look_up", "agent", PRIORITY_AGENT,
        cause={"type": "agent", "decisionId": "d-9", "goal": "look_upward"})
    appmod.behavior_store.log_end(run_id, "complete")
    resp = appmod.app.test_client().get(
        f"/api/robots/{Config.ROBOT_ID}/behavior/run-log/{run_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == run_id
    assert body["robotId"] == Config.ROBOT_ID
    assert body["behavior"] == "look_up"
    assert body["source"] == "agent"
    assert body["status"] == "complete"
    assert body["cause"]["goal"] == "look_upward"
    assert body["startedAt"] and body["endedAt"]
    assert body["outcome"] is None


def test_run_log_entry_unknown_run_is_404(appmod):
    resp = appmod.app.test_client().get(
        f"/api/robots/{Config.ROBOT_ID}/behavior/run-log/no-such-run")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_run_log_entry_other_robot_is_404(appmod):
    resp = appmod.app.test_client().get(
        "/api/robots/someone-else/behavior/run-log/whatever")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "unknown_robot"
