"""Tests for the voice MVP endpoints (/sound, /voice/demo, /voice/speak)."""
import pytest

import app.voice as voice
from app.app import app, bittle
from app.voice import BEEP_PATTERNS


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise voice.requests.exceptions.HTTPError(f"HTTP {self.status_code}")


def test_sound_patterns_reach_buzzer(client):
    for pattern, command in BEEP_PATTERNS.items():
        resp = client.post("/api/robots/bittle-1/sound", json={"pattern": pattern})
        body = resp.get_json()
        assert resp.status_code == 200 and body["success"] is True
        assert bittle.last_command == command


def test_sound_unknown_pattern_400(client):
    resp = client.post("/api/robots/bittle-1/sound", json={"pattern": "airhorn"})
    assert resp.status_code == 400


def test_voice_demo_full_chain(client, monkeypatch):
    def fake_post(url, json=None, timeout=None):
        assert url.endswith("/api/generate")
        assert json["model"] == "llama3.2:1b"
        assert json["options"]["num_predict"] == 120
        assert "Laika" in json["system"]
        return FakeResponse({"response": "Woof! Two plus two is four."})

    monkeypatch.setattr(voice.requests, "post", fake_post)
    resp = client.post("/api/robots/bittle-1/voice/demo",
                       json={"input": "What is 2+2?"})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["response"] == "Woof! Two plus two is four."
    assert body["transcribedText"] == "What is 2+2?"
    assert body["audioUrl"] is None
    assert set(body["latencySec"]) == {"wakeWord", "recording", "ollama",
                                       "tts", "total"}
    # Wake + recording + ready beeps all reached the (mock) buzzer.
    recent = [e["command"] for e in bittle.command_log[-3:]]
    assert recent == [BEEP_PATTERNS["beep_wake_word"],
                      BEEP_PATTERNS["recording"], BEEP_PATTERNS["ready"]]


def test_voice_demo_requires_input(client):
    assert client.post("/api/robots/bittle-1/voice/demo",
                       json={}).status_code == 400


def test_voice_demo_502_when_ollama_down(client, monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise voice.requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(voice.requests, "post", fake_post)
    resp = client.post("/api/robots/bittle-1/voice/demo",
                       json={"input": "hello"})
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "llm_unavailable"


def test_speak_503_without_api_key(client):
    resp = client.post("/api/robots/bittle-1/voice/speak",
                       json={"text": "hello"})
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "tts_not_configured"


def test_voice_health_reports_ollama_state(client, monkeypatch):
    monkeypatch.setattr(voice.requests, "get", lambda url, timeout=None:
                        FakeResponse({"models": [{"name": "llama3.2:1b"}]}))
    resp = client.get("/api/robots/bittle-1/voice/health")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["ollama"]["reachable"] is True
    assert body["ollama"]["modelAvailable"] is True
    assert body["ttsConfigured"] is False
