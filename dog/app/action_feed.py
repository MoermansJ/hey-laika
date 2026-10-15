"""Per-action feed: one entry per step the arbiter actually dispatches.

The run log (behavior_store) records one row per SUBMISSION — a whole
`navigate`, a whole `fruitfly_drive` — which is the wrong grain for watching
her think. Fruitfly and Roaming each submit ONE long-running generator, so
the individual decisions they act on (FORWARD, LEFT, a route's next burst)
never appeared anywhere at all: not in the queue, not in the run log, not in
any API. This feed is that missing grain — the arbiter pushes an entry for
every step it sends to the robot, tagged with the mode/subsystem that
generated it, so the console can show "[FRUITFLY] opk0n - FORWARD" as it
happens and watch it move through.

Memory only, capped ring: this is a live view, not provenance. The run log
remains the durable record of what ran and why.
"""
import random
import string
import threading
import time
from collections import deque

FEED_MAX = 50
_ID_ALPHABET = string.ascii_lowercase + string.digits

# cause.type -> the tag the console shows. Events carry their own namespace
# ("idle.timeout" -> IDLE, "leash.warn" -> LEASH), which says more than a
# flat "EVENT" on every binding-driven behavior.
CAUSE_TAGS = {
    "fruitfly": "FRUITFLY",
    "nav.target": "ROAMING",
    "nav.sweep": "ROAMING",
    "nav.override": "ROAMING",
    "nav.error": "SAFETY",
    "mode": "MODE",
    "manual": "MANUAL",
    "agent": "AGENT",
    "voice": "VOICE",
}


def _new_id() -> str:
    return "".join(random.choices(_ID_ALPHABET, k=5))


def source_tag(cause: dict | None, source: str = "") -> str:
    """Which mode/subsystem generated this action, as a short upper tag."""
    cause = cause or {}
    kind = cause.get("type", "")
    if kind == "event":
        event = str(cause.get("event", ""))
        return (event.split(".")[0] or "event").upper()
    if kind in CAUSE_TAGS:
        return CAUSE_TAGS[kind]
    return (kind or source or "system").split(".")[0].upper()


class ActionFeed:
    def __init__(self, maxlen: int = FEED_MAX, clock=time.time):
        self._entries: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._clock = clock

    def push(self, tag: str, action: str, command: str | None = None,
             behavior: str | None = None, run_id: str | None = None,
             step: int | None = None) -> dict:
        entry = {"id": _new_id(), "at": self._clock(), "tag": tag, "action": action,
                 "command": command, "behavior": behavior, "runId": run_id,
                 "step": step, "status": "executing", "endedAt": None}
        with self._lock:
            self._entries.appendleft(entry)
        return entry

    def finish(self, entry: dict | None, status: str = "done") -> None:
        if not entry:
            return
        with self._lock:
            for row in self._entries:
                if row["id"] == entry["id"]:
                    if row["status"] == "executing":
                        row["status"] = status
                        row["endedAt"] = self._clock()
                    return

    def recent(self, limit: int = 20) -> list[dict]:
        """Newest first — the order the console stacks them in."""
        with self._lock:
            return [dict(row) for row in list(self._entries)[:max(0, int(limit))]]
