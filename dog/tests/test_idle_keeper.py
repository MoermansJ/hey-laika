"""Unit tests for the host-managed idle ladder (sit -> lie)."""
import time

from app.idle_keeper import IdleKeeper


class FakeController:
    def __init__(self):
        self.commands = []
        self.last_motion_at = time.time()

    def send_command(self, command):
        self.commands.append(command)
        self.last_motion_at = time.time()
        return True


def make_keeper(ctrl, **kw):
    kw.setdefault("sit_after_s", 0.2)
    kw.setdefault("rest_after_s", 0.5)
    kw.setdefault("tick_s", 0.05)
    return IdleKeeper(ctrl, **kw)


def wait_for(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_idle_ladder_sits_then_lies():
    ctrl = FakeController()
    keeper = make_keeper(ctrl)
    keeper.start()
    try:
        assert wait_for(lambda: "ksit" in ctrl.commands)
        assert keeper.status()["state"] == IdleKeeper.SITTING
        # The keeper's own ksit must not reset the clock -> krest follows.
        assert wait_for(lambda: "krest" in ctrl.commands)
        assert keeper.status()["state"] == IdleKeeper.LYING
        assert ctrl.commands == ["ksit", "krest"]  # exactly one each
    finally:
        keeper.stop()


def test_external_activity_resets_ladder():
    ctrl = FakeController()
    keeper = make_keeper(ctrl)
    keeper.start()
    try:
        assert wait_for(lambda: "ksit" in ctrl.commands)
        ctrl.last_motion_at = time.time()  # external command arrives
        assert wait_for(lambda: keeper.status()["state"] == IdleKeeper.ACTIVE)
        # Idle again -> sits a second time.
        assert wait_for(lambda: ctrl.commands.count("ksit") == 2)
    finally:
        keeper.stop()


def test_suppressed_keeper_does_nothing():
    ctrl = FakeController()
    keeper = make_keeper(ctrl, suppressed=lambda: True)
    keeper.start()
    try:
        time.sleep(0.8)
        assert ctrl.commands == []
    finally:
        keeper.stop()


def test_disabled_keeper_does_nothing():
    ctrl = FakeController()
    keeper = make_keeper(ctrl, enabled=False)
    keeper.start()
    try:
        time.sleep(0.8)
        assert ctrl.commands == []
    finally:
        keeper.stop()
