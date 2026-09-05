"""Ears pipeline: UDP packet assembly, utterance segmentation, wake matching,
intent detection, persistence and the voice.phrase event. The transcriber is
faked so no model download is needed; one opt-in test runs real whisper on
the synthesized fixtures (EARS_REAL_MODEL=1)."""
import os
import struct
import threading
import time
import wave
from pathlib import Path

import pytest

from app.ears import (PACKET_HEADER, EarsService, WhisperTranscriber,
                      collapse_repeats, detect_intent, match_wake)
from app.models import init_db

FIXTURES = Path(__file__).parent / "fixtures"


class CapturingBinder:
    def __init__(self):
        self.events = []

    def trigger(self, event, data=None):
        self.events.append((event, data))
        return []


class FakeTranscriber:
    model_name = "fake"
    loaded = True

    def __init__(self, text):
        self.text = text
        self.calls = []

    def transcribe(self, pcm, sample_rate):
        self.calls.append((len(pcm), sample_rate))
        return self.text


def setup_module(module):
    init_db()


@pytest.mark.parametrize("text,expected", [
    ("Hey Laika, sit down.", "sit down"),
    ("Hey Laker, sit down.", "sit down"),
    ("hey leica lie down", "lie down"),
    ("Laika come here", "come here"),
    ("Okay Lycra, stop!", "stop"),
    ("Hey, like up, sit down.", "sit down"),
    ("Hey, Laika, sit down.", "sit down"),
    ("The weather is nice today.", None),
    ("I like a good dog", None),
    ("", None),
])
def test_wake_matching(text, expected):
    assert match_wake(text) == expected


def test_collapse_repeats_keeps_two_copies():
    assert collapse_repeats("Hello. " * 40) == "Hello. Hello."
    assert collapse_repeats("Hey Laika, hello. " * 5) == "Hey Laika, hello. Hey Laika, hello."
    assert collapse_repeats("no no no no stop") == "no no stop"
    assert collapse_repeats("Hey Laika, hello. Hey Laika, hello.") == "Hey Laika, hello. Hey Laika, hello."
    assert collapse_repeats("the weather is nice today") == "the weather is nice today"
    assert collapse_repeats("") == ""


def test_intents():
    assert detect_intent("sit down") == "sit"
    assert detect_intent("please lie down now") == "rest"
    assert detect_intent("stop") == "stop"
    assert detect_intent("who's a good girl") == "greet"
    assert detect_intent("tell me a joke") is None


def _tone_packet(seq, amplitude, samples=320):
    pcm = struct.pack("<%dh" % samples, *([amplitude, -amplitude] * (samples // 2)))
    return PACKET_HEADER.pack(seq) + pcm


def test_udp_segmentation_emits_wake_event_and_persists():
    clock = [100.0]
    binder = CapturingBinder()
    fake = FakeTranscriber("Hey Laika, sit down.")
    ears = EarsService(binder, transcriber=fake, sample_rate=16000,
                       silence_s=0.5, min_utterance_s=0.1,
                       clock=lambda: clock[0])
    # 1 s of "speech" in 20 ms packets, then quiet packets past the silence gap.
    seq = 0
    for _ in range(50):
        ears.feed_packet(_tone_packet(seq, 3000)); seq += 1; clock[0] += 0.02
    for _ in range(40):
        ears.feed_packet(_tone_packet(seq, 5)); seq += 1; clock[0] += 0.02
    assert ears.stats["packets"] == 90 and ears.stats["dropped"] == 0
    # The worker thread is not running in this test: drain the queue directly.
    pcm, rate, duration, _ = ears._queue.popleft()
    row = ears._process(pcm, rate, duration)
    assert row["wake"] is True and row["intent"] == "sit"
    event, payload = binder.events[0]
    assert event == "voice.phrase" and payload["command"] == "sit down"
    assert payload["intent"] == "sit" and payload["transcriptId"] == row["id"]
    assert payload["latencyS"] is not None
    assert ears.transcripts(1)[0]["text"] == "Hey Laika, sit down."
    assert fake.calls[0][1] == 16000


def test_dropped_packets_are_counted():
    ears = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"))
    ears.feed_packet(_tone_packet(1, 5))
    ears.feed_packet(_tone_packet(5, 5))
    assert ears.stats["dropped"] == 3


def test_wake_without_motion_intent_starts_a_conversation():
    init_db()
    binder = CapturingBinder()
    ears = EarsService(binder, transcriber=FakeTranscriber("Hey Laika, what time is it?"))
    row = ears._process(b"\x00\x00" * 16000, 16000, 1.0)
    assert row["wake"] is True and row["intent"] is None
    assert binder.events[-1][0] == "voice.wake"
    assert binder.events[-1][1]["command"] == "what time is it"


def test_listen_hands_the_next_utterance_to_the_caller_and_mute_drops_packets():
    init_db()
    binder = CapturingBinder()
    ears = EarsService(binder, transcriber=FakeTranscriber("Hey Laika, sit"), energy_floor=200)

    def speak_later():
        time.sleep(0.15)
        ears._process(b"\x00\x00" * 16000, 16000, 1.0)

    threading.Thread(target=speak_later).start()
    text, latency = ears.listen(2.0, 5.0)
    assert text == "Hey Laika, sit" and latency is not None
    assert binder.events == []                    # no wake, no intent: it was the request
    ears.mute(5.0)
    before = ears.stats["packets"]
    ears.feed_packet(_tone_packet(1, 5000))
    assert ears.stats["packets"] == before + 1 and not ears._speaking
    assert ears.status()["mutedForS"] > 4


def test_wake_model_hears_everything_and_the_accurate_one_hears_the_request():
    init_db()
    binder = CapturingBinder()
    accurate = FakeTranscriber("Hey Laika, sit")
    fast = FakeTranscriber("Hey Laika, sit")
    ears = EarsService(binder, transcriber=accurate, wake_transcriber=fast)
    ears._process(b"\x00\x00" * 16000, 16000, 1.0)
    assert len(fast.calls) == 1 and accurate.calls == []
    assert ears.status()["wakeModel"] == "fake"

    def speak_later():
        time.sleep(0.1)
        ears._process(b"\x00\x00" * 16000, 16000, 1.0)

    threading.Thread(target=speak_later).start()
    text, _ = ears.listen(2.0, 5.0)
    assert text == "Hey Laika, sit" and len(accurate.calls) == 1 and len(fast.calls) == 1
    ears.set_vocabulary(phrases=["Laika"])
    assert fast.prompt == accurate.prompt


def test_listening_utterance_jumps_the_queue():
    ears = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"),
                       silence_s=0.5, min_utterance_s=0.1, clock=lambda: 0.0)
    ears._queue.append((b"old", 16000, 1.0, 0.0))
    ears._listen = {"deadline": 99, "max": 5.0, "event": threading.Event(), "text": None, "latency": None}
    ears._utterance = bytearray(b"\x00\x00" * 8000)
    ears._utterance_started = 0.0
    ears._speaking = True
    ears._finish_utterance_locked()
    assert ears._queue[0][0] != b"old"


def test_listen_window_closes_when_nobody_speaks():
    ears = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"))
    ears._clock = lambda: 1000.0
    pending_started = threading.Thread(target=lambda: None)
    result = {}

    def run():
        result["value"] = ears.listen(0.5, 1.0)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.1)
    ears._clock = lambda: 1001.0            # the window has passed
    ears.flush_if_silent()
    t.join(3)
    assert result["value"] == (None, None)


def test_non_wake_utterance_persists_without_event():
    binder = CapturingBinder()
    ears = EarsService(binder, transcriber=FakeTranscriber("The weather is nice."))
    row = ears.feed_wav(FIXTURES / "no_wake.wav")
    assert row["wake"] is False and row["intent"] is None
    assert binder.events == []


def test_record_captures_the_live_stream_without_firing_the_event():
    init_db()
    binder = CapturingBinder()
    ears = EarsService(binder, transcriber=FakeTranscriber("Hey Laika, hello."),
                       energy_floor=200)

    def feed():
        for seq in range(20):
            ears.feed_packet(_tone_packet(seq, 50))
            time.sleep(0.02)

    feeder = threading.Thread(target=feed)
    feeder.start()
    result = ears.record(0.5)
    feeder.join()
    assert result["wake"] is True and result["intent"] == "greet"
    assert result["text"] == "Hey Laika, hello." and result["durationS"] > 0
    assert result["peak"] == 50 and result["floor"] == 200
    assert binder.events == []
    assert ears.transcripts(1)[0]["at"].endswith("+00:00")


def test_record_without_audio_reports_it():
    ears = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"))
    result = ears.record(0.5)
    assert result["text"] == "" and "no audio" in result["error"]


def test_vocabulary_extends_prompt_and_name_spellings_and_persists():
    init_db()
    transcriber = FakeTranscriber("Hey lake up, sit")
    ears = EarsService(CapturingBinder(), transcriber=transcriber)
    view = ears.set_vocabulary(phrases=["Laika", "sit down"], variants=["Lake up", "lake up"])
    assert view["prompt"].endswith("Laika. sit down.") and transcriber.prompt == view["prompt"]
    assert view["variants"] == ["lake up"]
    assert match_wake("Hey lake up, sit", variants=view["variants"]) == "sit"
    row = ears._process(b"\x00\x00" * 16000, 16000, 1.0)
    assert row["wake"] is True and row["intent"] == "sit"
    fresh = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"))
    fresh._load_vocabulary()
    assert fresh.vocabulary == {"phrases": ["Laika", "sit down"], "variants": ["lake up"]}
    with pytest.raises(ValueError):
        ears.set_vocabulary(variants="nope")


def test_wake_phrase_is_a_setting_and_drives_the_prompt():
    init_db()
    ears = EarsService(CapturingBinder(), transcriber=FakeTranscriber("Okay Bittle, stop"))
    view = ears.set_vocabulary(wake_phrase="Okay,  Bittle")
    assert view["wakePhrase"] == "okay bittle" and view["defaultWakePhrase"] == "hey laika"
    assert view["prompt"].startswith("Okay Bittle, sit. Okay Bittle, come here.")
    row = ears._process(b"\x00\x00" * 16000, 16000, 1.0)
    assert row["wake"] is True and row["intent"] == "stop"
    fresh = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"))
    fresh._load_vocabulary()
    assert fresh.wake_phrase == "okay bittle"
    with pytest.raises(ValueError):
        ears.set_vocabulary(wake_phrase="   ")


def test_feed_wav_rejects_stereo(tmp_path):
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\0\0\0\0" * 100)
    with pytest.raises(ValueError):
        EarsService(CapturingBinder(), transcriber=FakeTranscriber("x")).feed_wav(path)


def test_status_shape():
    ears = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"),
                       udp_port=5555, wake_phrase="hey laika")
    status = ears.status()
    assert status["udpPort"] == 5555 and status["streaming"] is False
    assert status["wakePhrase"] == "hey laika" and status["model"] == "fake"
    assert status["level"] == {"rms": 0, "peak": 0, "median": 0,
                               "floor": 300, "speaking": False}


def test_dc_offset_is_not_loudness():
    ears = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"),
                       energy_floor=200)
    silent_with_offset = struct.pack("<320h", *([1700] * 320))
    ears.feed_pcm(silent_with_offset)
    assert ears.status()["level"]["rms"] == 0 and not ears._speaking
    tone_with_offset = struct.pack("<320h", *([1700 + 800, 1700 - 800] * 160))
    ears.feed_pcm(tone_with_offset)
    level = ears.status()["level"]
    assert level["rms"] == 800 and level["peak"] == 800 and level["speaking"]


@pytest.mark.skipif(not os.getenv("EARS_REAL_MODEL"),
                    reason="set EARS_REAL_MODEL=1 to run whisper on the fixtures")
def test_real_whisper_on_synthesized_clip():
    binder = CapturingBinder()
    ears = EarsService(binder, transcriber=WhisperTranscriber("base"))
    row = ears.feed_wav(FIXTURES / "hey_laika_sit.wav")
    assert row["wake"] is True and row["intent"] == "sit"
    row = ears.feed_wav(FIXTURES / "no_wake.wav")
    assert row["wake"] is False
