"""Senses layer — always-on passive perception (NAVIGATION_MAPPING_BRIEF §3).

Perception is not arbitrated: the arbiter owns motion, senses only observe.

- Odometry shadow: wraps the controller's command path — the single choke
  point ALL motion flows through (arbiter behaviors, manual GUI, gait
  learner alike) — and dead-reckons a coarse pose from the bounded-motion
  vocabulary. Commanded turns update heading; bounded advances update x/y by
  a calibrated stride. No yaw feedback yet (spatial MVP integration later),
  so `driftM` grows with every move and is reported honestly.

- Opportunistic sniffer: fires an XWs WiFi scan (blocking ~2 s on the
  firmware) only in motion gaps, under a politeness contract: never while
  anything moved recently, at most once per minIntervalS, suppressed in away
  mode (leash armed — hotspot scans don't belong in the home map). Samples
  are pose-labeled and stored permanently in SQLite; the map accretes as a
  side effect of living.

- Each sample also carries what else the dog knew at that instant: the
  cached battery reading and, when the transport can read it, the measured
  IMU yaw (`gp`). Both are optional columns so the map can show them on
  hover without the sniff ever depending on them.

- Pose continuity: the pose is restored from the newest sample on start-up
  (with a restart penalty on the drift), so a restart does not tear the
  trail in two. `reset_pose()` re-anchors the origin when the dog is put
  back at a known spot.
"""
import json
import logging
import math
import re
import threading
import time

from sqlalchemy import Text, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

DEFAULTS = {
    "quietS": 5.0,          # no motion for this long -> a "motion gap"
    "minIntervalS": 60.0,   # politeness: at most one sniff per interval
    "strideMPerCycle": 0.10,  # tape-measure calibrated later (spatial MVP)
}

RESTART_DRIFT_M = 0.5   # honesty penalty: the dog may have been carried

# Bounded-motion vocabulary the shadow understands. Anything else just
# stamps "moved" (drift grows, pose stays).
_ADVANCE = re.compile(r"^k(wk|tr|cr|bk)F\s+(\d+)$")
_TURN = re.compile(r"^k(?:wk|vt)([LR])\s+(\d+)$")
_FLOAT_RE = re.compile(r"-?\d+\.?\d*")

MAX_SAMPLES_PER_QUERY = 2000


class WifiSample(Base):
    __tablename__ = "wifi_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    t: Mapped[float] = mapped_column()
    x: Mapped[float] = mapped_column(default=0.0)
    y: Mapped[float] = mapped_column(default=0.0)
    heading: Mapped[float] = mapped_column(default=0.0)
    drift_m: Mapped[float] = mapped_column(default=0.0)
    aps_json: Mapped[str] = mapped_column(Text, default="[]")
    battery: Mapped[float | None] = mapped_column(nullable=True)
    yaw: Mapped[float | None] = mapped_column(nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "t": self.t, "x": round(self.x, 2),
                "y": round(self.y, 2), "heading": round(self.heading, 1),
                "driftM": round(self.drift_m, 2),
                "battery": self.battery,
                "yaw": None if self.yaw is None else round(self.yaw, 1),
                "source": self.source or "auto",
                "aps": json.loads(self.aps_json or "[]")}


_ADDED_COLUMNS = {
    "battery": "FLOAT", "yaw": "FLOAT", "source": "TEXT",
}


def _ensure_columns() -> None:
    existing = {c["name"] for c in inspect(engine).get_columns("wifi_samples")}
    with engine.begin() as conn:
        for name, kind in _ADDED_COLUMNS.items():
            if name not in existing:
                conn.execute(text(
                    f"ALTER TABLE wifi_samples ADD COLUMN {name} {kind}"))


class SensesService:
    def __init__(self, controller, config: dict | None = None,
                 is_away=lambda: False):
        self.controller = controller
        self.config = {**DEFAULTS, **(config or {})}
        self.enabled = True
        self._is_away = is_away

        self._lock = threading.Lock()
        self._x = 0.0
        self._y = 0.0
        self._heading = 0.0          # degrees, 0 = boot orientation
        self._drift_m = 0.0          # accumulated commanded travel (honesty)
        self._last_sniff = 0.0
        self._sample_count = None    # lazy; filled on init
        self._stop = threading.Event()

    # ---- lifecycle ---------------------------------------------------------

    def init(self) -> None:
        Base.metadata.create_all(engine)
        _ensure_columns()
        with SessionLocal() as session:
            self._sample_count = session.query(WifiSample).count()
            last = (session.query(WifiSample)
                    .order_by(WifiSample.id.desc()).first())
        if last is not None:
            with self._lock:
                self._x, self._y = last.x, last.y
                self._heading = last.heading
                self._drift_m = last.drift_m + RESTART_DRIFT_M
            logger.info("Pose restored from sample %d at (%.1f, %.1f)",
                        last.id, last.x, last.y)
        threading.Thread(target=self._sniff_loop, daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()

    # ---- odometry shadow ---------------------------------------------------

    def instrument(self, controller) -> None:
        """Wrap send_command so every motion command updates the shadow.
        Composes with the metrics wrapper (each wraps the previous)."""
        original = controller.send_command

        def shadowed(command: str) -> bool:
            ok = original(command)
            if ok:
                try:
                    self.observe_command(command)
                except Exception:
                    logger.exception("Odometry shadow failed on %r", command)
            return ok

        controller.send_command = shadowed

    def observe_command(self, command: str) -> None:
        command = command.strip()
        with self._lock:
            advance = _ADVANCE.match(command)
            if advance:
                gait, cycles = advance.group(1), int(advance.group(2))
                meters = int(cycles) * self.config["strideMPerCycle"]
                if gait == "bk":
                    meters = -meters
                rad = math.radians(self._heading)
                self._x += meters * math.cos(rad)
                self._y += meters * math.sin(rad)
                self._drift_m += abs(meters)
                return
            turn = _TURN.match(command)
            if turn:
                direction, degrees = turn.group(1), float(turn.group(2))
                self._heading += degrees if direction == "L" else -degrees
                self._heading = (self._heading + 180.0) % 360.0 - 180.0
                self._drift_m += 0.05  # turning slips a little too
                return
            if command.startswith(("k", "i", "m")):
                # Unmodeled motion: pose unchanged, uncertainty grows.
                self._drift_m += 0.02

    def pose(self) -> dict:
        with self._lock:
            return {"x": round(self._x, 2), "y": round(self._y, 2),
                    "heading": round(self._heading, 1),
                    "driftM": round(self._drift_m, 2)}

    def reset_pose(self, heading: float = 0.0) -> dict:
        with self._lock:
            self._x = self._y = 0.0
            self._heading = float(heading)
            self._drift_m = 0.0
        logger.info("Pose reset to origin (heading %.0f)", heading)
        return self.pose()

    # ---- opportunistic sniffer --------------------------------------------

    def _may_sniff(self, now: float) -> bool:
        if not self.enabled or self._is_away():
            return False
        if now - self._last_sniff < self.config["minIntervalS"]:
            return False
        last_motion = getattr(self.controller, "last_motion_at", None)
        if last_motion is not None and \
                now - last_motion < self.config["quietS"]:
            return False
        return True

    def _sniff_loop(self) -> None:
        while not self._stop.wait(1.0):
            try:
                now = time.time()
                if self._may_sniff(now):
                    self._last_sniff = now
                    self.sniff(source="auto")
            except Exception:
                logger.exception("Sniff tick failed")

    def _read_yaw(self) -> float | None:
        try:
            lines = self.controller.query("gp")
        except Exception:
            return None
        if not lines:
            return None
        for line in "\n".join(lines).splitlines():
            if "ICM" in line or "MCU" in line:
                floats = _FLOAT_RE.findall(line)
                if len(floats) >= 6:
                    return float(floats[3])
        return None

    def _read_battery(self) -> float | None:
        try:
            return self.controller.get_telemetry().get("battery")
        except Exception:
            return None

    def sniff(self, source: str = "manual") -> dict | None:
        """One stop-and-sniff: XWs scan -> pose-labeled sample row."""
        lines = self.controller.query("XWs")
        if not lines:
            return None
        aps = []
        for raw in "\n".join(lines).splitlines():
            raw = raw.strip()
            if not raw.startswith("{"):
                continue
            try:
                ap = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "bssid" in ap and "rssi" in ap:
                aps.append({"ssid": ap.get("ssid"), "bssid": ap["bssid"],
                            "rssi": ap["rssi"], "channel": ap.get("channel")})
        if not aps:
            return None
        yaw = self._read_yaw()
        battery = self._read_battery()
        pose = self.pose()
        sample = WifiSample(t=time.time(), x=pose["x"], y=pose["y"],
                            heading=pose["heading"], drift_m=pose["driftM"],
                            aps_json=json.dumps(aps), battery=battery,
                            yaw=yaw, source=source)
        with SessionLocal() as session:
            session.add(sample)
            session.commit()
            result = sample.to_dict()
        with self._lock:
            self._sample_count = (self._sample_count or 0) + 1
        logger.info("Sniff (%s): %d APs at (%.1f, %.1f)", source, len(aps),
                    pose["x"], pose["y"])
        return result

    # ---- reporting ---------------------------------------------------------

    def status(self) -> dict:
        with self._lock:
            count = self._sample_count
        last = None
        with SessionLocal() as session:
            row = (session.query(WifiSample)
                   .order_by(WifiSample.id.desc()).first())
            if row:
                last = row.to_dict()
        return {"enabled": self.enabled, "away": bool(self._is_away()),
                "pose": self.pose(), "sampleCount": count,
                "lastSample": last, "config": dict(self.config),
                "lastSniffAgeS": round(time.time() - self._last_sniff, 1)
                                 if self._last_sniff else None}

    def samples(self, limit: int = 100, since: float | None = None,
                until: float | None = None, source: str | None = None,
                min_aps: int = 0, every: int = 1) -> dict:
        """Filtered, newest-first slice of the sample store.

        `every` keeps one row in N (by id order) so a long unattended run
        can be thinned server-side; `matched` counts rows before thinning
        and `limit` applies after it.
        """
        limit = max(1, min(int(limit), MAX_SAMPLES_PER_QUERY))
        every = max(1, int(every))
        with SessionLocal() as session:
            total = session.query(WifiSample).count()
            query = session.query(WifiSample)
            if since is not None:
                query = query.filter(WifiSample.t >= float(since))
            if until is not None:
                query = query.filter(WifiSample.t <= float(until))
            if source in ("auto", "manual"):
                if source == "auto":
                    query = query.filter((WifiSample.source == "auto")
                                         | (WifiSample.source.is_(None)))
                else:
                    query = query.filter(WifiSample.source == source)
            rows = query.order_by(WifiSample.id.desc()).all()
        items = [row.to_dict() for row in rows]
        if min_aps > 0:
            items = [item for item in items if len(item["aps"]) >= min_aps]
        matched = len(items)
        out = items[::every][:limit]
        return {"samples": out, "matched": matched, "total": total,
                "returned": len(out)}
