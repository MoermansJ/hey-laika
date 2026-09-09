"""Two-tier navigation errors and the error state that asks a human.

RecoverableError: the navigator saw something odd (a reading that
contradicts the map, a sensor value that jumped, a heading that disagrees
with the IMU, a command that did not go through). The handler waits a
moment, counts it, and lets the navigator re-check. Three consecutive
occurrences of the same kind escalate to an UnrecoverableError.

UnrecoverableError: a real, persistent contradiction. The error state
pauses the dog (arbiter stop plus a safety-priority halt behavior), holds
the mood light on a red 2 Hz blink, says the help prompt through the
speaker, raises a `nav.error` framework event, and blocks navigation until
a human answers through `/navigation/errors/respond` with one of
trust_map / trust_sensor / manual. Every occurrence, retry and resolution
lands in the nav_errors table for the GUI's error history.
"""
import json
import logging
import threading
import time

from sqlalchemy import Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

PROMPT = "I encountered a problem. Please help me understand what's happening."
RESOLUTIONS = ("trust_map", "trust_sensor", "manual")
ERROR_MOOD = "error"
HALT_BEHAVIOR = "error_halt"


class NavError(Exception):
    tier = "recoverable"

    def __init__(self, kind: str, message: str = "", context: dict | None = None):
        super().__init__(message or kind)
        self.kind = kind
        self.message = message or kind
        self.context = context or {}


class RecoverableError(NavError):
    tier = "recoverable"


class UnrecoverableError(NavError):
    tier = "unrecoverable"


class NavErrorRow(Base):
    __tablename__ = "nav_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[float] = mapped_column(Float, index=True)
    kind: Mapped[str] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(Text)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "t": self.t, "kind": self.kind, "tier": self.tier,
                "retries": self.retries, "message": self.message,
                "context": json.loads(self.context_json or "{}"),
                "resolution": self.resolution, "note": self.note,
                "resolvedAt": self.resolved_at}


class ErrorHandler:
    def __init__(self, on_escalate=None, max_retries: int = 3,
                 retry_wait_s: float = 0.3, persist: bool = True,
                 clock=time.time, sleep=time.sleep):
        self.on_escalate = on_escalate or (lambda error, error_id: None)
        self.max_retries = max_retries
        self.retry_wait_s = retry_wait_s
        self.persist = persist
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self.counts: dict[str, int] = {}
        self._memory: list[dict] = []
        self.stats = {"recoverable": 0, "escalated": 0, "unrecoverable": 0,
                      "silentRecoveries": 0}

    def init(self) -> None:
        Base.metadata.create_all(engine, tables=[NavErrorRow.__table__])

    # ---- the decision ------------------------------------------------------

    def handle(self, error: NavError) -> dict:
        """Recoverable: count, wait, ask for a re-check; the third strike
        escalates. Unrecoverable: straight to the error state."""
        if isinstance(error, RecoverableError):
            with self._lock:
                count = self.counts.get(error.kind, 0) + 1
                self.counts[error.kind] = count
            self.stats["recoverable"] += 1
            self._log(error, count)
            if count >= self.max_retries:
                escalated = UnrecoverableError(
                    error.kind, f"{error.message} (persisted {count} times)",
                    error.context)
                return self._escalate(escalated, count)
            self._sleep(self.retry_wait_s)
            return {"action": "retry", "attempt": count, "kind": error.kind,
                    "remaining": self.max_retries - count}
        with self._lock:
            count = self.counts.get(error.kind, 0)
        self.stats["unrecoverable"] += 1
        return self._escalate(error, count)

    def _escalate(self, error: UnrecoverableError, retries: int) -> dict:
        error_id = self._log(error, retries)
        with self._lock:
            self.counts[error.kind] = 0
        self.stats["escalated"] += 1
        logger.warning("Navigation error escalated: %s (%s)", error.kind, error.message)
        try:
            self.on_escalate(error, error_id)
        except Exception:
            logger.exception("Error-state entry failed")
        return {"action": "escalated", "errorId": error_id, "kind": error.kind,
                "retries": retries}

    def clear(self, kind: str | None = None) -> None:
        """The re-check came back clean: forget the streak (silent recovery)."""
        with self._lock:
            if kind is None:
                had = any(self.counts.values())
                self.counts.clear()
            else:
                had = self.counts.pop(kind, 0) > 0
        if had:
            self.stats["silentRecoveries"] += 1

    # ---- history -----------------------------------------------------------

    def _log(self, error: NavError, retries: int) -> int | None:
        entry = {"id": None, "t": self._clock(), "kind": error.kind,
                 "tier": error.tier, "retries": retries, "message": error.message,
                 "context": error.context, "resolution": None, "note": None,
                 "resolvedAt": None}
        if self.persist:
            try:
                with SessionLocal() as session:
                    row = NavErrorRow(t=entry["t"], kind=error.kind, tier=error.tier,
                                      retries=retries, message=error.message,
                                      context_json=json.dumps(error.context, default=str))
                    session.add(row)
                    session.commit()
                    entry["id"] = row.id
            except Exception:
                logger.exception("Navigation error row not written")
        with self._lock:
            if entry["id"] is None:
                entry["id"] = -(len(self._memory) + 1)
            self._memory.append(entry)
            self._memory = self._memory[-200:]
        return entry["id"]

    def resolve(self, error_id: int | None, resolution: str, note: str | None = None) -> None:
        resolved_at = self._clock()
        with self._lock:
            for entry in self._memory:
                if entry["id"] == error_id:
                    entry.update({"resolution": resolution, "note": note,
                                  "resolvedAt": resolved_at})
        if not self.persist or error_id is None or error_id < 0:
            return
        try:
            with SessionLocal() as session:
                row = session.get(NavErrorRow, error_id)
                if row is not None:
                    row.resolution = resolution
                    row.note = note
                    row.resolved_at = resolved_at
                    session.commit()
        except Exception:
            logger.exception("Navigation error resolution not written")

    def history(self, limit: int = 50) -> list[dict]:
        if not self.persist:
            with self._lock:
                return list(reversed(self._memory[-limit:]))
        with SessionLocal() as session:
            rows = (session.query(NavErrorRow)
                    .order_by(NavErrorRow.id.desc()).limit(limit).all())
        return [r.to_dict() for r in rows]

    def status(self) -> dict:
        with self._lock:
            counts = {k: v for k, v in self.counts.items() if v}
        return {"maxRetries": self.max_retries, "retryWaitS": self.retry_wait_s,
                "streaks": counts, **self.stats}


class ErrorState:
    """Pause, red light, spoken prompt, wait for a human."""

    def __init__(self, arbiter, mood=None, speak=None, trigger=None,
                 handler: ErrorHandler | None = None, clock=time.time,
                 speak_async: bool = True):
        self.arbiter = arbiter
        self.mood = mood
        self.speak = speak
        self.trigger = trigger or (lambda event, payload=None: None)
        self.handler = handler
        self._clock = clock
        self._speak_async = speak_async
        self._lock = threading.Lock()
        self.active: dict | None = None
        self.on_resolve = None      # navigator hook: (choice, error) -> dict
        self.stats = {"entered": 0, "resolved": 0, "spoken": 0, "speechErrors": 0}
        self.last_resolution: dict | None = None

    @property
    def blocked(self) -> bool:
        return self.active is not None

    def enter(self, error: NavError, error_id: int | None = None) -> dict:
        with self._lock:
            if self.active is not None:
                self.active.setdefault("also", []).append(
                    {"kind": error.kind, "message": error.message, "id": error_id})
                return dict(self.active)
            self.active = {"id": error_id, "kind": error.kind, "message": error.message,
                           "context": error.context, "since": self._clock(),
                           "prompt": PROMPT, "options": list(RESOLUTIONS)}
            snapshot = dict(self.active)
        self.stats["entered"] += 1
        try:
            self.arbiter.stop_current()
            self.arbiter.submit(HALT_BEHAVIOR, source="safety", priority=1,
                                cause={"type": "nav.error", "kind": error.kind,
                                       "errorId": error_id})
        except Exception:
            logger.exception("Error state: halt not submitted")
        if self.mood is not None:
            try:
                self.mood.hold(ERROR_MOOD)
            except Exception:
                logger.exception("Error state: mood not set")
        self._say(PROMPT)
        self.trigger("nav.error", {"kind": error.kind, "message": error.message,
                                   "errorId": error_id})
        return snapshot

    def _say(self, text: str) -> None:
        if self.speak is None:
            return

        def run():
            try:
                self.speak(text)
                self.stats["spoken"] += 1
            except Exception as exc:
                self.stats["speechErrors"] += 1
                logger.warning("Error state: prompt not spoken (%s)", exc)

        if self._speak_async:
            threading.Thread(target=run, daemon=True).start()
        else:
            run()

    def respond(self, choice: str, note: str | None = None) -> dict:
        if choice not in RESOLUTIONS:
            raise ValueError(f"choice must be one of {RESOLUTIONS}")
        with self._lock:
            if self.active is None:
                raise LookupError("no error is waiting for an answer")
            error = self.active
            self.active = None
        applied = None
        if self.on_resolve is not None:
            try:
                applied = self.on_resolve(choice, error)
            except Exception:
                logger.exception("Error resolution hook failed")
        if self.handler is not None:
            self.handler.resolve(error["id"], choice, note)
            self.handler.clear()
        if self.mood is not None:
            try:
                self.mood.release()
            except Exception:
                logger.exception("Error state: mood not released")
        self.stats["resolved"] += 1
        self.last_resolution = {"errorId": error["id"], "kind": error["kind"],
                                "choice": choice, "note": note,
                                "at": self._clock(), "applied": applied}
        self.trigger("nav.error.resolved", {"kind": error["kind"], "choice": choice,
                                            "errorId": error["id"]})
        return dict(self.last_resolution)

    def status(self) -> dict:
        with self._lock:
            active = dict(self.active) if self.active else None
        if active:
            active["waitingS"] = round(self._clock() - active["since"], 1)
        return {"active": active, "blocked": active is not None,
                "lastResolution": self.last_resolution, **self.stats}
