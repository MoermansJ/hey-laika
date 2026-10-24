"""The per-action feed: tagging by what generated an action, and the
arbiter pushing one entry per dispatched step — the grain the run log
doesn't have, where a continuous generator's individual decisions live."""
import time

from app.action_feed import ActionFeed, source_tag
from app.arbiter import Arbiter
from app.behavior_store import BehaviorStore
from app.bittle_controller import MockBittleController
from app.models import init_db


def setup_module(module):
    init_db()


def build():
    ctrl = MockBittleController()
    ctrl.connect()
    store = BehaviorStore()
    store.init()
    feed = ActionFeed()
    return feed, Arbiter(ctrl, store, sleep_fn=lambda s: None, action_feed=feed)


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ---- tagging ------------------------------------------------------------

def test_tags_name_the_mode_or_subsystem_that_generated_the_action():
    assert source_tag({"type": "fruitfly"}) == "FRUITFLY"
    assert source_tag({"type": "nav.target", "target": {}}) == "ROAMING"
    assert source_tag({"type": "mode", "mode": "stationary"}) == "MODE"
    assert source_tag({"type": "manual", "via": "api"}) == "MANUAL"


def test_event_causes_are_tagged_by_their_own_namespace():
    assert source_tag({"type": "event", "event": "idle.timeout"}) == "IDLE"
    assert source_tag({"type": "event", "event": "leash.warn"}) == "LEASH"


def test_an_unknown_cause_falls_back_to_its_type_rather_than_vanishing():
    assert source_tag({"type": "weather"}) == "WEATHER"
    assert source_tag(None, source="lifecycle") == "LIFECYCLE"


# ---- the ring itself ----------------------------------------------------

def test_entries_come_back_newest_first_with_short_ids():
    feed = ActionFeed()
    feed.push("FRUITFLY", "FORWARD", command="kwkF")
    feed.push("FRUITFLY", "LEFT", command="kwkL")

    actions = feed.recent()

    assert [a["action"] for a in actions] == ["LEFT", "FORWARD"]
    assert all(len(a["id"]) == 5 for a in actions)
    assert len({a["id"] for a in actions}) == 2


def test_finishing_an_entry_marks_only_that_one_done():
    feed = ActionFeed()
    first = feed.push("FRUITFLY", "FORWARD")
    feed.push("FRUITFLY", "LEFT")

    feed.finish(first, "done")

    by_action = {a["action"]: a for a in feed.recent()}
    assert by_action["FORWARD"]["status"] == "done"
    assert by_action["LEFT"]["status"] == "executing"


def test_the_ring_is_capped_and_drops_the_oldest():
    feed = ActionFeed(maxlen=3)
    for i in range(5):
        feed.push("MANUAL", f"step-{i}")

    assert [a["action"] for a in feed.recent(10)] == ["step-4", "step-3", "step-2"]


# ---- the arbiter writing into it ---------------------------------------

def test_each_generator_step_becomes_its_own_feed_entry():
    feed, arbiter = build()

    def steps():
        yield {"command": "kwkF", "label": "FORWARD", "settleS": 0}
        yield {"command": "kwkL", "label": "LEFT", "settleS": 0}

    arbiter.submit_generator("fruitfly_drive", steps, source="agent",
                             priority=3, cause={"type": "fruitfly"})

    assert wait_for(lambda: len(feed.recent()) == 2)
    actions = feed.recent()
    assert [a["action"] for a in actions] == ["LEFT", "FORWARD"]
    assert all(a["tag"] == "FRUITFLY" for a in actions)
    assert [a["command"] for a in actions] == ["kwkL", "kwkF"]
    assert wait_for(lambda: all(a["status"] == "done" for a in feed.recent()))


def test_a_step_without_a_label_falls_back_to_its_command():
    feed, arbiter = build()

    arbiter.submit_generator("navigate", lambda: iter([{"command": "kup", "settleS": 0}]),
                             source="agent", priority=3,
                             cause={"type": "nav.target", "target": {}})

    assert wait_for(lambda: feed.recent())
    entry = feed.recent()[0]
    assert entry["action"] == "kup" and entry["tag"] == "ROAMING"


def test_a_pause_only_step_is_not_recorded_as_an_action():
    feed, arbiter = build()

    arbiter.submit_generator("thinking", lambda: iter([{"settleS": 0}]),
                             source="manual", priority=2)

    assert wait_for(lambda: arbiter.status()["current"] is None)
    assert feed.recent() == []
