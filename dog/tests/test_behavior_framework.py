"""Tests for the behavior framework: arbiter, event binder, store seeds."""
import time

import pytest

from app.arbiter import Arbiter
from app.behavior_store import (PRIORITY_IDLE, PRIORITY_LIFECYCLE,
                                PRIORITY_MANUAL, PRIORITY_SAFETY)
from app.event_binder import EventBinder


class FakeStore:
    def __init__(self, behaviors=None, bindings=None):
        self._behaviors = behaviors or {}
        self._bindings = bindings or []
        self.runs = []

    def behavior(self, name):
        return self._behaviors.get(name)

    def bindings(self, event=None, enabled_only=False):
        out = [b for b in self._bindings
               if (event is None or b["event"] == event)
               and (not enabled_only or b["enabled"])]
        return sorted(out, key=lambda b: b["priority"])

    def log_start(self, name, source, priority):
        self.runs.append({"behavior": name, "source": source,
                          "priority": priority, "status": "running"})
        return str(len(self.runs) - 1)

    def log_end(self, run_id, status, detail=""):
        self.runs[int(run_id)].update({"status": status, "detail": detail})

    def recent_runs(self, limit=10):
        return list(reversed(self.runs))[:limit]


class FakeController:
    def __init__(self):
        self.commands = []
        self.last_motion_at = time.time()

    def send_command(self, command):
        self.commands.append(command)
        self.last_motion_at = time.time()
        return True

    def get_telemetry(self):
        return {"battery": getattr(self, "battery", None)}


def behavior(name, n_steps=1, interruptible=True, cooldown=0, settle=0.0):
    return {"id": name, "name": name, "description": "",
            "steps": [{"command": f"{name}-{i}", "settleS": settle}
                      for i in range(n_steps)],
            "interruptible": interruptible, "cooldownS": cooldown}


def wait_for(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def make_arbiter(store, ctrl):
    return Arbiter(ctrl, store, sleep_fn=lambda s: time.sleep(min(s, 0.02)))


def test_arbiter_executes_and_logs():
    store = FakeStore({"wave": behavior("wave", n_steps=3)})
    ctrl = FakeController()
    arb = make_arbiter(store, ctrl)
    result = arb.submit("wave", source="manual", priority=PRIORITY_MANUAL)
    assert result["status"] in ("executing", "queued")
    assert wait_for(lambda: store.runs and store.runs[-1]["status"] == "complete")
    assert ctrl.commands == ["wave-0", "wave-1", "wave-2"]
    arb.shutdown()


def test_higher_priority_preempts_interruptible():
    store = FakeStore({
        "slow": behavior("slow", n_steps=100, settle=0.05),
        "urgent": behavior("urgent", n_steps=1),
    })
    ctrl = FakeController()
    arb = make_arbiter(store, ctrl)
    arb.submit("slow", source="event.idle", priority=PRIORITY_IDLE)
    assert wait_for(lambda: ctrl.commands)  # slow started
    result = arb.submit("urgent", source="manual", priority=PRIORITY_MANUAL)
    assert result["status"] == "preempting"
    assert wait_for(lambda: "urgent-0" in ctrl.commands)
    statuses = {r["behavior"]: r["status"] for r in store.runs}
    assert wait_for(lambda: store.runs[0]["status"] == "interrupted")
    arb.shutdown()


def test_lower_priority_queues_and_runs_after():
    store = FakeStore({
        "first": behavior("first", n_steps=3, settle=0.03),
        "second": behavior("second", n_steps=1),
    })
    ctrl = FakeController()
    arb = make_arbiter(store, ctrl)
    arb.submit("first", priority=PRIORITY_MANUAL)
    assert wait_for(lambda: ctrl.commands)
    result = arb.submit("second", priority=PRIORITY_LIFECYCLE)
    assert result["status"] == "queued"
    assert wait_for(lambda: "second-0" in ctrl.commands)
    # first was NOT interrupted (lower-priority submission must wait)
    assert ctrl.commands.index("second-0") > ctrl.commands.index("first-2")
    arb.shutdown()


def test_cooldown_and_duplicate_rejection():
    store = FakeStore({"greet": behavior("greet", cooldown=60, settle=0.05,
                                         n_steps=5)})
    ctrl = FakeController()
    arb = make_arbiter(store, ctrl)
    assert arb.submit("greet")["status"] in ("executing", "queued")
    assert wait_for(lambda: ctrl.commands)
    dup = arb.submit("greet")
    assert dup["status"] == "rejected"
    assert dup["reason"] in ("already running", "cooldown")
    arb.shutdown()


def test_unknown_behavior_rejected():
    arb = make_arbiter(FakeStore(), FakeController())
    assert arb.submit("nope")["status"] == "rejected"
    arb.shutdown()


def test_binder_trigger_respects_filters():
    store = FakeStore(
        {"sit": behavior("sit"), "rest": behavior("rest")},
        bindings=[
            {"event": "idle.timeout", "filter": {"seconds": 60},
             "behavior": "sit", "priority": PRIORITY_IDLE, "enabled": True},
            {"event": "idle.timeout", "filter": {"seconds": 120},
             "behavior": "rest", "priority": PRIORITY_IDLE, "enabled": True},
            {"event": "idle.timeout", "filter": {"seconds": 999},
             "behavior": "rest", "priority": PRIORITY_IDLE, "enabled": False},
        ])
    submits = []

    class CapturingArbiter:
        def submit(self, name, source, priority):
            submits.append((name, source, priority))
            return {"status": "executing"}

        def status(self):
            return {"current": None}

    binder = EventBinder(CapturingArbiter(), store, FakeController())
    binder.trigger("idle.timeout", {"seconds": 60})
    assert submits == [("sit", "event.idle.timeout", PRIORITY_IDLE)]


def test_binder_idle_tick_fires_ladder_once():
    store = FakeStore(
        {"sit": behavior("sit"), "rest": behavior("rest")},
        bindings=[
            {"event": "idle.timeout", "filter": {"seconds": 1},
             "behavior": "sit", "priority": PRIORITY_IDLE, "enabled": True},
            {"event": "idle.timeout", "filter": {"seconds": 2},
             "behavior": "rest", "priority": PRIORITY_IDLE, "enabled": True},
        ])
    submits = []

    class CapturingArbiter:
        def submit(self, name, source, priority):
            submits.append(name)
            return {"status": "executing"}

        def status(self):
            return {"current": None}

    ctrl = FakeController()
    binder = EventBinder(CapturingArbiter(), store, ctrl)
    binder._seen_motion_at = ctrl.last_motion_at
    binder._idle_anchor = time.time() - 1.5  # past sit threshold
    binder._idle_tick()
    assert submits == ["sit"]
    binder._idle_tick()  # fired-set prevents repeat
    assert submits == ["sit"]
    binder._idle_anchor = time.time() - 2.5  # past rest threshold
    binder._idle_tick()
    assert submits == ["sit", "rest"]


def test_binder_exception_report_parsing():
    submits = []

    class CapturingArbiter:
        def submit(self, name, source, priority):
            submits.append((name, source))
            return {"status": "executing"}

        def status(self):
            return {"current": None}

    store = FakeStore(
        {"ack": behavior("ack")},
        bindings=[{"event": "exception.report", "filter": {"code": "-2"},
                   "behavior": "ack", "priority": PRIORITY_SAFETY,
                   "enabled": True}])
    binder = EventBinder(CapturingArbiter(), store, FakeController())
    binder.handle_output_line("EXCEPTION_REPORT -2 yaw 1.0 pitch 89.0 roll 2.0")
    assert submits == [("ack", "event.exception.report")]
    binder.handle_output_line("EXCEPTION_REPORT -4 yaw 0 pitch 0 roll 0")
    assert len(submits) == 1  # no binding for -4
