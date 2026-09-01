"""Request/command metrics for the adapter.

Two storage classes, per the observability brief (§A):
- Cumulative usage counters — persisted to SQLite via a periodic flush, so
  totals (commands sent, requests served) survive the frequent dev restarts.
- Rolling 1-hour latency/error windows — in-memory only; diagnostic data
  that is cheap to lose.

Everything is exposed as one JSON snapshot on GET /metrics, which the
orchestrator merges across the fleet and rolls up hourly into Postgres.
"""
import logging
import threading
import time
from collections import deque

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

WINDOW_S = 3600
FLUSH_INTERVAL_S = 15


class MetricCounter(Base):
    __tablename__ = "metrics_counters"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[float] = mapped_column(default=0.0)


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {}
        self._dirty = False
        self._windows: dict[str, deque] = {}  # key -> deque[(ts, ms, ok)]
        self._errors: deque = deque(maxlen=25)  # recent (ts, key, note)
        self._stop = threading.Event()

    # ---- lifecycle ---------------------------------------------------------

    def init(self) -> None:
        Base.metadata.create_all(engine)
        with SessionLocal() as session:
            for row in session.query(MetricCounter):
                self._counters[row.name] = row.value
        threading.Thread(target=self._flush_loop, daemon=True).start()

    def _flush_loop(self) -> None:
        while not self._stop.wait(FLUSH_INTERVAL_S):
            try:
                self.flush()
            except Exception:
                logger.exception("Metrics flush failed")

    def flush(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            items = dict(self._counters)
            self._dirty = False
        with SessionLocal() as session:
            for name, value in items.items():
                row = session.get(MetricCounter, name)
                if row is None:
                    row = MetricCounter(name=name)
                    session.add(row)
                row.value = value
            session.commit()

    # ---- recording ---------------------------------------------------------

    def inc(self, name: str, by: float = 1.0) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + by
            self._dirty = True

    def observe(self, key: str, duration_ms: float, ok: bool = True,
                note: str | None = None) -> None:
        """One timed event: bumps cumulative counters and the 1h window."""
        self.inc(f"{key}.count")
        now = time.time()
        if not ok:
            self.inc(f"{key}.errors")
            with self._lock:
                self._errors.append(
                    {"at": now, "key": key, "note": note or ""})
        with self._lock:
            window = self._windows.setdefault(key, deque())
            window.append((now, duration_ms, ok))
            self._prune(window, now)

    @staticmethod
    def _prune(window: deque, now: float) -> None:
        while window and window[0][0] < now - WINDOW_S:
            window.popleft()

    # ---- reporting ---------------------------------------------------------

    def snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            windows = {}
            for key, window in self._windows.items():
                self._prune(window, now)
                if not window:
                    continue
                values = sorted(ms for _, ms, _ in window)
                windows[key] = {
                    "count": len(values),
                    "errors": sum(1 for _, _, ok in window if not ok),
                    "avgMs": round(sum(values) / len(values), 1),
                    "p95Ms": round(values[int(0.95 * (len(values) - 1))], 1),
                    "maxMs": round(values[-1], 1),
                }
            counters = dict(self._counters)
            errors = list(self._errors)
        return {"counters": counters, "window1h": windows,
                "recentErrors": errors, "generatedAt": now}


metrics = Metrics()  # module singleton — the adapter has exactly one robot


def instrument_controller(controller) -> None:
    """Wrap the controller's command path with WS-channel timing.

    The controller already awaits the completion echo/frame, so wall time of
    send_command IS the robot round-trip. Wrapping (rather than editing the
    three controller classes) keeps mock/serial/wifi uniformly covered.
    """
    original = controller.send_command

    def timed_send(command: str) -> bool:
        start = time.time()
        ok = False
        try:
            ok = original(command)
            return ok
        finally:
            metrics.observe("ws.command", (time.time() - start) * 1000.0,
                            ok=bool(ok))

    controller.send_command = timed_send
