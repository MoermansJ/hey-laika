"""Tests for the adaptive polling policy."""
from app.poll_policy import PollPolicy


def test_idle_detection_from_posture_commands():
    policy = PollPolicy()
    assert policy.is_idle() is False       # no motion seen yet
    policy.observe_command("kwkF 3")
    assert policy.is_idle() is False
    policy.observe_command("krest")
    assert policy.is_idle() is True
    policy.observe_command("ksit")
    assert policy.is_idle() is True
    policy.observe_command("kup")
    assert policy.is_idle() is False


def test_non_motion_commands_do_not_clobber_posture():
    policy = PollPolicy()
    policy.observe_command("krest")
    policy.observe_command("XWd1 20")   # leash arming
    policy.observe_command("b 21 8")    # beep
    assert policy.is_idle() is True     # still resting


def test_intervals_stretch_when_idle():
    policy = PollPolicy({"telemetryTtlS": 40.0, "batteryPollS": 40.0,
                         "idleMultiplier": 3.0})
    policy.observe_command("kwkF 1")
    assert policy.telemetry_ttl() == 40.0
    policy.observe_command("ksit")
    assert policy.telemetry_ttl() == 120.0
    assert policy.battery_interval() == 120.0


def test_configure_accepts_csv_postures_and_rejects_junk():
    policy = PollPolicy()
    status = policy.configure({"idleMultiplier": 5, "idlePostures": "rest, zz",
                               "telemetryTtlS": -3, "batteryPollS": 60})
    assert status["config"]["idleMultiplier"] == 5.0
    assert status["config"]["idlePostures"] == ["rest", "zz"]
    assert status["config"]["telemetryTtlS"] == 40.0  # negative rejected
    assert status["config"]["batteryPollS"] == 60.0
    policy.observe_command("kzz")
    assert policy.is_idle() is True


def test_polling_api_roundtrip():
    from app.app import app
    client = app.test_client()
    status = client.get("/api/robots/bittle-1/polling").get_json()
    assert status["keepaliveS"] == 20
    updated = client.post("/api/robots/bittle-1/polling",
                          json={"idleMultiplier": 4}).get_json()
    assert updated["config"]["idleMultiplier"] == 4.0
    client.post("/api/robots/bittle-1/polling", json={"idleMultiplier": 3})
