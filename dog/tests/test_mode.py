"""Operating mode switching: which of conversation/eyes/arbiter get turned
on or off per mode, with every collaborator faked so a switch is checked
without a real arbiter thread or hardware."""
import pytest

from app.behavior_store import PRIORITY_LIFECYCLE
from app.mode import ModeService


class FakeArbiter:
    def __init__(self):
        self.submitted = []
        self.stopped = 0

    def submit(self, name, source="manual", priority=2, cause=None,
               suppress_avoidance=False):
        self.submitted.append((name, source, priority, cause))
        return {"status": "executing"}

    def stop_current(self):
        self.stopped += 1
        return {"status": "idle"}


class FakeConversation:
    def __init__(self):
        self.enabled = True


class FakeEyes:
    def __init__(self, configured=True):
        self.calls = []
        self.configured = configured

    def set_enabled(self, enabled):
        if not self.configured:
            raise RuntimeError("SATELLITE_HOST is not set")
        self.calls.append(enabled)


class FakeEventBinder:
    def __init__(self):
        self.triggered = []

    def trigger(self, event, data=None):
        self.triggered.append((event, data))
        return []


class FakeExplorer:
    def __init__(self):
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1
        return True

    def stop(self):
        self.stops += 1
        return True


class FakeHandInput:
    def __init__(self):
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1
        return True

    def stop(self):
        self.stops += 1
        return True


class FakeBehaviorStore:
    def __init__(self):
        self.idle_enabled = {"idle_sit": True, "idle_rest": True}

    def set_binding_enabled(self, event, behavior, enabled):
        assert event == "idle.timeout"
        self.idle_enabled[behavior] = enabled


def build():
    arbiter = FakeArbiter()
    conversation = FakeConversation()
    eyes = FakeEyes()
    event_binder = FakeEventBinder()
    behavior_store = FakeBehaviorStore()
    explorer = FakeExplorer()
    hand_input = FakeHandInput()
    mode = ModeService(arbiter, conversation, eyes, event_binder, behavior_store,
                       explorer, hand_input)
    return (mode, arbiter, conversation, eyes, event_binder, explorer, hand_input,
            behavior_store)


def test_given_a_fresh_service_when_asked_then_the_default_mode_is_stationary():
    mode, *_ = build()

    assert mode.status()["mode"] == "stationary"


def test_given_the_current_mode_when_reselected_then_nothing_is_reapplied():
    mode, arbiter, _, eyes, event_binder, explorer, hand_input, behavior_store = build()

    mode.set_mode("stationary")  # already the default; this must be a no-op

    assert arbiter.submitted == []
    assert eyes.calls == []
    assert event_binder.triggered == []
    assert explorer.starts == 0 and explorer.stops == 0
    assert hand_input.starts == 0 and hand_input.stops == 0
    assert behavior_store.idle_enabled == {"idle_sit": True, "idle_rest": True}


def test_given_stationary_when_selected_then_she_sits_once_and_nothing_moves_her_after():
    mode, arbiter, conversation, eyes, event_binder, explorer, hand_input, behavior_store = build()

    mode.set_mode("roaming")  # move off the default first
    mode.set_mode("stationary")

    assert conversation.enabled is True
    assert eyes.calls[-1] is True
    assert arbiter.submitted[-1][0] == "idle_sit"
    assert arbiter.submitted[-1][2] == PRIORITY_LIFECYCLE
    assert event_binder.triggered[-1] == ("mode.changed", {"mode": "stationary"})
    assert explorer.stops == 1   # stopped on the way out of roaming
    assert hand_input.starts == 0   # never entered phone mode
    # No autonomous movement after the one-time sit: the idle ladder (sit/rest
    # ticking) is silenced too, not just the orchestrator's personality loop.
    assert behavior_store.idle_enabled == {"idle_sit": False, "idle_rest": False}


def test_given_roaming_when_selected_then_listening_stays_on_and_the_explorer_starts():
    mode, arbiter, conversation, eyes, _, explorer, hand_input, behavior_store = build()

    mode.set_mode("roaming")

    assert conversation.enabled is True
    assert eyes.calls[-1] is True
    assert arbiter.submitted == []
    assert explorer.starts == 1
    assert hand_input.starts == 0   # never entered phone mode
    assert behavior_store.idle_enabled == {"idle_sit": True, "idle_rest": True}


def test_given_fruitfly_when_selected_then_conversation_and_eyes_are_cut_and_the_arbiter_is_freed():
    mode, arbiter, conversation, eyes, event_binder, explorer, hand_input, behavior_store = build()

    mode.set_mode("roaming")
    mode.set_mode("fruitfly")

    assert conversation.enabled is False
    assert eyes.calls[-1] is False
    assert arbiter.stopped == 1
    assert event_binder.triggered[-1] == ("mode.changed", {"mode": "fruitfly"})
    assert explorer.stops == 1   # stopped on the way out of roaming
    assert hand_input.starts == 0   # never entered phone mode
    # Stubbed: nothing drives her yet, so nothing should nudge her either.
    assert behavior_store.idle_enabled == {"idle_sit": False, "idle_rest": False}


def test_given_phone_when_selected_then_conversation_and_eyes_are_cut_and_hand_input_starts():
    mode, arbiter, conversation, eyes, event_binder, explorer, hand_input, behavior_store = build()

    mode.set_mode("roaming")
    mode.set_mode("phone")

    assert conversation.enabled is False
    assert eyes.calls[-1] is False
    assert event_binder.triggered[-1] == ("mode.changed", {"mode": "phone"})
    assert explorer.stops == 1   # stopped on the way out of roaming
    assert hand_input.starts == 1


def test_given_phone_when_left_then_hand_input_stops():
    mode, arbiter, conversation, eyes, event_binder, explorer, hand_input, behavior_store = build()

    mode.set_mode("phone")
    mode.set_mode("stationary")

    assert hand_input.starts == 1
    assert hand_input.stops == 1


def test_given_an_unknown_mode_when_selected_then_it_is_rejected():
    mode, *_ = build()

    with pytest.raises(ValueError):
        mode.set_mode("sleepwalk")


def test_given_no_satellite_configured_when_switching_modes_then_it_does_not_crash():
    arbiter = FakeArbiter()
    conversation = FakeConversation()
    eyes = FakeEyes(configured=False)   # e.g. Mocha, the mock GUI fixture
    event_binder = FakeEventBinder()
    behavior_store = FakeBehaviorStore()
    explorer = FakeExplorer()
    hand_input = FakeHandInput()
    mode = ModeService(arbiter, conversation, eyes, event_binder, behavior_store,
                       explorer, hand_input)

    mode.set_mode("roaming")
    mode.set_mode("stationary")
    mode.set_mode("fruitfly")
    mode.set_mode("phone")

    assert mode.status()["mode"] == "phone"
    assert eyes.calls == []
