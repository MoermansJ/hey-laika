"""Regression tests for the 2026-09-02 audit fixes (docs/reports/AUDIT_2026-09-02.md).

Covers: WiFi retry policy (never re-send motion), closed-socket handling,
the idle-ladder ownership race, request caps, power-session states, and
the event_exception push routing.
"""
import json
import sys
import time
import types

import pytest

import app.bittle_controller as bc
from app.bittle_controller import (MockBittleController, WiFiBittleController,
                                   _is_motion, _retry_safe)
from app.event_binder import EventBinder
from app.metrics import metrics
from app.models import SessionLocal, init_db
from app.power import PowerSession, PowerTracker


# ---- fakes -----------------------------------------------------------------

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
            raise TimeoutError("no frame queued")  # a timeout tick
        item = self.queue.pop(0)
        return item if isinstance(item, str) else json.dumps(item)

    def close(self):
        self.closed = True


class DyingWebSocket(FakeWebSocket):
    """Answers 'running' and then dies mid-command, like a dropped link."""

    def recv(self):
        if not self.queue:
            raise ConnectionResetError("Connection is already closed.")
        return super().recv()


def replies(frame, results=None):
    tid = frame["taskId"]
    return [{"taskId": tid, "status": "running"},
            {"taskId": tid, "status": "completed", "results": results or []}]


BANNER = ["Bittle X\r\nSoftware version: B10_251121"]


def commands_sent(ws):
    return [f["commands"] for f in ws.sent if f.get("type") == "command"]


@pytest.fixture()
def controller(monkeypatch):
    monkeypatch.setattr(bc, "_TIMEOUT_DEFAULT", 0.25)
    monkeypatch.setattr(bc, "_TIMEOUT_SKILL_WS", 0.25)
    ctrl = WiFiBittleController("fake-host")
    ctrl._ws = FakeWebSocket()
    return ctrl


def ws_module(monkeypatch, factory):
    mod = types.ModuleType("websocket")
    mod.create_connection = factory
    monkeypatch.setitem(sys.modules, "websocket", mod)


# ---- WiFi retry policy ----------------------------------------------------

def test_retry_safe_classification():
    assert _retry_safe("?") and _retry_safe("P") and _retry_safe("XWs")
    for cmd in ("kwkF", "krest", "b14,8", "c", "XWd", "b64:SQAA", "d"):
        assert not _retry_safe(cmd), cmd


def test_motion_classification():
    assert _is_motion("kwkF") and _is_motion("krest") and _is_motion("d")
    for cmd in ("b14,8", "XWd", "XWs", "?", "P", "j", "gp"):
        assert not _is_motion(cmd), cmd


def test_timeout_with_live_firmware_does_not_resend(controller):
    """Completion never arrives but the heartbeat probe succeeds: the
    firmware is busy, not dead, so the skill must not be queued again."""
    ws = controller._ws

    def handler(frame):
        if frame.get("type") == "heartbeat":
            return [{"type": "heartbeat", "timestamp": 1}]
        return [{"taskId": frame["taskId"], "status": "running"}]

    ws.handler = handler
    assert controller.send_command("kwkF") is False
    assert commands_sent(ws) == [["kwkF"]]
    assert controller._ws is ws  # no reconnect either


def test_link_lost_mid_skill_reconnects_but_never_resends(controller,
                                                          monkeypatch):
    dying = DyingWebSocket(
        handler=lambda f: [{"taskId": f["taskId"], "status": "running"}])
    controller._ws = dying
    fresh = FakeWebSocket(handler=lambda f: replies(
        f, results=BANNER if f["commands"] == ["?"] else ["ok"]))
    ws_module(monkeypatch, lambda url, timeout: fresh)
    before = metrics.snapshot()["counters"].get("ws.retry_suppressed", 0)

    started = time.time()
    assert controller.send_command("kwkF") is False
    assert time.time() - started < 2.0  # no 20 s spin on a dead socket
    assert controller._ws is fresh
    assert commands_sent(fresh) == [["?"]]  # banner only, skill NOT re-sent
    assert metrics.snapshot()["counters"]["ws.retry_suppressed"] == before + 1


def test_link_lost_mid_read_is_retried(controller, monkeypatch):
    dying = DyingWebSocket(
        handler=lambda f: [{"taskId": f["taskId"], "status": "running"}])
    controller._ws = dying
    fresh = FakeWebSocket(handler=lambda f: replies(
        f, results=BANNER if f["commands"] == ["?"] else ["Voltage: 7.85 V"]))
    ws_module(monkeypatch, lambda url, timeout: fresh)
    assert controller.get_telemetry()["battery"] == pytest.approx(67.7, abs=0.1)
    assert commands_sent(fresh) == [["?"], ["P"]]


def test_send_failure_before_delivery_is_retried(controller, monkeypatch):
    """The write itself failed: the skill never left the host, so re-sending
    after reconnect is safe (pre-existing behaviour, kept)."""
    controller._ws.closed = True
    fresh = FakeWebSocket(handler=lambda f: replies(
        f, results=BANNER if f["commands"] == ["?"] else ["ok"]))
    ws_module(monkeypatch, lambda url, timeout: fresh)
    assert controller.send_command("khi") is True
    assert commands_sent(fresh) == [["?"], ["khi"]]


def test_beep_does_not_stamp_motion(controller):
    controller._ws.handler = lambda f: replies(f, results=["b"])
    controller.last_motion_at = None
    assert controller.send_command("b14,8") is True
    assert controller.last_motion_at is None
    assert controller.send_command("ksit") is True
    assert controller.last_motion_at is not None


def test_dropped_telemetry_poll_is_retried_soon(controller):
    controller._ws.handler = lambda f: [{"taskId": f["taskId"],
                                          "status": "running"}]
    # Make the heartbeat probe succeed so no reconnect happens.
    controller._ws.handler = (lambda f: [{"type": "heartbeat"}]
                              if f.get("type") == "heartbeat"
                              else [{"taskId": f["taskId"], "status": "running"}])
    assert controller.get_telemetry()["battery"] is None
    # The miss is cached for _TELEMETRY_RETRY_S, not the full TTL.
    assert time.time() - controller._telemetry_at >= \
        controller.telemetry_ttl() - bc._TELEMETRY_RETRY_S - 0.5


def test_mock_battery_never_reaches_safety_floor():
    ctrl = MockBittleController()
    ctrl._battery_since = time.time() - 10 * 3600  # ten hours "ago"
    assert ctrl.get_telemetry()["battery"] == 20.0


# ---- idle ladder ownership ------------------------------------------------

class LadderStore:
    def __init__(self, sit_s, rest_s):
        self._bindings = [
            {"id": "b1", "event": "idle.timeout", "filter": {"seconds": sit_s},
             "behavior": "idle_sit", "priority": 5, "enabled": True},
            {"id": "b2", "event": "idle.timeout", "filter": {"seconds": rest_s},
             "behavior": "idle_rest", "priority": 5, "enabled": True},
        ]

    def bindings(self, event=None, enabled_only=False):
        return [b for b in self._bindings if event is None or b["event"] == event]

    def behavior(self, name):
        return {"name": name, "steps": []}


class LadderArbiter:
    def __init__(self):
        self.submits = []
        self.last_motion_at = None
        self.busy = False

    def submit(self, name, source, priority, cause=None):
        self.submits.append(name)
        return {"status": "executing"}

    def status(self):
        return {"current": {"behavior": "x"} if self.busy else None}


class LadderController:
    last_motion_at = None


def test_idle_ladder_reaches_rest_despite_arbiter_settle_race():
    clock = [1000.0]
    ctrl, arb = LadderController(), LadderArbiter()
    ctrl.last_motion_at = 1000.0
    binder = EventBinder(arb, LadderStore(60, 120), ctrl,
                         clock=lambda: clock[0])
    binder._seen_motion_at = ctrl.last_motion_at

    clock[0] = 1061.0
    binder._idle_tick()
    assert arb.submits == ["idle_sit"]

    # The arbiter performs idle_sit: both stamps land together, then its
    # 3 s settle ends before the next 5 s tick — the exact race.
    arb.last_motion_at = ctrl.last_motion_at = 1062.0
    clock[0] = 1066.0
    binder._idle_tick()
    assert binder._idle_anchor == 1000.0  # ladder NOT reset by own motion

    clock[0] = 1121.0
    binder._idle_tick()
    assert arb.submits == ["idle_sit", "idle_rest"]


def test_idle_ladder_resets_on_external_motion():
    clock = [1000.0]
    ctrl, arb = LadderController(), LadderArbiter()
    ctrl.last_motion_at = 1000.0
    binder = EventBinder(arb, LadderStore(60, 120), ctrl,
                         clock=lambda: clock[0])
    binder._seen_motion_at = ctrl.last_motion_at
    clock[0] = 1030.0
    ctrl.last_motion_at = 1030.0  # GUI slider, arbiter idle and silent
    binder._idle_tick()
    assert binder._idle_anchor == 1030.0
    clock[0] = 1061.0
    binder._idle_tick()
    assert arb.submits == []  # only 31 s idle since the external motion


# ---- power sessions --------------------------------------------------------

class PowerController:
    def __init__(self):
        self.connected = False
        self.battery = None

    def get_status(self):
        return {"connected": self.connected}

    def get_telemetry(self):
        return {"battery": self.battery}


def _clear_sessions():
    with SessionLocal() as session:
        session.query(PowerSession).delete()
        session.commit()


def test_power_unreachable_is_not_off_until_grace_expires():
    init_db()
    _clear_sessions()
    clock = [5000.0]
    ctrl = PowerController()
    tracker = PowerTracker(ctrl, poll_s=999, unreachable_grace_s=100,
                           clock=lambda: clock[0])
    tracker.init()
    tracker.shutdown()

    ctrl.connected = True  # socket up but no battery reading yet
    tracker._tick()
    assert tracker.state == "off"  # a session needs a real reading

    ctrl.battery = 80.0
    tracker._tick()
    assert tracker.state == "on"

    ctrl.connected = False  # WiFi blip
    tracker._tick()
    assert tracker.state == "unreachable"
    assert tracker.summary()["sessions"][0]["endedAt"] is None

    clock[0] += 50
    tracker._tick()
    assert tracker.state == "unreachable"

    ctrl.connected = True  # back within grace: same session continues
    tracker._tick()
    assert tracker.state == "on"
    assert len(tracker.summary()["sessions"]) == 1

    ctrl.connected = False
    tracker._tick()
    clock[0] += 101
    tracker._tick()
    assert tracker.state == "off"
    assert tracker.summary()["sessions"][0]["endedAt"] is not None
    assert tracker.summary()["sessions"][0]["endBattery"] == 80.0


def test_power_low_battery_loss_closes_immediately():
    init_db()
    _clear_sessions()
    ctrl = PowerController()
    tracker = PowerTracker(ctrl, poll_s=999, unreachable_grace_s=300)
    tracker.init()
    tracker.shutdown()
    ctrl.connected, ctrl.battery = True, 4.0
    tracker._tick()
    ctrl.connected = False
    tracker._tick()
    assert tracker.state == "off"


# ---- app routes -----------------------------------------------------------

@pytest.fixture()
def client():
    import app.app as appmod
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_duration_cap_returns_400(client):
    resp = client.post("/api/robots/bittle-1/execute_action",
                       json={"action": "idle_calm", "durationMs": 10 ** 10})
    assert resp.status_code == 400
    assert "durationMs" in resp.get_json()["message"]


def test_gait_iterations_cap_returns_400(client):
    resp = client.post("/api/robots/bittle-1/gait/start",
                       json={"iterations": 999})
    assert resp.status_code == 400


def test_bad_priority_returns_400_not_500(client):
    resp = client.post("/api/robots/bittle-1/arbiter/invoke",
                       json={"behavior": "acknowledgment", "priority": "x"})
    assert resp.status_code == 400


def test_abort_route_on_mock(client):
    resp = client.post("/api/robots/bittle-1/abort")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["aborted"] is True
    assert "arbiter" in body


def test_schema_exposes_decision_engine(client):
    body = client.get("/api/robots/bittle-1/schema").get_json()
    assert body["metadata"]["decisionEngine"] == "mock"
    assert "decisionModel" in body["metadata"]


def test_event_exception_frame_reaches_binder(monkeypatch):
    import app.app as appmod

    calls = []
    monkeypatch.setattr(appmod.event_binder, "trigger",
                        lambda event, data=None: calls.append((event, data)) or [])
    appmod._fan_out_event_frame({"type": "event_exception", "code": 4,
                                 "name": "FLIPPED", "ts": 1})
    assert calls == [("exception.report", {"code": "flipped"})]
