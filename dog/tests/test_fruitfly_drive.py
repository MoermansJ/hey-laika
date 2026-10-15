"""Fruitfly's F2 bridge (fruitfly_drive.py): decoded sim state -> gait
command mapping, and start/stop against a faked arbiter (no real arbiter
thread, no real sim HTTP server)."""
from app.fruitfly_drive import FRUITFLY_BEHAVIOR, FruitflyDriveService


class FakeArbiter:
    def __init__(self):
        self.submissions = []
        self._current_name = None
        self.stop_calls = 0

    def submit_generator(self, name, factory, source="manual", priority=2,
                         cause=None, interruptible=True, suppress_avoidance=False,
                         on_end=None):
        self.submissions.append({"name": name, "factory": factory, "source": source,
                                 "priority": priority, "cause": cause})
        self._current_name = name
        return {"status": "executing"}

    def current_behavior(self):
        return self._current_name

    def stop_current(self):
        self.stop_calls += 1
        self._current_name = None
        return {"stopped": True}


def make_drive(responses, **config):
    arbiter = FakeArbiter()
    queue = list(responses)

    def fetch_command():
        item = queue.pop(0) if queue else queue_default
        return item

    queue_default = None  # sentinel: sim unreachable once the queue drains
    drive = FruitflyDriveService(arbiter, "http://127.0.0.1:8765",
                                 config=config, fetch_command=fetch_command)
    return drive, arbiter


def test_start_submits_a_generator_behavior_at_agent_priority():
    drive, arbiter = make_drive([{"state": "STOP", "signals": {}}])

    drive.start()

    assert len(arbiter.submissions) == 1
    submission = arbiter.submissions[0]
    assert submission["name"] == FRUITFLY_BEHAVIOR
    assert submission["source"] == "agent"
    assert submission["cause"] == {"type": "fruitfly"}


def test_forward_left_right_decode_to_their_gait_skills():
    drive, _ = make_drive([
        {"state": "FORWARD", "signals": {}},
        {"state": "LEFT", "signals": {}},
        {"state": "RIGHT", "signals": {}},
        {"state": "STOP", "signals": {}},
    ], burstS=0.5)

    steps = drive._drive_steps()
    assert next(steps) == {"command": "kwkF", "label": "FORWARD", "settleS": 0.5}
    assert next(steps) == {"command": "kwkL", "label": "LEFT", "settleS": 0.5}
    assert next(steps) == {"command": "kwkR", "label": "RIGHT", "settleS": 0.5}
    assert next(steps) == {"command": "kbalance", "label": "STOP", "settleS": 0.5}


def test_backward_is_dropped_to_the_stop_command():
    drive, _ = make_drive([{"state": "BACKWARD", "signals": {}}], burstS=0.5)

    step = next(drive._drive_steps())

    # The decoded label still says BACKWARD — only the SKILL is dropped to the
    # stop command, so the feed stays honest about what the fly decided.
    assert step == {"command": "kbalance", "label": "BACKWARD", "settleS": 0.5}


def test_unreachable_sim_holds_balance_instead_of_raising():
    drive, _ = make_drive([], unreachableBackoffS=1.5)  # fetch_command() returns None

    step = next(drive._drive_steps())

    assert step == {"command": "kbalance", "label": "HOLD (sim unreachable)", "settleS": 1.5}


def test_stop_only_stops_the_arbiter_when_fruitfly_drive_is_the_current_behavior():
    drive, arbiter = make_drive([{"state": "STOP", "signals": {}}])

    assert drive.stop() is False
    assert arbiter.stop_calls == 0

    drive.start()
    assert drive.stop() is True
    assert arbiter.stop_calls == 1


def test_status_reports_the_last_decoded_state_and_signals():
    drive, _ = make_drive([{"state": "FORWARD", "signals": {"forward": 0.9}}])

    next(drive._drive_steps())

    assert drive.status() == {"lastState": "FORWARD", "lastSignals": {"forward": 0.9}}
