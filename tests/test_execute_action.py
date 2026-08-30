"""Tests for POST /execute_action (Phase 1b — orchestrator-driven behavior)."""
import pytest

from app.action_executor import ACTION_PLANS
from app.app import app, autonomous, bittle


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def post_action(client, action, duration_ms=100):
    return client.post("/api/robots/bittle-1/execute_action",
                       json={"action": action, "durationMs": duration_ms,
                             "sequenceId": 1})


def test_all_orchestrator_actions_have_plans():
    orchestrator_catalog = {
        "walk_slow", "walk_fast", "stand_up", "sit_down", "lie_down",
        "look_left", "look_right", "look_up", "play_bow", "backflip", "spin",
        "idle_calm", "sleep", "wake_up", "seek_attention",
        "look_around_low", "look_around_slow", "stretch"}
    assert orchestrator_catalog == set(ACTION_PLANS)


def test_look_around_sweeps_recenter(client):
    for action in ("look_around_low", "look_around_slow"):
        resp = post_action(client, action, 200)
        assert resp.get_json()["success"] is True, action
        assert bittle.read_joint_angles()[0] == 0, action


def test_skill_action_reaches_controller(client):
    resp = post_action(client, "stand_up")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["success"] is True and body["action"] == "stand_up"
    assert body["actualDurationMs"] >= 0
    assert bittle.last_command == "kbalance"


def test_look_action_moves_head_and_recenters(client):
    resp = post_action(client, "look_left", 150)
    assert resp.get_json()["success"] is True
    assert bittle.read_joint_angles()[0] == 0  # recentered at the end


def test_gait_restores_balance(client):
    post_action(client, "walk_slow", 100)
    assert bittle.last_command == "kbalance"


def test_unknown_action_400(client):
    assert post_action(client, "moonwalk").status_code == 400


def test_missing_action_400(client):
    resp = client.post("/api/robots/bittle-1/execute_action", json={})
    assert resp.status_code == 400


def test_409_while_adapter_loop_running(client):
    autonomous.start()
    try:
        assert post_action(client, "stand_up").status_code == 409
    finally:
        autonomous.stop()
