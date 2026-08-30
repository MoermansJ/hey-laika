"""'Hey Laika' voice interaction — MVP with stubbed audio I/O.

Phase 1 per the voice design doc: microphone input is stubbed as text POSTs,
speaker output is the Bittle's buzzer (`b` serial token) plus an optional
Eleven Labs TTS file. The LLM is a local Ollama model — deliberately the
lightest workable one (llama3.2:1b) as a temporary stand-in until the voice
hardware and a bigger model justify themselves.

Upgrade path (INMP441 + MAX98357A): swap the stubbed steps for real
recording/Whisper/playback; the endpoint contract stays the same.
"""
import logging
import time
from pathlib import Path

import requests

from app.config import Config

logger = logging.getLogger(__name__)

# Keep replies short — they are meant to be spoken aloud by a small robot dog.
LAIKA_SYSTEM_PROMPT = (
    "You are Laika, a small cheerful robot dog (a Petoi Bittle). "
    "Answer in one or two short spoken sentences — no lists, no markdown. "
    "Be warm, a little playful, and factually correct."
)

# Buzzer feedback patterns: OpenCat ASCII `b` token, (tone, duration) pairs.
# Tunable by ear once heard on the real buzzer.
BEEP_PATTERNS = {
    "beep_wake_word": "b 22 4 26 4",          # two short rising beeps
    "recording": "b 24 2 24 2 24 2 24 2 24 2",  # pulse
    "processing": "b 20 2 24 2 28 2",         # quick ascending triple
    "ready": "b 26 8",                        # one long beep
}


def play_beep(bittle, pattern: str) -> bool:
    """Send a named beep pattern to the robot; unknown pattern raises KeyError."""
    return bittle.send_command(BEEP_PATTERNS[pattern])


def query_ollama(prompt: str, model: str | None = None,
                 temperature: float = 0.7,
                 max_tokens: int = 120) -> tuple[str | None, str | None]:
    """Ask the local Ollama model; returns (response, error) — exactly one set."""
    try:
        response = requests.post(
            f"{Config.OLLAMA_URL}/api/generate",
            json={
                "model": model or Config.OLLAMA_MODEL,
                "prompt": prompt,
                "system": LAIKA_SYSTEM_PROMPT,
                "stream": False,
                # Ollama reads sampling knobs from `options`, not top-level.
                "options": {"temperature": temperature,
                            "num_predict": max_tokens},
            },
            timeout=Config.OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        text = (response.json().get("response") or "").strip()
        if not text:
            return None, "Ollama returned an empty response"
        return text, None
    except requests.exceptions.Timeout:
        return None, f"Ollama timed out after {Config.OLLAMA_TIMEOUT}s"
    except requests.exceptions.ConnectionError:
        return None, f"Ollama unreachable at {Config.OLLAMA_URL}"
    except requests.exceptions.RequestException as exc:
        return None, f"Ollama error: {exc}"


def ollama_health() -> dict:
    """Reachability + whether the configured model is pulled."""
    try:
        tags = requests.get(f"{Config.OLLAMA_URL}/api/tags", timeout=5).json()
        models = [m.get("name") for m in tags.get("models", [])]
        return {
            "reachable": True,
            "url": Config.OLLAMA_URL,
            "configuredModel": Config.OLLAMA_MODEL,
            "modelAvailable": any(
                name == Config.OLLAMA_MODEL or
                name.split(":")[0] == Config.OLLAMA_MODEL
                for name in models),
            "models": models,
        }
    except requests.exceptions.RequestException as exc:
        return {"reachable": False, "url": Config.OLLAMA_URL,
                "configuredModel": Config.OLLAMA_MODEL, "error": str(exc)}


class TtsNotConfiguredError(RuntimeError):
    pass


def synthesize_speech(text: str, voice_id: str | None = None) -> bytes:
    """Eleven Labs TTS; raises TtsNotConfiguredError without an API key."""
    if not Config.ELEVENLABS_API_KEY:
        raise TtsNotConfiguredError("ELEVENLABS_API_KEY not set")
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/"
        f"{voice_id or Config.ELEVENLABS_VOICE_ID}",
        headers={"xi-api-key": Config.ELEVENLABS_API_KEY,
                 "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.content


def save_tts_audio(audio_bytes: bytes, static_root: Path) -> str:
    """Save MP3 under the Flask static dir; returns the relative URL path."""
    responses_dir = static_root / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    filename = f"response_{int(time.time() * 1000)}.mp3"
    (responses_dir / filename).write_bytes(audio_bytes)
    return f"/static/responses/{filename}"
