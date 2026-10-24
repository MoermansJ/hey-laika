"""Operating mode: which systems are allowed to move her, and why.

Four modes, mirroring com.bittle.orchestrator.domain.behavior.OperatingMode:
stationary (sits once, talks, zero autonomous movement after that), roaming
(autonomous exploration and mapping, sensed frontier-driven), fruitfly (an
external "brain" drives her; no owner interaction), phone (hand-gesture
digit capture; conversation and eyes' person detection paused while a hand
is being read). See docs/design/PERSONALITY_MODES_BRIEF.md.

The orchestrator is the source of truth for the mode itself (persisted
there, survives an adapter restart) and pushes every change here via
POST /mode; this service is the adapter-side mirror that actually flips
conversation/eyes/arbiter/idle-ladder. Roaming's frontier explorer (P2,
explorer.py) is wired in; Fruitfly's connectome-driven brain is wired in
too (F2, fruitfly_drive.py — polls dog/fruitfly/server.py's live decoded
command and bridges it into the arbiter at `agent` priority). Phone's
hand-input reader (hands.py) is the one still unbuilt: wiring is here, the
reader itself is a later phase.

2026-09-25 incident: the orchestrator's personality-tick loop picked
backflip/spin while "in" Stationary (its boredom branch, unrelated to this
service) and event_binder.py's idle-ladder background thread — which fires
through the arbiter independent of mode — kept nudging posture regardless
of what mode was set. The loop is now never started (SetRobotModeUseCase);
this service now also explicitly silences the idle ladder for Stationary
and Fruitfly (_set_idle_ladder) rather than assuming "not roaming" left it
harmless.
"""
import logging
import time

from app.behavior_store import PRIORITY_LIFECYCLE

logger = logging.getLogger(__name__)

MODES = ("stationary", "roaming", "fruitfly", "phone")


class ModeService:
    def __init__(self, arbiter, conversation, eyes, event_binder, behavior_store,
                 explorer=None, hand_input=None, fruitfly_drive=None):
        self.arbiter = arbiter
        self.conversation = conversation
        self.eyes = eyes
        self.event_binder = event_binder
        self.behavior_store = behavior_store
        self.explorer = explorer
        self.hand_input = hand_input
        self.fruitfly_drive = fruitfly_drive
        self._mode = "stationary"
        self._changed_at = time.time()

    def status(self) -> dict:
        return {"mode": self._mode, "changedAt": self._changed_at}

    def set_mode(self, mode: str) -> dict:
        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode}")
        if mode != self._mode:
            logger.info("mode: %s -> %s", self._mode, mode)
            self._apply(mode)
            self._mode = mode
            self._changed_at = time.time()
            self.event_binder.trigger("mode.changed", {"mode": mode})
        return self.status()

    def _apply(self, mode: str) -> None:
        if mode != "roaming" and self.explorer is not None:
            self.explorer.stop()
        if mode != "phone" and self.hand_input is not None:
            self.hand_input.stop()
        if mode != "fruitfly" and self.fruitfly_drive is not None:
            self.fruitfly_drive.stop()
        if mode == "stationary":
            self.conversation.enabled = True
            self._set_eyes(True)
            self._set_idle_ladder(False)
            self.arbiter.submit("idle_sit", source="lifecycle",
                                priority=PRIORITY_LIFECYCLE,
                                cause={"type": "mode", "mode": mode})
        elif mode == "roaming":
            self.conversation.enabled = True
            self._set_eyes(True)
            self._set_idle_ladder(True)
            if self.explorer is not None:
                self.explorer.start()
        elif mode == "fruitfly":
            self.conversation.enabled = False
            self._set_eyes(False)
            self._set_idle_ladder(False)
            self.arbiter.stop_current()
            if self.fruitfly_drive is not None:
                self.fruitfly_drive.start()
        elif mode == "phone":
            self.conversation.enabled = False
            self._set_eyes(False)
            if self.hand_input is not None:
                self.hand_input.start()

    def _set_idle_ladder(self, enabled: bool) -> None:
        """Stationary: no autonomous movement at all, not even the gentle
        sit/rest ladder — it fires through the arbiter independent of mode
        (event_binder.py's own background thread) so it has to be disabled
        explicitly, not just left alone. Fruitfly: same — the connectome
        bridge (fruitfly_drive.py) already owns her at `agent` priority, and
        the idle ladder's sit/rest nudges have no business competing with
        that. Roaming restores it."""
        self.behavior_store.set_binding_enabled("idle.timeout", "idle_sit", enabled)
        self.behavior_store.set_binding_enabled("idle.timeout", "idle_rest", enabled)

    def _set_eyes(self, enabled: bool) -> None:
        try:
            self.eyes.set_enabled(enabled)
        except RuntimeError:
            pass   # no satellite configured (e.g. Mocha); nothing to flip
