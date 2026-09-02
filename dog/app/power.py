"""Power-session tracking (owner request 2026-09-01).

Snapshots the robot's state at power-on and power-off so battery health is
measurable over time and remaining runtime predictable:

- A session OPENS when the transport transitions unreachable -> connected
  (power-on snapshot: battery %, timestamp).
- It CLOSES on the reverse transition (power-off snapshot: last cached
  battery %, duration). The dog can't be asked at the moment it dies, so
  the close uses the last telemetry seen — with the 40 s telemetry TTL
  that's at most a little stale, which is fine for health trends.
- Completed sessions yield a drain rate (%/hour); the recent average
  predicts minutes of runtime left from the current battery level.
"""
import logging
import statistics
import threading
import time

from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

# Sessions shorter than this contribute no drain estimate — connection
# blips and reboots would otherwise pollute the battery-health data.
MIN_SESSION_FOR_DRAIN_S = 600


class PowerSession(Base):
    __tablename__ = "power_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[float] = mapped_column()
    start_battery: Mapped[float] = mapped_column(nullable=True)
    ended_at: Mapped[float] = mapped_column(nullable=True)
    end_battery: Mapped[float] = mapped_column(nullable=True)

    def drain_pct_per_hour(self) -> float | None:
        if self.ended_at is None or self.start_battery is None \
                or self.end_battery is None:
            return None
        duration = self.ended_at - self.started_at
        drop = self.start_battery - self.end_battery
        if duration < MIN_SESSION_FOR_DRAIN_S or drop <= 0:
            return None
        return drop / (duration / 3600.0)

    def to_dict(self) -> dict:
        duration = (self.ended_at - self.started_at) if self.ended_at else None
        drain = self.drain_pct_per_hour()
        return {
            "id": self.id,
            "startedAt": self.started_at,
            "startBattery": self.start_battery,
            "endedAt": self.ended_at,
            "endBattery": self.end_battery,
            "durationS": round(duration) if duration is not None else None,
            "drainPctPerHour": round(drain, 1) if drain is not None else None,
        }


class PowerTracker:
    """States: "off" (no session), "on" (session open, robot answering),
    "unreachable" (session open, transport lost). A session opens on the
    first successful battery read, not on socket connect, and closes only
    after the transport has been gone for `unreachable_grace_s` — a WiFi
    blip is not a power cycle. Battery below the firmware floor at the time
    of loss closes immediately (the dog really died)."""

    LOW_BATTERY_FLOOR_PCT = 5.0

    def __init__(self, controller, poll_s: float = 10.0,
                 unreachable_grace_s: float = 300.0, clock=time.time):
        self.controller = controller
        self.poll_s = poll_s
        self.unreachable_grace_s = unreachable_grace_s
        self._clock = clock
        self._connected = False
        self._session_id: int | None = None
        self._last_battery: float | None = None
        self._unreachable_since: float | None = None
        self._stop = threading.Event()

    @property
    def state(self) -> str:
        if self._session_id is None:
            return "off"
        return "unreachable" if self._unreachable_since else "on"

    def init(self) -> None:
        Base.metadata.create_all(engine)
        # Close any session left dangling by an adapter restart: its true
        # end is unknown, so it ends "now" with no end battery (excluded
        # from drain stats by the None end_battery).
        with SessionLocal() as session:
            dangling = session.query(PowerSession).filter_by(
                ended_at=None).all()
            for row in dangling:
                row.ended_at = time.time()
            if dangling:
                logger.info("Closed %d dangling power session(s)",
                            len(dangling))
            session.commit()
        threading.Thread(target=self._loop, daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()

    # ---- tracking ----------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_s):
            try:
                self._tick()
            except Exception:
                logger.exception("Power tick failed")

    def _tick(self) -> None:
        connected = bool(self.controller.get_status().get("connected"))
        battery = None
        if connected:
            battery = self.controller.get_telemetry().get("battery")
            if battery is not None:
                self._last_battery = battery
        self._connected = connected

        if connected and battery is not None:
            # A positive sign of life: open a session if none, and forgive
            # any outage that was in progress.
            if self._session_id is None:
                self._open_session(battery)
            elif self._unreachable_since:
                logger.info("Robot reachable again after %.0fs",
                            self._clock() - self._unreachable_since)
            self._unreachable_since = None
            return

        if self._session_id is None:
            return  # off, and still off
        now = self._clock()
        if self._unreachable_since is None:
            self._unreachable_since = now
            logger.info("Robot unreachable (battery was %s); grace %.0fs",
                        self._last_battery, self.unreachable_grace_s)
        died = (self._last_battery is not None
                and self._last_battery <= self.LOW_BATTERY_FLOOR_PCT)
        if died or now - self._unreachable_since >= self.unreachable_grace_s:
            self._close_session(self._last_battery)
            self._unreachable_since = None

    def _open_session(self, battery: float | None) -> None:
        with SessionLocal() as session:
            row = PowerSession(started_at=time.time(), start_battery=battery)
            session.add(row)
            session.commit()
            self._session_id = row.id
        logger.info("Power ON snapshot: battery=%s", battery)

    def _close_session(self, battery: float | None) -> None:
        if self._session_id is None:
            return
        with SessionLocal() as session:
            row = session.get(PowerSession, self._session_id)
            if row is not None:
                row.ended_at = time.time()
                row.end_battery = battery
                session.commit()
        logger.info("Power OFF snapshot: battery=%s", battery)
        self._session_id = None

    # ---- reporting ---------------------------------------------------------

    def summary(self) -> dict:
        with SessionLocal() as session:
            rows = (session.query(PowerSession)
                    .order_by(PowerSession.id.desc()).limit(20).all())
            sessions = [r.to_dict() for r in rows]
            rates = [r.drain_pct_per_hour() for r in rows]
        rates = [r for r in rates if r is not None][:5]
        avg_drain = round(statistics.mean(rates), 1) if rates else None

        predicted_minutes = None
        if avg_drain and self._connected and self._last_battery is not None:
            predicted_minutes = round(self._last_battery / avg_drain * 60)
        return {
            "connected": self._connected,
            "state": self.state,
            "unreachableSince": self._unreachable_since,
            "battery": self._last_battery,
            "avgDrainPctPerHour": avg_drain,
            "predictedMinutesLeft": predicted_minutes,
            "sessions": sessions,
        }
