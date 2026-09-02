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
import logging
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

RATE = 8000
CHUNK_BYTES = 1800          # < BUFF_LEN (2507) minus the "XWa" header and b64 slack
RING_BYTES = 8192           # mirrors the firmware ring; pacing waits when fuller
_FREE_RE = re.compile(r"=\s*\r?\n?\s*(\d+)")


class MouthService:
    def __init__(self, controller, pin: int | None, tts=None, sleep=time.sleep):
        self.controller = controller
        self.pin = pin
        self.tts = tts or default_tts
        self._sleep = sleep
        self._attached = False
        self.last = {"text": None, "at": None, "seconds": None, "chunks": 0,
                     "error": None}

    @property
    def enabled(self) -> bool:
        return bool(self.pin)

    def status(self) -> dict:
        return {"enabled": self.enabled, "pin": self.pin,
                "attached": self._attached, "sampleRate": RATE,
                "ttsEngine": getattr(self.tts, "__name__", "custom"), **self.last}

    # -- public --

    def say(self, text: str) -> dict:
        if not self.enabled:
            raise RuntimeError("SPEAKER_PIN is not set")
        wav = self.tts(text)
        return self.play_wav(wav, label=text)

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
                # Ring nearly full: wait for roughly one chunk to drain.
                self._sleep(CHUNK_BYTES / RATE)
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
    pcm8 = audioop.lin2lin(frames, 2, 1)
    return audioop.bias(pcm8, 1, 128)                          # signed -> unsigned


# ---- TTS sources ---------------------------------------------------------------

def default_tts(text: str) -> bytes:
    """Eleven Labs when configured, else espeak-ng if installed, else a
    tone-coded fallback so the playback path can still be validated."""
    from app.config import Config

    if Config.ELEVENLABS_API_KEY:
        from app.voice import synthesize_speech

        mp3 = synthesize_speech(text)
        return mp3_to_wav(mp3)
    if shutil.which("espeak-ng"):
        out = subprocess.run(["espeak-ng", "-v", "en", "-s", "150", "--stdout", text],
                             capture_output=True, timeout=20, check=True)
        return out.stdout
    logger.warning("No TTS engine (ELEVENLABS_API_KEY or espeak-ng); using tone fallback")
    return tone_wav(len(text))


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
