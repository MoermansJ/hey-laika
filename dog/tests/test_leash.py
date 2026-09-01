"""Tests for the proximity leash zone machine and API."""
import time

from app.leash import LeashService


class FakeBinder:
    def __init__(self):
        self.events = []

    def trigger(self, event, data=None):
        self.events.append((event, data))
        return []


class FakeController:
    def __init__(self):
        self.commands = []

    def send_command(self, command):
        self.commands.append(command)
        return True


def make_leash(binder=None, ctrl=None, **config):
    cfg = {"dwellS": 0.0, "lostAfterS": 2.0, **config}
    return LeashService(ctrl or FakeController(), binder or FakeBinder(),
                        config=cfg)


def feed(leash, rssi, n=6):
    """Push enough identical frames to flush the median+EMA toward rssi."""
    for _ in range(n):
        leash.handle_event_frame({"type": "event_rssi", "rssi": rssi,
                                  "ssid": "hotspot", "timestamp": 0})


def wait_for(pred, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_zones_progress_with_signal_loss():
    binder = FakeBinder()
    leash = make_leash(binder)
    leash.enabled = True
    feed(leash, -55, n=8)
    assert leash.status()["zone"] == "near"
    feed(leash, -75, n=10)
    assert leash.status()["zone"] == "warn"
    feed(leash, -84, n=10)
    assert leash.status()["zone"] == "far"
    feed(leash, -95, n=10)
    assert leash.status()["zone"] == "lost"
    # unknown -> near also emits (the "leash established / resume" hook).
    expected = ["leash.near", "leash.warn", "leash.far", "leash.lost"]
    assert wait_for(lambda: [e for e, _ in binder.events] == expected)
    leash.shutdown()


def test_hysteresis_blocks_marginal_recovery():
    leash = make_leash()
    leash.enabled = True
    feed(leash, -75, n=10)
    assert leash.status()["zone"] == "warn"
    # -71 is better than the -72 warn threshold but NOT by the 6 dB margin.
    feed(leash, -71, n=10)
    assert leash.status()["zone"] == "warn"
    # -60 clears -72 + 6 comfortably -> near again.
    feed(leash, -60, n=10)
    assert leash.status()["zone"] == "near"
    leash.shutdown()


def test_disabled_leash_emits_no_events():
    binder = FakeBinder()
    leash = make_leash(binder)
    feed(leash, -95, n=10)
    assert binder.events == []
    assert leash.status()["zone"] == "disabled"
    leash.shutdown()


def test_frame_silence_becomes_lost():
    binder = FakeBinder()
    leash = make_leash(binder, lostAfterS=0.5)
    leash.enabled = True
    feed(leash, -55, n=8)
    assert leash.status()["zone"] == "near"
    assert wait_for(lambda: leash.status()["zone"] == "lost", timeout=3.0)
    assert wait_for(lambda: ("leash.lost" in [e for e, _ in binder.events]))
    leash.shutdown()


def test_enabling_grants_grace_never_instant_lost():
    binder = FakeBinder()
    leash = make_leash(binder, lostAfterS=5.0)
    # Stale data from long ago must not trigger lost at arm time.
    feed(leash, -55, n=3)
    leash._last_frame_at = time.time() - 100
    leash.set_enabled(True)
    status = leash.status()
    assert status["zone"] == "unknown"
    time.sleep(1.5)  # well under lostAfterS: watchdog must stay quiet
    assert leash.status()["zone"] == "unknown"
    assert "leash.lost" not in [e for e, _ in binder.events]
    leash.shutdown()


def test_enable_arms_firmware_dead_man():
    ctrl = FakeController()
    leash = make_leash(ctrl=ctrl)
    leash.set_enabled(True)
    assert any(c.startswith("XWd1") for c in ctrl.commands)
    leash.set_enabled(False)
    assert "XWd0" in ctrl.commands
    leash.shutdown()


def test_marks_capture_current_smoothed_rssi():
    leash = make_leash()
    feed(leash, -70, n=10)
    entry = leash.mark("leash boundary")
    assert entry["label"] == "leash boundary"
    assert -75 < entry["rssi"] < -65
    assert leash.status()["marks"][-1]["label"] == "leash boundary"
    leash.shutdown()


def test_beacon_mode_ignores_ap_frames_and_tracks_beacon():
    binder = FakeBinder()
    ctrl = FakeController()
    ctrl.query = lambda c: [
        '=\r\n{"ssid":"iPhone","bssid":"AA","rssi":-45,"channel":6}\r\n'
        '{"ssid":"fedpol-7187781","bssid":"BB","rssi":-60,"channel":1}\r\nX']
    leash = make_leash(binder, ctrl, mode="beacon", beaconSsid="iPhone",
                       beaconIntervalS=0.1, lostAfterS=30.0)
    leash.enabled = True
    # AP frames (dog<->router) must be ignored in beacon mode.
    feed(leash, -60, n=10)
    assert leash.status()["rssi"] is None
    # The beacon loop should pick up the iPhone at -45 -> near.
    assert wait_for(lambda: leash.status()["zone"] == "near", timeout=4.0)
    assert leash.status()["ssid"] == "iPhone"
    assert -50 < leash.status()["rssi"] < -40
    leash.shutdown()


def test_configure_switches_mode_and_bumps_lost_after():
    leash = make_leash()
    status = leash.configure({"mode": "beacon", "beaconSsid": "iPhone",
                              "beaconIntervalS": 4.0, "lostAfterS": 2.0})
    assert status["config"]["mode"] == "beacon"
    assert status["config"]["beaconSsid"] == "iPhone"
    assert status["config"]["lostAfterS"] >= 12.0  # 3x interval floor
    leash.shutdown()


def test_leash_api_roundtrip():
    from app.app import app
    client = app.test_client()
    status = client.get("/api/robots/bittle-1/leash").get_json()
    assert status["zone"] == "disabled"
    updated = client.post("/api/robots/bittle-1/leash/config",
                          json={"enabled": True, "warnDbm": -70}).get_json()
    assert updated["enabled"] is True
    assert updated["config"]["warnDbm"] == -70
    marked = client.post("/api/robots/bittle-1/leash/mark",
                         json={"label": "kitchen door"}).get_json()
    assert marked["mark"]["label"] == "kitchen door"
    client.post("/api/robots/bittle-1/leash/config", json={"enabled": False})
