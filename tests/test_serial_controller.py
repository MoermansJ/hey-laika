"""Unit tests for SerialBittleController against a scripted fake port.

Response fixtures mirror real captures from firmware B10_251121
(orchestrator/docs/VALIDATION_RESULTS.md): \r\n line endings, echo-on-
completion, tab/comma j-response layout, unsolicited X… noise lines.
"""
import pytest

import app.bittle_controller as bc
from app.bittle_controller import SerialBittleController


class FakeSerial:
    def __init__(self, responses: bytes = b""):
        self.buffer = bytearray(responses)
        self.writes: list[bytes] = []

    @property
    def in_waiting(self):
        return len(self.buffer)

    def write(self, data):
        self.writes.append(bytes(data))

    def read(self, n):
        out = bytes(self.buffer[:n])
        del self.buffer[:n]
        return out

    def reset_input_buffer(self):
        self.buffer.clear()

    def close(self):
        pass


J_RESPONSE = (b"XAd\r\n=\r\n"
              b"0\t1\t2\t3\t4\t5\t6\t7\t8\t9\t10\t11\t12\t13\t14\t15\t\r\n"
              b"30,\t-82,\t-47,\t-2,\t0,\t0,\t0,\t0,\t73,\t73,\t73,\t73,\t"
              b"-57,\t-57,\t-57,\t-57,\t\r\nj\r\n")


@pytest.fixture()
def controller(monkeypatch):
    monkeypatch.setattr(bc, "_TIMEOUT_DEFAULT", 0.25)
    monkeypatch.setattr(bc, "_TIMEOUT_SKILL", 0.25)
    ctrl = SerialBittleController("FAKE")
    ctrl._serial = FakeSerial()
    return ctrl


def feed(ctrl, data: bytes):
    ctrl._serial.buffer.extend(data)


def written(ctrl) -> bytes:
    return b"".join(ctrl._serial.writes)


def test_move_joints_binary_encoding_and_completion(controller):
    # reset_input_buffer clears pre-fed data, so feed after patching write.
    orig_write = controller._serial.write

    def write_and_reply(data):
        orig_write(data)
        feed(controller, b"I\r\n")

    controller._serial.write = write_and_reply
    assert controller.move_joints([(0, 30), (12, -40)]) is True
    assert written(controller) == b"I\x00\x1e\x0c\xd8~"  # -40 as signed int8
    assert controller.commands_sent == 1


def test_move_joints_chunks_long_payloads(controller):
    controller._serial.write = lambda d: (controller._serial.writes.append(bytes(d)),
                                          feed(controller, b"I\r\n"))
    moves = [(i, 10) for i in bc.PHYSICAL_JOINTS] * 2  # 18 pairs -> 38 bytes
    controller.move_joints(moves)
    assert all(len(w) <= 20 for w in controller._serial.writes)
    assert len(controller._serial.writes) > 1


def test_move_joints_validation(controller):
    with pytest.raises(ValueError):
        controller.move_joints([(3, 10)])  # phantom joint
    with pytest.raises(ValueError):
        controller.move_joints([(0, 126)])  # beyond int8 clamp


def test_read_joint_angles_parses_real_capture(controller):
    orig_write = controller._serial.write
    controller._serial.write = lambda d: (orig_write(d), feed(controller, J_RESPONSE))
    angles = controller.read_joint_angles()
    assert angles == [30, -82, -47, -2, 0, 0, 0, 0, 73, 73, 73, 73,
                      -57, -57, -57, -57]


def test_dropped_command_returns_failure(controller):
    # Firmware drops busy-time commands: no echo ever arrives.
    assert controller.send_command("m0 20") is False
    assert controller.read_joint_angles() is None


def test_p_echo_is_case_insensitive(controller):
    orig_write = controller._serial.write
    controller._serial.write = lambda d: (orig_write(d), feed(controller, b"P\r\n"))
    assert controller.send_command("p") is True


def test_telemetry_parses_voltage(controller):
    orig_write = controller._serial.write
    controller._serial.write = lambda d: (orig_write(d),
                                          feed(controller,
                                               b"Voltage: 8.35 V\r\nP\r\n"))
    telemetry = controller.get_telemetry()
    assert telemetry["battery"] == 100.0
    assert written(controller) == b"P~"


def test_skill_echoes_bare_k(controller):
    orig_write = controller._serial.write
    controller._serial.write = lambda d: (orig_write(d),
                                          feed(controller, b"balance\r\nk\r\n"))
    assert controller.send_command("kbalance") is True
    assert controller.last_command == "kbalance"
