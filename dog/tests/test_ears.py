"""Ears pipeline: UDP packet assembly, utterance segmentation, wake matching,
intent detection, persistence and the voice.phrase event. The transcriber is
faked so no model download is needed; one opt-in test runs real whisper on
the synthesized fixtures (EARS_REAL_MODEL=1)."""
import os
import struct
import wave
from pathlib import Path

import pytest

from app.ears import (PACKET_HEADER, EarsService, WhisperTranscriber,
                      detect_intent, match_wake)
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
    ("The weather is nice today.", None),
    ("I like a good dog", None),
    ("", None),
])
def test_wake_matching(text, expected):
    assert match_wake(text) == expected


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
    assert binder.events == [("voice.phrase", {
        "text": "Hey Laika, sit down.", "command": "sit down",
        "intent": "sit", "transcriptId": row["id"]})]
    assert ears.transcripts(1)[0]["text"] == "Hey Laika, sit down."
    assert fake.calls[0][1] == 16000


def test_dropped_packets_are_counted():
    ears = EarsService(CapturingBinder(), transcriber=FakeTranscriber("x"))
    ears.feed_packet(_tone_packet(1, 5))
    ears.feed_packet(_tone_packet(5, 5))
    assert ears.stats["dropped"] == 3


def test_non_wake_utterance_persists_without_event():
    binder = CapturingBinder()
    ears = EarsService(binder, transcriber=FakeTranscriber("The weather is nice."))
    row = ears.feed_wav(FIXTURES / "no_wake.wav")
    assert row["wake"] is False and row["intent"] is None
    assert binder.events == []


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


@pytest.mark.skipif(not os.getenv("EARS_REAL_MODEL"),
                    reason="set EARS_REAL_MODEL=1 to run whisper on the fixtures")
def test_real_whisper_on_synthesized_clip():
    binder = CapturingBinder()
    ears = EarsService(binder, transcriber=WhisperTranscriber("base"))
    row = ears.feed_wav(FIXTURES / "hey_laika_sit.wav")
    assert row["wake"] is True and row["intent"] == "sit"
    row = ears.feed_wav(FIXTURES / "no_wake.wav")
    assert row["wake"] is False
