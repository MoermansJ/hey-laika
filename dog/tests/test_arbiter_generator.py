"""Generator-backed arbiter behaviors: steps from code, preemption closes
the generator, on_end reports the outcome, the suppress-avoidance flag."""
import threading
import time

from app.arbiter import Arbiter
from app.behavior_store import BehaviorStore
from app.bittle_controller import MockBittleController
from app.models import init_db


def setup_module(module):
    init_db()


def build(sleep=None):
    ctrl = MockBittleController()
    ctrl.connect()
    store = BehaviorStore()
    store.init()
    return ctrl, Arbiter(ctrl, store, sleep_fn=sleep or (lambda s: None))


def wait_idle(arbiter, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = arbiter.status()          # one locked snapshot, no race
        if status["current"] is None and not status["queued"]:
            return True
        time.sleep(0.02)
    return False


def wait_for(predicate, timeout=5.0):
    """The arbiter clears `current` before it logs the run end and calls
    on_end, so "idle" alone doesn't mean the callback has fired yet."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_generator_steps_run_and_report_completion():
    ctrl, arbiter = build()
    ends = []
    seen = []

    def steps():
        yield {"command": "kup", "settleS": 0}
        seen.append(ctrl.last_command)
        yield {"command": "kwkF 2", "settleS": 0}
        seen.append(ctrl.last_command)

    out = arbiter.submit_generator("walk_a_bit", steps, on_end=lambda s, d: ends.append(s))
    assert out["status"] == "executing"
    assert wait_idle(arbiter)
    assert seen == ["kup", "kwkF 2"]
    assert wait_for(lambda: ends)
    assert ends == ["complete"]
    run = arbiter.status()["recentRuns"][0]
    assert run["behavior"] == "walk_a_bit" and run["status"] == "complete"


def test_preemption_closes_the_generator_and_names_the_preemptor():
    ctrl, arbiter = build(sleep=time.sleep)
    closed = threading.Event()
    ends = []

    def steps():
        try:
            while True:
                yield {"command": "kwkF 1", "settleS": 0.05}
        finally:
            closed.set()

    arbiter.submit_generator("forever", steps, priority=3, on_end=lambda s, d: ends.append(s))
    time.sleep(0.15)
    assert arbiter.status()["current"]["generated"] is True
    result = arbiter.submit("rest_now", source="safety", priority=1)
    assert result["status"] == "preempting"
    assert closed.wait(3.0)
    assert wait_idle(arbiter)
    assert wait_for(lambda: ends)
    assert ends == ["interrupted"]
    runs = {r["behavior"]: r for r in arbiter.status()["recentRuns"]}
    assert runs["forever"]["status"] == "interrupted"
    assert runs["forever"]["preemptedBy"] == runs["rest_now"]["id"]


def test_generator_may_end_the_run_with_its_own_status():
    _, arbiter = build()
    ends = []

    def steps():
        yield {"status": "failed", "detail": "no route", "settleS": 0}

    arbiter.submit_generator("plan", steps, on_end=lambda s, d: ends.append((s, d)))
    assert wait_idle(arbiter)
    assert wait_for(lambda: ends)
    assert ends == [("failed", "no route")]


def test_suppress_avoidance_flag_follows_the_running_behavior():
    _, arbiter = build(sleep=time.sleep)
    assert not arbiter.avoidance_suppressed()
    arbiter.submit_generator("jump", lambda: iter([{"command": "kjmp", "settleS": 0.2}]),
                             suppress_avoidance=True)
    time.sleep(0.05)
    assert arbiter.avoidance_suppressed()
    assert arbiter.status()["current"]["suppressAvoidance"] is True
    assert wait_idle(arbiter)
    assert not arbiter.avoidance_suppressed()
    out = arbiter.submit("acknowledgment", suppress_avoidance=True)
    assert out["status"] == "executing"
    assert wait_idle(arbiter)


def test_duplicate_generator_names_are_rejected_like_behaviors():
    _, arbiter = build(sleep=time.sleep)
    factory = lambda: iter([{"command": "kup", "settleS": 0.2}])
    assert arbiter.submit_generator("navigate", factory)["status"] == "executing"
    assert arbiter.submit_generator("navigate", factory)["status"] == "rejected"
    assert wait_idle(arbiter)


def test_queue_accepts_ten_lower_priority_submissions_then_rejects_the_eleventh():
    _, arbiter = build(sleep=time.sleep)
    arbiter.submit_generator("current", lambda: iter([{"command": "kup", "settleS": 1.0}]),
                             priority=3)
    time.sleep(0.05)   # let it become the running behavior
    queued_factory = lambda: iter([{"command": "kup", "settleS": 0.01}])

    results = [arbiter.submit_generator(f"queued-{i}", queued_factory, priority=4)
               for i in range(11)]

    assert [r["status"] for r in results[:10]] == ["queued"] * 10
    assert results[10] == {"status": "rejected", "reason": "queue full"}
    assert wait_idle(arbiter)
