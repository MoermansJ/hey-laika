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


def test_mock_controller_simulates_telemetry():
    c = MockBittleController()
    telemetry = c.get_telemetry()
    assert 0 <= telemetry["battery"] <= 100
    assert telemetry["signal"] == "strong"


def test_mock_rich_synthesizes_scans(monkeypatch):
    from app.config import Config
    from app.bittle_controller import MockBittleController

    monkeypatch.setattr(Config, "MOCK_RICH", True)
    ctrl = MockBittleController()
    lines = ctrl.query("XWs")
    assert lines and "MockSpot" in lines[0] and "bssid" in lines[0]
    # Plain mock (default) stays inert for tests.
    monkeypatch.setattr(Config, "MOCK_RICH", False)
    assert MockBittleController().query("XWs") is None
