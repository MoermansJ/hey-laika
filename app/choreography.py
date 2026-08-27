"""Animation library — pre-programmed movement sequences for the Bittle.

Commands follow the Petoi OpenCat serial protocol shape ("k<skill>").
The exact skill names should be verified against the Bittle X V2 firmware
in Phase 1; in mock mode they are only logged.
"""
from dataclasses import dataclass, field


@dataclass
class AnimationFrame:
    command: str
    duration: float = 1.0  # seconds to hold before the next frame


@dataclass
class Animation:
    name: str
    description: str
    frames: list[AnimationFrame] = field(default_factory=list)


class ChoreographyLibrary:
    def __init__(self):
        self._animations: dict[str, Animation] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            Animation("walk_forward", "Walk forward for a few seconds",
                      [AnimationFrame("kwkF", 3.0), AnimationFrame("kbalance", 0.5)]),
            Animation("spin_right", "Spin in place to the right",
                      [AnimationFrame("kvtR", 2.5), AnimationFrame("kbalance", 0.5)]),
            Animation("wave_arm", "Wave a front leg hello",
                      [AnimationFrame("khi", 2.0), AnimationFrame("kbalance", 0.5)]),
            Animation("play_dead", "Dramatically flop over",
                      [AnimationFrame("kpd", 3.0), AnimationFrame("kbalance", 1.0)]),
            Animation("stretch", "A long morning stretch",
                      [AnimationFrame("kstr", 2.5), AnimationFrame("kbalance", 0.5)]),
            Animation("excited_jump", "Excited bouncing",
                      [AnimationFrame("kjmp", 1.5), AnimationFrame("kjmp", 1.5),
                       AnimationFrame("kbalance", 0.5)]),
            Animation("curious_sniff", "Lower head and sniff around",
                      [AnimationFrame("ksnf", 2.0), AnimationFrame("kvtL", 1.0),
                       AnimationFrame("kbalance", 0.5)]),
            Animation("sit", "Sit down calmly",
                      [AnimationFrame("ksit", 2.0)]),
            Animation("rest", "Lie down and rest",
                      [AnimationFrame("krest", 2.0)]),
        ]
        for anim in defaults:
            self._animations[anim.name] = anim

    def list_animations(self) -> list[dict]:
        return [{"name": a.name, "description": a.description, "frames": len(a.frames)}
                for a in self._animations.values()]

    def names(self) -> list[str]:
        return list(self._animations.keys())

    def get(self, name: str) -> Animation | None:
        return self._animations.get(name)

    def build_command_sequence(self, name: str) -> list[AnimationFrame]:
        anim = self.get(name)
        return list(anim.frames) if anim else []
