"""AGENT-06: PUT /api/robots/<id>/behavior/run-log/<run_id>/outcome."""
import pytest

from app.behavior_store import PRIORITY_AGENT
from app.config import Config

URL = f"/api/robots/{Config.ROBOT_ID}/behavior/run-log/{{}}/outcome"


@pytest.fixture
def appmod():
    import app.app as module
    module.app.config["TESTING"] = True
    return module


@pytest.fixture
def client(appmod):
    return appmod.app.test_client()


@pytest.fixture
def run_id(appmod):
    rid = appmod.behavior_store.log_start(
        "look_up", "agent", PRIORITY_AGENT,
        cause={"type": "agent", "decisionId": "d-1", "goal": "look_upward"})
    appmod.behavior_store.log_end(rid, "complete")
    return rid


BODY = {"success": True, "confidence": 0.87,
        "reason": "Motion now centered vertically in frame",
        "evaluator_version": "1.0", "evaluated_at": "2026-10-11T12:00:02Z"}


def test_put_outcome_updates_the_run(client, appmod, run_id):
    resp = client.put(URL.format(run_id), json=BODY)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "updated"
    assert body["run"]["id"] == run_id
    assert body["run"]["outcome"]["success"] is True
    assert body["run"]["outcome"]["confidence"] == 0.87
    stored = appmod.behavior_store.run_entry(run_id).outcome
    assert stored.success is True
    assert stored.reason == "Motion now centered vertically in frame"
    assert stored.evaluator_version == "1.0"
    assert stored.evaluated_at == "2026-10-11T12:00:02Z"


def test_put_outcome_is_idempotent(client, appmod, run_id):
    first = client.put(URL.format(run_id), json=BODY).get_json()["run"]
    second = client.put(URL.format(run_id), json=BODY).get_json()["run"]
    assert first == second
    assert appmod.behavior_store.run(run_id) == second


def test_repeat_without_evaluated_at_keeps_the_first_stamp(client, appmod, run_id):
    body = {k: v for k, v in BODY.items() if k != "evaluated_at"}
    first = client.put(URL.format(run_id), json=body).get_json()["run"]
    assert first["outcome"]["evaluated_at"]
    second = client.put(URL.format(run_id), json=body).get_json()["run"]
    assert second["outcome"]["evaluated_at"] == first["outcome"]["evaluated_at"]
    assert first == second


def test_later_different_outcome_replaces_the_earlier_one(client, appmod, run_id):
    client.put(URL.format(run_id), json=BODY)
    resp = client.put(URL.format(run_id),
                      json={**BODY, "success": False, "confidence": 0.2,
                            "reason": "no motion"})
    assert resp.status_code == 200
    stored = appmod.behavior_store.run_entry(run_id).outcome
    assert stored.success is False
    assert stored.reason == "no motion"


def test_camel_case_keys_and_sensor_delta_accepted(client, appmod, run_id):
    resp = client.put(URL.format(run_id),
                      json={"success": None, "confidence": 0.0,
                            "reason": "no checker", "evaluatorVersion": "2.0",
                            "evaluatedAt": "2026-10-11T12:00:03Z",
                            "sensorDelta": {"pitch": 4}})
    assert resp.status_code == 200
    entry = appmod.behavior_store.run_entry(run_id)
    assert entry.outcome.success is None
    assert entry.outcome.evaluator_version == "2.0"
    assert entry.sensor_delta == {"pitch": 4}


def test_unknown_run_is_404(client):
    resp = client.put(URL.format("no-such-run"), json=BODY)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


@pytest.mark.parametrize("body", [
    {**BODY, "confidence": 1.5},
    {**BODY, "confidence": "high"},
    {**BODY, "success": "yes"},
    {**BODY, "sensor_delta": [1, 2]},
])
def test_invalid_body_is_400(client, run_id, body):
    resp = client.put(URL.format(run_id), json=body)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"


def test_non_object_body_is_400(client, run_id):
    resp = client.put(URL.format(run_id), data="nope",
                      content_type="text/plain")
    assert resp.status_code == 400


def test_other_robot_is_404(client):
    resp = client.put("/api/robots/someone-else/behavior/run-log/x/outcome",
                      json=BODY)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "unknown_robot"
