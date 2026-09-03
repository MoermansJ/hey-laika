"""Mood light: base/flash layering, event mapping, resync, disabled path."""
import pytest

from app.mood import EVENT_MOODS, MOODS, MoodService
from app.satellite import SatelliteError


class FakeSatellite:
    def __init__(self, enabled=True, fail=False):
        self.enabled = enabled
        self.fail = fail
        self.calls = []
        self.shown = {"r": 0, "g": 0, "b": 0, "effect": "off"}

    def set_led(self, r, g, b, effect="solid", period_ms=1500, brightness=255):
        if self.fail:
            raise SatelliteError("offline")
        self.calls.append((r, g, b, effect, period_ms, brightness))
        self.shown = {"r": r, "g": g, "b": b, "effect": effect}
        return dict(self.shown)

    def led(self):
        return dict(self.shown)

    def info(self):
        return {"host": "sat", "enabled": self.enabled}


def make(satellite=None, **kw):
    return MoodService(satellite or FakeSatellite(), clock=kw.pop("clock", lambda: 100.0), **kw)


def test_set_pins_a_named_mood_on_the_led():
    sat = FakeSatellite()
    mood = make(sat)
    status = mood.set("happy")
    assert sat.calls[-1][:4] == MOODS["happy"][:4]
    assert status["mood"] == "happy" and status["base"] == "happy"
    assert status["flash"] is None and status["sets"] == 1


def test_init_paints_the_base_mood_immediately():
    sat = FakeSatellite()
    mood = make(sat, resync_s=3600)
    mood.init()
    assert sat.calls[-1][:4] == MOODS["idle"][:4]
    mood.shutdown()


def test_unknown_mood_is_rejected():
    with pytest.raises(ValueError):
        make().set("grumpy")
    with pytest.raises(ValueError):
        make().set_color(1, 2, 3, effect="rainbow")


def test_flash_layers_over_base_and_reverts():
    sat = FakeSatellite()
    mood = make(sat)
    mood.set("idle")
    status = mood.flash("heard", 30)
    assert status["mood"] == "heard" and status["base"] == "idle"
    assert status["flash"]["name"] == "heard"
    assert 0 < status["flash"]["remainingS"] <= 30
    mood._end_flash()
    assert mood.status()["mood"] == "idle"
    assert sat.calls[-1][:3] == MOODS["idle"][:3]
    mood.shutdown()


def test_events_map_to_base_or_flash():
    sat = FakeSatellite()
    mood = make(sat)
    mood.on_event("leash.warn", {})
    assert mood.status()["base"] == "warn"
    mood.on_event("voice.phrase", {"intent": "sit"})
    assert mood.status()["mood"] == "heard" and mood.status()["base"] == "warn"
    mood.on_event("vision.clear", {})
    assert mood.status()["mood"] == "warn"
    mood.on_event("nothing.known", {})
    assert mood.status()["lastEvent"] == "vision.clear"
    mood.shutdown()


def test_every_event_mood_exists():
    for mood, _seconds in EVENT_MOODS.values():
        assert mood is None or mood in MOODS


def test_custom_colour_becomes_base():
    sat = FakeSatellite()
    mood = make(sat)
    status = mood.set_color(10, 20, 30, effect="blink", period_ms=400, brightness=99)
    assert sat.calls[-1] == (10, 20, 30, "blink", 400, 99)
    assert status["mood"] == "custom" and status["color"]["periodMs"] == 400


def test_satellite_failure_is_recorded():
    mood = make(FakeSatellite(fail=True))
    status = mood.set("happy")
    assert status["failures"] == 1 and "offline" in status["lastError"]


def test_resync_repaints_a_rebooted_satellite():
    sat = FakeSatellite()
    mood = make(sat)
    mood.set("alert")
    sat.shown = {"r": 0, "g": 0, "b": 0, "effect": "off"}   # satellite rebooted
    mood._resync_once()
    assert sat.calls[-1][:4] == MOODS["alert"][:4]
    calls = len(sat.calls)
    mood._resync_once()
    assert len(sat.calls) == calls                            # already in sync


def test_disabled_without_satellite():
    mood = make(FakeSatellite(enabled=False))
    assert mood.enabled is False
    mood.on_event("leash.lost", {})
    assert mood.status()["sets"] == 0
    assert mood.set("happy")["enabled"] is False
