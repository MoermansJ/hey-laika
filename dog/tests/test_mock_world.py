"""The simulated room behind the mock controller."""
from app.bittle_controller import MockBittleController
from app.mock_world import DEFAULT_WALLS, MockWorld, rect


def test_ray_casts_hit_the_nearest_wall_within_two_metres():
    world = MockWorld(walls=rect(-1.0, -1.0, 3.0, 2.0))
    assert world.range_cm() is None                 # east wall is 3 m away
    world.turn(180)
    assert world.range_cm() == 100.0                # west wall at x = -1
    world.turn(-90)                                 # facing north (+y)
    assert world.range_cm() == 200.0
    assert world.range_cm(pan_deg=90) == 100.0      # panned left: west again


def test_commands_move_the_dog_by_the_calibrated_stride():
    world = MockWorld(walls=DEFAULT_WALLS)
    assert world.apply_command("kwkF 3")
    assert round(world.x, 3) == 0.324 and world.y == 0.0
    assert world.apply_command("kwkL 90") and world.heading == 90.0
    assert world.apply_command("kbkF 1") and round(world.y, 3) == -0.1
    assert world.apply_command("m 0 45") and world.pan_deg == 45.0
    assert not world.apply_command("ksit")
    assert world.moves == 3


def test_box_ahead_shows_up_in_the_default_room():
    world = MockWorld()
    assert world.range_cm() == 120.0
    world.apply_command("kwkF 3")
    assert world.range_cm() == 87.6


def test_mock_controller_uses_the_world():
    ctrl = MockBittleController()
    ctrl.connect()
    assert ctrl.read_range_cm(9) == 120.0
    ctrl.send_command("kwkL 90")
    assert ctrl.query("gp") == ["ICM: 0.00 0.00 9.81 90.00 0.0 0.0"]
    assert ctrl.read_range_cm(9) == 200.0
    ctrl.world.walls = rect(-1.0, -1.0, 3.0, 2.0)
    ctrl.move_joints([(0, 90)])                     # 'I' joint frames also pan
    assert ctrl.read_range_cm(9) == 100.0           # north + 90 left = west wall
