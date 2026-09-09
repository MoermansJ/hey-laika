"""Map builder: ray casting, echo handling, contradictions, sweeps."""
from app.map_builder import MapBuilder
from app.occupancy import FREE, OCCUPIED, UNKNOWN, OccupancyGrid


def make():
    grid = OccupancyGrid(0.10)
    return grid, MapBuilder(grid, {"flushS": 999})


def test_ray_marks_free_up_to_the_echo_and_a_hit_at_it():
    grid, builder = make()
    pose = {"x": 0.05, "y": 0.05, "heading": 0.0}
    out = builder.integrate(55.0, pose)
    assert out["hit"]["cx"] == 6 and out["hit"]["cy"] == 0
    assert out["freed"] == 6
    assert grid.state(3, 0) == FREE
    assert grid.state(6, 0) == UNKNOWN          # one hit is not a wall yet
    builder.integrate(55.0, pose)
    assert grid.state(6, 0) == OCCUPIED
    assert builder.stats["integrated"] == 2


def test_heading_and_pan_rotate_the_ray():
    grid, builder = make()
    pose = {"x": 0.05, "y": 0.05, "heading": 90.0}
    out = builder.integrate(33.0, pose)                  # echo at y = 0.38 m
    assert (out["hit"]["cx"], out["hit"]["cy"]) == (0, 3)
    out = builder.integrate(33.0, pose, pan_deg=-90.0)   # panned right: east
    assert (out["hit"]["cx"], out["hit"]["cy"]) == (3, 0)


def test_no_echo_and_own_body_are_skipped():
    grid, builder = make()
    pose = {"x": 0.0, "y": 0.0, "heading": 0.0}
    assert builder.integrate(None, pose)["skipped"] == "no echo"
    assert builder.integrate(2.0, pose)["skipped"].startswith("too close")
    assert grid.counts()["touched"] == 0
    assert builder.stats["skipped"] == 2


def test_beyond_max_range_frees_the_beam_without_a_hit():
    grid, builder = make()
    out = builder.integrate(250.0, {"x": 0.05, "y": 0.05, "heading": 0.0})
    assert out["hit"] is None and out["freed"] == 21
    assert grid.state(19, 0) == FREE


def test_contradictions_are_reported_then_integrated():
    grid, builder = make()
    pose = {"x": 0.05, "y": 0.05, "heading": 0.0}
    for _ in range(3):
        builder.integrate(90.0, pose)          # cells 0..8 confidently free
    out = builder.integrate(45.0, pose)        # now an echo at x = 0.50 m, cell 5
    kinds = [c["kind"] for c in out["contradictions"]]
    assert kinds == ["occupied_where_free"]
    assert out["contradictions"][0]["cx"] == 5
    assert builder.stats["contradictions"] == 1

    grid.set_state(6, 0, OCCUPIED)
    out = builder.integrate(120.0, pose)       # beam passes through the pinned wall
    passed = {(c["kind"], c["cx"]) for c in out["contradictions"]}
    assert ("free_where_occupied", 6) in passed
    assert ("free_where_occupied", 9) in passed  # the wall the 90 cm echoes built
    assert grid.state(6, 0) == OCCUPIED        # a pin outlives one reading


def test_corrections_pin_whichever_side_the_human_trusts():
    grid, builder = make()
    cells = [{"kind": "occupied_where_free", "cx": 4, "cy": 0},
             {"kind": "free_where_occupied", "cx": 6, "cy": 0}]
    assert builder.apply_correction(cells, "sensor") == 2
    assert grid.state(4, 0) == OCCUPIED and grid.state(6, 0) == FREE
    builder.apply_correction(cells, "map")
    assert grid.state(4, 0) == FREE and grid.state(6, 0) == OCCUPIED


def test_sweep_integrates_every_pan():
    grid, builder = make()
    pose = {"x": 0.05, "y": 0.05, "heading": 0.0}
    out = builder.integrate_sweep([(-90, 30.0), (0, 30.0), (90, None)], pose)
    assert out["readings"] == 3 and out["hits"] == 2
    assert grid.get_cell(3, 0)["hits"] == 1 and grid.get_cell(0, -3)["hits"] == 1
