"""Fruitfly's F2 bridge into the arbiter (PERSONALITY_MODES_BRIEF.md §6.3):
polls the live connectome sim (dog/fruitfly/server.py) over localhost HTTP
for its currently decoded locomotor command and submits one short gait
burst per poll at `agent` priority — structurally the same bounded-burst
generator pattern as explorer.py/navigator.py, but driven by the sim's
decoded state instead of the frontier map or a nav target. The arbiter
itself owns execution, preemption at step boundaries and the run log
(every burst this submits is already audited there via its `cause`); the
logging here is the human-readable trail of which fly state decoded to
which command, matching the console idiom sim.py/server.py already use.

BACKWARD is decoded by the sim (sim.py's docstring, §6.2) but mapped to the
same command as STOP here: no backward-walk skill exists in this adapter's
command set (action_executor.py/gait_learner.py only ever send
kwkF/kwkL/kwkR + kbalance), so inventing one to send to real hardware would
be a guess, not a verified skill — the brief explicitly allows dropping it
at this bridge for exactly that reason.
"""
import logging

import requests

from app.behavior_store import PRIORITY_AGENT

logger = logging.getLogger(__name__)

FRUITFLY_BEHAVIOR = "fruitfly_drive"

STATE_TO_COMMAND = {
    "FORWARD": "kwkF",
    "LEFT": "kwkL",
    "RIGHT": "kwkR",
    "STOP": "kbalance",
    "BACKWARD": "kbalance",
}

DEFAULTS = {
    "burstS": 1.0,              # settle time per gait burst ("short", per the brief)
    "pollTimeoutS": 0.5,
    "unreachableBackoffS": 2.0,
}


class FruitflyDriveService:
    def __init__(self, arbiter, sim_url: str, config: dict | None = None,
                 fetch_command=None, trigger=None):
        self.arbiter = arbiter
        self.sim_url = sim_url.rstrip("/")
        self.config = {**DEFAULTS, **(config or {})}
        self._fetch_command = fetch_command or self._http_fetch
        self.trigger = trigger or (lambda event, payload=None: None)
        self._last_state: str | None = None
        self._last_signals: dict = {}
        self._unreachable_logged = False

    # ---- lifecycle, mirroring ExplorerService's start/stop shape ----------

    def start(self) -> dict:
        result = self.arbiter.submit_generator(
            FRUITFLY_BEHAVIOR, self._drive_steps, source="agent",
            priority=PRIORITY_AGENT, cause={"type": "fruitfly"})
        logger.info("Fruitfly drive: start requested (%s)", result.get("status"))
        return result

    def stop(self) -> bool:
        if self.arbiter.current_behavior() != FRUITFLY_BEHAVIOR:
            return False
        stopped = bool(self.arbiter.stop_current().get("stopped"))
        if stopped:
            logger.info("Fruitfly drive: stopped")
        return stopped

    def status(self) -> dict:
        return {"lastState": self._last_state, "lastSignals": dict(self._last_signals)}

    # ---- the generator: poll, map, yield one burst, repeat -----------------

    def _drive_steps(self):
        while True:
            command = self._fetch_command()
            if command is None:
                if not self._unreachable_logged:
                    logger.warning("Fruitfly drive: sim at %s unreachable; holding balance",
                                   self.sim_url)
                    self._unreachable_logged = True
                yield {"command": "kbalance", "label": "HOLD (sim unreachable)",
                       "settleS": float(self.config["unreachableBackoffS"])}
                continue
            self._unreachable_logged = False
            state = command.get("state", "STOP")
            signals = command.get("signals", {})
            if state != self._last_state:
                logger.info("Fruitfly drive: decoded %s -> %s", self._last_state, state)
                self.trigger("fruitfly.command", {"state": state, "signals": signals})
            self._last_state, self._last_signals = state, signals
            skill = STATE_TO_COMMAND.get(state, "kbalance")
            # `label` is what the action feed shows ("FORWARD"), rather than
            # the skill token it maps to ("kwkF").
            yield {"command": skill, "label": state,
                   "settleS": float(self.config["burstS"])}

    def _http_fetch(self) -> dict | None:
        try:
            response = requests.get(f"{self.sim_url}/command",
                                    timeout=float(self.config["pollTimeoutS"]))
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return None
