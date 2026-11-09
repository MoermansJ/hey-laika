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

Giant-fiber escape override (§6.1's "closing the loop with Laika's ranger
and camera" v2, picked up by the Fly Brain Loom Demo design doc): a second,
optional sidecar (fly-brain-loom/sidecar/gf_server.py — snuri00/fruit-fly-
connectome + flyvis over Laika's real camera, not the open-loop locomotor
sim above) is polled the same way. A fresh giant-fiber spike there preempts
one locomotor burst with the same kjmp/kbalance pair the BACKFLIP catalogue
action already uses (action_executor.py's verified jump skill), rate
limited by `gfCooldownS` so a sustained loom can't spam jumps. Disabled by
leaving `gf_url` unset/empty — the locomotor-only behavior is unchanged.
"""
import logging
import time

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
    "gfCooldownS": 4.0,         # min gap between escape jumps, however often GF fires
    "escapeJumpS": 1.0,         # kjmp settle time (matches action_executor's backflip plan)
    "escapeRecoverS": 0.6,      # kbalance settle time restoring stance after the jump
}


class FruitflyDriveService:
    def __init__(self, arbiter, sim_url: str, gf_url: str | None = None,
                 config: dict | None = None, fetch_command=None, fetch_gf=None,
                 trigger=None):
        self.arbiter = arbiter
        self.sim_url = sim_url.rstrip("/")
        self.gf_url = gf_url.rstrip("/") if gf_url else None
        self.config = {**DEFAULTS, **(config or {})}
        self._fetch_command = fetch_command or self._http_fetch
        self._fetch_gf = fetch_gf or self._http_fetch_gf
        self.trigger = trigger or (lambda event, payload=None: None)
        self._last_state: str | None = None
        self._last_signals: dict = {}
        self._unreachable_logged = False
        self._gf_unreachable_logged = False
        self._last_gf_status: dict | None = None  # for status() -- observability only
        self._last_gf_seen_at: float | None = None
        self._last_escape_at = 0.0

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
        """lastGf* mirrors whatever _check_gf_escape() last read from the
        sidecar -- cached here (not fetched fresh on every call) so a GUI
        poll never adds its own extra hit to gf_server.py; it rides the same
        ~1 drive-loop-iteration cadence the escape decision itself runs at."""
        gf = self._last_gf_status or {}
        return {"lastState": self._last_state, "lastSignals": dict(self._last_signals),
                "gfEnabled": self.gf_url is not None,
                "gfRateHz": gf.get("gfRateHz"), "gfSpikes": gf.get("gfSpikes"),
                "lastGfAt": gf.get("lastGfAt"),
                "lastEscapeAt": self._last_escape_at or None}

    # ---- the generator: poll, map, yield one burst, repeat -----------------

    def _drive_steps(self):
        while True:
            if self.gf_url:
                escape_steps = self._check_gf_escape()
                if escape_steps is not None:
                    yield from escape_steps
                    continue
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

    # ---- giant-fiber escape override ---------------------------------------

    def _check_gf_escape(self) -> list[dict] | None:
        """Returns the jump+recover burst pair if a fresh, off-cooldown giant
        fiber spike is waiting at the sidecar, else None (walk as normal)."""
        gf = self._fetch_gf()
        self._last_gf_status = gf
        if gf is None:
            if not self._gf_unreachable_logged:
                logger.warning("Fruitfly drive: giant-fiber sidecar at %s unreachable; "
                               "walk-only until it answers", self.gf_url)
                self._gf_unreachable_logged = True
            return None
        self._gf_unreachable_logged = False
        last_gf_at = gf.get("lastGfAt")
        now = time.time()
        if (last_gf_at is None
                or last_gf_at == self._last_gf_seen_at
                or now - self._last_escape_at < float(self.config["gfCooldownS"])):
            return None
        self._last_gf_seen_at = last_gf_at
        self._last_escape_at = now
        logger.info("Fruitfly drive: giant fiber spike -> escape jump")
        self.trigger("fruitfly.escape", {"lastGfAt": last_gf_at, "gfSpikes": gf.get("gfSpikes")})
        return [
            {"command": "kjmp", "label": "ESCAPE (giant fiber)",
             "settleS": float(self.config["escapeJumpS"])},
            {"command": "kbalance", "label": "recover",
             "settleS": float(self.config["escapeRecoverS"])},
        ]

    def _http_fetch_gf(self) -> dict | None:
        try:
            response = requests.get(f"{self.gf_url}/command",
                                    timeout=float(self.config["pollTimeoutS"]))
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return None
