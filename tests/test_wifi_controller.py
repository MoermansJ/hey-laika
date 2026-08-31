"""Unit tests for WiFiBittleController against a scripted fake WebSocket.

Frame fixtures mirror the stock BiBoard firmware's task protocol
(opencat-esp32 webServer.h): JSON frames matched by taskId with status
running/completed/error, interleaved connected/heartbeat noise, and
"b64:" base64(token + int8 args) for binary commands.
"""
import base64
import json
import sys
import types

import pytest

import app.bittle_controller as bc
from app.bittle_controller import (SerialBittleController,
                                   WiFiBittleController,
                                   create_bittle_controller)


class FakeWebSocket:
    def __init__(self, handler=None):
        self.sent: list[dict] = []
        self.queue: list = []
        self.handler = handler
        self.closed = False

    def settimeout(self, timeout):
        pass

    def send(self, raw):
        if self.closed:
            raise RuntimeError("socket is already closed.")
        frame = json.loads(raw)
        self.sent.append(frame)
        if self.handler:
            self.queue.extend(self.handler(frame))

    def recv(self):
        if not self.queue:
            raise TimeoutError("no frame queued")
        item = self.queue.pop(0)
        return item if isinstance(item, str) else json.dumps(item)

    def close(self):
        self.closed = True


def replies(frame, results=None, noise=()):
    """Firmware reply sequence for one command frame, with optional noise."""
    tid = frame["taskId"]
    return [*noise,
            {"taskId": tid, "status": "running"},
            {"taskId": tid, "status": "completed", "results": results or []}]


BANNER = ["Bittle X\r\nSoftware version: B10_251121"]

# Same capture layout as the serial tests (tab/comma j-response).
J_RESULTS = ["=\n"
             "0\t1\t2\t3\t4\t5\t6\t7\t8\t9\t10\t11\t12\t13\t14\t15\t\n"
             "30,\t-82,\t-47,\t-2,\t0,\t0,\t0,\t0,\t73,\t73,\t73,\t73,\t"
             "-57,\t-57,\t-57,\t-57,\t"]


@pytest.fixture()
def controller(monkeypatch):
    monkeypatch.setattr(bc, "_TIMEOUT_DEFAULT", 0.25)
    monkeypatch.setattr(bc, "_TIMEOUT_SKILL_WS", 0.25)
    ctrl = WiFiBittleController("fake-host")
    ctrl._ws = FakeWebSocket()
    return ctrl


def ws_module(monkeypatch, factory):
    """Install a fake `websocket` module whose create_connection is factory."""
    mod = types.ModuleType("websocket")
    mod.create_connection = factory
    monkeypatch.setitem(sys.modules, "websocket", mod)


def test_command_walks_task_states_and_skips_noise(controller):
    noise = [{"type": "connected"},
             {"type": "heartbeat"},
             {"taskId": "someone-elses-task", "status": "completed"},
             "not even json"]
    controller._ws.handler = lambda f: replies(f, noise=noise)
    assert controller.send_command("ksit") is True
    frame = controller._ws.sent[0]
    assert frame["type"] == "command"
    assert frame["commands"] == ["ksit"]
    assert isinstance(frame["taskId"], str)
    assert controller.last_command == "ksit"
    assert controller.commands_sent == 1


def test_error_status_fails(controller):
    controller._ws.handler = lambda f: [
        {"taskId": f["taskId"], "status": "error", "error": "boom"}]
    assert controller.send_command("kup") is False
    assert controller.commands_sent == 0


def test_no_completion_times_out(controller):
    # Firmware never replies (e.g. task silently dropped): give up at deadline.
    assert controller.send_command("m0 20") is False


def test_move_joints_b64_encoding(controller):
    controller._ws.handler = replies
    assert controller.move_joints([(0, 30), (12, -40)]) is True
    command = controller._ws.sent[0]["commands"][0]
    assert command.startswith("b64:")
    # Raw token + int8 pairs; the firmware appends the '~' itself.
    assert base64.b64decode(command[4:]) == b"I\x00\x1e\x0c\xd8"


def test_move_joints_validation(controller):
    with pytest.raises(ValueError):
        controller.move_joints([(3, 10)])  # phantom joint
    with pytest.raises(ValueError):
        controller.move_joints([(0, 126)])  # beyond int8 clamp


def test_read_joint_angles_parses_results(controller):
    controller._ws.handler = lambda f: replies(f, results=J_RESULTS)
    assert controller.read_joint_angles() == [
        30, -82, -47, -2, 0, 0, 0, 0, 73, 73, 73, 73, -57, -57, -57, -57]


def test_reconnect_and_retry_after_dropped_socket(controller, monkeypatch):
    # Firmware drops idle clients (>40s); the next send must reconnect.
    dead = controller._ws
    dead.closed = True
    fresh = FakeWebSocket(handler=lambda f: replies(
        f, results=BANNER if f["commands"] == ["?"] else ["ok"]))
    ws_module(monkeypatch, lambda url, timeout: fresh)
    assert controller.send_command("khi") is True
    assert controller._ws is fresh
    assert [f["commands"] for f in fresh.sent] == [["?"], ["khi"]]


def test_connect_parses_banner(monkeypatch):
    monkeypatch.setattr(bc, "_TIMEOUT_DEFAULT", 0.25)
    ws = FakeWebSocket(handler=lambda f: replies(f, results=BANNER))
    ws_module(monkeypatch, lambda url, timeout: ws)
    ctrl = WiFiBittleController("fake-host", 8181)
    assert ctrl.connect() is True
    assert ctrl.get_info() == {"model": "Bittle X",
                               "firmwareVersion": "B10_251121"}


def test_connect_ignores_junk_banner(monkeypatch):
    # Stale frames from a dropped task can pollute the '?' reply.
    ws = FakeWebSocket(handler=lambda f: replies(f, results=["G", "X"]))
    ws_module(monkeypatch, lambda url, timeout: ws)
    ctrl = WiFiBittleController("fake-host")
    assert ctrl.connect() is True
    assert ctrl.get_info() == {"model": None, "firmwareVersion": None}


def test_factory_serial_and_wifi_branches():
    class Cfg:
        MOCK_MODE = False
        BITTLE_COMMUNICATION_METHOD = "wifi"
        BITTLE_WIFI_HOST = "10.0.0.5"
        BITTLE_WIFI_PORT = 8181
        BITTLE_SERIAL_PORT = "COM9"
        BITTLE_SERIAL_BAUD = 57600

    wifi = create_bittle_controller(Cfg)
    assert isinstance(wifi, WiFiBittleController)
    assert (wifi.host, wifi.port) == ("10.0.0.5", 8181)

    Cfg.BITTLE_COMMUNICATION_METHOD = "serial"
    serial = create_bittle_controller(Cfg)
    assert isinstance(serial, SerialBittleController)
    assert (serial.port, serial.baudrate) == ("COM9", 57600)
