"""Battery saver tiers: thresholds, quiet time, wake-ups, hysteresis, the
knobs it turns on the eyes, the mood light and the sniffer, and the settings."""
import pytest

from app.models import init_db
from app.power_saver import SAY_CRITICAL, SAY_REFUSE, PowerSaver


class FakeEyes:
    def __init__(self):
        self.fps = 4.0
        self._enabled = True
        self._running = True

    @property
    def enabled(self):
        return self._enabled and self._running

    def set_fps(self, fps): self.fps = fps
    def set_enabled(self, on): self._running = on


class FakeMood:
    def __init__(self): self.dim = 1.0
    def set_dim(self, f): self.dim = f


class FakeSenses:
    def __init__(self): self.enabled = True


class FakeRanger:
    def __init__(self): self.gated = False


class FakeBinder:
    def __init__(self):
        self.listeners = []
        self.events = []

    def trigger(self, event, data=None):
        self.events.append(event)
        return []


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def advance(self, s): self.t += s


def make(battery=80.0, gate=False):
    init_db()
    clock = Clock()
    reading = {"battery": battery}
    idle = {"s": 0.0}
    motion = {"at": clock.t}                 # a motion command just happened
    said = []
    binder, eyes, mood, senses, ranger = FakeBinder(), FakeEyes(), FakeMood(), FakeSenses(), FakeRanger()
    saver = PowerSaver(binder, eyes, mood, senses, battery_reader=lambda: reading["battery"],
                       idle_seconds=lambda: idle["s"], speak=said.append, clock=clock, enabled=False,
                       ranger=ranger, motion_at=lambda: motion["at"])
    saver.init()
    if not gate:
        saver.config["sensorsWhenStationary"] = 1.0      # the tier tests want sensors independent of motion
    return saver, dict(clock=clock, reading=reading, idle=idle, motion=motion, said=said, binder=binder,
                       eyes=eyes, mood=mood, senses=senses, ranger=ranger)


def test_starts_active_and_goes_eco_after_a_quiet_spell():
    saver, f = make()
    assert saver.evaluate()["tier"] == "active"
    f["idle"]["s"] = 301
    f["clock"].advance(301)
    s = saver.evaluate()
    assert s["tier"] == "eco" and s["reasons"] == ["quiet 5 min"]
    assert f["eyes"].fps == 1.0 and f["mood"].dim == 0.4 and f["senses"].enabled is False


def test_doze_lies_down_switches_servos_off_and_pauses_the_camera():
    saver, f = make()
    f["idle"]["s"] = 901
    f["clock"].advance(901)
    s = saver.evaluate()
    assert s["tier"] == "doze"
    assert f["binder"].events == ["power.doze"]
    assert f["eyes"].enabled is False and f["mood"].dim == 0.1


def test_activity_wakes_from_a_quiet_tier_and_restores_everything():
    saver, f = make()
    f["idle"]["s"] = 901
    f["clock"].advance(901)
    saver.evaluate()
    saver.on_event("voice.wake", {})
    s = saver.status()
    assert s["tier"] == "active" and s["wakes"] == 1 and s["lastWake"] == "voice.wake"
    assert f["eyes"].enabled is True and f["eyes"].fps == 4.0
    assert f["mood"].dim == 1.0 and f["senses"].enabled is True


def test_battery_tiers_hold_until_charged_past_hysteresis():
    saver, f = make(battery=14.0)
    assert saver.evaluate()["tier"] == "doze"
    saver.on_event("voice.wake", {})           # someone is there, but the pack is flat
    assert saver.tier == "doze"
    f["reading"]["battery"] = 18.0             # above dozePct but inside the band
    assert saver.evaluate()["tier"] == "doze"
    f["reading"]["battery"] = 21.0             # charged past 15 + 5
    assert saver.evaluate()["tier"] == "eco"   # still under ecoPct
    f["reading"]["battery"] = 33.0
    assert saver.evaluate()["tier"] == "eco"   # eco is battery-forced too: needs 30 + 5
    f["reading"]["battery"] = 36.0
    assert saver.evaluate()["tier"] == "active"


def test_critical_speaks_once_refuses_motion_and_uses_safety_binding():
    saver, f = make(battery=5.0)
    saver.evaluate()
    saver.evaluate()
    assert saver.tier == "critical" and f["binder"].events == ["power.critical"]
    assert f["said"] == [SAY_CRITICAL]
    assert saver.motion_allowed() == SAY_REFUSE
    f["reading"]["battery"] = 60.0
    assert saver.evaluate()["tier"] == "active" and saver.motion_allowed() is None


def test_manual_override_and_back_to_auto():
    saver, f = make()
    assert saver.override("doze")["tier"] == "doze" and saver.status()["manual"] == "doze"
    saver.on_event("voice.wake", {})           # a held tier ignores activity
    assert saver.tier == "doze"
    assert saver.override(None)["tier"] == "active" and saver.status()["manual"] is None
    with pytest.raises(ValueError):
        saver.override("nap")


def test_sensors_pause_when_stationary_and_resume_on_motion():
    saver, f = make(gate=True)
    s = saver.evaluate()
    assert s["moving"] is True and s["sensorsGated"] is False and f["eyes"].enabled and not f["ranger"].gated
    f["clock"].advance(21)                   # no motion command for 21 s
    s = saver.evaluate()
    assert s["moving"] is False and s["sensorsGated"] is True
    assert f["eyes"].enabled is False and f["ranger"].gated is True and f["senses"].enabled is False
    assert saver.tier == "active"            # the ears and the speaker are untouched: still active
    f["motion"]["at"] = f["clock"].t         # she moves again
    s = saver.evaluate()
    assert s["moving"] is True and f["eyes"].enabled is True and f["eyes"].fps == 4.0
    assert f["ranger"].gated is False and f["senses"].enabled is True


def test_gate_respects_the_eco_tier_and_can_be_switched_off():
    saver, f = make(gate=True)
    f["idle"]["s"] = 301
    f["clock"].advance(301)
    saver.evaluate()
    assert saver.tier == "eco" and f["eyes"].enabled is False    # stationary for 301 s too
    f["motion"]["at"] = f["clock"].t
    saver.evaluate()
    assert f["eyes"].enabled is True and f["eyes"].fps == 1.0 and f["senses"].enabled is False
    saver.configure({"sensorsWhenStationary": 1})
    f["clock"].advance(100)
    saver.evaluate()
    assert f["eyes"].enabled is True and saver.status()["moving"] is True


def test_configure_validates_and_persists():
    saver, f = make()
    s = saver.configure({"ecoIdleS": 60, "ecoPct": 40})
    assert s["config"]["ecoIdleS"] == 60 and s["config"]["ecoPct"] == 40
    fresh, _ = make()
    assert fresh.config["ecoIdleS"] == 60
    with pytest.raises(ValueError):
        saver.configure({"dozePct": 50})       # above ecoPct
    with pytest.raises(ValueError):
        saver.configure({"bogus": 1})
    saver.configure({"ecoIdleS": 300, "ecoPct": 30, "sensorsWhenStationary": 0})
