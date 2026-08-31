"""Unit tests for the gait learning session against a scripted controller."""
import time

import pytest

from app.gait_learner import GaitLearner, _norm


class ScriptedController:
    """Yaw advances by a configured amount whenever a kwk* command lands."""

    def __init__(self, turn_gain=1.0, drift_per_cycle=0.0, voltage=7.8):
        self.yaw = 0.0
        self.turn_gain = turn_gain
        self.drift_per_cycle = drift_per_cycle
        self.voltage = voltage
        self.commands: list[str] = []
        self.spin = 0.0  # deg advanced per gp read while a kvt gait runs

    def send_command(self, command):
        self.commands.append(command)
        parts = command.split()
        if parts[0] == "kwkL":
            self.yaw += int(parts[1]) * self.turn_gain
        elif parts[0] == "kwkR":
            self.yaw -= int(parts[1]) * self.turn_gain
        elif parts[0] == "kwkF":
            self.yaw += int(parts[1]) * self.drift_per_cycle
        elif command == "kvtL":
            self.spin = 8.0  # continuous turn-in-place, like real firmware
        elif command == "kvtR":
            self.spin = -8.0
        elif command == "kup":
            was_spinning = self.spin != 0.0
            self.spin = 0.0
            return was_spinning  # kup no-ops report failure on hardware
        return True

    def query(self, command):
        if command == "gp":
            self.yaw += self.spin
            return [f"ICM:\t0.1\t0.2\t9.8\t{self.yaw:.1f}\t1.0\t-0.5"]
        if command == "P":
            return [f"Voltage: {self.voltage} V"]
        return []


def make_learner(ctrl):
    learner = GaitLearner(ctrl, settle_poll_s=0.01, settle_reads=1,
                          max_turn_wait_s=0.5, rearm_wait_s=0.0,
                          walk_s_per_cycle=0.0, post_turn_wait_s=0.0,
                          walk_extra_s=0.0)
    learner.vt_poll_s = 0.0
    return learner


def run_to_state(learner, states, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if learner.get_status()["state"] in states:
            return learner.get_status()
        if learner.get_status()["state"] == "awaiting_recenter":
            learner.confirm_recenter()
        time.sleep(0.02)
    raise TimeoutError(f"never reached {states}: {learner.get_status()}")


def test_turn_model_learns_gain():
    ctrl = ScriptedController(turn_gain=1.2)  # turns 20% long
    learner = make_learner(ctrl)
    assert learner.start(sequence=["kwkL 90", "kwkR 90"], batch_size=2)
    status = run_to_state(learner, ("done",))
    model = status["model"]
    assert model["turn_gain_left"] == pytest.approx(1.2, abs=0.01)
    assert model["turn_gain_right"] == pytest.approx(1.2, abs=0.01)
    assert model["turn_gains"]["L90"] == pytest.approx(1.2, abs=0.01)
    # kup was interleaved before each gait
    assert ctrl.commands.count("kup") == 2


def test_walk_learns_heading_drift_not_distance():
    ctrl = ScriptedController(drift_per_cycle=-2.5)  # rightward drift
    learner = make_learner(ctrl)
    assert learner.start(sequence=["kwkF 4"], batch_size=2)
    run_to_state(learner, ("done",))
    result = learner.get_model()
    assert result["model"]["heading_drift_deg_per_cycle"] == \
        pytest.approx(-2.5, abs=0.1)
    trial = result["trials"][0]
    assert trial["predicted_distance_m"] == pytest.approx(0.436, abs=0.001)
    assert "actual_distance_m" not in trial  # distance is not measurable


def test_batches_pause_for_recenter():
    ctrl = ScriptedController()
    learner = make_learner(ctrl)
    assert learner.start(sequence=["kwkL 45", "kwkR 45", "kwkL 90"],
                         batch_size=2)
    deadline = time.time() + 5
    while learner.get_status()["state"] != "awaiting_recenter":
        assert time.time() < deadline
        time.sleep(0.02)
    assert learner.get_status()["trialsDone"] == 2
    learner.confirm_recenter()
    run_to_state(learner, ("done",))
    assert learner.get_status()["trialsDone"] == 3


def test_low_battery_pauses_session():
    ctrl = ScriptedController(voltage=6.5)  # below the 6.9V floor
    learner = make_learner(ctrl)
    assert learner.start(sequence=["kwkL 45"], batch_size=1)
    status = run_to_state(learner, ("paused_low_battery",))
    assert status["trialsDone"] == 0  # no motion attempted on a sagging pack


def test_auto_recenter_returns_home_and_restores_heading():
    ctrl = ScriptedController(turn_gain=1.0)
    learner = make_learner(ctrl)
    assert learner.start(sequence=["kwkL 90"], batch_size=1,
                         recenter="auto", verify_every=99)
    status = run_to_state(learner, ("done",))
    pose = status["poseEstimate"]
    # The trial arc displaced it ~0.47m; recentering must have walked it back
    # and restored heading within the feedback-turn tolerance.
    assert any(c.startswith("kwkF") for c in ctrl.commands)
    assert abs(pose["headingDeg"]) <= 15
    assert (pose["x"] ** 2 + pose["y"] ** 2) ** 0.5 < 0.35
    # No human pause was needed (verify_every high, single trial).
    assert status["state"] == "done"


def test_auto_recenter_verify_pause():
    ctrl = ScriptedController(turn_gain=1.0)
    learner = make_learner(ctrl)
    assert learner.start(sequence=["kwkL 45", "kwkR 45", "kwkL 90"],
                         batch_size=1, recenter="auto", verify_every=2)
    deadline = time.time() + 10
    while learner.get_status()["state"] != "awaiting_recenter":
        assert time.time() < deadline
        time.sleep(0.02)
    assert learner.get_status()["trialsDone"] == 2
    learner.confirm_recenter()  # human confirms -> pose trust resets
    status = run_to_state(learner, ("done",))
    assert status["trialsDone"] == 3


def test_vt_turn_closed_loop_stops_near_target():
    ctrl = ScriptedController()
    learner = make_learner(ctrl)
    actual = learner._vt_turn("L", 90.0)
    # Spin advances 8 deg/read; stop lead 5 deg -> stops within one step.
    assert actual == pytest.approx(88, abs=8)
    assert ctrl.spin == 0.0  # kup was sent — never left spinning
    assert "kvtL" in ctrl.commands and "kup" in ctrl.commands


def test_yaw_wrap_normalization():
    assert _norm(329.6) == pytest.approx(-30.4)
    assert _norm(-267.4) == pytest.approx(92.6)


def test_second_start_rejected_while_running():
    ctrl = ScriptedController()
    learner = make_learner(ctrl)
    assert learner.start(sequence=["kwkL 45"] * 4, batch_size=1)
    assert learner.start(sequence=["kwkL 45"]) is False
    learner.stop()
    run_to_state(learner, ("stopped", "done"))
