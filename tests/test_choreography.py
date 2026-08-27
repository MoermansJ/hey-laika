from app.choreography import ChoreographyLibrary


def test_default_animations_present():
    lib = ChoreographyLibrary()
    names = lib.names()
    for expected in ("walk_forward", "spin_right", "wave_arm", "play_dead",
                     "stretch", "excited_jump", "curious_sniff"):
        assert expected in names


def test_build_command_sequence():
    lib = ChoreographyLibrary()
    frames = lib.build_command_sequence("walk_forward")
    assert frames, "walk_forward should produce frames"
    assert all(f.command and f.duration > 0 for f in frames)


def test_unknown_animation_is_empty():
    assert ChoreographyLibrary().build_command_sequence("moonwalk") == []
