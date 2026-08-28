"""Tests for the robot-scoped Flask API (mock mode, per conftest)."""
import pytest

from app.app import app
from app.config import Config

RID = Config.ROBOT_ID  # "bittle-1" by default


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_is_unscoped_and_reports_identity(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["robotId"] == RID
    assert data["service"] == "bittle-python"


def test_status_for_own_robot_id(client):
    resp = client.get(f"/api/robots/{RID}/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["robotId"] == RID
    assert data["connected"] is True
    assert data["mode"] == "mock"


def test_wrong_robot_id_is_rejected(client):
    resp = client.get("/api/robots/some-other-bot/status")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "unknown_robot"


def test_personality_shape(client):
    resp = client.get(f"/api/robots/{RID}/personality")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("energy", "happiness", "boredom", "curiosity", "mood"):
        assert key in data


def test_behavior_decision(client):
    resp = client.get(f"/api/robots/{RID}/behavior")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["robotId"] == RID
    assert data["behavior"]
    assert data["source"] == "mock"


def test_command_requires_body(client):
    resp = client.post(f"/api/robots/{RID}/command", json={})
    assert resp.status_code == 400


def test_command_executes(client):
    resp = client.post(f"/api/robots/{RID}/command", json={"command": "kbalance"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_interact_updates_personality(client):
    resp = client.post(f"/api/robots/{RID}/interact/pet")
    assert resp.status_code == 200
    assert "personality" in resp.get_json()


def test_interact_rejects_unknown_type(client):
    resp = client.post(f"/api/robots/{RID}/interact/tickle")
    assert resp.status_code == 400


def test_choreography_list_and_execute(client):
    listing = client.get(f"/api/robots/{RID}/choreography/list").get_json()
    names = [a["name"] for a in listing["animations"]]
    assert "sit" in names

    resp = client.post(f"/api/robots/{RID}/choreography/execute/sit")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_choreography_unknown_animation(client):
    resp = client.post(f"/api/robots/{RID}/choreography/execute/moonwalk")
    assert resp.status_code == 404


def test_autonomous_lifecycle(client):
    status = client.get(f"/api/robots/{RID}/autonomous/status").get_json()
    assert status["running"] is False

    started = client.post(f"/api/robots/{RID}/autonomous/start").get_json()
    assert started["running"] is True

    stopped = client.post(f"/api/robots/{RID}/autonomous/stop").get_json()
    assert stopped["running"] is False


def test_activity_and_display(client):
    client.post(f"/api/robots/{RID}/interact/play")
    activity = client.get(f"/api/robots/{RID}/activity").get_json()
    assert any("play" in entry["message"] for entry in activity["activity"])

    display = client.get(f"/api/robots/{RID}/display").get_json()
    assert display["type"] == "text"
    assert "value" in display
