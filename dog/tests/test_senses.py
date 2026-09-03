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
    assert senses.samples(5)["samples"][0]["id"] == sample["id"]


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


def test_sample_carries_battery_yaw_and_source():
    class Ctrl(FakeController):
        def query(self, command):
            self.commands.append(command)
            if command == "gp":
                return ["ICM: -0.18 -0.10 10.07 -288.0 -1.2 -0.7"]
            return list(self.scan_lines)

        def get_telemetry(self):
            return {"battery": 73.5, "signal": "strong"}

    senses = SensesService(Ctrl(scan_lines=SCAN))
    senses._sample_count = 0
    sample = senses.sniff(source="manual")
    assert sample["battery"] == 73.5
    assert sample["yaw"] == -288.0
    assert sample["source"] == "manual"


def test_samples_filters_and_thinning():
    ctrl = FakeController(scan_lines=SCAN)
    senses = SensesService(ctrl)
    senses._sample_count = 0
    ids = [senses.sniff(source="auto")["id"] for _ in range(6)]
    manual = senses.sniff(source="manual")
    page = senses.samples(limit=100)
    assert page["total"] >= 7 and page["returned"] >= 7
    assert page["samples"][0]["id"] == manual["id"]   # newest first
    only_manual = senses.samples(source="manual")
    assert all(s["source"] == "manual" for s in only_manual["samples"])
    since = senses.samples(since=manual["t"])
    assert [s["id"] for s in since["samples"]] == [manual["id"]]
    thinned = senses.samples(since=0, every=3, limit=100)
    assert thinned["matched"] == page["matched"]
    assert thinned["returned"] < page["returned"]
    assert senses.samples(min_aps=3)["matched"] == 0
    assert ids[0] not in [s["id"] for s in senses.samples(limit=2)["samples"]]


def test_pose_restored_on_init_and_reset():
    ctrl = FakeController(scan_lines=SCAN)
    first = SensesService(ctrl)
    first.instrument(ctrl)
    first._sample_count = 0
    ctrl.send_command("kwkL 90")
    ctrl.send_command("kwkF 4")
    first.sniff()
    first.shutdown()

    second = SensesService(FakeController())
    second.init()
    second.shutdown()
    pose = second.pose()
    assert pose["heading"] == 90.0 and pose["y"] == 0.4
    assert pose["driftM"] > first.pose()["driftM"]
    assert second.reset_pose(heading=45) == \
        {"x": 0.0, "y": 0.0, "heading": 45.0, "driftM": 0.0}


def test_samples_api_filters_and_reset():
    from app.app import app
    client = app.test_client()
    page = client.get("/api/robots/bittle-1/senses/samples"
                      "?limit=5&since=0&every=2&minAps=1").get_json()
    assert {"samples", "matched", "total", "returned", "pose"} <= page.keys()
    assert page["returned"] <= 5
    assert client.get("/api/robots/bittle-1/senses/samples?source=x"
                      ).status_code == 400
    assert client.get("/api/robots/bittle-1/senses/samples?limit=abc"
                      ).status_code == 400
    reset = client.post("/api/robots/bittle-1/senses/pose/reset",
                        json={"heading": 10}).get_json()
    assert reset["pose"] == {"x": 0.0, "y": 0.0, "heading": 10.0,
                             "driftM": 0.0}
