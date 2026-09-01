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
"""
import json
import logging
import math
import re
import threading
import time

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

DEFAULTS = {
    "quietS": 5.0,          # no motion for this long -> a "motion gap"
    "minIntervalS": 60.0,   # politeness: at most one sniff per interval
    "strideMPerCycle": 0.10,  # tape-measure calibrated later (spatial MVP)
}

# Bounded-motion vocabulary the shadow understands. Anything else just
# stamps "moved" (drift grows, pose stays).
_ADVANCE = re.compile(r"^k(wk|tr|cr|bk)F\s+(\d+)$")
_TURN = re.compile(r"^k(?:wk|vt)([LR])\s+(\d+)$")


class WifiSample(Base):
    __tablename__ = "wifi_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    t: Mapped[float] = mapped_column()
    x: Mapped[float] = mapped_column(default=0.0)
    y: Mapped[float] = mapped_column(default=0.0)
    heading: Mapped[float] = mapped_column(default=0.0)
    drift_m: Mapped[float] = mapped_column(default=0.0)
    aps_json: Mapped[str] = mapped_column(Text, default="[]")

    def to_dict(self) -> dict:
        return {"id": self.id, "t": self.t, "x": round(self.x, 2),
                "y": round(self.y, 2), "heading": round(self.heading, 1),
                "driftM": round(self.drift_m, 2),
                "aps": json.loads(self.aps_json or "[]")}


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
        with SessionLocal() as session:
            self._sample_count = session.query(WifiSample).count()
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
                    self.sniff()
            except Exception:
                logger.exception("Sniff tick failed")

    def sniff(self) -> dict | None:
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
        pose = self.pose()
        sample = WifiSample(t=time.time(), x=pose["x"], y=pose["y"],
                            heading=pose["heading"], drift_m=pose["driftM"],
                            aps_json=json.dumps(aps))
        with SessionLocal() as session:
            session.add(sample)
            session.commit()
            result = sample.to_dict()
        with self._lock:
            self._sample_count = (self._sample_count or 0) + 1
        logger.info("Sniff: %d APs at (%.1f, %.1f)", len(aps),
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

    def samples(self, limit: int = 100) -> list[dict]:
        with SessionLocal() as session:
            rows = (session.query(WifiSample)
                    .order_by(WifiSample.id.desc()).limit(limit))
            return [r.to_dict() for r in rows]
