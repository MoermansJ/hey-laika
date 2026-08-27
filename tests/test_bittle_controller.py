from app.bittle_controller import MockBittleController, create_bittle_controller


def test_factory_returns_mock_in_mock_mode():
    controller = create_bittle_controller()
    assert isinstance(controller, MockBittleController)


def test_mock_controller_tracks_commands():
    c = MockBittleController()
    assert c.connect()
    assert c.send_command("kwkF")
    assert c.send_command("kbalance")
    status = c.get_status()
    assert status["connected"] is True
    assert status["last_command"] == "kbalance"
    assert status["commands_sent"] == 2
