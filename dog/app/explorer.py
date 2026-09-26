"""Roaming Assistant's explorer: walks to the nearest unmapped frontier,
stands, photographs it and stores a collection point, then repeats.

P2 v1 (PERSONALITY_MODES_BRIEF.md §5, concrete plan in §7a): frontier cells
are free cells next to unknown ones on the existing occupancy grid; score is
nearby-unknown-cell count over the planner's path distance to it (no
energy-per-metre division yet — that needs drain data this project doesn't
have). Walking itself reuses the navigator's existing target mechanics
(NavigationService.set_target, the same path /navigation/target already
drives) rather than a new arbiter behavior. Captioning is stubbed to a fixed
string until P3 wires a local vision model in.
"""
import logging
import math
import threading
import time
from pathlib import Path

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import Config
from app.models import Base, SessionLocal, engine
from app.navigator import NavigationRefused

logger = logging.getLogger(__name__)

DEFAULTS = {
    "minScore": 0.15,           # unknown cells per metre of path; below this, stop
    "frontierRadiusCells": 6,   # ~60 cm at the default 10 cm grid resolution
    "batteryFloor": 20.0,       # percent
    "sessionCapS": 1200.0,      # wall-clock cap for one exploration session
    "pollIntervalS": 1.0,
    "arriveTimeoutS": 90.0,     # give up on a stuck route rather than loop forever
    "maxConsecutiveRefusals": 5,  # e.g. an open nav error waiting for a human
}

STUB_CAPTION = "A view of the room."
MAX_POINTS = 300   # size-capped ring: the oldest point (row + photo) is dropped

_TERMINAL_STATES = ("arrived", "unreachable", "failed", "cancelled", "idle", "error")


class CollectionPoint(Base):
    __tablename__ = "collection_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    t: Mapped[float] = mapped_column()
    x: Mapped[float] = mapped_column()
    y: Mapped[float] = mapped_column()
    heading: Mapped[float] = mapped_column(default=0.0)
    has_photo: Mapped[bool] = mapped_column(default=False)
    caption: Mapped[str] = mapped_column(Text, default="")
    battery: Mapped[float | None] = mapped_column(nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "t": self.t, "x": round(self.x, 2), "y": round(self.y, 2),
                "heading": round(self.heading, 1), "hasPhoto": self.has_photo,
                "caption": self.caption, "battery": self.battery}


class ExplorerService:
    def __init__(self, navigation, grid, planner, senses, eyes,
                 battery_reader=lambda: None, trigger=None,
                 config: dict | None = None, photo_dir: Path | None = None,
                 sleep=time.sleep, clock=time.time):
        self.navigation = navigation
        self.grid = grid
        self.planner = planner
        self.senses = senses
        self.eyes = eyes
        self._battery = battery_reader
        self.trigger = trigger or (lambda event, payload=None: None)
        self.config = {**DEFAULTS, **(config or {})}
        self.photo_dir = photo_dir or (Config.data_dir() / "collection_points")
        self._sleep = sleep
        self._clock = clock

        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None
        self._stopped_reason: str | None = None
        self.points_visited = 0

    # ---- lifecycle -----------------------------------------------------

    def init(self) -> None:
        Base.metadata.create_all(engine, tables=[CollectionPoint.__table__])
        self.photo_dir.mkdir(parents=True, exist_ok=True)

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._started_at = self._clock()
            self._stopped_reason = None
            self.points_visited = 0
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        logger.info("Explorer: started")
        return True

    def stop(self) -> bool:
        with self._lock:
            if not self._running:
                return False
            self._running = False
        self.navigation.cancel()
        logger.info("Explorer: stopped")
        return True

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def status(self) -> dict:
        with self._lock:
            return {"running": self._running, "pointsVisited": self.points_visited,
                    "startedAt": self._started_at, "stoppedReason": self._stopped_reason}

    # ---- the loop --------------------------------------------------------

    def _run(self) -> None:
        refusals = 0
        while self.running:
            if self._session_over():
                self._halt("session cap reached")
                return
            battery = self._safe_battery()
            if battery is not None and battery < float(self.config["batteryFloor"]):
                self._halt("battery floor reached")
                return
            target = self._pick_frontier()
            if target is None:
                self._halt("no frontier scored above the threshold")
                return
            tx, ty, _score = target
            try:
                result = self.navigation.set_target(tx, ty, source="agent")
            except NavigationRefused:
                result = {"status": "rejected"}
            if result.get("status") == "rejected":
                refusals += 1
                if refusals >= int(self.config["maxConsecutiveRefusals"]):
                    self._halt("navigation refused repeatedly "
                              "(an open error or away mode may be blocking it)")
                    return
                self._sleep(float(self.config["pollIntervalS"]))
                continue
            refusals = 0
            outcome = self._await_arrival()
            if not self.running:
                return
            if outcome == "arrived":
                self._collect()
            # unreachable/failed/cancelled/timeout: try a different frontier

    def _session_over(self) -> bool:
        return self._started_at is not None and \
            self._clock() - self._started_at > float(self.config["sessionCapS"])

    def _halt(self, reason: str) -> None:
        with self._lock:
            self._running = False
            self._stopped_reason = reason
        logger.info("Explorer: stopping (%s)", reason)
        self.trigger("explore.stopped", {"reason": reason, "points": self.points_visited})

    def _safe_battery(self):
        try:
            return self._battery()
        except Exception:
            return None

    def _await_arrival(self) -> str:
        deadline = self._clock() + float(self.config["arriveTimeoutS"])
        while self.running and self._clock() < deadline:
            if self.navigation.state in _TERMINAL_STATES:
                return self.navigation.state
            self._sleep(float(self.config["pollIntervalS"]))
        if self.running:
            self.navigation.cancel()
        return "timeout"

    # ---- frontier scoring --------------------------------------------------

    def _pick_frontier(self):
        known = {(c["cx"], c["cy"]): c["state"] for c in self.grid.cells(known_only=True)}
        free = [cell for cell, state in known.items() if state == "free"]
        if not free:
            return None
        radius = int(self.config["frontierRadiusCells"])
        pose = self.senses.pose()
        best = None
        for cx, cy in free:
            if not self._is_frontier(cx, cy, known):
                continue
            wx, wy = self.grid.center(cx, cy)
            unknown_nearby = self._unknown_nearby(cx, cy, radius, known)
            distance = self._path_distance(pose, wx, wy)
            if distance <= 0.05:
                continue
            score = unknown_nearby / distance
            if best is None or score > best[2]:
                best = (wx, wy, score)
        if best is None or best[2] < float(self.config["minScore"]):
            return None
        return best

    @staticmethod
    def _is_frontier(cx: int, cy: int, known: dict) -> bool:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (cx + dx, cy + dy) not in known:
                return True
        return False

    @staticmethod
    def _unknown_nearby(cx: int, cy: int, radius: int, known: dict) -> int:
        count = 0
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if (cx + dx, cy + dy) not in known:
                    count += 1
        return count

    def _path_distance(self, pose: dict, wx: float, wy: float) -> float:
        plan = self.planner.plan((pose["x"], pose["y"]), (wx, wy))
        if not plan.get("ok"):
            return math.hypot(wx - pose["x"], wy - pose["y"])
        points = [(pose["x"], pose["y"]), *plan["waypoints"]]
        total = sum(math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
                    for i in range(len(points) - 1))
        return total or 0.05

    # ---- arrival: stand, photograph, store -----------------------------

    def _collect(self) -> None:
        pose = self.senses.pose()
        photo_bytes = None
        try:
            photo_bytes = self.eyes.capture()
        except Exception as exc:
            logger.warning("Explorer: photo capture failed: %s", exc)
        battery = self._safe_battery()
        with SessionLocal() as session:
            point = CollectionPoint(t=self._clock(), x=pose["x"], y=pose["y"],
                                    heading=pose["heading"], has_photo=photo_bytes is not None,
                                    caption=STUB_CAPTION, battery=battery)
            session.add(point)
            session.commit()
            point_id = point.id
        if photo_bytes is not None:
            (self.photo_dir / f"{point_id}.jpg").write_bytes(photo_bytes)
        self._prune()
        self.points_visited += 1
        logger.info("Explorer: collection point #%d at (%.1f, %.1f)",
                    point_id, pose["x"], pose["y"])
        self.trigger("explore.point", {"id": point_id, "x": pose["x"], "y": pose["y"]})

    def _prune(self) -> None:
        with SessionLocal() as session:
            total = session.query(CollectionPoint).count()
            if total <= MAX_POINTS:
                return
            old = (session.query(CollectionPoint).order_by(CollectionPoint.id.asc())
                   .limit(total - MAX_POINTS).all())
            for row in old:
                (self.photo_dir / f"{row.id}.jpg").unlink(missing_ok=True)
                session.delete(row)
            session.commit()

    # ---- reporting for the GUI --------------------------------------------

    def points(self, limit: int = 200, since: float | None = None,
               until: float | None = None) -> dict:
        limit = max(1, min(int(limit), MAX_POINTS))
        with SessionLocal() as session:
            total = session.query(CollectionPoint).count()
            query = session.query(CollectionPoint)
            if since is not None:
                query = query.filter(CollectionPoint.t >= float(since))
            if until is not None:
                query = query.filter(CollectionPoint.t <= float(until))
            rows = query.order_by(CollectionPoint.id.desc()).limit(limit).all()
        items = [row.to_dict() for row in rows]
        return {"points": items, "total": total, "returned": len(items)}

    def photo(self, point_id: int) -> bytes | None:
        path = self.photo_dir / f"{int(point_id)}.jpg"
        if not path.is_file():
            return None
        return path.read_bytes()
