"""Roaming Assistant's frontier explorer: picking a target, walking there on
the real navigation stack (mock world), collecting a point, and the stop
conditions (battery floor, session cap, no frontier left)."""
import tempfile
import time
from pathlib import Path

from app.arbiter import Arbiter
from app.behavior_store import BehaviorStore
from app.bittle_controller import MockBittleController
from app.explorer import MAX_POINTS, ExplorerService
from app.map_builder import MapBuilder
from app.mock_world import MockWorld, rect
from app.models import init_db
from app.nav_errors import ErrorHandler, ErrorState
from app.navigator import NavigationService
from app.occupancy import OccupancyGrid
from app.path_planner import PathPlanner
from app.sensor_log import ActionLog, SensorLog
from app.senses import SensesService

ROOM = rect(-3.0, -3.0, 3.0, 3.0)


class FakeMood:
    def hold(self, mood):
        pass

    def release(self):
        pass


class FakeEyes:
    def __init__(self, jpeg: bytes | None = b"\xff\xd8fake-jpeg"):
        self.jpeg = jpeg
        self.calls = 0

    def capture(self) -> bytes:
        self.calls += 1
        if self.jpeg is None:
            raise RuntimeError("satellite unreachable")
        return self.jpeg


def setup_module(module):
    init_db()


def build(explorer_config=None, battery=100.0, eyes=None, photo_dir=None, clock=None):
    ctrl = MockBittleController()
    ctrl.world = MockWorld(walls=ROOM)
    ctrl.world.spin_deg_per_s = 720.0   # the real 9.4 deg/s would slow the suite
    ctrl.connect()
    store = BehaviorStore()
    store.init()
    arbiter = Arbiter(ctrl, store, sleep_fn=lambda s: None)
    senses = SensesService(ctrl)
    senses.instrument(ctrl)
    grid = OccupancyGrid()
    builder = MapBuilder(grid, {"flushS": 999})
    planner = PathPlanner(grid)
    errors = ErrorHandler(persist=False, sleep=lambda s: None)
    error_state = ErrorState(arbiter, mood=FakeMood(), speak=None,
                             handler=errors, speak_async=False)
    nav = NavigationService(
        ctrl, arbiter, senses, None, grid, builder, planner,
        SensorLog(persist=False), ActionLog(persist=False), errors, error_state,
        config={"sensorHz": 50}, sleep=lambda s: None)
    nav.instrument(ctrl)
    senses.reset_pose(0.0)

    explorer = ExplorerService(
        nav, grid, planner, senses, eyes or FakeEyes(),
        battery_reader=lambda: battery,
        config={"pollIntervalS": 0.01, "arriveTimeoutS": 5.0, "minScore": 0.0,
                **(explorer_config or {})},
        photo_dir=photo_dir or Path(tempfile.mkdtemp()),
        clock=clock or time.time)
    explorer.init()
    return explorer, grid, senses


def seed_frontier(grid: OccupancyGrid, half: int = 3):
    """A small square of known-free cells around the origin, its edges
    bordering unknown space — enough for `_pick_frontier` to find a target."""
    for cx in range(-half, half + 1):
        for cy in range(-half, half + 1):
            grid.observe_free(cx, cy)
            grid.observe_free(cx, cy)   # two misses to clear the UNKNOWN band


def wait_until(predicate, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_given_no_known_floor_when_started_then_it_halts_immediately_with_no_frontier():
    explorer, _grid, _senses = build()

    explorer.start()
    try:
        assert wait_until(lambda: not explorer.running)
        assert explorer.status()["stoppedReason"] == "no frontier scored above the threshold"
        assert explorer.points_visited == 0
    finally:
        explorer.stop()


def test_given_battery_under_the_floor_when_started_then_it_halts_without_walking():
    explorer, grid, _senses = build(battery=10.0, explorer_config={"batteryFloor": 20.0})
    seed_frontier(grid)

    explorer.start()
    try:
        assert wait_until(lambda: not explorer.running)
        assert explorer.status()["stoppedReason"] == "battery floor reached"
        assert explorer.points_visited == 0
    finally:
        explorer.stop()


def test_given_a_clock_past_the_session_cap_when_started_then_it_halts():
    values = iter([0.0, 5000.0, 5000.0, 5000.0])
    explorer, grid, _senses = build(
        explorer_config={"sessionCapS": 1200.0},
        clock=lambda: next(values, 5000.0))
    seed_frontier(grid)

    explorer.start()
    try:
        assert wait_until(lambda: not explorer.running)
        assert explorer.status()["stoppedReason"] == "session cap reached"
    finally:
        explorer.stop()


def test_given_a_frontier_when_started_then_she_walks_there_and_a_collection_point_is_stored():
    explorer, grid, senses = build()
    seed_frontier(grid)

    explorer.start()
    try:
        assert wait_until(lambda: explorer.points_visited >= 1, timeout=10.0)
    finally:
        explorer.stop()
    assert wait_until(lambda: not explorer.running)

    # >=1, not ==1: stop() and the background loop race (minScore=0 means she
    # never runs out of frontier on her own), so a second visit can land
    # between "points_visited hit 1" and stop() taking effect. The property
    # under test is that a visit produces a correctly-stored point, not a
    # specific count.
    page = explorer.points(limit=10)
    assert page["returned"] >= 1
    point = page["points"][0]
    assert point["hasPhoto"] is True
    assert point["caption"] == "A view of the room."
    assert explorer.photo(point["id"]) == b"\xff\xd8fake-jpeg"


def test_given_the_satellite_unreachable_when_she_arrives_then_the_point_is_stored_without_a_photo():
    explorer, grid, senses = build(eyes=FakeEyes(jpeg=None))
    seed_frontier(grid)

    explorer.start()
    try:
        assert wait_until(lambda: explorer.points_visited >= 1, timeout=10.0)
    finally:
        explorer.stop()

    point = explorer.points(limit=10)["points"][0]
    assert point["hasPhoto"] is False
    assert explorer.photo(point["id"]) is None


def test_given_a_running_explorer_when_stopped_then_the_route_is_cancelled_and_the_loop_ends():
    explorer, grid, senses = build(explorer_config={"arriveTimeoutS": 30.0})
    seed_frontier(grid)

    explorer.start()
    try:
        assert wait_until(lambda: explorer.running)
    finally:
        explorer.stop()

    assert wait_until(lambda: not explorer.running)
    assert explorer.navigation.target is None or explorer.navigation.state in (
        "cancelled", "idle", "arrived")


def test_given_more_points_than_the_cap_when_collected_then_the_oldest_is_pruned(monkeypatch):
    import app.explorer as explorer_module

    monkeypatch.setattr(explorer_module, "MAX_POINTS", 2)
    explorer, grid, senses = build()
    photo_dir = explorer.photo_dir

    for _ in range(3):
        explorer._collect()

    page = explorer.points(limit=10)
    assert page["total"] == 2
    assert page["points"][0]["id"] > page["points"][1]["id"]
    remaining_ids = {p["id"] for p in page["points"]}
    assert len(list(photo_dir.glob("*.jpg"))) == len(remaining_ids)


def test_given_default_max_points_when_asked_then_it_is_the_documented_ring_size():
    assert MAX_POINTS == 300


class RefusingNavigation:
    """Stands in for a navigator stuck behind an open error waiting for a
    human (e.g. dead-reckoning drift past the limit) — every target is
    refused, never accepted."""
    state = "idle"
    target = None

    def set_target(self, x, y, source="agent"):
        from app.navigator import NavigationRefused
        raise NavigationRefused("an error is waiting for a human answer")

    def cancel(self):
        return {"stopped": False}


def test_given_navigation_persistently_refused_when_started_then_it_gives_up():
    grid = OccupancyGrid()
    seed_frontier(grid)
    planner = PathPlanner(grid)
    senses = SensesService(MockBittleController())
    senses.reset_pose(0.0)
    explorer = ExplorerService(
        RefusingNavigation(), grid, planner, senses, FakeEyes(),
        battery_reader=lambda: 100.0,
        config={"pollIntervalS": 0.01, "maxConsecutiveRefusals": 3, "minScore": 0.0},
        photo_dir=Path(tempfile.mkdtemp()))
    explorer.init()

    explorer.start()
    try:
        assert wait_until(lambda: not explorer.running, timeout=5.0)
        assert explorer.status()["stoppedReason"] == (
            "navigation refused repeatedly "
            "(an open error or away mode may be blocking it)")
    finally:
        explorer.stop()
