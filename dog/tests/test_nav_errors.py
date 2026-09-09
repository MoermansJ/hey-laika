"""Two-tier error handling and the error state, with fakes for the body."""
import pytest

from app.models import init_db
from app.nav_errors import (PROMPT, ErrorHandler, ErrorState, RecoverableError,
                            UnrecoverableError)


class FakeArbiter:
    def __init__(self):
        self.stopped = 0
        self.submitted = []

    def stop_current(self):
        self.stopped += 1
        return {"stopped": True}

    def submit(self, name, source="manual", priority=2, cause=None, **_):
        self.submitted.append((name, source, priority, cause))
        return {"status": "executing"}


class FakeMood:
    def __init__(self):
        self.held = None
        self.released = 0

    def hold(self, mood):
        self.held = mood

    def release(self):
        self.released += 1


def setup_module(module):
    init_db()


def test_three_strikes_escalate_and_a_clean_check_resets():
    escalated = []
    waits = []
    handler = ErrorHandler(on_escalate=lambda e, i: escalated.append((e, i)),
                           persist=False, sleep=waits.append)
    err = RecoverableError("map_contradiction", "wall where floor was", {"cx": 1})
    assert handler.handle(err) == {"action": "retry", "attempt": 1,
                                   "kind": "map_contradiction", "remaining": 2}
    assert handler.handle(err)["attempt"] == 2
    assert waits == [0.3, 0.3]
    handler.clear("map_contradiction")
    assert handler.stats["silentRecoveries"] == 1
    assert handler.handle(err)["attempt"] == 1
    handler.handle(err)
    out = handler.handle(err)
    assert out["action"] == "escalated" and out["retries"] == 3
    assert len(escalated) == 1
    assert isinstance(escalated[0][0], UnrecoverableError)
    assert "persisted 3 times" in escalated[0][0].message
    assert handler.counts["map_contradiction"] == 0
    tiers = [row["tier"] for row in handler.history()]
    assert tiers[0] == "unrecoverable" and tiers.count("recoverable") == 5


def test_unrecoverable_goes_straight_to_the_error_state():
    escalated = []
    handler = ErrorHandler(on_escalate=lambda e, i: escalated.append(e), persist=False)
    out = handler.handle(UnrecoverableError("lost", "drift too large"))
    assert out["action"] == "escalated" and escalated[0].kind == "lost"
    assert handler.stats == {"recoverable": 0, "escalated": 1, "unrecoverable": 1,
                             "silentRecoveries": 0}


def test_history_persists_to_the_database_with_resolution():
    handler = ErrorHandler(persist=True)
    handler.init()
    out = handler.handle(UnrecoverableError("action_failed", "kwkF 3 refused",
                                            {"command": "kwkF 3"}))
    error_id = out["errorId"]
    assert isinstance(error_id, int) and error_id > 0
    handler.resolve(error_id, "manual", note="carried her back")
    row = handler.history(1)[0]
    assert row["id"] == error_id and row["resolution"] == "manual"
    assert row["note"] == "carried her back" and row["context"] == {"command": "kwkF 3"}


def test_error_state_pauses_lights_speaks_and_waits():
    arbiter, mood, spoken, events = FakeArbiter(), FakeMood(), [], []
    handler = ErrorHandler(persist=False)
    state = ErrorState(arbiter, mood=mood, speak=spoken.append,
                       trigger=lambda e, p=None: events.append((e, p)),
                       handler=handler, speak_async=False)
    error = UnrecoverableError("map_contradiction", "wall here", {"cells": [1]})
    snapshot = state.enter(error, 7)
    assert state.blocked and snapshot["prompt"] == PROMPT
    assert arbiter.stopped == 1
    assert arbiter.submitted[0][0] == "error_halt" and arbiter.submitted[0][2] == 1
    assert mood.held == "error"
    assert spoken == [PROMPT]
    assert events[0] == ("nav.error", {"kind": "map_contradiction", "message": "wall here",
                                       "errorId": 7})
    again = state.enter(UnrecoverableError("lost", "also lost"), 8)
    assert again["id"] == 7 and state.active["also"][0]["kind"] == "lost"
    assert state.status()["active"]["waitingS"] >= 0

    with pytest.raises(ValueError):
        state.respond("ignore")
    applied = []
    state.on_resolve = lambda choice, err: applied.append((choice, err["id"])) or {"ok": 1}
    out = state.respond("trust_map", note="the shelf moved")
    assert out["choice"] == "trust_map" and out["applied"] == {"ok": 1}
    assert applied == [("trust_map", 7)]
    assert not state.blocked and mood.released == 1
    assert events[-1][0] == "nav.error.resolved"
    with pytest.raises(LookupError):
        state.respond("manual")


def test_speech_failure_is_counted_not_raised():
    def broken(_text):
        raise RuntimeError("no speaker")
    state = ErrorState(FakeArbiter(), speak=broken, speak_async=False)
    state.enter(UnrecoverableError("lost", "x"))
    assert state.stats["speechErrors"] == 1 and state.blocked
