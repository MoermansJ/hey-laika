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
from app.models import Base, SessionLocal, engine, utcnow

logger = logging.getLogger(__name__)

PACKET_HEADER = struct.Struct(">I")  # sequence number, then int16 LE samples

# Spellings whisper produces for "Laika" (owner's accent + tiny model).
WAKE_VARIANTS = ("laika", "laker", "lika", "leica", "lycra", "lyca", "like a",
                 "laca", "lika", "lakea", "leika", "lyka")
WAKE_LEADERS = ("hey", "hi", "ok", "okay", "yo", "")

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
        return {"id": self.id, "at": self.at.isoformat() if self.at else None,
                "text": self.text, "wake": self.wake, "intent": self.intent,
                "durationS": round(self.duration_s, 2),
                "latencyS": round(self.latency_s, 2)}


# ---- wake phrase + intent ----------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[^a-z' ]+", " ", text.lower()).strip()


def match_wake(text: str, phrase: str = "hey laika") -> str | None:
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
        for variant in WAKE_VARIANTS:
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
        if sample_rate != 16000:
            step = sample_rate / 16000.0
            idx = (np.arange(int(len(audio) / step)) * step).astype(np.int64)
            audio = audio[idx]
        segments, _info = self._load().transcribe(
            audio, language="en", beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()


# ---- the service --------------------------------------------------------------

class EarsService:
    def __init__(self, event_binder, transcriber=None,
                 sample_rate: int = 16000, udp_port: int = 5005,
                 wake_phrase: str = "hey laika", energy_floor: int = 600,
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
        self._work = threading.Condition()
        self._stop = threading.Event()
        self.stats = {"packets": 0, "dropped": 0, "lastSeq": None,
                      "lastPacketAt": None, "utterances": 0, "wakes": 0,
                      "lastText": None, "lastError": None}

    # -- lifecycle --

    def init(self) -> None:
        Base.metadata.create_all(engine)
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
        self.feed_pcm(datagram[PACKET_HEADER.size:])

    def feed_pcm(self, pcm: bytes) -> None:
        """Raw int16 mono samples at self.sample_rate; segments utterances."""
        now = self._clock()
        loud = _rms(pcm) >= self.energy_floor
        with self._lock:
            if loud:
                if not self._speaking:
                    self._speaking = True
                    self._utterance_started = now
                    self._utterance = bytearray()
                self._last_voice_at = now
            if self._speaking:
                self._utterance += pcm
                too_long = now - self._utterance_started >= self.max_utterance_s
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

    def _process(self, pcm: bytes, rate: int, duration: float) -> dict | None:
        if self.transcriber is None:
            self.stats["lastError"] = "no transcriber configured"
            return None
        started = time.time()
        text = self.transcriber.transcribe(pcm, rate)
        latency = time.time() - started
        self.stats["utterances"] += 1
        self.stats["lastText"] = text
        if not text:
            return None
        command = match_wake(text, self.wake_phrase)
        wake = command is not None
        intent = detect_intent(command) if wake else None
        row = self._persist(text, wake, intent, duration, latency)
        logger.info("Ears: %r wake=%s intent=%s (%.2fs)", text, wake, intent, latency)
        if wake:
            self.stats["wakes"] += 1
            self.binder.trigger("voice.phrase", {
                "text": text, "command": command, "intent": intent or "unknown",
                "transcriptId": row.get("id")})
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
        """The stream stopped mid-utterance (packet loss): close it out."""
        with self._lock:
            if self._speaking and self._clock() - self._last_voice_at >= self.silence_s:
                self._finish_utterance_locked()

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
            **self.stats,
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
    return (sum(s * s for s in samples) / count) ** 0.5


def build_transcriber():
    if not Config.EARS_ENABLED:
        return None
    return WhisperTranscriber(Config.WHISPER_MODEL, Config.WHISPER_CACHE or None)
