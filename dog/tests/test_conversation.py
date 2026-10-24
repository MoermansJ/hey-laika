"""Conversation turns: wake -> sit -> listen -> LLM router -> behavior and/or
speech, with every collaborator faked (ears, mood, mouth, binder, store,
LLM) so a turn runs in milliseconds and deterministically."""
import threading
import time

import pytest

from app.conversation import (ANSWER_TOOL, DEFAULT_INTRODUCTION, DEFAULT_REPLY_CHARS,
                              MAX_INTRODUCTION_CHARS, SAY_NO_LLM, SAY_NOT_HEARD,
                              ConversationService, InfoTool, battery_sentence, cap_reply,
                              parse_router_reply)
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


def _battery_tool(pct=54.2, minutes=124):
    return InfoTool("battery", "say the battery level",
                    lambda: battery_sentence(lambda: {"battery": pct, "minutesLeft": minutes}),
                    keywords=r"\bbatter(y|ies)\b")


def _service(ears=None, mouth=None, llm=None, beeps=None, info_tools=None):
    init_db()
    binder = FakeBinder()
    svc = ConversationService(ears or FakeEars(), FakeMood(), mouth or FakeMouth(), binder,
                              FakeStore(), llm or FakeLlm(),
                              beep=(beeps.append if beeps is not None else None),
                              info_tools=info_tools)
    svc.warm_up = lambda: None            # tests count LLM calls; no warm-up call
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
    assert as_json is True and 'The user said: "what is the capital of France"' in prompt
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
    svc.set_prompt('The user said: "%s"\nRespond to exactly what the user said. Be concise and brief.', 320)


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


def test_battery_question_is_answered_from_live_state_without_the_llm():
    llm = FakeLlm()
    svc, binder = _service(llm=llm, info_tools=[_battery_tool()])
    svc.start("what's your battery level", source="text")
    _finish(svc)
    assert llm.calls == [] and svc.mouth.said == ["My battery level is 54 percent. About 2 hours and 4 minutes left."]
    assert svc.mouth.played == ["positive_bark"] * 3
    turn = svc.turns(1)[0]
    assert turn["tool"] == "battery" and turn["llmS"] == 0.0 and svc.stats["infoAnswers"] == 1
    assert not any(e == "voice.intent" for e, _ in binder.events)
    assert any(t["name"] == "battery" and t["kind"] == "info" for t in svc.status()["tools"])


def test_llm_may_pick_an_info_tool_too():
    llm = FakeLlm('{"tool": "battery", "say": "Let me check."}')
    svc, _ = _service(llm=llm, info_tools=[_battery_tool(pct=9, minutes=None)])
    svc.start("how much juice have you got left", source="text")
    _finish(svc)
    assert len(llm.calls) == 1 and '"battery"' in llm.calls[0][1]
    assert svc.mouth.said == ["My battery level is 9 percent."]


def test_battery_sentence_handles_missing_readings():
    assert battery_sentence(lambda: {"battery": None}) == "I don't know my battery level right now."
    assert battery_sentence(lambda: {"battery": 80, "minutesLeft": 45}) == "My battery level is 80 percent. About 45 minutes left."
    assert battery_sentence(lambda: {"battery": 100, "minutesLeft": 250}) == "My battery level is 100 percent. About 4 hours left."


def test_cap_reply_cuts_at_a_sentence():
    text = "First sentence here. Second sentence follows! Third one is long " + "x" * 300
    out = cap_reply(text, 60)
    assert out == "First sentence here. Second sentence follows!"
    assert cap_reply("short", 60) == "short"


def test_parse_router_reply_tolerates_prose_and_bad_json():
    assert parse_router_reply('Sure: {"tool": "sit", "say": "Ok"}', {"sit", "answer"}) == ("sit", "Ok")
    assert parse_router_reply('{"tool": "dance", "say": "Ok"}', {"sit", "answer"}) == ("answer", "Ok")
    assert parse_router_reply("Paris is the capital.", {"answer"}) == ("answer", "Paris is the capital.")


# ---- AGENT-15: orchestrator agent tools in the stationary assistant ---------

class FakeAgent:
    enabled = True

    def __init__(self, tools=None, accept=True):
        self._tools = tools if tools is not None else [
            {"name": "look_upward", "description": "Face upward", "category": "postural"},
            {"name": "sit", "description": "Sit down", "category": "postural"}]
        self.accept = accept
        self.runs = []

    def tools(self):
        return list(self._tools)

    def run(self, tool, goal=None):
        self.runs.append((tool, goal))
        if self.accept:
            return {"decisionId": "d-1", "goal": goal, "tools": [tool],
                    "results": [{"tool": tool, "status": "queued"}], "accepted": True,
                    "message": None}
        return {"decisionId": "d-1", "goal": goal, "tools": [tool],
                "results": [{"tool": tool, "status": "rejected", "message": "cooldown"}],
                "accepted": False, "message": "cooldown"}

    def status(self):
        return {"enabled": True}


def _agent_service(llm, agent):
    init_db()
    binder = FakeBinder()
    svc = ConversationService(FakeEars(), FakeMood(), FakeMouth(), binder, FakeStore(), llm,
                              agent=agent)
    svc.warm_up = lambda: None
    svc.init()
    return svc, binder


def test_agent_tools_are_offered_to_the_router_without_shadowing_voice_intents():
    agent = FakeAgent()
    svc, _ = _agent_service(FakeLlm(), agent)
    tools = svc._tools()
    kinds = {t["name"]: t["kind"] for t in tools}
    assert kinds["look_upward"] == "agent"
    assert kinds["sit"] == "behavior"                 # the voice.intent binding keeps "sit"
    assert [t["name"] for t in tools].count("sit") == 1
    assert svc.status()["agent"] == {"enabled": True}


def test_agent_tool_choice_is_submitted_through_the_orchestrator():
    agent = FakeAgent()
    svc, binder = _agent_service(FakeLlm('{"tool": "look_upward", "say": "Looking up."}'),
                                 agent)
    svc.start("look up at the ceiling", source="text")
    _finish(svc)
    assert agent.runs == [("look_upward", "look_upward")]
    assert not any(e == "voice.intent" for e, _ in binder.events)
    assert svc.mouth.said == ["Looking up."]
    assert svc.stats["agentRuns"] == 1 and svc.stats["toolRuns"] == 0
    assert svc.turns(1)[0]["tool"] == "look_upward"


def test_rejected_agent_tool_says_so():
    agent = FakeAgent(accept=False)
    svc, _ = _agent_service(FakeLlm('{"tool": "look_upward", "say": "Looking up."}'), agent)
    svc.start("look up", source="text")
    _finish(svc)
    assert svc.mouth.said == ["I can't do that right now."]
    turn = svc.turns(1)[0]
    assert turn["tool"] == "look_upward (rejected)" and turn["error"] == "cooldown"
    assert svc.stats["agentRuns"] == 0


def test_no_agent_tools_when_the_orchestrator_offers_none():
    svc, _ = _agent_service(FakeLlm(), FakeAgent(tools=[]))
    assert all(t["kind"] != "agent" for t in svc._tools())


# ---- "Hey Laika, introduce yourself" ----------------------------------------

def _introduce_service(llm=None):
    """The tool reads the service's own mirror, so it is wired lazily here
    exactly as app.py wires it."""
    holder = {}
    tool = InfoTool("introduce", "introduce yourself: say who you are",
                    lambda: holder["svc"].introduction,
                    keywords=r"introduce (your ?self|her ?self)|tell (me|us) about your ?self"
                             r"|\bwho are you\b|\bwhat are you\b")
    svc, binder = _service(llm=llm or FakeLlm(), info_tools=[tool])
    holder["svc"] = svc
    return svc, binder


def test_introduce_yourself_speaks_the_default_text_without_the_llm():
    llm = FakeLlm()
    svc, binder = _introduce_service(llm)
    svc.start("introduce yourself", source="voice")
    _finish(svc)
    assert llm.calls == []                       # the keyword match skips the router
    assert svc.mouth.said == [DEFAULT_INTRODUCTION]
    assert svc.mouth.played == ["positive_bark"] * 3      # the sound contract holds
    turn = svc.turns(1)[0]
    assert turn["tool"] == "introduce" and turn["llmS"] == 0.0
    assert svc.stats["infoAnswers"] == 1
    assert not any(e == "voice.intent" for e, _ in binder.events)


def test_the_orchestrators_push_replaces_what_she_says():
    svc, _ = _introduce_service()
    view = svc.set_introduction("  I am Mocha,\n a mock dog.  ")
    assert view["introduction"] == "I am Mocha, a mock dog."     # whitespace collapsed
    assert view["source"] == "orchestrator" and view["truncated"] is False
    svc.start("who are you", source="voice")
    _finish(svc)
    assert svc.mouth.said == ["I am Mocha, a mock dog."]


def test_introduction_falls_back_to_the_constant_until_a_push_lands():
    svc, _ = _introduce_service()
    view = svc.introduction_view()
    assert view["introduction"] == DEFAULT_INTRODUCTION and view["source"] == "default"
    # The approved text has to survive the reply cap, or the demo is cut short.
    assert view["truncated"] is False and view["chars"] <= DEFAULT_REPLY_CHARS


def test_introduction_rejects_empty_and_oversized_text():
    svc, _ = _introduce_service()
    for bad in (None, "", "   ", 42):
        with pytest.raises(ValueError):
            svc.set_introduction(bad)
    with pytest.raises(ValueError):
        svc.set_introduction("x" * (MAX_INTRODUCTION_CHARS + 1))
    assert svc.introduction == DEFAULT_INTRODUCTION          # nothing was applied


def test_introduction_view_flags_text_the_reply_cap_would_cut():
    svc, _ = _introduce_service()
    svc.set_introduction("One. " + "Long sentence that keeps going. " * 20)
    view = svc.introduction_view()
    assert view["truncated"] is True and view["spokenChars"] < view["chars"]


def test_llm_may_pick_the_introduce_tool_for_a_phrasing_the_pattern_misses():
    llm = FakeLlm('{"tool": "introduce", "say": "Let me think."}')
    svc, _ = _introduce_service(llm)
    svc.start("go on then, say a bit about yourself for the guests", source="text")
    _finish(svc)
    assert len(llm.calls) == 1
    assert svc.mouth.said == [DEFAULT_INTRODUCTION]          # the tool's text, not the say
