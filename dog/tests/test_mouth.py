"""Mouth: WAV -> 8 kHz 8-bit conversion, chunking and pacing against the
firmware protocol (XWp / XWa / XWq), with a scripted controller."""
import io
import os
import wave

import pytest

import app.mouth as mouth_module
from app.action_feed import SPEECH_LABEL_MAX, ActionFeed
from app.mouth import (CHUNK_BYTES, RATE, KOKORO_VOICES, MouthService, default_tts,
                       kokoro_tts, to_pcm8, tone_wav, tts_engine_name)


def make_wav(seconds=1.0, rate=16000, channels=1, width=2):
    buf = io.BytesIO()
    frames = int(rate * seconds)
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(width); w.setframerate(rate)
        sample = (1000).to_bytes(width, "little", signed=True) * channels
        w.writeframes(sample * frames)
    return buf.getvalue()


class ScriptedController:
    def __init__(self, free_sequence=None):
        self.commands = []
        self.binary = []
        self.free = list(free_sequence or [])

    def send_command(self, command):
        self.commands.append(command)
        return True

    def query_binary(self, payload):
        self.binary.append(payload)
        free = self.free.pop(0) if self.free else 8192
        return ["=", str(free)]


def test_to_pcm8_resamples_and_biases():
    pcm = to_pcm8(make_wav(seconds=0.5, rate=16000))
    assert len(pcm) == RATE // 2                     # 0.5 s at 8 kHz
    assert all(0 <= b <= 255 for b in pcm)
    assert 120 <= sum(pcm) / len(pcm) <= 136 or max(pcm) > 128  # unsigned, centred


def test_to_pcm8_accepts_stereo_and_8khz():
    assert len(to_pcm8(make_wav(seconds=0.25, rate=8000, channels=2))) == RATE // 4


def test_tone_fallback_is_valid_wav():
    pcm = to_pcm8(tone_wav(24))
    assert len(pcm) > RATE // 4


def test_sound_library_lists_and_decodes_clips(tmp_path):
    from app.mouth import SoundLibrary

    (tmp_path / "chirp.wav").write_bytes(make_wav(seconds=0.2))
    (tmp_path / "notes.txt").write_text("ignored")
    library = SoundLibrary(tmp_path)
    assert library.names() == ["chirp"]
    assert library.wav("chirp") == make_wav(seconds=0.2)
    assert library.wav("chirp") is library.wav("chirp")       # cached
    with pytest.raises(KeyError):
        library.wav("bark")
    assert SoundLibrary(tmp_path / "missing").names() == []


def test_play_sound_goes_through_the_speaker(tmp_path):
    from app.mouth import SoundLibrary

    (tmp_path / "bark.wav").write_bytes(make_wav(seconds=0.5))
    ctrl = ScriptedController()
    mouth = MouthService(ctrl, pin=10, sleep=lambda s: None, sounds=SoundLibrary(tmp_path))
    result = mouth.play_sound("bark")
    assert result["text"] == "sound:bark" and result["seconds"] == 0.5
    assert ctrl.commands == ["XWp10", "XWf"] and ctrl.binary
    assert mouth.status()["sounds"] == ["bark"]
    with pytest.raises(RuntimeError):
        MouthService(ctrl, pin=None, sounds=SoundLibrary(tmp_path)).play_sound("bark")


def test_shipped_bark_clips_decode():
    from app.mouth import SoundLibrary

    library = SoundLibrary()
    assert {"positive_bark", "positive_bark2", "negative_bark"} <= set(library.names())
    assert len(to_pcm8(library.wav("positive_bark"))) > RATE // 4    # > 0.25 s of audio


def test_voice_setting_reaches_a_voice_aware_tts_and_persists():
    from app.models import init_db
    init_db()
    seen = []

    def tts(text, voice):
        seen.append((text, dict(voice)))
        return make_wav(0.2)

    ctrl = ScriptedController()
    mouth = MouthService(ctrl, pin=10, tts=tts, sleep=lambda s: None)
    mouth.set_voice(voice="en-gb", variant="f3", speed=170, pitch=60)
    mouth.say("hello")
    assert seen[-1] == ("hello", {"voice": "en-gb", "variant": "f3", "speed": 170, "pitch": 60})
    fresh = MouthService(ctrl, pin=10, tts=tts, sleep=lambda s: None)
    fresh.init()
    assert fresh.voice["voice"] == "en-gb" and fresh.voice["speed"] == 170
    with pytest.raises(ValueError):
        mouth.set_voice(speed=10)
    with pytest.raises(ValueError):
        mouth.set_voice(variant="robot")
    assert mouth.status()["voice"]["variant"] == "f3"
    mouth.set_voice(voice="en-us", variant="", speed=150, pitch=50)


def test_plain_tts_still_works_without_a_voice_parameter():
    ctrl = ScriptedController()
    mouth = MouthService(ctrl, pin=10, tts=lambda text: make_wav(0.2), sleep=lambda s: None)
    assert mouth.say("hi")["chunks"] >= 1


def test_play_wav_attaches_once_and_chunks():
    ctrl = ScriptedController()
    mouth = MouthService(ctrl, pin=10, sleep=lambda s: None)
    result = mouth.play_wav(make_wav(seconds=1.0))
    assert ctrl.commands.count("XWp10") == 1         # attach exactly once
    assert ctrl.commands[-1] == "XWf"                 # every clip ends with clip-complete
    assert result["chunks"] == -(-RATE // CHUNK_BYTES)  # ceil(8000 / chunk)
    assert all(p.startswith(b"XWa") for p in ctrl.binary)
    assert all(len(p) - 3 <= CHUNK_BYTES for p in ctrl.binary)
    mouth.play_wav(make_wav(seconds=0.1))
    assert ctrl.commands.count("XWp10") == 1         # still attached, not re-sent


def test_pacing_sleeps_when_ring_is_nearly_full():
    slept = []
    ctrl = ScriptedController(free_sequence=[100, 8000, 8000, 8000, 8000])
    mouth = MouthService(ctrl, pin=9, sleep=slept.append)
    mouth.play_wav(make_wav(seconds=1.0))
    assert len(slept) == 1 and slept[0] == pytest.approx((CHUNK_BYTES - 100) / RATE + 0.02)


def test_say_requires_pin():
    mouth = MouthService(ScriptedController(), pin=None)
    with pytest.raises(RuntimeError):
        mouth.say("hello")
    assert mouth.status()["enabled"] is False


def test_say_uses_injected_tts():
    ctrl = ScriptedController()
    mouth = MouthService(ctrl, pin=9, tts=lambda text: make_wav(seconds=0.2),
                         sleep=lambda s: None)
    result = mouth.say("hi there")
    assert result["text"] == "hi there" and result["seconds"] == pytest.approx(0.2)
    assert mouth.stop() is True and ctrl.commands[-1] == "XWq"


def test_mock_controller_accepts_binary():
    from app.bittle_controller import MockBittleController

    ctrl = MockBittleController()
    assert ctrl.query_binary(b"XWa" + bytes(100)) == ["=", "8192"]


# ---- the action feed: speech bypasses the arbiter, so the mouth writes it ----

def _feed_mouth(**kwargs):
    feed = ActionFeed()
    mouth = MouthService(ScriptedController(), pin=10, tts=lambda text: tone_wav(len(text)),
                         sleep=lambda s: None, feed=feed, **kwargs)
    return mouth, feed


def test_speech_reaches_the_action_feed_with_the_words_spoken():
    mouth, feed = _feed_mouth()
    mouth.say("Sitting down now.")
    entry = feed.recent(1)[0]
    assert entry["tag"] == "SPEECH" and entry["action"] == "Sitting down now."
    assert entry["status"] == "done" and entry["endedAt"] is not None


def test_a_clip_is_tagged_sound_not_speech():
    mouth, feed = _feed_mouth()
    mouth.play_wav(make_wav(seconds=0.1), label="sound:positive_bark", kind="SOUND")
    entry = feed.recent(1)[0]
    assert entry["tag"] == "SOUND" and entry["action"] == "sound:positive_bark"


def test_a_long_reply_is_shortened_for_the_feed_line():
    mouth, feed = _feed_mouth()
    mouth.say("word " * 200)
    action = feed.recent(1)[0]["action"]
    assert len(action) <= SPEECH_LABEL_MAX and action.endswith("…")


def test_a_failed_clip_does_not_sit_in_the_feed_as_executing():
    feed = ActionFeed()
    ctrl = ScriptedController()
    ctrl.query_binary = lambda payload: None          # firmware never acknowledges
    mouth = MouthService(ctrl, pin=10, tts=lambda text: tone_wav(len(text)),
                         sleep=lambda s: None, feed=feed)
    with pytest.raises(RuntimeError):
        mouth.say("This will not play.")
    assert feed.recent(1)[0]["status"] == "failed"


def test_without_a_feed_the_mouth_still_works():
    mouth = MouthService(ScriptedController(), pin=10, tts=lambda text: tone_wav(len(text)),
                         sleep=lambda s: None)
    assert mouth.say("No feed wired.")["chunks"] > 0


# ---- Kokoro: natural local TTS, the espeak-ng/Eleven Labs middle ground ----
# (CONVERSATION_BRIEF.md). Faked here so no 190 MB model download is needed;
# one opt-in test runs the real model, mirroring test_ears.py's whisper gate.

class FakeKokoro:
    def __init__(self):
        self.calls = []

    def create(self, text, voice="af_heart", speed=1.0, lang="en-us"):
        import numpy as np

        self.calls.append((text, voice, speed, lang))
        return np.zeros(int(24000 * 0.3), dtype=np.float32), 24000


def _fake_engine(monkeypatch):
    fake = FakeKokoro()
    monkeypatch.setattr(mouth_module, "_load_kokoro", lambda: fake)
    return fake


def test_kokoro_tts_converts_float_samples_to_a_playable_wav(monkeypatch):
    fake = _fake_engine(monkeypatch)
    wav = kokoro_tts("Hello", {"voice": "af_heart", "speed": 150})
    assert fake.calls == [("Hello", "af_heart", 1.0, "en-us")]
    assert len(to_pcm8(wav)) > 0


def test_kokoro_tts_falls_back_to_the_default_voice_for_an_unknown_id(monkeypatch):
    fake = _fake_engine(monkeypatch)
    kokoro_tts("Hi", {"voice": "not-a-real-voice", "speed": 150})
    assert fake.calls[0][1] == mouth_module.DEFAULT_KOKORO_VOICE


def test_kokoro_speed_maps_the_wpm_slider_onto_its_own_multiplier(monkeypatch):
    fake = _fake_engine(monkeypatch)
    kokoro_tts("Hi", {"voice": "af_heart", "speed": 300})    # the slider's max
    assert fake.calls[-1][2] == pytest.approx(2.0)
    kokoro_tts("Hi", {"voice": "af_heart", "speed": 10})     # below the slider's min
    assert fake.calls[-1][2] == pytest.approx(0.5)


def _no_cloud_voice(monkeypatch):
    import app.config as config_module

    monkeypatch.setattr(config_module.Config, "ELEVENLABS_API_KEY", "")


def test_engine_precedence_prefers_kokoro_over_espeak(monkeypatch):
    _no_cloud_voice(monkeypatch)
    monkeypatch.setattr(mouth_module, "kokoro_available", lambda: True)
    monkeypatch.setattr(mouth_module.shutil, "which", lambda name: "/usr/bin/espeak-ng")
    assert tts_engine_name(default_tts) == "kokoro"


def test_engine_precedence_falls_back_to_espeak_without_kokoro_files(monkeypatch):
    _no_cloud_voice(monkeypatch)
    monkeypatch.setattr(mouth_module, "kokoro_available", lambda: False)
    monkeypatch.setattr(mouth_module.shutil, "which", lambda name: "/usr/bin/espeak-ng")
    assert tts_engine_name(default_tts) == "espeak-ng"


def test_engine_precedence_elevenlabs_wins_over_kokoro(monkeypatch):
    import app.config as config_module

    monkeypatch.setattr(config_module.Config, "ELEVENLABS_API_KEY", "sk-test")
    monkeypatch.setattr(mouth_module, "kokoro_available", lambda: True)
    assert tts_engine_name(default_tts) == "elevenlabs"


def test_voices_view_lists_kokoro_voices_when_kokoro_is_the_engine(monkeypatch):
    _no_cloud_voice(monkeypatch)
    monkeypatch.setattr(mouth_module, "kokoro_available", lambda: True)
    mouth = MouthService(ScriptedController(), pin=10)
    view = mouth.voices_view()
    assert view["engine"] == "kokoro"
    assert {v["id"] for v in view["voices"]} == {v["id"] for v in KOKORO_VOICES}
    assert view["variants"] == [""]


def test_set_voice_rejects_an_espeak_voice_id_while_kokoro_is_active(monkeypatch):
    _no_cloud_voice(monkeypatch)
    monkeypatch.setattr(mouth_module, "kokoro_available", lambda: True)
    mouth = MouthService(ScriptedController(), pin=10)
    with pytest.raises(ValueError):
        mouth.set_voice(voice="en-gb")
    mouth.set_voice(voice="af_bella")
    assert mouth.voice["voice"] == "af_bella"


@pytest.mark.skipif(not os.getenv("MOUTH_REAL_KOKORO"),
                    reason="set MOUTH_REAL_KOKORO=1 to run the real Kokoro model")
def test_real_kokoro_produces_audible_speech():
    wav = kokoro_tts("Hello, I am Laika, and this is a real test of my voice.",
                     {"voice": "af_heart", "speed": 150})
    assert len(to_pcm8(wav)) > RATE // 2    # at least half a second of real audio
