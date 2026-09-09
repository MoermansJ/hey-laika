"""Occupancy grid: cell maths, confidence, corrections, persistence."""
from app.models import init_db
from app.occupancy import FREE, OCCUPIED, UNKNOWN, OccupancyGrid


def setup_module(module):
    init_db()


def test_cells_and_centres():
    grid = OccupancyGrid(0.10)
    assert grid.cell_of(0.0, 0.0) == (0, 0)
    assert grid.cell_of(0.55, -0.05) == (5, -1)
    assert grid.center(5, -1) == (0.55, -0.05)


def test_one_hit_is_not_a_wall_two_are():
    grid = OccupancyGrid()
    assert grid.observe_hit(3, 3) == UNKNOWN
    assert grid.observe_hit(3, 3) == OCCUPIED
    assert grid.is_blocked(3, 3)
    assert grid.observe_free(3, 3) == UNKNOWN     # one miss casts doubt
    assert grid.observe_hit(3, 3) == OCCUPIED     # the next hit restores it
    cell = grid.get_cell(3, 3)
    assert cell["hits"] == 3 and cell["misses"] == 1


def test_one_miss_is_free_and_values_clamp():
    grid = OccupancyGrid()
    assert grid.observe_free(1, 1) == FREE
    for _ in range(40):
        grid.observe_free(1, 1)
    assert grid.logodds(1, 1) == -4.0
    assert grid.counts() == {"known": 1, "free": 1, "occupied": 0, "touched": 1}


def test_human_pin_survives_a_stray_reading():
    grid = OccupancyGrid()
    grid.set_state(2, 2, OCCUPIED)
    grid.observe_free(2, 2)
    assert grid.state(2, 2) == OCCUPIED
    grid.set_state(2, 2, UNKNOWN)
    assert grid.state(2, 2) == UNKNOWN and grid.counts()["touched"] == 0


def test_json_and_bounds():
    grid = OccupancyGrid()
    grid.observe_free(-2, 4)
    grid.observe_hit(7, -3)
    grid.observe_hit(7, -3)
    data = grid.to_json()
    assert data["bounds"] == {"minCx": -2, "maxCx": 7, "minCy": -3, "maxCy": 4}
    assert sorted(data["cells"]) == [[-2, 4, "f", -0.4], [7, -3, "o", 1.7]]
    assert grid.cells(bounds=(0, 10, -5, 0)) == [
        {"cx": 7, "cy": -3, "state": OCCUPIED, "logodds": 1.7}]


def test_save_and_load_round_trip():
    grid = OccupancyGrid()
    grid.clear()
    grid.save()
    grid.observe_hit(1, 2)
    grid.observe_hit(1, 2)
    grid.observe_free(0, 0)
    assert grid.save() == 2
    assert grid.save() == 0

    other = OccupancyGrid()
    assert other.load() == 2
    assert other.state(1, 2) == OCCUPIED and other.state(0, 0) == FREE
    assert other.get_cell(1, 2)["hits"] == 2

    other.set_state(1, 2, UNKNOWN)
    other.save()
    third = OccupancyGrid()
    assert third.load() == 1

    third.clear()
    third.save()
    assert OccupancyGrid().load() == 0
