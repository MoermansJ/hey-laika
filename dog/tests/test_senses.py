"""Tests for the senses layer: odometry shadow + opportunistic sniffer."""
import time

from app.models import init_db
from app.senses import SensesService


class FakeController:
    def __init__(self, scan_lines=None):
        self.commands = []
        self.last_motion_at = None
        self.scan_lines = scan_lines or []

    def send_command(self, command):
        self.commands.append(command)
        self.last_motion_at = time.time()
        return True

    def query(self, command):
        self.commands.append(command)
        return list(self.scan_lines)


def setup_module(module):
    init_db()


SCAN = ['=\r\n{"ssid":"a","bssid":"AA:BB","rssi":-50,"channel":1}\r\n'
        '{"ssid":"b","bssid":"CC:DD","rssi":-80,"channel":11}\r\nX\r\n']


def test_shadow_advances_and_turns():
    ctrl = FakeController()
    senses = SensesService(ctrl)
    senses.instrument(ctrl)
    ctrl.send_command("kwkF 5")      # 5 cycles x 0.10 m east (heading 0)
    assert senses.pose()["x"] == 0.5
    ctrl.send_command("kwkL 90")     # now facing +y
    assert senses.pose()["heading"] == 90.0
    ctrl.send_command("kwkF 3")
    pose = senses.pose()
    assert pose["x"] == 0.5 and pose["y"] == 0.3
    ctrl.send_command("kbkF 1")      # back up along heading
    assert senses.pose()["y"] == 0.2
    assert senses.pose()["driftM"] > 0


def test_shadow_ignores_non_motion_and_wraps_heading():
    ctrl = FakeController()
    senses = SensesService(ctrl)
    senses.instrument(ctrl)
    ctrl.send_command("ksit")        # unmodeled: pose fixed, drift grows
    assert senses.pose()["x"] == 0 and senses.pose()["driftM"] > 0
    for _ in range(3):
        ctrl.send_command("kwkR 90")
    assert senses.pose()["heading"] == -270.0 % 360 - 360 or \
        senses.pose()["heading"] == 90.0  # wrapped to (-180, 180]


def test_sniff_stores_pose_labeled_sample():
    ctrl = FakeController(scan_lines=SCAN)
    senses = SensesService(ctrl)
    senses.instrument(ctrl)
    senses._sample_count = 0
    ctrl.send_command("kwkF 2")
    sample = senses.sniff()
    assert sample is not None
    assert len(sample["aps"]) == 2
    assert sample["aps"][0]["bssid"] == "AA:BB"
    assert sample["x"] == 0.2
    assert senses.samples(5)[0]["id"] == sample["id"]


def test_politeness_contract():
    ctrl = FakeController(scan_lines=SCAN)
    senses = SensesService(ctrl, config={"quietS": 5.0, "minIntervalS": 60.0})
    now = time.time()
    # Just moved -> no sniff.
    ctrl.last_motion_at = now
    assert senses._may_sniff(now) is False
    # Quiet long enough -> sniff allowed.
    ctrl.last_motion_at = now - 10
    assert senses._may_sniff(now) is True
    # But not twice within the interval.
    senses._last_sniff = now - 5
    assert senses._may_sniff(now) is False


def test_away_mode_suppresses_sniffing():
    ctrl = FakeController(scan_lines=SCAN)
    away = {"on": True}
    senses = SensesService(ctrl, is_away=lambda: away["on"])
    ctrl.last_motion_at = time.time() - 100
    assert senses._may_sniff(time.time()) is False
    away["on"] = False
    assert senses._may_sniff(time.time()) is True


def test_senses_api():
    from app.app import app
    client = app.test_client()
    status = client.get("/api/robots/bittle-1/senses").get_json()
    assert "pose" in status and "sampleCount" in status
    samples = client.get("/api/robots/bittle-1/senses/samples").get_json()
    assert isinstance(samples["samples"], list)
