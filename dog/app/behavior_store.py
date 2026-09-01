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
from datetime import datetime, timezone

from sqlalchemy import String, Text, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, engine, utcnow

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

    def to_dict(self) -> dict:
        return {
            "id": self.id, "behavior": self.behavior_name, "source": self.source,
            "priority": self.priority, "status": self.status, "detail": self.detail,
            "cause": json.loads(self.cause_json or "null"),
            "preemptedBy": self.preempted_by,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "endedAt": self.ended_at.isoformat() if self.ended_at else None,
        }


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
]

SEED_BINDINGS = [
    {"event": "robot.online", "filter": None,
     "behavior": "startup_greeting", "priority": PRIORITY_LIFECYCLE, "enabled": True},
    {"event": "idle.timeout", "filter": {"seconds": 60},
     "behavior": "idle_sit", "priority": PRIORITY_IDLE, "enabled": True},
    {"event": "idle.timeout", "filter": {"seconds": 120},
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
            for seed in SEED_BINDINGS:
                # Original seeds only populate an empty table (users may have
                # deliberately deleted them); NEW event families (leash.*)
                # are added whenever their event has no binding at all.
                if not fresh_db:
                    is_new_family = seed["event"].startswith("leash.")
                    exists = session.query(Binding).filter_by(
                        event=seed["event"]).first() is not None
                    if not is_new_family or exists:
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
        # the provenance columns existed need them added in place.
        existing = {c["name"] for c in
                    inspect(engine).get_columns("framework_behavior_runs")}
        with engine.begin() as conn:
            if "cause_json" not in existing:
                conn.execute(text("ALTER TABLE framework_behavior_runs "
                                  "ADD COLUMN cause_json TEXT DEFAULT 'null'"))
            if "preempted_by" not in existing:
                conn.execute(text("ALTER TABLE framework_behavior_runs "
                                  "ADD COLUMN preempted_by VARCHAR(36)"))

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
