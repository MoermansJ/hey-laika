"""Mouth: WAV -> 8 kHz 8-bit conversion, chunking and pacing against the
firmware protocol (XWp / XWa / XWq), with a scripted controller."""
import io
import wave

import pytest

from app.mouth import CHUNK_BYTES, RATE, MouthService, to_pcm8, tone_wav


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
