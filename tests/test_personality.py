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
    assert decision["source"] == "mock"  # no API key in tests
