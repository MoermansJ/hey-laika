"""Storage for the behavior framework: behaviors, bindings, run log.

Behaviors are named declarative step sequences (data, not code); bindings
map lifecycle events to behaviors with a priority. Seeded builtins use
REAL firmware commands (the planning doc's kbktS/kbktL do not exist —
sit is 'ksit', lie down is 'krest').

Priority convention (docs/design/BEHAVIOR_FRAMEWORK_BRIEF.md, LOWER wins):
  1 safety · 2 manual · 3 agent · 4 lifecycle · 5 idle
"""
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, Text, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import Config
from app.models import Base, SessionLocal, engine, iso_utc, utcnow

PRIORITY_SAFETY = 1
PRIORITY_MANUAL = 2
PRIORITY_AGENT = 3
PRIORITY_LIFECYCLE = 4
PRIORITY_IDLE = 5


class StoredBehavior(Base):
    __tablename__ = "framework_behaviors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    steps_json: Mapped[str] = mapped_column(Text)  # [{command, settleS}, ...]
    interruptible: Mapped[bool] = mapped_column(default=True)
    cooldown_s: Mapped[int] = mapped_column(default=0)
    is_builtin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "steps": json.loads(self.steps_json),
            "interruptible": self.interruptible, "cooldownS": self.cooldown_s,
            "isBuiltin": self.is_builtin,
        }


class Binding(Base):
    __tablename__ = "framework_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event: Mapped[str] = mapped_column(String(64))  # robot.online, idle.timeout, ...
    filter_json: Mapped[str] = mapped_column(Text, default="null")
    behavior_name: Mapped[str] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(default=PRIORITY_LIFECYCLE)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "event": self.event,
            "filter": json.loads(self.filter_json),
            "behavior": self.behavior_name, "priority": self.priority,
            "enabled": self.enabled,
        }


class BehaviorRun(Base):
    __tablename__ = "framework_behavior_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    behavior_name: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64))  # event.robot.online, manual, agent
    priority: Mapped[int] = mapped_column(default=PRIORITY_MANUAL)
    status: Mapped[str] = mapped_column(String(16))  # running|complete|interrupted|failed
    detail: Mapped[str] = mapped_column(Text, default="")
    # Provenance: what caused this run — {"type": "event", "event": ...,
    # "payload": ..., "bindingId": ...} | {"type": "manual"|"agent", ...}
    cause_json: Mapped[str] = mapped_column(Text, default="null")
    # Run id of the higher-priority run that interrupted this one, or the
    # literal "manual_stop" for an explicit arbiter stop.
    preempted_by: Mapped[str] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    ended_at: Mapped[datetime] = mapped_column(nullable=True)
    # Agent tool composition (AGENT-03): outcome evaluation written back by
    # the Java orchestrator after the run, and the raw before/after sensor
    # changes it judged. Both JSON text, NULL until the orchestrator syncs.
    outcome_json: Mapped[str] = mapped_column("outcome", Text, nullable=True)
    sensor_delta_json: Mapped[str] = mapped_column("sensor_delta", Text,
                                                   nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "behavior": self.behavior_name, "source": self.source,
            "priority": self.priority, "status": self.status, "detail": self.detail,
            "cause": json.loads(self.cause_json or "null"),
            "preemptedBy": self.preempted_by,
            "startedAt": iso_utc(self.started_at),
            "endedAt": iso_utc(self.ended_at),
            "outcome": json.loads(self.outcome_json) if self.outcome_json else None,
            "sensorDelta": (json.loads(self.sensor_delta_json)
                            if self.sensor_delta_json else None),
        }


@dataclass
class OutcomeEvaluation:
    """Outcome of a run as judged by the Java orchestrator's
    GoalOutcomeEvaluator. ``success`` is None when the goal could not be
    evaluated (no goal declared / no checker registered)."""
    success: bool | None
    confidence: float = 0.0
    reason: str = ""
    evaluator_version: str = "1.0"
    evaluated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "OutcomeEvaluation":
        """Accept both snake_case and the orchestrator's camelCase keys."""
        if not isinstance(data, dict):
            raise ValueError("outcome must be an object")
        success = data.get("success")
        if success is not None and not isinstance(success, bool):
            raise ValueError("outcome.success must be a boolean or null")
        confidence = float(data.get("confidence", 0.0) or 0.0)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("outcome.confidence must be between 0 and 1")
        return cls(
            success=success,
            confidence=confidence,
            reason=str(data.get("reason") or ""),
            evaluator_version=str(data.get("evaluator_version")
                                  or data.get("evaluatorVersion") or "1.0"),
            evaluated_at=data.get("evaluated_at") or data.get("evaluatedAt"),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BehaviorRunLogEntry:
    """Typed view of one framework_behavior_runs row, including the agent
    outcome fields. Rows written before AGENT-03 read back with
    ``outcome``/``sensor_delta`` = None."""
    id: str
    behavior_name: str
    source: str
    priority: int
    status: str
    detail: str = ""
    cause: Any = None
    preempted_by: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    outcome: OutcomeEvaluation | None = None
    sensor_delta: dict | None = field(default=None)

    @classmethod
    def from_row(cls, row: "BehaviorRun") -> "BehaviorRunLogEntry":
        outcome = (OutcomeEvaluation.from_dict(json.loads(row.outcome_json))
                   if row.outcome_json else None)
        return cls(
            id=row.id, behavior_name=row.behavior_name, source=row.source,
            priority=row.priority, status=row.status, detail=row.detail or "",
            cause=json.loads(row.cause_json or "null"),
            preempted_by=row.preempted_by,
            started_at=iso_utc(row.started_at), ended_at=iso_utc(row.ended_at),
            outcome=outcome,
            sensor_delta=(json.loads(row.sensor_delta_json)
                          if row.sensor_delta_json else None),
        )


def migrate_run_log(bind=None) -> list[str]:
    """Bring an existing framework_behavior_runs table up to the current
    schema in place. ``create_all`` never alters existing tables, so columns
    added after a database was created are ALTERed in here. Idempotent:
    every step checks first, so running it any number of times is safe.
    Returns the names of the columns it added (empty when up to date)."""
    bind = bind if bind is not None else engine
    existing = {c["name"] for c in
                inspect(bind).get_columns("framework_behavior_runs")}
    added = []
    with bind.begin() as conn:
        for name, ddl in _RUN_LOG_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE framework_behavior_runs "
                                  f"ADD COLUMN {name} {ddl}"))
                added.append(name)
        # Goal/outcome queries (pattern rollup) only ever look at runs that
        # already carry an outcome, so keep the index partial and small.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_framework_runs_outcome "
            "ON framework_behavior_runs (source, behavior_name, started_at) "
            "WHERE outcome IS NOT NULL"))
    return added


# (column, DDL) pairs added to framework_behavior_runs after its first release.
_RUN_LOG_COLUMNS = [
    ("cause_json", "TEXT DEFAULT 'null'"),
    ("preempted_by", "VARCHAR(36)"),
    ("outcome", "TEXT"),
    ("sensor_delta", "TEXT"),
]


# ---- seeds (idempotent; keyed by name) -------------------------------------

SEED_BEHAVIORS = [
    {
        "name": "startup_greeting",
        "description": "Go-mode announcement when the robot comes online",
        "steps": [
            {"command": "kup", "settleS": 2.5},
            {"command": "kstr", "settleS": 5.0},
            {"command": "kup", "settleS": 2.0},
            {"command": "b 14 8 18 8 21 8 26 4", "settleS": 1.5},
            {"command": "kbalance", "settleS": 2.0},
        ],
        "interruptible": True, "cooldownS": 60,
    },
    {
        "name": "idle_sit",
        "description": "Settle into a sit after a quiet minute",
        "steps": [{"command": "ksit", "settleS": 3.0}],
        "interruptible": True, "cooldownS": 0,
    },
    {
        "name": "idle_rest",
        "description": "Lie down after two quiet minutes",
        "steps": [{"command": "krest", "settleS": 3.0}],
        "interruptible": True, "cooldownS": 0,
    },
    {
        "name": "rest_now",
        "description": "Safety: battery critically low — lie down",
        "steps": [{"command": "kup", "settleS": 1.5},
                  {"command": "krest", "settleS": 3.0}],
        "interruptible": False, "cooldownS": 120,
    },
    {
        "name": "power_nap",
        "description": "Battery saver: lie down and switch the servos off",
        "steps": [{"command": "krest", "settleS": 3.0},
                  {"command": "d", "settleS": 1.0}],
        "interruptible": True, "cooldownS": 0,
    },
    {
        "name": "acknowledgment",
        "description": "Quick chirp + attentive stand (wake-word ack)",
        "steps": [{"command": "b 21 8 26 8", "settleS": 0.5},
                  {"command": "kup", "settleS": 1.5}],
        "interruptible": True, "cooldownS": 5,
    },
    {
        "name": "leash_warn",
        "description": "Leash stretching: stop, sit, chirp for the owner",
        "steps": [{"command": "ksit", "settleS": 2.0},
                  {"command": "b 21 8 18 8", "settleS": 0.5}],
        "interruptible": True, "cooldownS": 10,
    },
    {
        "name": "leash_far",
        "description": "Leash at its end: insistent double chirp, stay put",
        "steps": [{"command": "b 26 8 26 8 21 4", "settleS": 0.5}],
        "interruptible": True, "cooldownS": 8,
    },
    {
        "name": "obstacle_stop",
        "description": "Safety: something is right ahead — stop and step back",
        "steps": [{"command": "kup", "settleS": 1.0},
                  {"command": "kbkF 1", "settleS": 2.0},
                  {"command": "kup", "settleS": 1.0}],
        "interruptible": True, "cooldownS": 2,
    },
    {
        "name": "error_halt",
        "description": "Safety: navigation error — stand still and ask for help",
        "steps": [{"command": "kup", "settleS": 1.5},
                  {"command": "b 10 8 8 8", "settleS": 0.5}],
        "interruptible": True, "cooldownS": 3,
    },
]

SEED_BINDINGS = [
    {"event": "robot.online", "filter": None,
     "behavior": "startup_greeting", "priority": PRIORITY_LIFECYCLE, "enabled": True},
    # Thresholds seed from IDLE_SIT_S / IDLE_REST_S (config.py); once the
    # bindings exist the Behavior Lab editor owns them.
    {"event": "idle.timeout", "filter": {"seconds": Config.IDLE_SIT_S},
     "behavior": "idle_sit", "priority": PRIORITY_IDLE, "enabled": True},
    {"event": "idle.timeout", "filter": {"seconds": Config.IDLE_REST_S},
     "behavior": "idle_rest", "priority": PRIORITY_IDLE, "enabled": True},
    {"event": "battery.low", "filter": {"pct": 5},
     "behavior": "rest_now", "priority": PRIORITY_SAFETY, "enabled": True},
    # Host-decided fall recovery: ships disabled until tuned live.
    {"event": "exception.report", "filter": {"code": "flipped"},
     "behavior": "acknowledgment", "priority": PRIORITY_SAFETY, "enabled": False},
    # Proximity leash (LeashService emits these only while the leash is
    # enabled). leash.lost reuses the safety rest behavior.
    {"event": "leash.warn", "filter": None,
     "behavior": "leash_warn", "priority": PRIORITY_LIFECYCLE, "enabled": True},
    {"event": "leash.far", "filter": None,
     "behavior": "leash_far", "priority": PRIORITY_LIFECYCLE, "enabled": True},
    {"event": "leash.lost", "filter": None,
     "behavior": "rest_now", "priority": PRIORITY_SAFETY, "enabled": True},
    # Voice (ears.py): the wake phrase + a keyword intent runs straight away.
    {"event": "voice.phrase", "filter": {"intent": "sit"},
     "behavior": "idle_sit", "priority": PRIORITY_MANUAL, "enabled": True},
    {"event": "voice.phrase", "filter": {"intent": "rest"},
     "behavior": "idle_rest", "priority": PRIORITY_MANUAL, "enabled": True},
    {"event": "voice.phrase", "filter": {"intent": "stop"},
     "behavior": "rest_now", "priority": PRIORITY_SAFETY, "enabled": True},
    {"event": "voice.phrase", "filter": {"intent": "greet"},
     "behavior": "startup_greeting", "priority": PRIORITY_MANUAL, "enabled": True},
    # Battery saver (power_saver.py): doze after a long quiet spell or on a low
    # battery; critical at safety priority.
    {"event": "power.doze", "filter": None,
     "behavior": "power_nap", "priority": PRIORITY_LIFECYCLE, "enabled": True},
    {"event": "power.critical", "filter": None,
     "behavior": "power_nap", "priority": PRIORITY_SAFETY, "enabled": True},
    # Conversation (conversation.py): the listening posture, and the tool menu
    # the LLM router chooses from. Every voice.intent binding is one tool the
    # next "Hey Laika" can pick; the filter's intent is the tool's name.
    {"event": "conversation.listen", "filter": None,
     "behavior": "idle_sit", "priority": PRIORITY_MANUAL, "enabled": True},
    {"event": "voice.intent", "filter": {"intent": "sit"},
     "behavior": "idle_sit", "priority": PRIORITY_MANUAL, "enabled": True},
    {"event": "voice.intent", "filter": {"intent": "lie_down"},
     "behavior": "idle_rest", "priority": PRIORITY_MANUAL, "enabled": True},
    {"event": "voice.intent", "filter": {"intent": "stop"},
     "behavior": "rest_now", "priority": PRIORITY_SAFETY, "enabled": True},
    {"event": "voice.intent", "filter": {"intent": "greet"},
     "behavior": "startup_greeting", "priority": PRIORITY_MANUAL, "enabled": True},
    {"event": "voice.intent", "filter": {"intent": "acknowledge"},
     "behavior": "acknowledgment", "priority": PRIORITY_MANUAL, "enabled": True},
    # Vision (eyes.py): someone in the camera's view. The mood light reacts
    # on its own; moving the dog on sight ships disabled until follow-me.
    {"event": "vision.person", "filter": None,
     "behavior": "acknowledgment", "priority": PRIORITY_LIFECYCLE, "enabled": False},
]


class BehaviorStore:
    """Thread-safe-enough CRUD over short-lived sessions."""

    def init(self) -> None:
        Base.metadata.create_all(engine)
        self._ensure_run_columns()
        with SessionLocal() as session:
            for seed in SEED_BEHAVIORS:
                if session.query(StoredBehavior).filter_by(
                        name=seed["name"]).first() is None:
                    session.add(StoredBehavior(
                        id=str(uuid.uuid4()), name=seed["name"],
                        description=seed["description"],
                        steps_json=json.dumps(seed["steps"]),
                        interruptible=seed["interruptible"],
                        cooldown_s=seed["cooldownS"], is_builtin=True))
            fresh_db = session.query(Binding).first() is None
            present = {(b.event, b.filter_json) for b in session.query(Binding).all()}
            for seed in SEED_BINDINGS:
                # Original seeds only populate an empty table (users may have
                # deliberately deleted them); NEW event families are added
                # per (event, filter) whenever that exact pair is absent, so a
                # family with several seeds (the voice.intent tools) fills in
                # completely and a later new tool lands on an existing table.
                if not fresh_db:
                    is_new_family = seed["event"].startswith(
                        ("leash.", "voice.", "vision.", "conversation.", "power."))
                    if not is_new_family or (seed["event"], json.dumps(seed["filter"])) in present:
                        continue
                session.add(Binding(
                    id=str(uuid.uuid4()), event=seed["event"],
                    filter_json=json.dumps(seed["filter"]),
                    behavior_name=seed["behavior"],
                    priority=seed["priority"], enabled=seed["enabled"]))
            session.commit()

    @staticmethod
    def _ensure_run_columns() -> None:
        # create_all never alters existing tables; run logs created before
        # the provenance/outcome columns existed need them added in place.
        migrate_run_log(engine)

    # -- behaviors --
    def behaviors(self) -> list[dict]:
        with SessionLocal() as session:
            return [b.to_dict() for b in session.query(StoredBehavior)
                    .order_by(StoredBehavior.name)]

    def behavior(self, name: str) -> dict | None:
        with SessionLocal() as session:
            row = session.query(StoredBehavior).filter_by(name=name).first()
            return row.to_dict() if row else None

    def upsert_behavior(self, data: dict) -> dict:
        with SessionLocal() as session:
            row = session.query(StoredBehavior).filter_by(
                name=data["name"]).first()
            if row is None:
                row = StoredBehavior(id=str(uuid.uuid4()), name=data["name"])
                session.add(row)
            row.description = data.get("description", row.description or "")
            row.steps_json = json.dumps(data["steps"])
            row.interruptible = bool(data.get("interruptible", True))
            row.cooldown_s = int(data.get("cooldownS", 0))
            session.commit()
            return row.to_dict()

    # -- bindings --
    def bindings(self, event: str | None = None,
                 enabled_only: bool = False) -> list[dict]:
        with SessionLocal() as session:
            query = session.query(Binding)
            if event is not None:
                query = query.filter_by(event=event)
            if enabled_only:
                query = query.filter_by(enabled=True)
            return [b.to_dict() for b in query.order_by(Binding.priority)]

    def upsert_binding(self, data: dict) -> dict:
        with SessionLocal() as session:
            row = None
            if data.get("id"):
                row = session.query(Binding).filter_by(id=data["id"]).first()
            if row is None:
                row = Binding(id=str(uuid.uuid4()))
                session.add(row)
            row.event = data["event"]
            row.filter_json = json.dumps(data.get("filter"))
            row.behavior_name = data["behavior"]
            row.priority = int(data.get("priority", PRIORITY_LIFECYCLE))
            row.enabled = bool(data.get("enabled", True))
            session.commit()
            return row.to_dict()

    def set_binding_enabled(self, event: str, behavior: str,
                            enabled: bool) -> int:
        with SessionLocal() as session:
            rows = session.query(Binding).filter_by(
                event=event, behavior_name=behavior).all()
            for row in rows:
                row.enabled = enabled
            session.commit()
            return len(rows)

    # -- run log --
    def log_start(self, behavior_name: str, source: str, priority: int,
                  cause: dict | None = None, run_id: str | None = None) -> str:
        run_id = run_id or str(uuid.uuid4())
        with SessionLocal() as session:
            session.add(BehaviorRun(id=run_id, behavior_name=behavior_name,
                                    source=source, priority=priority,
                                    cause_json=json.dumps(cause),
                                    status="running"))
            session.commit()
        return run_id

    def log_end(self, run_id: str, status: str, detail: str = "",
                preempted_by: str | None = None) -> None:
        with SessionLocal() as session:
            row = session.query(BehaviorRun).filter_by(id=run_id).first()
            if row:
                row.status = status
                row.detail = detail
                if preempted_by:
                    row.preempted_by = preempted_by
                row.ended_at = datetime.now(timezone.utc)
                session.commit()

    def recent_runs(self, limit: int = 10) -> list[dict]:
        with SessionLocal() as session:
            return [r.to_dict() for r in session.query(BehaviorRun)
                    .order_by(BehaviorRun.started_at.desc()).limit(limit)]

    def run_entry(self, run_id: str) -> BehaviorRunLogEntry | None:
        with SessionLocal() as session:
            row = session.query(BehaviorRun).filter_by(id=run_id).first()
            return BehaviorRunLogEntry.from_row(row) if row else None

    def set_outcome(self, run_id: str, outcome: OutcomeEvaluation | dict,
                    sensor_delta: dict | None = None) -> dict | None:
        """Attach the orchestrator's outcome evaluation to a run.

        Idempotent: writing the same outcome again leaves the row exactly as
        it was; a later write replaces the earlier one (last writer wins).
        ``sensor_delta`` is only overwritten when given. Returns the updated
        run dict, or None when the run id is unknown."""
        if isinstance(outcome, dict):
            outcome = OutcomeEvaluation.from_dict(outcome)
        if sensor_delta is not None and not isinstance(sensor_delta, dict):
            raise ValueError("sensor_delta must be an object")
        outcome_json = json.dumps(outcome.to_dict(), sort_keys=True)
        with SessionLocal() as session:
            row = session.query(BehaviorRun).filter_by(id=run_id).first()
            if row is None:
                return None
            row.outcome_json = outcome_json
            if sensor_delta is not None:
                row.sensor_delta_json = json.dumps(sensor_delta, sort_keys=True)
            session.commit()
            return row.to_dict()

    def runs_with_outcome(self, behavior_name: str | None = None,
                          source: str | None = None,
                          limit: int = 100) -> list[dict]:
        """Runs that already carry an outcome, newest first (served by the
        partial ix_framework_runs_outcome index)."""
        with SessionLocal() as session:
            query = session.query(BehaviorRun).filter(
                BehaviorRun.outcome_json.isnot(None))
            if source is not None:
                query = query.filter(BehaviorRun.source == source)
            if behavior_name is not None:
                query = query.filter(BehaviorRun.behavior_name == behavior_name)
            return [r.to_dict() for r in
                    query.order_by(BehaviorRun.started_at.desc()).limit(limit)]
