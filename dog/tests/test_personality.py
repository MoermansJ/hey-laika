from app.choreography import ChoreographyLibrary
from app.models import init_db
from app.personality_engine import PersonalityEngine


def setup_module(module):
    init_db()


def test_initial_state_shape():
    state = PersonalityEngine().get_state()
    for key in ("energy", "happiness", "boredom", "curiosity", "mood"):
        assert key in state


def test_interaction_changes_state():
    engine = PersonalityEngine()
    before = engine.get_state()
    after = engine.record_interaction("play")
    assert after["boredom"] <= before["boredom"]


def test_unknown_interaction_raises():
    import pytest
    with pytest.raises(ValueError):
        PersonalityEngine().record_interaction("teleport")


def test_mock_decision_is_valid():
    engine = PersonalityEngine()
    available = ChoreographyLibrary().names()
    decision = engine.get_next_behavior(available)
    assert decision["behavior"] in available
    assert decision["reason"]
    assert decision["source"] == "mock"  # DECISION_ENGINE=mock in tests


def test_claude_engine_without_key_raises(monkeypatch):
    from app.config import Config
    from app.personality_engine import MissingCredentialsError

    monkeypatch.setattr(Config, "DECISION_ENGINE", "claude")
    monkeypatch.setattr(Config, "ANTHROPIC_API_KEY", "")
    import pytest
    with pytest.raises(MissingCredentialsError):
        PersonalityEngine().get_next_behavior(["sit"])


def test_ollama_engine_uses_local_decision(monkeypatch):
    import app.voice
    from app.config import Config

    monkeypatch.setattr(Config, "DECISION_ENGINE", "ollama")
    calls = {}

    def fake_query(prompt, model=None, temperature=0.7, max_tokens=120,
                   system=None, format_json=False):
        calls["system"] = system
        calls["format_json"] = format_json
        return '{"behavior": "sit", "reason": "resting my paws"}', None

    monkeypatch.setattr(app.voice, "query_ollama", fake_query)
    decision = PersonalityEngine().get_next_behavior(["sit", "stretch"])
    assert decision["behavior"] == "sit"
    assert decision["source"] == "ollama"
    assert calls["format_json"] is True
    assert "mind of Bittle" in calls["system"]  # decision prompt, not the voice persona


def test_ollama_engine_falls_back_to_mock_on_failure(monkeypatch):
    import app.voice
    from app.config import Config

    monkeypatch.setattr(Config, "DECISION_ENGINE", "ollama")
    monkeypatch.setattr(app.voice, "query_ollama",
                        lambda *a, **k: (None, "Ollama unreachable"))
    available = ChoreographyLibrary().names()
    decision = PersonalityEngine().get_next_behavior(available)
    assert decision["behavior"] in available
    assert decision["source"] == "ollama_fallback"


def test_ollama_engine_rejects_unlisted_behavior(monkeypatch):
    import app.voice
    from app.config import Config

    monkeypatch.setattr(Config, "DECISION_ENGINE", "ollama")
    monkeypatch.setattr(app.voice, "query_ollama",
                        lambda *a, **k: ('{"behavior": "backflip"}', None))
    decision = PersonalityEngine().get_next_behavior(["sit"])
    assert decision["behavior"] == "sit"  # fell back to mock over ["sit"]
    assert decision["source"] == "ollama_fallback"
