"""Conversation: "Hey Laika" -> sit and listen -> transcript -> LLM router ->
a behavior and/or a spoken reply (CONVERSATION_BRIEF.md).

One turn is a small state machine run on its own thread:

  idle -> listening -> thinking -> speaking -> idle

The router is the LLM itself, constrained to JSON, choosing one tool from a
menu that is generated live from the framework's bindings on the event
`voice.intent`. So the trigger -> action table the console already edits is
also the voice command vocabulary: add a binding, and the next "Hey Laika"
can pick it. When no tool fits, the tool is "answer" and the reply is spoken.
A future planning agent replaces `route()` and keeps the same contract.

Sound contract: one bark when she starts taking the request (recording, or a
same-utterance request accepted), two barks before the terminal step, which
is running the chosen behavior or speaking the answer. Barks are speaker
clips; the buzzer is the fallback without a speaker. Soft buzzer chirps mark
a listening window nobody spoke into.
"""
import json
import logging
import re
import threading
import time
from datetime import datetime

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, Setting, engine, iso_utc, utcnow

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = ("You are a helpful assistant, the user wants help with the message "
                  "appended at the end of this prompt. Instructions: Be concise and "
                  "brief --- User message: %s")
BREVITY = " Answer in one or two short spoken sentences, no lists, no markdown."
ROUTER_SYSTEM = (
    "You route a spoken request addressed to a small robot dog. Choose exactly one "
    "tool from the list and reply with JSON only, no prose: "
    '{{"tool": "<name>", "say": "<one short spoken sentence>"}}.\n'
    "Tools:\n{tools}\n"
    "Use \"answer\" when no tool fits and put the whole answer in \"say\": "
    "one or two short spoken sentences, no lists, no markdown."
)
ANSWER_TOOL = "answer"
SETTINGS_KEY = "conversation.prompt"
DEFAULT_REPLY_CHARS = 320
DEFAULT_LISTEN_S = 8.0
LISTEN_MAX_UTTERANCE_S = 12.0
SPEAK_TAIL_S = 0.6
MEMORY_TURNS = 3
MEMORY_GAP_S = 300.0
TURNS_KEPT = 200

BARK_SOUND = "positive_bark"
BARK_FALLBACK_BEEP = "beep_wake_word"
BARK_GAP_S = 0.15

SAY_NOT_HEARD = "I didn't catch that."
SAY_NO_LLM = "I can't think right now."
SAY_ACK = "Okay."


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    source: Mapped[str] = mapped_column(String(16), default="voice")
    heard: Mapped[str] = mapped_column(Text, default="")
    tool: Mapped[str] = mapped_column(String(64), nullable=True)
    said: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, nullable=True)
    whisper_s: Mapped[float] = mapped_column(Float, nullable=True)
    llm_s: Mapped[float] = mapped_column(Float, nullable=True)
    speak_s: Mapped[float] = mapped_column(Float, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "at": iso_utc(self.at), "source": self.source,
                "heard": self.heard, "tool": self.tool, "said": self.said,
                "error": self.error, "whisperS": self.whisper_s,
                "llmS": self.llm_s, "speakS": self.speak_s}


def cap_reply(text: str, limit: int) -> str:
    """Cut at a sentence boundary before `limit` characters; playback is real
    time, so every extra sentence is seconds of waiting."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if cut < limit // 3:
        cut = head.rfind(" ")
    return (head[:cut + 1] if cut > 0 else head).strip()


def parse_router_reply(raw: str, tools: set) -> tuple[str, str]:
    """(tool, say) from the model's JSON; anything malformed becomes an answer
    made of whatever text came back."""
    text = (raw or "").strip()
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            tool = str(data.get("tool") or ANSWER_TOOL).strip().lower()
            say = str(data.get("say") or "").strip()
            if tool not in tools:
                tool = ANSWER_TOOL
            return tool, say
        except (ValueError, AttributeError):
            pass
    return ANSWER_TOOL, text.strip("`").strip()


class ConversationService:
    def __init__(self, ears, mood, mouth, binder, store, llm, beep=None,
                 enabled: bool = True, listen_s: float = DEFAULT_LISTEN_S,
                 reply_chars: int = DEFAULT_REPLY_CHARS, clock=time.time):
        self.ears = ears
        self.mood = mood
        self.mouth = mouth
        self.binder = binder
        self.store = store
        self.llm = llm                     # (prompt, system, format_json) -> (text, error)
        self.beep = beep or (lambda pattern: None)
        self.enabled = enabled
        self.listen_s = listen_s
        self.reply_chars = reply_chars
        self._clock = clock
        self._lock = threading.Lock()
        self.state = "idle"
        self.current: dict | None = None
        self.prompt = DEFAULT_PROMPT
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_turn_at = 0.0
        self.stats = {"turns": 0, "toolRuns": 0, "answers": 0, "failures": 0,
                      "lastError": None}

    # -- lifecycle --

    def init(self) -> None:
        Base.metadata.create_all(engine)
        self._load_prompt()
        self.binder.listeners.append(self.on_event)

    # -- entry points --

    def on_event(self, event: str, payload: dict | None = None) -> None:
        """Binder listener: the ears fire voice.wake for a wake phrase whose
        command is not one of the keyword motion intents."""
        if event != "voice.wake" or not self.enabled:
            return
        payload = payload or {}
        self.start(payload.get("command") or None, source="voice",
                   whisper_s=payload.get("latencyS"))

    def start(self, question: str | None, source: str = "voice",
              whisper_s: float | None = None) -> dict:
        """Begin a turn. With a question the listening step is skipped (the
        request came in the same utterance, or was typed)."""
        with self._lock:
            busy = self.state != "idle"
            if busy and self.state == "speaking":
                self._cancel_locked()              # a new wake cuts the reply short
                busy = False
            if busy:
                return self._status_locked()
            self._cancel.clear()
            self.current = {"startedAt": self._clock(), "source": source,
                            "heard": question or "", "tool": None, "said": "",
                            "error": None, "whisperS": whisper_s, "llmS": None,
                            "speakS": None, "barks": 0}
            self.state = "listening" if question is None else "thinking"
            self._thread = threading.Thread(target=self._run, args=(question,), daemon=True)
            self._thread.start()
        return self.status()

    def cancel(self) -> dict:
        with self._lock:
            self._cancel_locked()
        return self.status()

    # -- the turn --

    def _run(self, question: str | None) -> None:
        turn = self.current
        try:
            self.binder.trigger("conversation.listen", {"heard": question or ""})
            self._bark(1, turn)                        # picked up: the request may start
            if question is None:
                self.mood.hold("listening")
                heard, whisper_s = self.ears.listen(self.listen_s, LISTEN_MAX_UTTERANCE_S)
                if self._cancel.is_set():
                    return
                turn["whisperS"] = whisper_s
                if heard is None:                      # nothing said in the window
                    self.beep("timeout")
                    return
                turn["heard"] = heard
                if not heard.strip():
                    self._speak(SAY_NOT_HEARD, turn)
                    return
                question = heard
            self._set_state("thinking")
            self.mood.hold("thinking")
            tools = self._tools()
            started = self._clock()
            raw, error = self.llm(self._router_prompt(question), self._router_system(tools), True)
            turn["llmS"] = round(self._clock() - started, 2)
            if self._cancel.is_set():
                return
            if error or raw is None:
                turn["error"] = error or "empty reply"
                self.stats["failures"] += 1
                self.stats["lastError"] = turn["error"]
                self.mood.flash("warn", 3.0)
                self._speak(SAY_NO_LLM, turn)
                return
            tool, say = parse_router_reply(raw, {t["name"] for t in tools} | {ANSWER_TOOL})
            turn["tool"] = tool
            self._bark(2, turn)                        # terminal step reached
            if self._cancel.is_set():
                return
            if tool != ANSWER_TOOL:
                self.stats["toolRuns"] += 1
                self.binder.trigger("voice.intent", {"intent": tool, "text": question})
                say = say or SAY_ACK
            else:
                self.stats["answers"] += 1
            self._speak(cap_reply(say, self.reply_chars), turn)
        except Exception as exc:
            logger.exception("Conversation turn failed")
            turn["error"] = str(exc)
            self.stats["failures"] += 1
            self.stats["lastError"] = str(exc)
        finally:
            self.stats["turns"] += 1
            self._persist(turn)
            self._last_turn_at = self._clock()
            with self._lock:
                self.mood.release()
                self.state = "idle"
                self.current = None

    def _bark(self, times: int, turn: dict) -> None:
        """The sound contract's cue, on the speaker when there is one. The ears
        are muted for the clip so she does not hear herself bark."""
        turn.setdefault("barks", 0)
        if not getattr(self.mouth, "enabled", False):
            for _ in range(times):
                self.beep(BARK_FALLBACK_BEEP)
            turn["barks"] += times
            return
        for i in range(times):
            try:
                result = self.mouth.play_sound(BARK_SOUND)
                self.ears.mute(float(result.get("seconds") or 0.7) + SPEAK_TAIL_S)
                turn["barks"] += 1
            except Exception as exc:
                turn["error"] = f"speaker: {exc}"
                self.stats["lastError"] = turn["error"]
                return
            if i + 1 < times:
                time.sleep(BARK_GAP_S)

    def _speak(self, text: str, turn: dict) -> None:
        turn["said"] = text
        if not text:
            return
        self._set_state("speaking")
        self.mood.hold("speaking")
        if not getattr(self.mouth, "enabled", False):
            return                                     # console-only reply
        started = self._clock()
        try:
            result = self.mouth.say(text)
            seconds = float(result.get("seconds") or 0.0)
            # The clip keeps playing out of the firmware ring after say()
            # returns; the ears stay muted until it must be over.
            self.ears.mute(max(0.0, seconds - (self._clock() - started)) + SPEAK_TAIL_S)
            turn["speakS"] = round(self._clock() - started, 2)
        except Exception as exc:
            turn["error"] = f"speaker: {exc}"
            self.stats["lastError"] = turn["error"]

    def _set_state(self, state: str) -> None:
        with self._lock:
            self.state = state

    def _cancel_locked(self) -> None:
        self._cancel.set()
        try:
            self.mouth.stop()
        except Exception:
            pass
        self.mood.release()
        self.state = "idle"
        self.current = None

    # -- the router --

    def _tools(self) -> list[dict]:
        tools = []
        for binding in self.store.bindings(event="voice.intent", enabled_only=True):
            name = (binding.get("filter") or {}).get("intent")
            if not name:
                continue
            behavior = self.store.behavior(binding["behavior"]) or {}
            tools.append({"name": str(name).lower(), "behavior": binding["behavior"],
                          "description": behavior.get("description") or binding["behavior"]})
        return tools

    def _router_system(self, tools: list[dict]) -> str:
        lines = [f'- "{t["name"]}": {t["description"]}' for t in tools]
        lines.append(f'- "{ANSWER_TOOL}": answer the question or reply to what was said')
        return ROUTER_SYSTEM.format(tools="\n".join(lines))

    def _router_prompt(self, question: str) -> str:
        memory = self._memory()
        prefix = ("Earlier in this conversation:\n" + "\n".join(memory) + "\n\n") if memory else ""
        try:
            body = self.prompt % question if "%s" in self.prompt else f"{self.prompt}\n{question}"
        except (TypeError, ValueError):
            body = f"{self.prompt}\n{question}"
        return prefix + body + BREVITY

    def _memory(self) -> list[str]:
        if self._clock() - self._last_turn_at > MEMORY_GAP_S:
            return []
        lines = []
        for turn in reversed(self.turns(MEMORY_TURNS)):
            if turn["heard"]:
                lines.append(f"User: {turn['heard']}")
            if turn["said"]:
                lines.append(f"You: {turn['said']}")
        return lines

    # -- prompt setting --

    def set_prompt(self, prompt: str | None = None, reply_chars: int | None = None) -> dict:
        if prompt is not None:
            prompt = prompt.strip()
            if not prompt:
                raise ValueError("prompt must not be empty")
            self.prompt = prompt
        if reply_chars is not None:
            reply_chars = int(reply_chars)
            if not 40 <= reply_chars <= 2000:
                raise ValueError("replyChars must be between 40 and 2000")
            self.reply_chars = reply_chars
        with SessionLocal() as session:
            row = session.get(Setting, SETTINGS_KEY) or Setting(key=SETTINGS_KEY)
            row.value = json.dumps({"prompt": self.prompt, "replyChars": self.reply_chars})
            session.add(row)
            session.commit()
        return self.prompt_view()

    def prompt_view(self) -> dict:
        return {"prompt": self.prompt, "defaultPrompt": DEFAULT_PROMPT,
                "replyChars": self.reply_chars, "brevity": BREVITY.strip()}

    def _load_prompt(self) -> None:
        with SessionLocal() as session:
            row = session.get(Setting, SETTINGS_KEY)
        if row is None:
            return
        try:
            data = json.loads(row.value or "{}")
        except ValueError:
            return
        if data.get("prompt"):
            self.prompt = str(data["prompt"])
        if data.get("replyChars"):
            self.reply_chars = int(data["replyChars"])

    # -- persistence and reporting --

    def _persist(self, turn: dict) -> None:
        try:
            with SessionLocal() as session:
                session.add(ConversationTurn(
                    source=turn["source"], heard=turn["heard"], tool=turn["tool"],
                    said=turn["said"], error=turn["error"], whisper_s=turn["whisperS"],
                    llm_s=turn["llmS"], speak_s=turn["speakS"]))
                session.commit()
                stale = (session.query(ConversationTurn.id)
                         .order_by(ConversationTurn.id.desc()).offset(TURNS_KEPT).all())
                if stale:
                    (session.query(ConversationTurn)
                     .filter(ConversationTurn.id.in_([s.id for s in stale]))
                     .delete(synchronize_session=False))
                    session.commit()
        except Exception:
            logger.exception("Conversation turn not persisted")

    def turns(self, limit: int = 10) -> list[dict]:
        with SessionLocal() as session:
            rows = (session.query(ConversationTurn)
                    .order_by(ConversationTurn.id.desc()).limit(limit).all())
            return [r.to_dict() for r in rows]

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict:
        current = dict(self.current) if self.current else None
        state = self.state
        if current:
            current["elapsedS"] = round(self._clock() - current.pop("startedAt"), 1)
        return {"enabled": self.enabled, "state": state, "current": current,
                "listenS": self.listen_s, "tools": self._tools(),
                **self.prompt_view(), **self.stats}
