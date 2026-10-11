"""AGENT-03: run-log outcome / sensor_delta schema, migration and CRUD."""
import json
import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect, text

from app.behavior_store import (BehaviorRunLogEntry, BehaviorStore,
                                OutcomeEvaluation, migrate_run_log)

# framework_behavior_runs exactly as it shipped before provenance/outcome.
LEGACY_RUNS_DDL = """
CREATE TABLE framework_behavior_runs (
    id VARCHAR(36) PRIMARY KEY,
    behavior_name VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL,
    priority INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL,
    detail TEXT NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME
)
"""


@pytest.fixture
def legacy_engine():
    path = os.path.join(tempfile.mkdtemp(), "legacy_runs.db")
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text(LEGACY_RUNS_DDL))
        conn.execute(text(
            "INSERT INTO framework_behavior_runs VALUES "
            "('old-1', 'idle_sit', 'event.idle.timeout', 5, 'complete', '', "
            "'2026-01-01 10:00:00', '2026-01-01 10:00:03')"))
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def store():
    s = BehaviorStore()
    s.init()
    return s


def _columns(eng):
    return {c["name"] for c in inspect(eng).get_columns("framework_behavior_runs")}


def _indexes(eng):
    return {i["name"] for i in inspect(eng).get_indexes("framework_behavior_runs")}


# ---- migration ---------------------------------------------------------------

def test_migration_adds_outcome_columns_and_index(legacy_engine):
    assert "outcome" not in _columns(legacy_engine)
    added = migrate_run_log(legacy_engine)
    assert added == ["cause_json", "preempted_by", "outcome", "sensor_delta"]
    cols = _columns(legacy_engine)
    assert {"outcome", "sensor_delta", "cause_json", "preempted_by"} <= cols
    assert "ix_framework_runs_outcome" in _indexes(legacy_engine)


def test_migration_is_idempotent(legacy_engine):
    migrate_run_log(legacy_engine)
    before = (_columns(legacy_engine), _indexes(legacy_engine))
    assert migrate_run_log(legacy_engine) == []
    assert migrate_run_log(legacy_engine) == []
    assert (_columns(legacy_engine), _indexes(legacy_engine)) == before


def test_old_rows_still_readable_after_migration(legacy_engine):
    migrate_run_log(legacy_engine)
    with legacy_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, behavior_name, status, cause_json, outcome, sensor_delta "
            "FROM framework_behavior_runs WHERE id = 'old-1'")).one()
    assert row.id == "old-1" and row.behavior_name == "idle_sit"
    assert row.status == "complete"
    assert row.cause_json == "null"  # column default fills legacy rows
    assert row.outcome is None and row.sensor_delta is None


def test_store_init_twice_is_safe(store):
    store.init()
    store.init()
    from app.models import engine
    assert {"outcome", "sensor_delta"} <= _columns(engine)
    assert "ix_framework_runs_outcome" in _indexes(engine)


# ---- dataclasses -------------------------------------------------------------

def test_outcome_evaluation_accepts_camel_and_snake_case():
    camel = OutcomeEvaluation.from_dict({
        "success": True, "confidence": 0.87, "reason": "centered",
        "evaluatorVersion": "2.1", "evaluatedAt": "2026-10-11T12:00:00Z"})
    snake = OutcomeEvaluation.from_dict({
        "success": True, "confidence": 0.87, "reason": "centered",
        "evaluator_version": "2.1", "evaluated_at": "2026-10-11T12:00:00Z"})
    assert camel == snake
    assert camel.evaluator_version == "2.1"


def test_outcome_evaluation_allows_null_success():
    o = OutcomeEvaluation.from_dict({"success": None, "reason": "No goal declared"})
    assert o.success is None and o.confidence == 0.0
    assert o.evaluator_version == "1.0"


@pytest.mark.parametrize("bad", [
    {"success": "yes"},
    {"success": True, "confidence": 1.5},
    {"success": True, "confidence": -0.1},
    "not-a-dict",
])
def test_outcome_evaluation_rejects_invalid(bad):
    with pytest.raises(ValueError):
        OutcomeEvaluation.from_dict(bad)


# ---- CRUD on the real store --------------------------------------------------

def test_new_run_has_null_outcome(store):
    run_id = store.log_start("idle_sit", "agent", 3, cause={"type": "agent"})
    run = next(r for r in store.recent_runs(50) if r["id"] == run_id)
    assert run["outcome"] is None and run["sensorDelta"] is None
    entry = store.run_entry(run_id)
    assert isinstance(entry, BehaviorRunLogEntry)
    assert entry.outcome is None and entry.sensor_delta is None
    assert entry.cause == {"type": "agent"}


def test_set_outcome_roundtrip(store):
    run_id = store.log_start("idle_sit", "agent", 3,
                             cause={"type": "agent", "goal": "look_upward"})
    store.log_end(run_id, "complete")
    delta = {"pitch": {"before": 0.0, "after": 12.5}}
    result = store.set_outcome(run_id, {
        "success": True, "confidence": 0.87,
        "reason": "Motion now centered vertically in frame",
        "evaluatorVersion": "1.0"}, sensor_delta=delta)
    assert result["outcome"]["success"] is True
    assert result["outcome"]["confidence"] == 0.87
    assert result["sensorDelta"] == delta
    assert result["status"] == "complete"  # untouched by the outcome write

    entry = store.run_entry(run_id)
    assert entry.outcome == OutcomeEvaluation(
        success=True, confidence=0.87,
        reason="Motion now centered vertically in frame",
        evaluator_version="1.0")
    assert entry.sensor_delta == delta


def test_set_outcome_is_idempotent(store):
    run_id = store.log_start("idle_rest", "agent", 3)
    payload = {"success": False, "confidence": 0.4, "reason": "no change"}
    first = store.set_outcome(run_id, payload, sensor_delta={"d": 1})
    second = store.set_outcome(run_id, payload, sensor_delta={"d": 1})
    third = store.set_outcome(run_id, OutcomeEvaluation.from_dict(payload))
    assert first == second == third  # sensor_delta kept when omitted
    from app.models import engine
    with engine.connect() as conn:
        raw = conn.execute(text(
            "SELECT outcome FROM framework_behavior_runs WHERE id = :id"),
            {"id": run_id}).scalar_one()
    assert json.loads(raw)["success"] is False  # stored as valid JSON


def test_set_outcome_last_write_wins(store):
    run_id = store.log_start("idle_rest", "agent", 3)
    store.set_outcome(run_id, {"success": False, "confidence": 0.2, "reason": "a"})
    store.set_outcome(run_id, {"success": True, "confidence": 0.9, "reason": "b"})
    assert store.run_entry(run_id).outcome.success is True
    assert store.run_entry(run_id).outcome.reason == "b"


def test_set_outcome_unknown_run_returns_none(store):
    assert store.set_outcome("no-such-run", {"success": True}) is None
    assert store.run_entry("no-such-run") is None


def test_set_outcome_rejects_bad_sensor_delta(store):
    run_id = store.log_start("idle_sit", "agent", 3)
    with pytest.raises(ValueError):
        store.set_outcome(run_id, {"success": True}, sensor_delta=[1, 2])
    assert store.run_entry(run_id).outcome is None  # nothing half-written


def test_runs_with_outcome_filters(store):
    with_outcome = store.log_start("rest_now", "agent", 3)
    without = store.log_start("rest_now", "agent", 3)
    manual = store.log_start("rest_now", "manual", 2)
    store.set_outcome(with_outcome, {"success": True, "confidence": 1.0})
    store.set_outcome(manual, {"success": False})
    ids = {r["id"] for r in store.runs_with_outcome(behavior_name="rest_now",
                                                    source="agent")}
    assert with_outcome in ids
    assert without not in ids and manual not in ids
    all_ids = {r["id"] for r in store.runs_with_outcome(behavior_name="rest_now")}
    assert {with_outcome, manual} <= all_ids
