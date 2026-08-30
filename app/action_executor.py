"""Executes the orchestrator's abstract behavior actions on hardware.

Phase 1b of the personality system: the orchestrator's behavior loop owns the
brain and POSTs execute_action; this module translates each abstract action id
into concrete firmware commands (skills or joint moves) and paces them to the
requested duration.

Mapping notes:
- Gaits (walk/spin) start a cyclic skill, hold it for the requested duration,
  then restore the balance stand — cyclic skills run until replaced.
- The Bittle head has pan only (no tilt servo), so look_up is a small scan
  sweep rather than a true upward look.
- backflip is deliberately mapped to a jump: the real kbf skill is unverified
  on this firmware and risks the robot landing on its electronics.
"""
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_HEAD = 0
_LOOK_ANGLE = 40
_SCAN_ANGLE = 25


@dataclass
class Step:
    kind: str          # "skill" | "joints" | "pause"
    skill: str | None = None
    joints: list | None = None
    seconds: float = 0.0


def _skill(token: str) -> Step:
    return Step("skill", skill=token)


def _joints(moves: list) -> Step:
    return Step("joints", joints=moves)


def _pause(seconds: float) -> Step:
    return Step("pause", seconds=seconds)


# Steps per action. "hold" pads the remaining duration; gaits get their stand
# restored afterwards so the orchestrator's posture model stays truthful.
ACTION_PLANS: dict[str, list[Step]] = {
    "walk_slow":  [_skill("kwkF"), _pause(-1), _skill("kbalance")],
    "walk_fast":  [_skill("kwkF"), _pause(-1), _skill("kbalance")],
    "stand_up":   [_skill("kbalance")],
    "sit_down":   [_skill("ksit")],
    "lie_down":   [_skill("krest")],
    "look_left":  [_joints([(_HEAD, _LOOK_ANGLE)]), _pause(-1),
                   _joints([(_HEAD, 0)])],
    "look_right": [_joints([(_HEAD, -_LOOK_ANGLE)]), _pause(-1),
                   _joints([(_HEAD, 0)])],
    "look_up":    [_joints([(_HEAD, _SCAN_ANGLE)]), _pause(0.3),
                   _joints([(_HEAD, -_SCAN_ANGLE)]), _pause(0.3),
                   _joints([(_HEAD, 0)])],
    "play_bow":   [_skill("kstr"), _pause(-1), _skill("kbalance")],
    "backflip":   [_skill("kjmp"), _pause(-1), _skill("kbalance")],
    "spin":       [_skill("kvtR"), _pause(-1), _skill("kbalance")],
    "idle_calm":  [_pause(-1)],
    "sleep":      [_skill("krest"), _pause(-1)],
    "wake_up":    [_joints([(_HEAD, 15)]), _pause(0.3), _joints([(_HEAD, 0)]),
                   _pause(-1)],
    "seek_attention": [_skill("khi"), _pause(-1), _skill("kbalance")],
}


def execute_action(bittle, action_id: str,
                   duration_ms: int) -> tuple[bool, int, str]:
    """Run one abstract action; returns (success, actual_ms, message).

    A pause of -1 is elastic: it absorbs whatever remains of duration_ms so
    the wall-clock pacing matches the orchestrator's expectation.
    """
    plan = ACTION_PLANS.get(action_id)
    if plan is None:
        raise KeyError(action_id)
    started = time.time()
    budget = max(duration_ms, 0) / 1000.0
    for step in plan:
        if step.kind == "skill":
            if not bittle.send_command(step.skill):
                return False, int((time.time() - started) * 1000), \
                    f"skill {step.skill} got no completion echo"
        elif step.kind == "joints":
            if not bittle.move_joints(step.joints):
                return False, int((time.time() - started) * 1000), \
                    "joint move got no completion echo"
        elif step.kind == "pause":
            if step.seconds >= 0:
                time.sleep(step.seconds)
            else:
                remaining = budget - (time.time() - started)
                # Leave headroom for the restore steps that follow.
                if remaining > 0.05:
                    time.sleep(remaining)
    actual = int((time.time() - started) * 1000)
    logger.info("Executed action %s in %d ms", action_id, actual)
    return True, actual, "executed"
