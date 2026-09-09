"""A* planner: routes around walls, prunes to waypoints, converts to legs."""
import time

from app.occupancy import OCCUPIED, OccupancyGrid
from app.path_planner import PathPlanner


def wall(grid, cells):
    for cx, cy in cells:
        grid.set_state(cx, cy, OCCUPIED)


def test_straight_line_on_an_empty_map_is_one_waypoint():
    grid = OccupancyGrid()
    planner = PathPlanner(grid)
    out = planner.plan((0.05, 0.05), (1.0, 0.05))
    assert out["ok"]
    assert out["waypoints"] == [(1.0, 0.05)]


def test_route_goes_around_a_wall():
    grid = OccupancyGrid()
    wall(grid, [(5, y) for y in range(-4, 5)])        # wall at x = 0.5 m
    planner = PathPlanner(grid)
    out = planner.plan((0.05, 0.05), (1.05, 0.05))
    assert out["ok"]
    blocked = planner.blocked_cells()
    for x, y in out["waypoints"]:
        assert grid.cell_of(x, y) not in blocked
    assert len(out["waypoints"]) >= 2                 # a detour, not a straight line
    assert out["waypoints"][-1] == (1.05, 0.05)
    assert max(abs(y) for _, y in out["waypoints"]) > 0.45


def test_walled_in_target_is_unreachable():
    grid = OccupancyGrid()
    ring = [(x, y) for x in range(8, 13) for y in range(-2, 3)
            if x in (8, 12) or y in (-2, 2)]
    wall(grid, ring)
    planner = PathPlanner(grid, {"goalSearchCells": 0})
    out = planner.plan((0.05, 0.05), (1.05, 0.05))
    assert not out["ok"] and "no route" in out["reason"]


def test_target_inside_an_obstacle_snaps_to_the_nearest_open_cell():
    grid = OccupancyGrid()
    wall(grid, [(10, 0)])
    planner = PathPlanner(grid)
    out = planner.plan((0.05, 0.05), (1.05, 0.05))
    assert out["ok"]
    assert out["goalCell"] != [10, 0]
    assert grid.cell_of(*out["waypoints"][-1]) not in planner.blocked_cells()


def test_unknown_cells_cost_more_than_seen_floor():
    grid = OccupancyGrid()
    for x in range(0, 11):
        for y in range(2, 4):
            grid.set_state(x, y, "free")                # a seen corridor at y = 0.25 m
    planner = PathPlanner(grid, {"unknownCost": 4.0})
    out = planner.plan((0.05, 0.05), (1.05, 0.05))
    assert out["ok"]
    assert any(y > 0.15 for _, y in out["waypoints"][:-1])


def test_planning_is_fast_on_a_room_sized_map():
    grid = OccupancyGrid()
    wall(grid, [(x, 30) for x in range(-30, 31)] + [(x, -30) for x in range(-30, 31)]
         + [(30, y) for y in range(-30, 31)] + [(-30, y) for y in range(-30, 31)]
         + [(0, y) for y in range(-20, 21)])
    planner = PathPlanner(grid)
    started = time.time()
    out = planner.plan((-2.5, 0.0), (2.5, 0.0))
    assert out["ok"]
    assert time.time() - started < 1.0


def test_legs_and_stride_conversion():
    planner = PathPlanner(OccupancyGrid())
    leg = planner.leg({"x": 0.0, "y": 0.0, "heading": 0.0}, (0.0, 1.0))
    assert leg["turnDeg"] == 90.0 and leg["cycles"] == 9 and not leg["arrived"]
    assert planner.turn_command(leg["turnDeg"]) == "kwkL 90"
    assert planner.turn_command(-45.0) == "kwkR 45"
    assert planner.advance_commands(leg["cycles"]) == ["kwkF 3", "kwkF 3", "kwkF 3"]
    assert planner.cycles_for(0.10) == 1 and planner.cycles_for(0.03) == 0
    assert round(planner.distance_for(9), 3) == 0.996
    small = planner.leg({"x": 0.0, "y": 0.0, "heading": 0.0}, (0.5, 0.05))
    assert small["turnDeg"] == 0.0                     # under the minimum turn
    near = planner.leg({"x": 0.0, "y": 0.0, "heading": 0.0}, (0.1, 0.0))
    assert near["arrived"]
