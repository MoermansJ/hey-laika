"""Mouth: host TTS -> 8 kHz 8-bit PCM -> firmware PWM playback on the Grove
Speaker Plus (VOICE_RELAY_BRIEF.md build plan step 4).

Firmware side (hey-laika XW tool set):
  XWp<pin>   attach the sigma-delta output to GPIO <pin> (ASCII digits) and
             start the 8 kHz playback timer; persisted in NVS
  XWa<pcm>   append unsigned 8-bit samples to the playback ring (binary,
             sent through the WebSocket b64 path); replies '=' + free bytes
  XWq        stop and flush

Chunks are sized to the firmware command buffer and paced by the free-space
reply so the ring never overflows and the loop never starves. Speech quality
is walkie-talkie: intelligible, not pretty (the board has no DAC).
"""
import audioop
import io
import inspect
import json
import logging
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

RATE = 8000
# 1536 samples = 192 ms per frame (~2 KB of base64 on the wire). The
# firmware's command buffer takes 2.5 KB; its heap once failed on a 2.4 KB
# frame (LoadProhibited, 2026-09-04) and fork a51fd08 now drops such frames
# instead of crashing, but a 1536-byte frame (2 KB of base64) stalled the
# WebSocket layer with no reply at all (2026-09-04 17:46). 1024 is the
# largest frame that works. At the measured ~100 ms round trip it fills the
# ring only slightly faster than the 8 KB/s drain, so the firmware holds
# playback until SPEAKER_START_BYTES are buffered or XWf ends the clip.
CHUNK_BYTES = 1024
RING_BYTES = 8192           # mirrors the firmware ring; pacing waits when fuller
RMS_TARGET = 8200           # ~0.25 full scale after normalisation
_FREE_RE = re.compile(r"=\s*\r?\n?\s*(\d+)")


SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"


class SoundLibrary:
    """Named clips (WAV or MP3 files in dog/sounds) decoded once to WAV."""

    def __init__(self, directory: str | Path = SOUNDS_DIR):
        self.directory = Path(directory)
        self._cache: dict[str, bytes] = {}

    def names(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted(p.stem for p in self.directory.iterdir()
                      if p.suffix.lower() in (".wav", ".mp3"))

    def wav(self, name: str) -> bytes:
        if name in self._cache:
            return self._cache[name]
        for suffix in (".wav", ".mp3"):
            path = self.directory / f"{name}{suffix}"
            if path.is_file():
                data = path.read_bytes()
                wav = mp3_to_wav(data) if suffix == ".mp3" else data
                self._cache[name] = wav
                return wav
        raise KeyError(f"unknown sound '{name}' (one of {', '.join(self.names())})")


VOICE_KEY = "mouth.voice"
DEFAULT_VOICE = {"voice": "en-us", "variant": "", "speed": 150, "pitch": 50}
ESPEAK_VARIANTS = ["", "m1", "m2", "m3", "m4", "m5", "m6", "m7",
                   "f1", "f2", "f3", "f4", "f5", "croak", "whisper"]
PREVIEW_TEXT = "Hi, I am Laika. This is how I sound."


class MouthService:
    def __init__(self, controller, pin: int | None, tts=None, sleep=time.sleep,
                 sounds: SoundLibrary | None = None):
        self.controller = controller
        self.pin = pin
        self.tts = tts or default_tts
        self._sleep = sleep
        self._attached = False
        self.sounds = sounds or SoundLibrary()
        self.voice = dict(DEFAULT_VOICE)
        self._voices_cache: list[dict] | None = None
        self.last = {"text": None, "at": None, "seconds": None, "chunks": 0,
                     "error": None}

    @property
    def enabled(self) -> bool:
        return bool(self.pin)

    def init(self) -> None:
        """Load the saved voice (settings row); harmless without a database."""
        try:
            from app.models import SessionLocal, Setting
            with SessionLocal() as session:
                row = session.get(Setting, VOICE_KEY)
            if row is not None:
                data = json.loads(row.value or "{}")
                self.voice.update({k: data[k] for k in DEFAULT_VOICE if k in data})
        except Exception:
            logger.exception("Mouth: voice setting not loaded")

    def status(self) -> dict:
        return {"enabled": self.enabled, "pin": self.pin,
                "attached": self._attached, "sampleRate": RATE,
                "ttsEngine": tts_engine_name(self.tts),
                "voice": dict(self.voice),
                "sounds": self.sounds.names(), **self.last}

    # -- public --

    def say(self, text: str) -> dict:
        if not self.enabled:
            raise RuntimeError("SPEAKER_PIN is not set")
        wav = self._synthesize(text)
        return self.play_wav(wav, label=text)

    def _synthesize(self, text: str) -> bytes:
        try:
            takes_voice = len(inspect.signature(self.tts).parameters) >= 2
        except (TypeError, ValueError):
            takes_voice = False
        return self.tts(text, dict(self.voice)) if takes_voice else self.tts(text)

    # -- voice setting (the console's dropdown) --

    def voices_view(self) -> dict:
        if self._voices_cache is None:
            self._voices_cache = espeak_voices()
        return {"engine": tts_engine_name(self.tts), "current": dict(self.voice),
                "voices": list(self._voices_cache), "variants": list(ESPEAK_VARIANTS),
                "previewText": PREVIEW_TEXT}

    def set_voice(self, voice=None, variant=None, speed=None, pitch=None,
                  preview: bool = False) -> dict:
        view = self.voices_view()
        if voice is not None:
            ids = {v["id"] for v in view["voices"]}
            if ids and voice not in ids:
                raise ValueError(f"unknown voice '{voice}'")
            self.voice["voice"] = str(voice)
        if variant is not None:
            if variant not in ESPEAK_VARIANTS:
                raise ValueError(f"variant must be one of {ESPEAK_VARIANTS}")
            self.voice["variant"] = variant
        if speed is not None:
            speed = int(speed)
            if not 80 <= speed <= 300:
                raise ValueError("speed must be 80..300 words per minute")
            self.voice["speed"] = speed
        if pitch is not None:
            pitch = int(pitch)
            if not 0 <= pitch <= 99:
                raise ValueError("pitch must be 0..99")
            self.voice["pitch"] = pitch
        try:
            from app.models import SessionLocal, Setting
            with SessionLocal() as session:
                row = session.get(Setting, VOICE_KEY) or Setting(key=VOICE_KEY)
                row.value = json.dumps(self.voice)
                session.add(row)
                session.commit()
        except Exception:
            logger.exception("Mouth: voice setting not saved")
        if preview and self.enabled:
            self.say(PREVIEW_TEXT)
        return self.voices_view()

    def play_sound(self, name: str) -> dict:
        """A clip from the library (positive_bark, ...) on the speaker."""
        if not self.enabled:
            raise RuntimeError("SPEAKER_PIN is not set")
        return self.play_wav(self.sounds.wav(name), label=f"sound:{name}")

    def play_wav(self, wav_bytes: bytes, label: str = "") -> dict:
        if not self.enabled:
            raise RuntimeError("SPEAKER_PIN is not set")
        pcm = to_pcm8(wav_bytes)
        self._attach()
        sent = 0
        chunks = 0
        for offset in range(0, len(pcm), CHUNK_BYTES):
            chunk = pcm[offset:offset + CHUNK_BYTES]
            free = self._push(chunk)
            sent += len(chunk)
            chunks += 1
            if free is not None and free < CHUNK_BYTES:
                # Ring nearly full: wait just until the next chunk fits.
                self._sleep((CHUNK_BYTES - free) / RATE + 0.02)
        self.controller.send_command("XWf")   # clip complete: start even if under the prebuffer
        seconds = len(pcm) / RATE
        self.last = {"text": label, "at": time.time(), "seconds": round(seconds, 2),
                     "chunks": chunks, "error": None}
        return dict(self.last)

    def stop(self) -> bool:
        return self.controller.send_command("XWq")

    # -- firmware protocol --

    def _attach(self) -> None:
        if self._attached:
            return
        if not self.controller.send_command(f"XWp{self.pin}"):
            raise RuntimeError("firmware refused XWp (speaker pin)")
        self._attached = True

    def _push(self, chunk: bytes) -> int | None:
        query = getattr(self.controller, "query_binary", None)
        if query is None:
            ok = self.controller.send_command("XWa")   # mock/serial: no audio path
            return RING_BYTES if ok else None
        results = query(b"XWa" + chunk)
        if results is None:
            self._attached = False
            raise RuntimeError("speaker chunk not acknowledged")
        match = _FREE_RE.search("\n".join(results))
        return int(match.group(1)) if match else None


# ---- audio conversion --------------------------------------------------------

def to_pcm8(wav_bytes: bytes) -> bytes:
    """Any PCM WAV -> 8 kHz mono unsigned 8-bit."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if channels > 1:
        frames = audioop.tomono(frames, width, 0.5, 0.5)
    if width != 2:
        frames = audioop.lin2lin(frames, width, 2)
    if rate != RATE:
        frames, _ = audioop.ratecv(frames, 2, 1, rate, RATE, None)
    peak = audioop.max(frames, 2) or 1
    frames = audioop.mul(frames, 2, min(4.0, 28000 / peak))   # normalise, cap gain
    # Speech sits ~10 dB under its peaks and vanished on the 2 W speaker while
    # tones and barks were loud (2026-09-04): lift to a loudness target and let
    # audioop.mul clip the peaks, walkie-talkie style.
    rms = audioop.rms(frames, 2) or 1
    if rms < RMS_TARGET:
        frames = audioop.mul(frames, 2, min(4.0, RMS_TARGET / rms))
    pcm8 = audioop.lin2lin(frames, 2, 1)
    return audioop.bias(pcm8, 1, 128)                          # signed -> unsigned


# ---- TTS sources ---------------------------------------------------------------

def tts_engine_name(tts) -> str:
    if tts is not default_tts:
        return getattr(tts, "__name__", "custom")
    from app.config import Config

    if Config.ELEVENLABS_API_KEY:
        return "elevenlabs"
    return "espeak-ng" if shutil.which("espeak-ng") else "tone"


def default_tts(text: str, voice: dict | None = None) -> bytes:
    """Eleven Labs when configured, else espeak-ng if installed, else a
    tone-coded fallback so the playback path can still be validated."""
    from app.config import Config

    if Config.ELEVENLABS_API_KEY:
        from app.voice import synthesize_speech

        mp3 = synthesize_speech(text)
        return mp3_to_wav(mp3)
    if shutil.which("espeak-ng"):
        return espeak_tts(text, voice or DEFAULT_VOICE)
    logger.warning("No TTS engine (ELEVENLABS_API_KEY or espeak-ng); using tone fallback")
    return tone_wav(len(text))


def espeak_tts(text: str, voice: dict) -> bytes:
    name = voice.get("voice") or "en-us"
    if voice.get("variant"):
        name = f"{name}+{voice['variant']}"
    out = subprocess.run(["espeak-ng", "-v", name, "-s", str(voice.get("speed", 150)),
                          "-p", str(voice.get("pitch", 50)), "--stdout", text],
                         capture_output=True, timeout=20, check=True)
    return out.stdout


def espeak_voices() -> list[dict]:
    """English voices espeak-ng can render here (the mbrola ones need
    binaries this image does not ship, so they are skipped)."""
    if not shutil.which("espeak-ng"):
        return []
    try:
        out = subprocess.run(["espeak-ng", "--voices=en"], capture_output=True,
                             text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    voices, seen = [], set()
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 5 or parts[4].startswith("mb/") or parts[1] == "variant":
            continue
        lang, gender, name = parts[1], parts[2].split("/")[-1], parts[3].replace("_", " ")
        if lang in seen:
            continue
        seen.add(lang)
        voices.append({"id": lang, "name": name, "gender": gender})
    return voices


def mp3_to_wav(mp3: bytes) -> bytes:
    import av  # bundled with faster-whisper

    container = av.open(io.BytesIO(mp3))
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    pcm = bytearray()
    for frame in container.decode(stream):
        for out in resampler.resample(frame):
            pcm += out.to_ndarray().tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(bytes(pcm))
    return buf.getvalue()


def tone_wav(chars: int) -> bytes:
    """A short two-tone chirp per ~8 characters: audible proof of playback."""
    import math

    buf = io.BytesIO()
    samples = bytearray()
    for i in range(max(1, chars // 8)):
        freq = 660 if i % 2 == 0 else 880
        for n in range(int(RATE * 0.12)):
            samples += int(12000 * math.sin(2 * math.pi * freq * n / RATE)).to_bytes(2, "little", signed=True)
        samples += b"\0\0" * int(RATE * 0.04)
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE)
        wav.writeframes(bytes(samples))
    return buf.getvalue()


def load_wav(path: str | Path) -> bytes:
    return Path(path).read_bytes()
