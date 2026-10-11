"""AGENT-15: the adapter's client for the orchestrator agent API."""
import requests

from app.agent_client import AgentToolsClient


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, tools=None, patterns=None, submit=None, fail=False):
        self.tools = tools if tools is not None else []
        self.patterns = patterns if patterns is not None else {}
        self.submit = submit or (lambda body: FakeResponse(200, {
            "status": "queued", "runLogId": "r-" + body["toolName"], "position": 0}))
        self.fail = fail
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        if self.fail:
            raise requests.ConnectionError("refused")
        if url.endswith("/tools"):
            return FakeResponse(200, self.tools)
        if url.endswith("/patterns"):
            return FakeResponse(200, self.patterns.get(params["goal"], []))
        return FakeResponse(404, {})

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        if self.fail:
            raise requests.ConnectionError("refused")
        return self.submit(json)


TOOLS = [{"name": "look_upward", "description": "Face upward", "category": "postural"},
         {"name": "tilt_head", "description": "Tilt head", "category": "postural"},
         {"name": "bark", "description": "Bark once", "category": "vocal"}]


def client(session, **kw):
    return AgentToolsClient("http://orch:8080/", "bittle-1", session=session, **kw)


def test_disabled_without_base_url():
    c = AgentToolsClient("", "bittle-1", session=FakeSession(tools=TOOLS))
    assert not c.enabled
    assert c.tools() == [] and c.patterns("bark") == []


def test_tools_are_fetched_from_the_robot_path_and_cached():
    now = [100.0]
    session = FakeSession(tools=TOOLS)
    c = client(session, clock=lambda: now[0])
    assert [t["name"] for t in c.tools()] == ["look_upward", "tilt_head", "bark"]
    assert session.calls[0][1] == "http://orch:8080/api/v1/agent/bittle-1/tools"
    c.tools()
    assert len(session.calls) == 1            # cached
    now[0] += 6
    c.tools()
    assert len(session.calls) == 2            # refreshed after the TTL


def test_unreachable_orchestrator_gives_no_tools_and_counts_the_error():
    c = client(FakeSession(fail=True))
    assert c.tools() == []
    assert c.patterns("bark") == []
    assert c.stats["errors"] == 2 and "refused" in c.stats["lastError"]


def test_run_submits_the_single_tool_with_goal_and_decision():
    session = FakeSession(tools=TOOLS)
    result = client(session).run("look_upward")
    assert result["accepted"] is True and result["tools"] == ["look_upward"]
    post = [c for c in session.calls if c[0] == "POST"][0]
    assert post[1] == "http://orch:8080/api/v1/agent/bittle-1/submit-tool"
    assert post[2]["toolName"] == "look_upward" and post[2]["goal"] == "look_upward"
    assert post[2]["decisionId"] == result["decisionId"]
    assert result["results"][0]["status"] == "queued"


def test_proven_pattern_replaces_the_pick_and_shares_one_decision():
    patterns = {"look_upward": [
        {"toolCombination": ["tilt_head", "look_upward"], "successRate": 0.9, "attempts": 10},
        {"toolCombination": ["look_upward"], "successRate": 0.2, "attempts": 10}]}
    session = FakeSession(tools=TOOLS, patterns=patterns)
    c = client(session)
    result = c.run("look_upward")
    posts = [c_[2] for c_ in session.calls if c_[0] == "POST"]
    assert [p["toolName"] for p in posts] == ["tilt_head", "look_upward"]
    assert len({p["decisionId"] for p in posts}) == 1
    assert result["tools"] == ["tilt_head", "look_upward"] and result["accepted"]
    assert c.stats["patternsUsed"] == 1


def test_unproven_or_unavailable_pattern_is_ignored():
    patterns = {"look_upward": [
        {"toolCombination": ["tilt_head", "look_upward"], "successRate": 1.0, "attempts": 2}],
        "bark": [{"toolCombination": ["move_forward", "bark"], "successRate": 1.0,
                  "attempts": 9}]}
    c = client(FakeSession(tools=TOOLS, patterns=patterns))
    assert c.plan("look_upward", "look_upward") == ["look_upward"]   # too few attempts
    assert c.plan("bark", "bark") == ["bark"]                        # tool not in this mode


def test_rejection_stops_the_sequence_and_reports_the_message():
    patterns = {"look_upward": [
        {"toolCombination": ["tilt_head", "look_upward"], "successRate": 0.9, "attempts": 10}]}
    session = FakeSession(tools=TOOLS, patterns=patterns,
                          submit=lambda body: FakeResponse(200, {"status": "rejected",
                                                                 "message": "cooldown"}))
    c = client(session)
    result = c.run("look_upward")
    assert result["accepted"] is False and result["message"] == "cooldown"
    assert len([x for x in session.calls if x[0] == "POST"]) == 1
    assert c.stats["rejected"] == 1


def test_http_error_from_orchestrator_becomes_a_rejection():
    session = FakeSession(tools=TOOLS, submit=lambda body: FakeResponse(
        404, {"error": "robot_not_found", "message": "No robot registered"}))
    result = client(session).submit("bark", "bark", "d-1")
    assert result == {"status": "rejected", "message": "No robot registered"}


def test_unreachable_orchestrator_on_submit_is_a_rejection():
    result = client(FakeSession(fail=True)).run("bark")
    assert result["accepted"] is False
    assert "unreachable" in result["message"]
