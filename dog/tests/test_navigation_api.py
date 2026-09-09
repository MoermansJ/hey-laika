"""The navigation routes on the Flask app (mock mode, simulated room)."""
import time

import pytest

from app.app import app, nav_error_state, nav_grid, navigation
from app.config import Config
from app.nav_errors import UnrecoverableError

RID = Config.ROBOT_ID


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def wait_until(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_sensors_latest_and_recent(client):
    fresh = client.get(f"/api/robots/{RID}/sensors/latest?fresh=1").get_json()
    assert fresh["fresh"] is True
    # After 20 quiet seconds the battery saver gates the ranger: the reading
    # is then the cached one, flagged gated, and may be empty.
    assert fresh["latest"]["rangeCm"] is not None or fresh["latest"]["gated"]
    assert "rateHz" in fresh
    recent = client.get(f"/api/robots/{RID}/sensors/recent?limit=5").get_json()
    assert recent["returned"] >= 1 and recent["readings"][0]["t"] > 0
    csv = client.get(f"/api/robots/{RID}/sensors/recent?limit=2&format=csv")
    assert csv.status_code == 200 and csv.data.startswith(b"t,rangeCm")


def test_navigation_status_map_and_config(client):
    status = client.get(f"/api/robots/{RID}/navigation").get_json()
    assert status["robotId"] == RID and status["state"] in (
        "idle", "arrived", "cancelled", "unreachable", "failed")
    assert status["avoidance"]["rangerEnabled"] in (True, False)
    data = client.get(f"/api/robots/{RID}/navigation/map").get_json()
    assert data["resolutionM"] == Config.NAV_GRID_RES_M and "cells" in data
    out = client.post(f"/api/robots/{RID}/navigation/config",
                      json={"stopCm": 22, "junk": "x"}).get_json()
    assert out["config"]["stopCm"] == 22.0
    client.post(f"/api/robots/{RID}/navigation/config", json={"stopCm": 25})


def test_map_cell_edit_and_reset(client):
    bad = client.post(f"/api/robots/{RID}/navigation/map/cell",
                      json={"cx": 1, "cy": 1, "state": "wall"})
    assert bad.status_code == 400
    out = client.post(f"/api/robots/{RID}/navigation/map/cell",
                      json={"cx": 40, "cy": 40, "state": "occupied"}).get_json()
    assert out["cell"]["state"] == "occupied"
    assert nav_grid.state(40, 40) == "occupied"
    reset = client.post(f"/api/robots/{RID}/navigation/map/reset").get_json()
    assert reset["cleared"] >= 1 and nav_grid.counts()["touched"] == 0


def test_target_requires_coordinates_and_runs_a_route(client):
    assert client.post(f"/api/robots/{RID}/navigation/target", json={"x": 1}).status_code == 400
    out = client.post(f"/api/robots/{RID}/navigation/target",
                      json={"x": 0.4, "y": 0.0}).get_json()
    assert out["status"] in ("executing", "queued", "preempting")
    assert out["target"]["x"] == 0.4
    assert wait_until(lambda: not navigation.active, 30.0)
    status = client.get(f"/api/robots/{RID}/navigation").get_json()
    assert status["state"] in ("arrived", "unreachable", "cancelled"), status["finished"]
    export = client.get(f"/api/robots/{RID}/navigation/data/export").get_json()
    assert export["kind"] == "actions" and export["returned"] >= 1
    csv = client.get(f"/api/robots/{RID}/navigation/data/export?format=csv&kind=readings")
    assert csv.status_code == 200 and csv.data.startswith(b"t,rangeCm")
    assert client.get(f"/api/robots/{RID}/navigation/data/export?kind=x").status_code == 400


def test_cancel_sweep_and_override(client):
    out = client.post(f"/api/robots/{RID}/navigation/cancel").get_json()
    assert "state" in out
    sweep = client.post(f"/api/robots/{RID}/navigation/sweep").get_json()
    assert sweep["status"] in ("executing", "queued", "rejected")
    assert client.post(f"/api/robots/{RID}/navigation/override", json={}).status_code == 400
    over = client.post(f"/api/robots/{RID}/navigation/override",
                       json={"command": "kjmp", "settleS": 0.2}).get_json()
    assert over["status"] in ("executing", "queued", "preempting", "rejected")
    assert wait_until(lambda: not navigation.active, 20.0)


def test_error_state_blocks_targets_until_answered(client):
    nav_error_state.enter(UnrecoverableError("map_contradiction", "test wall",
                                             {"cells": []}), None)
    refused = client.post(f"/api/robots/{RID}/navigation/target", json={"x": 0.2, "y": 0})
    assert refused.status_code == 409
    errors = client.get(f"/api/robots/{RID}/navigation/errors").get_json()
    assert errors["blocked"] is True and errors["active"]["kind"] == "map_contradiction"
    bad = client.post(f"/api/robots/{RID}/navigation/errors/respond", json={"choice": "shrug"})
    assert bad.status_code == 400
    ok = client.post(f"/api/robots/{RID}/navigation/errors/respond",
                     json={"choice": "trust_map", "note": "false alarm"}).get_json()
    assert ok["choice"] == "trust_map"
    again = client.post(f"/api/robots/{RID}/navigation/errors/respond", json={"choice": "manual"})
    assert again.status_code == 409
    assert client.get(f"/api/robots/{RID}/navigation/errors").get_json()["blocked"] is False
