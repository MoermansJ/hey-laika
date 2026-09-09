"""Timestamped sensor readings and motion outcomes, kept for mapping and
for the machine-learning work later.

SensorLog: every tick of the navigation loop records what the dog knew at
that instant (range ahead, pose, IMU yaw when fused, battery, the command
in flight, the behavior running). Readings live in a ring buffer for the
`/sensors/latest` and `/sensors/recent` routes and are flushed to SQLite
in batches so the loop never waits on the disk.

ActionLog: one row per motion command that reached the firmware, with the
sensor snapshot at the moment it was sent, and an outcome filled in later
(sent / failed / blocked / arrived). `export()` returns rows as JSON or
CSV; the field glossary lives in docs/design/NAVIGATION_PHASE1.md.
"""
import csv
import io
import json
import logging
import threading
import time
from collections import deque

from sqlalchemy import Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

MAX_EXPORT_ROWS = 20000


class SensorReadingRow(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[float] = mapped_column(Float, index=True)
    range_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_ok: Mapped[int] = mapped_column(Integer, default=0)
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    heading: Mapped[float] = mapped_column(Float, default=0.0)
    drift_m: Mapped[float] = mapped_column(Float, default=0.0)
    yaw: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery: Mapped[float | None] = mapped_column(Float, nullable=True)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    pan_deg: Mapped[float] = mapped_column(Float, default=0.0)


class ActionRow(Base):
    __tablename__ = "action_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[float] = mapped_column(Float, index=True)
    command: Mapped[str] = mapped_column(Text)
    gait: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(Text, default="other")
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    heading: Mapped[float] = mapped_column(Float, default=0.0)
    yaw: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, default="sent")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)


READING_FIELDS = ("t", "rangeCm", "rangeOk", "x", "y", "heading", "driftM",
                  "yaw", "battery", "command", "behavior", "panDeg")
ACTION_FIELDS = ("id", "t", "command", "gait", "kind", "source", "x", "y",
                 "heading", "yaw", "rangeCm", "battery", "targetM", "outcome",
                 "detail", "endedAt")


def _reading_dict(row: SensorReadingRow) -> dict:
    return {"t": row.t, "rangeCm": row.range_cm, "rangeOk": bool(row.range_ok),
            "x": row.x, "y": row.y, "heading": row.heading, "driftM": row.drift_m,
            "yaw": row.yaw, "battery": row.battery, "command": row.command,
            "behavior": row.behavior, "panDeg": row.pan_deg}


def _action_dict(row: ActionRow) -> dict:
    return {"id": row.id, "t": row.t, "command": row.command, "gait": row.gait,
            "kind": row.kind, "source": row.source, "x": row.x, "y": row.y,
            "heading": row.heading, "yaw": row.yaw, "rangeCm": row.range_cm,
            "battery": row.battery, "targetM": row.target_m,
            "outcome": row.outcome, "detail": row.detail, "endedAt": row.ended_at}


def to_csv(rows: list[dict], fields: tuple) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields), extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})
    return buffer.getvalue()


class SensorLog:
    def __init__(self, flush_s: float = 5.0, history: int = 1200,
                 persist: bool = True, clock=time.time):
        self.flush_s = flush_s
        self.persist = persist
        self._clock = clock
        self._lock = threading.Lock()
        self._recent: deque = deque(maxlen=history)
        self._pending: list[dict] = []
        self._stop = threading.Event()
        self.stats = {"recorded": 0, "flushed": 0, "dropped": 0,
                      "lastFlushAt": None, "lastFlushMs": None}
        self._tick_times: deque = deque(maxlen=50)

    def init(self) -> None:
        Base.metadata.create_all(engine, tables=[SensorReadingRow.__table__,
                                                 ActionRow.__table__])
        if self.persist:
            threading.Thread(target=self._flush_loop, daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()
        self.flush()

    def record(self, reading: dict) -> dict:
        reading = {"t": self._clock(), **reading}
        with self._lock:
            self._recent.append(reading)
            self._pending.append(reading)
            self._tick_times.append(reading["t"])
            self.stats["recorded"] += 1
        return reading

    def latest(self) -> dict | None:
        with self._lock:
            return dict(self._recent[-1]) if self._recent else None

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            items = list(self._recent)
        return items[-limit:][::-1]

    def rate_hz(self) -> float | None:
        with self._lock:
            times = list(self._tick_times)
        if len(times) < 2:
            return None
        span = times[-1] - times[0]
        return round((len(times) - 1) / span, 1) if span > 0 else None

    def flush(self) -> int:
        with self._lock:
            pending, self._pending = self._pending, []
        if not pending:
            return 0
        if not self.persist:
            return len(pending)
        started = time.time()
        try:
            with SessionLocal() as session:
                session.add_all(SensorReadingRow(
                    t=r["t"], range_cm=r.get("rangeCm"),
                    range_ok=1 if r.get("rangeOk") else 0,
                    x=r.get("x", 0.0), y=r.get("y", 0.0),
                    heading=r.get("heading", 0.0), drift_m=r.get("driftM", 0.0),
                    yaw=r.get("yaw"), battery=r.get("battery"),
                    command=r.get("command"), behavior=r.get("behavior"),
                    pan_deg=r.get("panDeg", 0.0)) for r in pending)
                session.commit()
        except Exception:
            logger.exception("Sensor log flush failed; %d readings dropped",
                             len(pending))
            self.stats["dropped"] += len(pending)
            return 0
        self.stats["flushed"] += len(pending)
        self.stats["lastFlushAt"] = self._clock()
        self.stats["lastFlushMs"] = round((time.time() - started) * 1000)
        return len(pending)

    def _flush_loop(self) -> None:
        while not self._stop.wait(self.flush_s):
            try:
                self.flush()
            except Exception:
                logger.exception("Sensor log flush tick failed")

    def stored(self, since: float | None = None, limit: int = 1000) -> list[dict]:
        limit = max(1, min(int(limit), MAX_EXPORT_ROWS))
        with SessionLocal() as session:
            query = session.query(SensorReadingRow)
            if since is not None:
                query = query.filter(SensorReadingRow.t >= float(since))
            rows = query.order_by(SensorReadingRow.t.desc()).limit(limit).all()
        return [_reading_dict(r) for r in rows]

    def status(self) -> dict:
        with self._lock:
            pending = len(self._pending)
            buffered = len(self._recent)
        return {"rateHz": self.rate_hz(), "buffered": buffered,
                "pending": pending, "flushS": self.flush_s,
                "persist": self.persist, **self.stats}


def classify(command: str) -> tuple[str, str | None]:
    """(kind, gait) for a firmware command: advance / turn / skill / joint / other."""
    command = command.strip()
    if command.startswith("k"):
        parts = command[1:].split()
        name = parts[0] if parts else ""
        if name[:2] in ("wk", "tr", "cr", "bk") and name[2:] == "F":
            return "advance", name
        if name[:2] in ("wk", "vt") and name[2:] in ("L", "R"):
            return "turn", name
        return "skill", name
    if command[:1] in ("m", "i", "I", "M"):
        return "joint", None
    return "other", None


class ActionLog:
    def __init__(self, persist: bool = True, clock=time.time):
        self.persist = persist
        self._clock = clock
        self._lock = threading.Lock()
        self._recent: deque = deque(maxlen=200)
        self.stats = {"recorded": 0, "outcomes": 0}

    def record(self, command: str, snapshot: dict, source: str | None = None,
               target_m: float | None = None) -> int | None:
        kind, gait = classify(command)
        entry = {"t": self._clock(), "command": command, "gait": gait, "kind": kind,
                 "source": source, "x": snapshot.get("x", 0.0),
                 "y": snapshot.get("y", 0.0), "heading": snapshot.get("heading", 0.0),
                 "yaw": snapshot.get("yaw"), "rangeCm": snapshot.get("rangeCm"),
                 "battery": snapshot.get("battery"), "targetM": target_m,
                 "outcome": "sent", "detail": None, "endedAt": None, "id": None}
        self.stats["recorded"] += 1
        if self.persist:
            try:
                with SessionLocal() as session:
                    row = ActionRow(t=entry["t"], command=command, gait=gait, kind=kind,
                                    source=source, x=entry["x"], y=entry["y"],
                                    heading=entry["heading"], yaw=entry["yaw"],
                                    range_cm=entry["rangeCm"], battery=entry["battery"],
                                    target_m=target_m)
                    session.add(row)
                    session.commit()
                    entry["id"] = row.id
            except Exception:
                logger.exception("Action log write failed")
        with self._lock:
            self._recent.append(entry)
        return entry["id"]

    def outcome(self, action_id: int | None, outcome: str, detail: str | None = None) -> None:
        self.stats["outcomes"] += 1
        ended = self._clock()
        with self._lock:
            for entry in reversed(self._recent):
                if entry["id"] == action_id:
                    entry.update({"outcome": outcome, "detail": detail, "endedAt": ended})
                    break
        if action_id is None or not self.persist:
            return
        try:
            with SessionLocal() as session:
                row = session.get(ActionRow, action_id)
                if row is not None:
                    row.outcome = outcome
                    row.detail = detail
                    row.ended_at = ended
                    session.commit()
        except Exception:
            logger.exception("Action log outcome write failed")

    def recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            items = list(self._recent)
        return items[-limit:][::-1]

    def export(self, since: float | None = None, limit: int = MAX_EXPORT_ROWS) -> list[dict]:
        limit = max(1, min(int(limit), MAX_EXPORT_ROWS))
        if not self.persist:
            items = [e for e in self.recent(limit) if since is None or e["t"] >= since]
            return items
        with SessionLocal() as session:
            query = session.query(ActionRow)
            if since is not None:
                query = query.filter(ActionRow.t >= float(since))
            rows = query.order_by(ActionRow.t.asc()).limit(limit).all()
        return [_action_dict(r) for r in rows]

    def export_csv(self, since: float | None = None, limit: int = MAX_EXPORT_ROWS) -> str:
        return to_csv(self.export(since, limit), ACTION_FIELDS)

    def status(self) -> dict:
        return {**self.stats, "persist": self.persist}


def readings_csv(rows: list[dict]) -> str:
    return to_csv(rows, READING_FIELDS)


def dumps(rows: list[dict]) -> str:
    return json.dumps(rows)
