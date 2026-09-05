"""Ears: the XIAO ESP32S3 Sense satellite streams 16 kHz mono PCM over UDP;
this module turns it into transcripts and `voice.phrase` events.

Pipeline (VOICE_RELAY_BRIEF.md, build plan step 2):

  UDP packets (4-byte big-endian sequence + int16 PCM)  ->  ring buffer
  -> energy gate segments an utterance (speech above the floor, then
     `silence_s` of quiet, capped at `max_utterance_s`)
  -> transcriber (faster-whisper, CPU int8) in one worker thread
  -> wake gate: the transcript must START with the wake phrase, matched
     fuzzily because "Laika" arrives as Laker / Leica / Lycra / lika
  -> intent keywords -> event_binder.trigger("voice.phrase", {...})
  -> every utterance persists as a Transcript row (provenance: "things the
     owner said"), wake or not.

Wake detection is text-based on purpose: it needs no trained model and
works today; openWakeWord can be slotted in front of the transcriber later
as a cheaper first gate. The transcriber is injectable so tests run without
downloading a model.
"""
import json
import logging
import re
import socket
import struct
import threading
import time
import wave
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import Config
from app.models import Base, SessionLocal, Setting, engine, iso_utc, utcnow

logger = logging.getLogger(__name__)

PACKET_HEADER = struct.Struct(">I")  # sequence number, then int16 LE samples
LEVEL_WINDOW_PACKETS = 50


# Spellings whisper produces for "Laika" (owner's accent + tiny model).
WAKE_VARIANTS = ("laika", "laker", "lika", "leica", "lycra", "lyca", "like a",
                 "like up", "laca", "lakea", "leika", "lyka")
WAKE_LEADERS = ("hey", "hi", "ok", "okay", "yo", "")
WHISPER_PROMPT = "Hey Laika, sit. Hey Laika, come here. Hey Laika, lie down."
PROMPT_TEMPLATE = "{phrase}, sit. {phrase}, come here. {phrase}, lie down."
VOCABULARY_KEY = "ears.vocabulary"
MAX_VOCABULARY = 40
RECORD_MAX_S = 10.0

INTENTS = [
    ("sit", ("sit",)),
    ("rest", ("lie down", "lay down", "rest", "sleep", "go to bed")),
    ("stand", ("stand", "get up", "up")),
    ("come", ("come", "here", "follow")),
    ("stop", ("stop", "stay", "freeze", "halt")),
    ("greet", ("hello", "good dog", "good girl", "who's a good")),
]


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    text: Mapped[str] = mapped_column(Text)
    wake: Mapped[bool] = mapped_column(Boolean, default=False)
    intent: Mapped[str] = mapped_column(String(32), nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    latency_s: Mapped[float] = mapped_column(Float, default=0.0)

    def to_dict(self) -> dict:
        return {"id": self.id, "at": iso_utc(self.at),
                "text": self.text, "wake": self.wake, "intent": self.intent,
                "durationS": round(self.duration_s, 2),
                "latencyS": round(self.latency_s, 2)}


# ---- wake phrase + intent ----------------------------------------------------

def collapse_repeats(text: str, max_repeats: int = 2) -> str:
    """Whisper sometimes loops ("Hello. Hello. Hello. ..." for seconds of
    audio); keep at most `max_repeats` consecutive copies of any 1-4 word
    phrase."""
    out: list[str] = []
    for word in text.split():
        out.append(word)
        for n in range(1, 5):
            if len(out) < n * (max_repeats + 1):
                break
            phrase = out[-n:]
            copies = (out[-n * (k + 1):len(out) - n * k] for k in range(max_repeats + 1))
            if all(copy == phrase for copy in copies):
                del out[-n:]
                break
    return " ".join(out)


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z' ]+", " ", text.lower()).split())


def match_wake(text: str, phrase: str = "hey laika",
               variants: tuple | list = ()) -> str | None:
    """Return the command part after the wake phrase, or None if the
    utterance did not start with it. Tolerates whisper's spellings."""
    words = _normalize(text)
    if not words:
        return None
    # The configured phrase is one accepted spelling; whisper's variants of
    # the name are accepted after any of the usual leaders.
    exact = _normalize(phrase)
    if words == exact or words.startswith(exact + " "):
        return words[len(exact):].strip(" ,.")
    for lead in WAKE_LEADERS:
        for variant in (*WAKE_VARIANTS, *variants):
            head = f"{lead} {variant}".strip()
            if words == head or words.startswith(head + " "):
                return words[len(head):].strip(" ,.")
    return None


def detect_intent(command: str) -> str | None:
    for intent, keys in INTENTS:
        if any(key in command for key in keys):
            return intent
    return None


# ---- transcribers -------------------------------------------------------------

class WhisperTranscriber:
    """faster-whisper on CPU; loads lazily on the first utterance."""

    def __init__(self, model_name: str, download_root: str | None = None):
        self.model_name = model_name
        self.download_root = download_root
        self.prompt = WHISPER_PROMPT
        self._model = None
        self.loaded = False

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            started = time.time()
            self._model = WhisperModel(self.model_name, device="cpu",
                                       compute_type="int8",
                                       download_root=self.download_root)
            self.loaded = True
            logger.info("Whisper '%s' loaded in %.1fs", self.model_name,
                        time.time() - started)
        return self._model

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        import numpy as np

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        audio -= audio.mean()
        if sample_rate != 16000:
            step = sample_rate / 16000.0
            idx = (np.arange(int(len(audio) / step)) * step).astype(np.int64)
            audio = audio[idx]
        segments, _info = self._load().transcribe(
            audio, language="en", beam_size=1, vad_filter=True,
            initial_prompt=self.prompt, condition_on_previous_text=False)
        return collapse_repeats(" ".join(s.text.strip() for s in segments).strip())


# ---- the service --------------------------------------------------------------

class EarsService:
    def __init__(self, event_binder, transcriber=None,
                 sample_rate: int = 16000, udp_port: int = 5005,
                 wake_phrase: str = "hey laika", energy_floor: int = 300,
                 silence_s: float = 0.8, max_utterance_s: float = 8.0,
                 min_utterance_s: float = 0.4, clock=time.time):
        self.binder = event_binder
        self.transcriber = transcriber
        self.sample_rate = sample_rate
        self.udp_port = udp_port
        self.wake_phrase = wake_phrase
        self.energy_floor = energy_floor
        self.silence_s = silence_s
        self.max_utterance_s = max_utterance_s
        self.min_utterance_s = min_utterance_s
        self._clock = clock

        self._lock = threading.Lock()
        self._utterance = bytearray()
        self._speaking = False
        self._last_voice_at = 0.0
        self._utterance_started = 0.0
        self._queue: deque = deque()
        self._levels: deque = deque(maxlen=LEVEL_WINDOW_PACKETS)
        self._level_rms = 0.0
        self._record: bytearray | None = None
        self._mute_until = 0.0
        self._listen: dict | None = None     # {"deadline", "max", "event", "text", "latency"}
        self.default_wake_phrase = wake_phrase
        self.vocabulary = {"phrases": [], "variants": []}
        self._work = threading.Condition()
        self._stop = threading.Event()
        self.stats = {"packets": 0, "dropped": 0, "lastSeq": None,
                      "lastPacketAt": None, "utterances": 0, "wakes": 0,
                      "lastText": None, "lastError": None}

    # -- lifecycle --

    def init(self) -> None:
        Base.metadata.create_all(engine)
        self._load_vocabulary()
        threading.Thread(target=self._transcribe_loop, daemon=True).start()
        threading.Thread(target=self._udp_loop, daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()
        with self._work:
            self._work.notify_all()

    # -- input paths --

    def feed_packet(self, datagram: bytes) -> None:
        """One UDP datagram from the satellite: 4-byte sequence + PCM."""
        if len(datagram) <= PACKET_HEADER.size:
            return
        (seq,) = PACKET_HEADER.unpack_from(datagram)
        last = self.stats["lastSeq"]
        if last is not None and seq > last + 1:
            self.stats["dropped"] += seq - last - 1
        self.stats["lastSeq"] = seq
        self.stats["packets"] += 1
        self.stats["lastPacketAt"] = self._clock()
        if self._clock() < self._mute_until:
            # The speaker is playing centimetres from the mic: hear nothing.
            with self._lock:
                self._speaking = False
                self._utterance = bytearray()
            return
        self.feed_pcm(datagram[PACKET_HEADER.size:])

    def feed_pcm(self, pcm: bytes) -> None:
        """Raw int16 mono samples at self.sample_rate; segments utterances."""
        now = self._clock()
        rms = _rms(pcm)
        loud = rms >= self.energy_floor
        self._levels.append(rms)
        self._level_rms = rms
        with self._lock:
            if self._record is not None:
                self._record += pcm
                return
            if loud:
                if not self._speaking:
                    self._speaking = True
                    self._utterance_started = now
                    self._utterance = bytearray()
                self._last_voice_at = now
            if self._speaking:
                self._utterance += pcm
                max_s = self._listen["max"] if self._listen else self.max_utterance_s
                too_long = now - self._utterance_started >= max_s
                quiet = now - self._last_voice_at >= self.silence_s
                if too_long or (quiet and not loud):
                    self._finish_utterance_locked()

    def feed_wav(self, path: str | Path) -> dict | None:
        """Test path: run one WAV file through the pipeline synchronously."""
        with wave.open(str(path), "rb") as wav:
            if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
                raise ValueError("WAV must be 16-bit mono")
            pcm = wav.readframes(wav.getnframes())
            rate = wav.getframerate()
        return self._process(pcm, rate, len(pcm) / 2 / rate)

    def flush(self) -> None:
        with self._lock:
            if self._speaking:
                self._finish_utterance_locked()

    def record(self, seconds: float) -> dict:
        """Console bench tool: capture the next `seconds` of the live stream
        regardless of the gate, transcribe it, persist the transcript and
        report whether the wake phrase matched. Never fires voice.phrase."""
        seconds = max(0.5, min(float(seconds), RECORD_MAX_S))
        with self._lock:
            if self._speaking:
                self._finish_utterance_locked()
            self._record = bytearray()
        deadline = self._clock() + seconds
        while self._clock() < deadline:
            time.sleep(0.05)
        with self._lock:
            pcm = bytes(self._record or b"")
            self._record = None
        duration = len(pcm) / 2 / self.sample_rate
        peak = max((_rms(pcm[i:i + 640]) for i in range(0, len(pcm), 640)), default=0.0)
        result = {"seconds": seconds, "durationS": round(duration, 2),
                  "peak": round(peak), "floor": self.energy_floor}
        if duration < 0.2:
            return {**result, "text": "", "wake": False,
                    "error": "no audio arrived from the satellite"}
        row = self._process(pcm, self.sample_rate, duration, trigger=False) or {}
        text = self.stats["lastText"] or ""
        command = match_wake(text, self.wake_phrase, self.vocabulary["variants"])
        return {**result, "text": text, "wake": command is not None,
                "command": command, "intent": row.get("intent"),
                "latencyS": row.get("latencyS"), "transcriptId": row.get("id")}

    # -- vocabulary: extra prompt phrases for whisper, extra spellings of the name --

    def vocabulary_view(self) -> dict:
        return {"wakePhrase": self.wake_phrase,
                "defaultWakePhrase": self.default_wake_phrase,
                "phrases": list(self.vocabulary["phrases"]),
                "variants": list(self.vocabulary["variants"]),
                "builtinVariants": list(WAKE_VARIANTS),
                "prompt": self._prompt()}

    def set_vocabulary(self, phrases=None, variants=None, wake_phrase=None) -> dict:
        def clean(items, label):
            if items is None:
                return None
            if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
                raise ValueError(f"{label} must be a list of strings")
            out: list[str] = []
            for item in items:
                item = " ".join(item.split())
                if item and item.lower() not in {o.lower() for o in out}:
                    out.append(item)
            if len(out) > MAX_VOCABULARY:
                raise ValueError(f"at most {MAX_VOCABULARY} {label}")
            return out

        if wake_phrase is not None:
            if not isinstance(wake_phrase, str) or not _normalize(wake_phrase):
                raise ValueError("wakePhrase must be a non-empty string")
            self.wake_phrase = _normalize(wake_phrase)
        new_phrases = clean(phrases, "phrases")
        new_variants = clean(variants, "variants")
        if new_phrases is not None:
            self.vocabulary["phrases"] = new_phrases
        if new_variants is not None:
            self.vocabulary["variants"] = [v for v in (_normalize(x) for x in new_variants) if v]
        self._save_vocabulary()
        self._apply_vocabulary()
        return self.vocabulary_view()

    def _prompt(self) -> str:
        phrase = " ".join(w.capitalize() for w in self.wake_phrase.split())
        extra = [p if p.endswith((".", "!", "?")) else p + "." for p in self.vocabulary["phrases"]]
        return " ".join([PROMPT_TEMPLATE.format(phrase=phrase), *extra])

    def _apply_vocabulary(self) -> None:
        if self.transcriber is not None:
            self.transcriber.prompt = self._prompt()

    def _load_vocabulary(self) -> None:
        with SessionLocal() as session:
            row = session.get(Setting, VOCABULARY_KEY)
        if row is not None:
            try:
                data = json.loads(row.value or "{}")
            except ValueError:
                data = {}
            self.vocabulary = {"phrases": list(data.get("phrases", [])),
                               "variants": list(data.get("variants", []))}
            if _normalize(str(data.get("wakePhrase") or "")):
                self.wake_phrase = _normalize(data["wakePhrase"])
        self._apply_vocabulary()

    def _save_vocabulary(self) -> None:
        with SessionLocal() as session:
            row = session.get(Setting, VOCABULARY_KEY) or Setting(key=VOCABULARY_KEY)
            row.value = json.dumps({**self.vocabulary, "wakePhrase": self.wake_phrase})
            session.add(row)
            session.commit()

    # -- internals --

    def _finish_utterance_locked(self) -> None:
        pcm = bytes(self._utterance)
        started = self._utterance_started
        self._speaking = False
        self._utterance = bytearray()
        duration = len(pcm) / 2 / self.sample_rate
        if duration < self.min_utterance_s:
            return
        with self._work:
            self._queue.append((pcm, self.sample_rate, duration, started))
            if len(self._queue) > 3:
                self._queue.popleft()  # never let a backlog grow unbounded
            self._work.notify()

    def _transcribe_loop(self) -> None:
        while not self._stop.is_set():
            with self._work:
                while not self._queue and not self._stop.is_set():
                    self._work.wait()
                if self._stop.is_set():
                    return
                pcm, rate, duration, _started = self._queue.popleft()
            try:
                self._process(pcm, rate, duration)
            except Exception as exc:
                self.stats["lastError"] = str(exc)
                logger.exception("Ears: transcription failed")

    def _process(self, pcm: bytes, rate: int, duration: float,
                 trigger: bool = True) -> dict | None:
        if self.transcriber is None:
            self.stats["lastError"] = "no transcriber configured"
            return None
        started = time.time()
        text = self.transcriber.transcribe(pcm, rate)
        latency = time.time() - started
        self.stats["utterances"] += 1
        self.stats["lastText"] = text
        listen = self._listen
        if listen is not None and trigger:
            # A conversation is waiting for this utterance: it is the request,
            # not a new wake phrase.
            row = self._persist(text, False, None, duration, latency) if text else None
            logger.info("Ears (listening): %r (%.2fs)", text, latency)
            listen["text"] = text or ""
            listen["latency"] = round(latency, 2)
            listen["event"].set()
            return row
        if not text:
            return None
        command = match_wake(text, self.wake_phrase, self.vocabulary["variants"])
        wake = command is not None
        intent = detect_intent(command) if wake else None
        row = self._persist(text, wake, intent, duration, latency)
        logger.info("Ears: %r wake=%s intent=%s (%.2fs)", text, wake, intent, latency)
        if wake:
            self.stats["wakes"] += 1
        if wake and trigger:
            payload = {"text": text, "command": command, "transcriptId": row.get("id"),
                       "latencyS": round(latency, 2)}
            if intent:
                # Keyword shortcut: sit / rest / stop / greet run straight away.
                self.binder.trigger("voice.phrase", {**payload, "intent": intent})
            else:
                # Everything else is a conversation turn (conversation.py).
                self.binder.trigger("voice.wake", payload)
        return row

    def _persist(self, text, wake, intent, duration, latency) -> dict:
        with SessionLocal() as session:
            row = Transcript(text=text, wake=wake, intent=intent,
                             duration_s=duration, latency_s=latency)
            session.add(row)
            session.commit()
            stale = (session.query(Transcript.id)
                     .order_by(Transcript.id.desc()).offset(500).all())
            if stale:
                (session.query(Transcript)
                 .filter(Transcript.id.in_([s.id for s in stale]))
                 .delete(synchronize_session=False))
                session.commit()
            return row.to_dict()

    def _udp_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        try:
            sock.bind(("0.0.0.0", self.udp_port))
        except OSError as exc:
            self.stats["lastError"] = f"UDP bind failed: {exc}"
            logger.error("Ears: cannot bind UDP %s: %s", self.udp_port, exc)
            return
        logger.info("Ears: listening for PCM on udp/%s", self.udp_port)
        while not self._stop.is_set():
            try:
                datagram, _addr = sock.recvfrom(4096)
            except socket.timeout:
                self.flush_if_silent()
                continue
            except OSError:
                break
            self.feed_packet(datagram)
        sock.close()

    def flush_if_silent(self) -> None:
        """The stream stopped mid-utterance (packet loss): close it out. Also
        the tick that ends a listening window nobody spoke into."""
        with self._lock:
            if self._speaking and self._clock() - self._last_voice_at >= self.silence_s:
                self._finish_utterance_locked()
            listen = self._listen
            if listen and not self._speaking and self._clock() >= listen["deadline"]:
                listen["event"].set()

    # -- conversation hooks --

    def mute(self, seconds: float) -> None:
        """Drop the microphone for `seconds` (the speaker is playing)."""
        self._mute_until = max(self._mute_until, self._clock() + float(seconds))

    def listen(self, window_s: float, max_utterance_s: float) -> tuple[str | None, float | None]:
        """Block until the next utterance is transcribed and return
        (text, whisperSeconds); (None, None) when the window closes with
        nothing said. The text goes to the caller instead of the wake
        matcher. Only one listener at a time."""
        pending = {"deadline": self._clock() + window_s, "max": max_utterance_s,
                   "event": threading.Event(), "text": None, "latency": None}
        with self._lock:
            if self._listen is not None:
                raise RuntimeError("already listening")
            self._listen = pending
        # Speech may start just before the deadline and run to the cap, and
        # whisper needs a moment after that.
        pending["event"].wait(window_s + max_utterance_s + 15.0)
        with self._lock:
            self._listen = None
        return pending["text"], pending["latency"]

    # -- reporting --

    def status(self) -> dict:
        now = self._clock()
        last = self.stats["lastPacketAt"]
        return {
            "enabled": True,
            "udpPort": self.udp_port,
            "sampleRate": self.sample_rate,
            "wakePhrase": self.wake_phrase,
            "streaming": last is not None and now - last < 2.0,
            "lastPacketAgeS": round(now - last, 1) if last else None,
            "modelLoaded": bool(getattr(self.transcriber, "loaded", False)),
            "model": getattr(self.transcriber, "model_name", None),
            "level": self._level(),
            "listening": self._listen is not None,
            "mutedForS": round(max(0.0, self._mute_until - now), 1),
            "vocabulary": self.vocabulary_view(),
            **self.stats,
        }

    def _level(self) -> dict:
        recent = list(self._levels)
        return {
            "rms": round(self._level_rms),
            "peak": round(max(recent)) if recent else 0,
            "median": round(sorted(recent)[len(recent) // 2]) if recent else 0,
            "floor": self.energy_floor,
            "speaking": self._speaking,
        }

    def transcripts(self, limit: int = 20) -> list[dict]:
        with SessionLocal() as session:
            rows = (session.query(Transcript).order_by(Transcript.id.desc())
                    .limit(limit).all())
            return [r.to_dict() for r in rows]


def _rms(pcm: bytes) -> float:
    count = len(pcm) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack("<%dh" % count, pcm[:count * 2])
    mean = sum(samples) / count
    return (sum((s - mean) ** 2 for s in samples) / count) ** 0.5


def build_transcriber():
    if not Config.EARS_ENABLED:
        return None
    return WhisperTranscriber(Config.WHISPER_MODEL, Config.WHISPER_CACHE or None)
