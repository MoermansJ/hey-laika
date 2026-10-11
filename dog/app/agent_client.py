"""Agent tool composition, adapter side (AGENT-15).

The stationary assistant (ConversationService) lets the LLM router pick
orchestrator-managed agent tools next to its own voice.intent tools. This
client talks to the orchestrator's agent API:

- GET  /api/v1/agent/{robotId}/tools               -> tools allowed in the current mode
- GET  /api/v1/agent/{robotId}/patterns?goal=X     -> learned tool combinations, best first
- POST /api/v1/agent/{robotId}/submit-tool         -> {toolName, goal, decisionId}

A goal's learned combination replaces the single tool the router picked once
it has proven itself (enough attempts at a good success rate). Every call
degrades quietly: the orchestrator being down means no agent tools, never a
failed conversation turn.
"""
import logging
import time
import uuid

import requests

logger = logging.getLogger(__name__)

ACCEPTED = ("executing", "queued", "preempting")
TOOLS_TTL_S = 5.0


class AgentToolsClient:
    def __init__(self, base_url: str | None, robot_id: str, timeout_s: float = 2.0,
                 min_pattern_attempts: int = 3, min_pattern_rate: float = 0.5,
                 session=None, clock=time.monotonic):
        self.base_url = (base_url or "").rstrip("/")
        self.robot_id = robot_id
        self.timeout_s = timeout_s
        self.min_pattern_attempts = min_pattern_attempts
        self.min_pattern_rate = min_pattern_rate
        self.http = session or requests.Session()
        self._clock = clock
        self._tools: list[dict] = []
        self._tools_at: float | None = None
        self.stats = {"submitted": 0, "rejected": 0, "errors": 0, "patternsUsed": 0,
                      "lastError": None}

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/agent/{self.robot_id}{path}"

    def _error(self, what: str, exc: Exception) -> None:
        self.stats["errors"] += 1
        self.stats["lastError"] = f"{what}: {exc}"
        logger.warning("Agent %s failed: %s", what, exc)

    # -- reads --

    def tools(self) -> list[dict]:
        """Agent tools allowed in the robot's current mode ([] when unreachable).
        Cached briefly: the conversation status is polled by the GUI."""
        if not self.enabled:
            return []
        now = self._clock()
        if self._tools_at is not None and now - self._tools_at < TOOLS_TTL_S:
            return list(self._tools)
        try:
            resp = self.http.get(self._url("/tools"), timeout=self.timeout_s)
            resp.raise_for_status()
            data = resp.json()
            tools = [t for t in data if isinstance(t, dict) and t.get("name")] \
                if isinstance(data, list) else []
        except Exception as exc:
            self._error("tools", exc)
            tools = []
        self._tools, self._tools_at = tools, now
        return list(tools)

    def patterns(self, goal: str) -> list[dict]:
        """Learned combinations for the goal, best first ([] when unreachable)."""
        if not self.enabled or not goal:
            return []
        try:
            resp = self.http.get(self._url("/patterns"), params={"goal": goal},
                                 timeout=self.timeout_s)
            resp.raise_for_status()
            data = resp.json()
            return [p for p in data if isinstance(p, dict)] if isinstance(data, list) else []
        except Exception as exc:
            self._error("patterns", exc)
            return []

    def plan(self, tool: str, goal: str) -> list[str]:
        """The tools to run for the goal: the best learned combination when it has
        at least min_pattern_attempts at min_pattern_rate or better, else [tool]."""
        allowed = {t["name"] for t in self.tools()}
        for pattern in self.patterns(goal):
            combo = [str(name) for name in (pattern.get("toolCombination") or [])]
            if not combo or any(name not in allowed for name in combo):
                continue
            if (int(pattern.get("attempts") or 0) >= self.min_pattern_attempts
                    and float(pattern.get("successRate") or 0.0) >= self.min_pattern_rate):
                if combo != [tool]:
                    self.stats["patternsUsed"] += 1
                return combo
            break      # best first: the rest are worse
        return [tool]

    # -- writes --

    def submit(self, tool: str, goal: str | None, decision_id: str) -> dict:
        """One tool call. The arbiter's answer, or a local rejection on errors."""
        try:
            resp = self.http.post(self._url("/submit-tool"), timeout=self.timeout_s,
                                  json={"toolName": tool, "goal": goal,
                                        "decisionId": decision_id})
            if resp.status_code >= 400:
                try:
                    message = resp.json().get("message")
                except ValueError:
                    message = None
                return {"status": "rejected",
                        "message": message or f"orchestrator HTTP {resp.status_code}"}
            data = resp.json()
            return data if isinstance(data, dict) and data.get("status") else \
                {"status": "rejected", "message": "empty orchestrator response"}
        except Exception as exc:
            self._error("submit", exc)
            return {"status": "rejected", "message": f"orchestrator unreachable: {exc}"}

    def run(self, tool: str, goal: str | None = None) -> dict:
        """Run the router's pick for its goal: plan (learned combination or the
        tool alone), then submit each tool under one decision id, stopping at
        the first rejection."""
        goal = goal or tool
        decision_id = str(uuid.uuid4())
        combo = self.plan(tool, goal)
        results = []
        for name in combo:
            result = self.submit(name, goal, decision_id)
            results.append({"tool": name, **result})
            if result.get("status") not in ACCEPTED:
                self.stats["rejected"] += 1
                logger.info("Agent tool %s (goal %s) rejected: %s", name, goal,
                            result.get("message"))
                break
            self.stats["submitted"] += 1
        accepted = bool(results) and all(r.get("status") in ACCEPTED for r in results)
        return {"decisionId": decision_id, "goal": goal, "tools": combo,
                "results": results, "accepted": accepted,
                "message": None if accepted else results[-1].get("message")}

    def status(self) -> dict:
        return {"enabled": self.enabled, "baseUrl": self.base_url or None, **self.stats}
