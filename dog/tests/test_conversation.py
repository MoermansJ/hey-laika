"""Conversation turns: wake -> sit -> listen -> LLM router -> behavior and/or
speech, with every collaborator faked (ears, mood, mouth, binder, store,
LLM) so a turn runs in milliseconds and deterministically."""
import threading
import time

import pytest

from app.conversation import (ANSWER_TOOL, SAY_NO_LLM, SAY_NOT_HEARD, ConversationService,
                              cap_reply, parse_router_reply)
from app.models import init_db


class FakeEars:
    def __init__(self, heard="what is the capital of France", latency=0.7):
        self.heard = heard
        self.latency = latency
        self.muted_for = None
        self.listen_calls = []

    def listen(self, window_s, max_utterance_s):
        self.listen_calls.append((window_s, max_utterance_s))
        if self.heard is None:
            return None, None
        return self.heard, self.latency

    def mute(self, seconds):
        self.muted_for = seconds


class FakeMood:
    def __init__(self):
        self.calls = []

    def hold(self, mood): self.calls.append(("hold", mood))
    def release(self): self.calls.append(("release", None))
    def flash(self, mood, seconds): self.calls.append(("flash", mood))


class FakeMouth:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.said = []
        self.played = []
        self.stopped = 0

    def say(self, text):
        self.said.append(text)
        return {"seconds": 1.5, "chunks": 12, "error": None}

    def play_sound(self, name):
        self.played.append(name)
        return {"seconds": 0.7, "chunks": 6, "error": None}

    def stop(self):
        self.stopped += 1
        return True


class FakeBinder:
    def __init__(self):
        self.listeners = []
        self.events = []

    def trigger(self, event, data=None):
        self.events.append((event, data or {}))
        return []


class FakeStore:
    def __init__(self):
        self._bindings = [
            {"event": "voice.intent", "filter": {"intent": "sit"}, "behavior": "idle_sit"},
            {"event": "voice.intent", "filter": {"intent": "greet"}, "behavior": "startup_greeting"},
        ]

    def bindings(self, event=None, enabled_only=True):
        return [b for b in self._bindings if event is None or b["event"] == event]

    def behavior(self, name):
        return {"name": name, "description": f"{name} description"}


class FakeLlm:
    def __init__(self, reply='{"tool": "answer", "say": "Paris."}', error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def __call__(self, prompt, system, as_json):
        self.calls.append((prompt, system, as_json))
        return (None, self.error) if self.error else (self.reply, None)


def _service(ears=None, mouth=None, llm=None, beeps=None):
    init_db()
    binder = FakeBinder()
    svc = ConversationService(ears or FakeEars(), FakeMood(), mouth or FakeMouth(), binder,
                              FakeStore(), llm or FakeLlm(),
                              beep=(beeps.append if beeps is not None else None))
    svc.init()
    return svc, binder


def _finish(svc, timeout=5.0):
    deadline = time.time() + timeout
    while svc.state != "idle" and time.time() < deadline:
        time.sleep(0.01)
    if svc._thread:
        svc._thread.join(timeout)
    assert svc.state == "idle"


def test_wake_without_command_listens_routes_and_speaks():
    beeps = []
    ears = FakeEars()
    llm = FakeLlm()
    svc, binder = _service(ears=ears, llm=llm, beeps=beeps)
    svc.on_event("voice.wake", {"text": "Hey Laika.", "command": "", "latencyS": 0.6})
    _finish(svc)
    assert ears.listen_calls == [(svc.listen_s, 12.0)]
    assert [e for e, _ in binder.events] == ["conversation.listen"]     # sat; the answer is not a tool
    assert svc.mouth.said == ["Paris."]
    assert ears.muted_for is not None and ears.muted_for > 0
    # The sound contract: one bark on pick-up, two before the terminal step.
    assert svc.mouth.played == ["positive_bark"] * 3 and beeps == []
    prompt, system, as_json = llm.calls[0]
    assert as_json is True and "User message: what is the capital of France" in prompt
    assert '"sit"' in system and '"greet"' in system and f'"{ANSWER_TOOL}"' in system
    holds = [m for kind, m in svc.mood.calls if kind == "hold"]
    assert holds == ["listening", "thinking", "speaking"] and svc.mood.calls[-1][0] == "release"
    turn = svc.turns(1)[0]
    assert turn["heard"] == "what is the capital of France" and turn["said"] == "Paris."
    assert turn["tool"] == ANSWER_TOOL and turn["whisperS"] == 0.7 and turn["llmS"] is not None


def test_same_utterance_request_skips_listening():
    ears = FakeEars()
    svc, binder = _service(ears=ears)
    svc.on_event("voice.wake", {"text": "Hey Laika, what is the capital of France?",
                                "command": "what is the capital of France", "latencyS": 0.9})
    _finish(svc)
    assert ears.listen_calls == []
    holds = [m for kind, m in svc.mood.calls if kind == "hold"]
    assert holds == ["thinking", "speaking"]
    assert svc.turns(1)[0]["heard"] == "what is the capital of France"


def test_tool_choice_fires_voice_intent_and_says_confirmation():
    llm = FakeLlm('{"tool": "sit", "say": "Sitting down."}')
    svc, binder = _service(llm=llm)
    svc.start("could you sit please", source="text")
    _finish(svc)
    assert ("voice.intent", {"intent": "sit", "text": "could you sit please"}) in binder.events
    assert svc.mouth.said == ["Sitting down."]
    assert svc.mouth.played == ["positive_bark"] * 3
    # Two barks come before the behavior runs: the last bark precedes the intent event.
    assert svc.turns(1)[0]["tool"] == "sit" and svc.stats["toolRuns"] == 1


def test_unknown_tool_name_becomes_an_answer():
    llm = FakeLlm('{"tool": "backflip", "say": "I cannot do that yet."}')
    svc, binder = _service(llm=llm)
    svc.start("do a backflip", source="text")
    _finish(svc)
    assert not any(e == "voice.intent" for e, _ in binder.events)
    assert svc.turns(1)[0]["tool"] == ANSWER_TOOL and svc.mouth.said == ["I cannot do that yet."]


def test_nothing_said_in_the_window_beeps_and_stays_quiet():
    beeps = []
    svc, binder = _service(ears=FakeEars(heard=None), beeps=beeps)
    svc.start(None)
    _finish(svc)
    assert svc.mouth.played == ["positive_bark"] and beeps == ["timeout"] and svc.mouth.said == []
    assert svc.turns(1)[0]["heard"] == "" and svc.turns(1)[0]["tool"] is None


def test_empty_transcript_apologises():
    svc, _ = _service(ears=FakeEars(heard=""))
    svc.start(None)
    _finish(svc)
    assert svc.mouth.said == [SAY_NOT_HEARD]


def test_llm_failure_is_spoken_and_flashes_warn():
    svc, _ = _service(llm=FakeLlm(error="Ollama unreachable"))
    svc.start("hello there", source="text")
    _finish(svc)
    assert svc.mouth.said == [SAY_NO_LLM]
    assert ("flash", "warn") in svc.mood.calls
    assert svc.turns(1)[0]["error"] == "Ollama unreachable" and svc.stats["failures"] == 1


def test_speaker_missing_still_records_the_reply_and_barks_on_the_buzzer():
    beeps = []
    svc, _ = _service(mouth=FakeMouth(enabled=False), beeps=beeps)
    svc.start("hello there", source="text")
    _finish(svc)
    assert svc.mouth.said == [] and svc.turns(1)[0]["said"] == "Paris."
    assert beeps == ["beep_wake_word"] * 3


def test_memory_rides_along_within_the_gap():
    llm = FakeLlm()
    svc, _ = _service(llm=llm)
    svc.start("first question", source="text")
    _finish(svc)
    svc.start("second question", source="text")
    _finish(svc)
    prompt = llm.calls[1][0]
    assert "Earlier in this conversation" in prompt and "User: first question" in prompt
    assert "You: Paris." in prompt


def test_prompt_setting_persists_and_validates():
    svc, _ = _service()
    view = svc.set_prompt("Answer as a pirate. %s", 200)
    assert view["prompt"].startswith("Answer as a pirate") and view["replyChars"] == 200
    fresh, _ = _service()
    assert fresh.prompt == "Answer as a pirate. %s" and fresh.reply_chars == 200
    with pytest.raises(ValueError):
        svc.set_prompt("   ")
    with pytest.raises(ValueError):
        svc.set_prompt(reply_chars=5)
    svc.set_prompt("You are a helpful assistant, the user wants help with the message "
                   "appended at the end of this prompt. Instructions: Be concise and "
                   "brief --- User message: %s", 320)


def test_busy_service_ignores_a_second_wake_but_cancel_stops_speech():
    slow = FakeEars(heard="slow question")
    started = threading.Event()

    class SlowLlm(FakeLlm):
        def __call__(self, prompt, system, as_json):
            started.set()
            time.sleep(0.3)
            return super().__call__(prompt, system, as_json)

    svc, binder = _service(ears=slow, llm=SlowLlm())
    svc.start(None)
    started.wait(2)
    assert svc.state == "thinking"
    svc.start(None)                       # ignored while thinking
    assert len(slow.listen_calls) == 1
    _finish(svc)
    svc.start("another", source="text")
    _finish(svc)
    assert svc.cancel()["state"] == "idle"


def test_cap_reply_cuts_at_a_sentence():
    text = "First sentence here. Second sentence follows! Third one is long " + "x" * 300
    out = cap_reply(text, 60)
    assert out == "First sentence here. Second sentence follows!"
    assert cap_reply("short", 60) == "short"


def test_parse_router_reply_tolerates_prose_and_bad_json():
    assert parse_router_reply('Sure: {"tool": "sit", "say": "Ok"}', {"sit", "answer"}) == ("sit", "Ok")
    assert parse_router_reply('{"tool": "dance", "say": "Ok"}', {"sit", "answer"}) == ("answer", "Ok")
    assert parse_router_reply("Paris is the capital.", {"answer"}) == ("answer", "Paris is the capital.")
