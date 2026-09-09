"""Navigation end to end on the simulated room: routes, replanning around
a box, the reactive stop, overrides, error escalation and human answers."""
import time
from types import SimpleNamespace

import pytest

from app.arbiter import Arbiter
from app.behavior_store import BehaviorStore
from app.bittle_controller import MockBittleController
from app.map_builder import MapBuilder
from app.mock_world import DEFAULT_WALLS, MockWorld, rect
from app.models import init_db
from app.nav_errors import ErrorHandler, ErrorState
from app.navigator import NavigationRefused, NavigationService
from app.occupancy import OCCUPIED, OccupancyGrid
from app.path_planner import PathPlanner
from app.ranger import RangerService
from app.senses import SensesService
from app.sensor_log import ActionLog, SensorLog

ROOM = rect(-1.0, -1.0, 3.0, 2.0)
BOX = rect(1.2, -0.15, 1.5, 0.15)


class FakeMood:
    def __init__(self):
        self.calls = []

    def hold(self, mood):
        self.calls.append(("hold", mood))

    def release(self):
        self.calls.append(("release", None))


def setup_module(module):
    init_db()


def build(walls=None, config=None, arbiter_sleep=None, away=False):
    ctrl = MockBittleController()
    ctrl.world = MockWorld(walls=ROOM if walls is None else walls)
    ctrl.world.spin_deg_per_s = 720.0     # the real 9.4 deg/s would slow the suite
    ctrl.connect()
    store = BehaviorStore()
    store.init()
    arbiter = Arbiter(ctrl, store, sleep_fn=arbiter_sleep or (lambda s: None))
    senses = SensesService(ctrl)
    senses.instrument(ctrl)
    ranger = RangerService(ctrl, pin=9, min_interval_s=0.0)
    grid = OccupancyGrid()
    builder = MapBuilder(grid, {"flushS": 999})
    planner = PathPlanner(grid)
    errors = ErrorHandler(persist=False, sleep=lambda s: None)
    events, spoken, mood = [], [], FakeMood()
    error_state = ErrorState(arbiter, mood=mood, speak=spoken.append,
                             trigger=lambda e, p=None: events.append((e, p)),
                             handler=errors, speak_async=False)
    nav = NavigationService(
        ctrl, arbiter, senses, ranger, grid, builder, planner,
        SensorLog(persist=False), ActionLog(persist=False), errors, error_state,
        trigger=lambda e, p=None: events.append((e, p)),
        config={"sensorHz": 50, **(config or {})}, is_away=lambda: away,
        sleep=lambda s: None)
    nav.instrument(ctrl)
    senses.reset_pose(0.0)
    trail = []
    original = ctrl.send_command

    def tracked(command):
        ok = original(command)
        trail.append((command, ctrl.world.x, ctrl.world.y))
        return ok
    ctrl.send_command = tracked
    return SimpleNamespace(ctrl=ctrl, arbiter=arbiter, senses=senses, ranger=ranger,
                           grid=grid, builder=builder, planner=planner, nav=nav,
                           errors=errors, error_state=error_state, events=events,
                           spoken=spoken, mood=mood, trail=trail, store=store)


def wait_until(predicate, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def idle(h):
    status = h.arbiter.status()
    return status["current"] is None and not status["queued"]


def settled(h):
    return wait_until(lambda: not h.nav.active and idle(h))


def test_arrives_across_open_floor():
    h = build()
    result = h.nav.set_target(1.0, 0.0)
    assert result["status"] in ("executing", "queued")
    assert settled(h)
    assert h.nav.state == "arrived", h.nav.status()
    pose = h.senses.pose()
    assert abs(pose["x"] - 1.0) <= 0.15 and abs(pose["y"]) <= 0.15
    assert abs(h.ctrl.world.x - 1.0) <= 0.15
    assert any(e == "nav.arrived" for e, _ in h.events)
    assert any(c.startswith("kwkF") for c, _, _ in h.trail)
    kinds = {a["kind"] for a in h.nav.action_log.recent(50)}
    assert "advance" in kinds
    assert h.nav.status()["sensors"]["recorded"] > 0


def test_walks_around_the_box_and_maps_it():
    h = build(walls=DEFAULT_WALLS)
    h.nav.set_target(2.0, 0.0)
    assert settled(h)
    assert h.nav.state == "arrived", h.nav.status()
    assert abs(h.ctrl.world.x - 2.0) <= 0.2 and abs(h.ctrl.world.y) <= 0.2
    for _, x, y in h.trail:
        assert not (1.2 <= x <= 1.5 and -0.15 <= y <= 0.15), "walked through the box"
    occupied = h.grid.occupied_cells()
    assert any(11 <= cx <= 15 and -2 <= cy <= 1 for cx, cy in occupied), occupied
    assert h.nav.stats["sweeps"] >= 1
    assert any(e == "map.updated" for e, _ in h.events)


def test_unreachable_target_is_reported():
    ring = rect(1.0, -0.5, 2.0, 0.5)
    h = build(walls=ROOM + ring, config={"sweepAtStart": False})
    for cx in range(10, 21):
        for cy in (-5, 5):
            h.grid.set_state(cx, cy, OCCUPIED)
    for cy in range(-5, 6):
        for cx in (10, 20):
            h.grid.set_state(cx, cy, OCCUPIED)
    h.nav.set_target(1.5, 0.0)
    assert settled(h)
    assert h.nav.state == "unreachable"
    assert any(e == "nav.unreachable" for e, _ in h.events)
    assert h.nav.target is None


def test_reactive_stop_fires_on_forward_motion_only():
    wall = [((0.3, -1.0), (0.3, 2.0))]
    h = build(walls=ROOM + wall)
    h.ctrl.send_command("kbkF 1")             # backing up: never a stop
    h.nav._tick()
    assert h.nav.stats["stops"] == 0
    h.ctrl.world.x = 0.0
    h.ctrl.send_command("kwkF 1")
    h.nav._tick()
    assert h.nav.stats["stops"] == 1
    assert wait_until(lambda: idle(h))
    runs = [r["behavior"] for r in h.arbiter.status()["recentRuns"]]
    assert "obstacle_stop" in runs
    assert any(e == "nav.blocked" for e, _ in h.events)
    assert h.nav.last_block["rangeCm"] < 25
    assert h.grid.counts()["touched"] > 0


def test_override_suppresses_avoidance_until_it_ends():
    wall = [((0.3, -1.0), (0.3, 2.0))]
    h = build(walls=ROOM + wall, arbiter_sleep=time.sleep)
    h.ctrl.send_command("kwkF 1")             # now 20 cm from the wall
    h.nav.override(command="kjmp", settle_s=0.6)
    assert wait_until(lambda: h.arbiter.avoidance_suppressed(), 2.0)
    h.nav._tick()
    assert h.nav.stats["suppressed"] == 1 and h.nav.stats["stops"] == 0
    assert wait_until(lambda: idle(h), 3.0)
    assert not h.arbiter.avoidance_suppressed()
    h.nav._tick()
    assert h.nav.stats["stops"] == 1
    assert wait_until(lambda: idle(h), 5.0)


def test_route_blocked_by_a_surprise_wall_replans_and_gives_up_honestly():
    h = build(walls=ROOM + [((0.6, -1.0), (0.6, 2.0))],
              config={"sweepAtStart": False, "maxReplans": 3})
    h.nav.set_target(1.5, 0.0)
    assert settled(h)
    assert h.nav.state == "unreachable", h.nav.status()
    assert h.nav.blocked_count >= 1
    assert h.ctrl.world.x < 0.6
    assert h.grid.counts()["occupied"] >= 1


def test_three_contradictions_escalate_and_the_human_resolves():
    h = build(walls=ROOM + [((0.6, -1.0), (0.6, 2.0))])
    for cy in range(-3, 4):
        h.grid.set_state(6, cy, "free")            # the map insists it is floor
    for _ in range(3):
        h.nav.sweep()
        assert wait_until(lambda: idle(h))
    assert h.error_state.blocked
    assert h.nav.stats["escalated"] == 1
    assert ("hold", "error") in h.mood.calls
    assert h.spoken and "help" in h.spoken[0]
    assert any(e == "nav.error" for e, _ in h.events)
    runs = [r["behavior"] for r in h.arbiter.status()["recentRuns"]]
    assert "error_halt" in runs
    history = h.errors.history()
    assert [row["tier"] for row in history][:4] == \
        ["unrecoverable", "recoverable", "recoverable", "recoverable"]
    with pytest.raises(NavigationRefused):
        h.nav.set_target(0.3, 0.0)

    flagged = h.error_state.active["context"]["cells"]
    assert flagged and all(c["cx"] == 6 for c in flagged)
    result = h.error_state.respond("trust_sensor", note="it is a bookshelf")
    assert result["applied"]["cells"] == len(flagged)
    assert all(h.grid.state(c["cx"], c["cy"]) == OCCUPIED for c in flagged)
    assert not h.error_state.blocked
    assert ("release", None) in h.mood.calls
    assert h.errors.history()[-1]["resolution"] is None   # oldest recoverable row
    assert h.errors.history()[0]["resolution"] == "trust_sensor"
    assert any(e == "nav.error.resolved" for e, _ in h.events)


def test_manual_answer_cancels_the_route():
    h = build()
    h.error_state.enter(__import__("app.nav_errors", fromlist=["x"]).UnrecoverableError(
        "lost", "test"), None)
    assert wait_until(lambda: idle(h))
    h.nav.target = {"x": 1.0, "y": 0.0, "source": "manual", "setAt": 0}
    h.nav.state = "error"
    out = h.error_state.respond("manual")
    assert out["applied"] == {"choice": "manual", "cells": 0, "resumed": False}
    assert h.nav.target is None and h.nav.state == "idle"


def test_yaw_fusion_corrects_heading_and_counts_disagreement():
    h = build()
    h.ctrl.world.turn(40.0)                    # somebody turned her by hand
    h.nav._after_motion()
    assert h.senses.pose()["heading"] == 40.0
    assert h.errors.counts["localization_drift"] == 1
    h.nav._after_motion()                      # agrees now: streak cleared
    assert h.errors.counts.get("localization_drift", 0) == 0


def test_sensor_jump_while_still_is_an_anomaly():
    h = build(walls=ROOM + [((1.9, -1.0), (1.9, 2.0))])
    h.nav.sample()
    h.ctrl.world.walls = ROOM + [((0.2, -1.0), (0.2, 2.0))]
    h.nav.sample()
    assert h.errors.counts["sensor_anomaly"] == 1


def test_away_mode_refuses_navigation():
    h = build(away=True)
    with pytest.raises(NavigationRefused):
        h.nav.set_target(1.0, 0.0)


def test_status_and_map_json_shapes():
    h = build()
    status = h.nav.status()
    assert status["state"] == "idle" and status["avoidance"]["stopCm"] == 25.0
    assert {"sensors", "map", "errors", "config", "stats"} <= status.keys()
    data = h.nav.map_json()
    assert data["resolutionM"] == 0.1 and "cells" in data and data["pose"]["x"] == 0.0
    h.nav.configure({"stopCm": 30, "avoidanceEnabled": False, "sweepAngles": [-45, 0, 45]})
    assert h.nav.config["stopCm"] == 30.0 and h.nav.config["avoidanceEnabled"] is False
    assert h.nav.config["sweepAngles"] == [-45.0, 0.0, 45.0]
