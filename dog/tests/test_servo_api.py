"""Tests for the /schema and /servo endpoints (mock controller)."""
import pytest

from app.app import app, autonomous, bittle
from app.robot_schema import SERVO_INDICES


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_schema_shape(client):
    resp = client.get("/api/robots/bittle-1/schema")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["robotType"] == "bittle_x_v2"
    schema = body["schema"]
    assert len(schema["servos"]) == 9
    assert {s["index"] for s in schema["servos"]} == set(SERVO_INDICES)
    assert all(s["min"] < s["max"] for s in schema["servos"])
    assert any(a["id"] == "kbalance" and a["verified"] for a in schema["actions"])
    assert all(s["available"] is False for s in schema["sensors"])
    assert body["metadata"]["servoCount"] == 9


def test_schema_unknown_robot_404(client):
    assert client.get("/api/robots/nope/schema").status_code == 404


def test_servo_read_returns_physical_joints(client):
    resp = client.get("/api/robots/bittle-1/servo")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert [j["index"] for j in body["joints"]] == list(SERVO_INDICES)


def test_servo_move_updates_mock_state(client):
    resp = client.post("/api/robots/bittle-1/servo",
                       json={"joints": [{"index": 0, "angle": 30},
                                        {"index": 12, "angle": -40}]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True and body["clamped"] is False
    angles = bittle.read_joint_angles()
    assert angles[0] == 30 and angles[12] == -40


def test_servo_move_clamps_to_schema_limits(client):
    resp = client.post("/api/robots/bittle-1/servo",
                       json={"joints": [{"index": 0, "angle": 120}]})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["clamped"] is True
    assert body["movedJoints"][0]["angle"] == 90  # head_pan max


def test_servo_move_rejects_phantom_and_bad_input(client):
    assert client.post("/api/robots/bittle-1/servo",
                       json={"joints": [{"index": 3, "angle": 10}]}).status_code == 400
    assert client.post("/api/robots/bittle-1/servo",
                       json={"joints": []}).status_code == 400
    assert client.post("/api/robots/bittle-1/servo",
                       json={"joints": [{"index": 0}]}).status_code == 400


def test_servo_move_409_while_autonomous(client):
    autonomous.start()
    try:
        resp = client.post("/api/robots/bittle-1/servo",
                           json={"joints": [{"index": 0, "angle": 10}]})
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "autonomy_running"
    finally:
        autonomous.stop()
