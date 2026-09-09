"""A simulated room for the mock controller: walls as line segments, the
dog's true pose, and a ray-cast ranger, so mapping, planning, avoidance and
contradiction detection can be exercised end to end without hardware.

The world moves the dog by the same calibrated stride model the senses
layer dead-reckons with (0.10 m first cycle, 0.112 m per cycle after), so
by default the estimate and the truth agree; `slip` scales the real travel
to fake a slippery floor and `noise_cm` jitters the echoes. Yaw is reported
unwrapped, like the ICM42670 does.
"""
import math
import random
import re

FIRST_CYCLE_M = 0.10
PER_CYCLE_M = 0.112
MAX_RANGE_M = 2.0

_ADVANCE = re.compile(r"^k(wk|tr|cr|bk)F\s+(\d+)$")
_TURN = re.compile(r"^k(?:wk|vt)([LR])(?:\s+(\d+))?$")
_JOINT = re.compile(r"^[mMiI]\s+0[\s:](-?\d+)")


def rect(x0: float, y0: float, x1: float, y1: float) -> list[tuple]:
    return [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
            ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]


# A 4 x 3 m room with the dog starting near its west wall facing east,
# and a 30 cm box 1.2 m ahead of her.
DEFAULT_WALLS = rect(-1.0, -1.0, 3.0, 2.0) + rect(1.2, -0.15, 1.5, 0.15)


class MockWorld:
    def __init__(self, walls: list[tuple] | None = None, x: float = 0.0,
                 y: float = 0.0, heading: float = 0.0, slip: float = 1.0,
                 noise_cm: float = 0.0, rng: random.Random | None = None):
        self.walls = list(DEFAULT_WALLS if walls is None else walls)
        self.x, self.y, self.heading = x, y, heading
        self.slip = slip
        self.noise_cm = noise_cm
        self.pan_deg = 0.0
        self._rng = rng or random.Random(7)
        self.moves = 0

    # ---- motion ------------------------------------------------------------

    def advance(self, meters: float) -> None:
        rad = math.radians(self.heading)
        self.x += meters * self.slip * math.cos(rad)
        self.y += meters * self.slip * math.sin(rad)
        self.moves += 1

    def turn(self, degrees: float) -> None:
        self.heading += degrees
        self.moves += 1

    def apply_command(self, command: str) -> bool:
        command = command.strip()
        advance = _ADVANCE.match(command)
        if advance:
            cycles = int(advance.group(2))
            meters = FIRST_CYCLE_M + PER_CYCLE_M * (cycles - 1) if cycles > 0 else 0.0
            self.advance(-meters if advance.group(1) == "bk" else meters)
            return True
        turn = _TURN.match(command)
        if turn:
            degrees = float(turn.group(2) or 30)
            self.turn(degrees if turn.group(1) == "L" else -degrees)
            return True
        joint = _JOINT.match(command)
        if joint:
            self.pan_deg = float(joint.group(1))
            return True
        return False

    def yaw(self) -> float:
        return self.heading

    # ---- sensing -----------------------------------------------------------

    def range_m(self, pan_deg: float | None = None) -> float | None:
        pan = self.pan_deg if pan_deg is None else pan_deg
        rad = math.radians(self.heading + pan)
        dx, dy = math.cos(rad), math.sin(rad)
        best = None
        for (ax, ay), (bx, by) in self.walls:
            hit = _ray_segment(self.x, self.y, dx, dy, ax, ay, bx, by)
            if hit is not None and hit > 1e-6 and (best is None or hit < best):
                best = hit
        if best is None or best > MAX_RANGE_M:
            return None
        return best

    def range_cm(self, pan_deg: float | None = None) -> float | None:
        distance = self.range_m(pan_deg)
        if distance is None:
            return None
        cm = distance * 100.0
        if self.noise_cm:
            cm += self._rng.uniform(-self.noise_cm, self.noise_cm)
        return round(max(1.0, cm), 1)

    def status(self) -> dict:
        return {"x": round(self.x, 3), "y": round(self.y, 3),
                "heading": round(self.heading, 1), "panDeg": self.pan_deg,
                "walls": len(self.walls), "moves": self.moves}


def _ray_segment(px, py, dx, dy, ax, ay, bx, by) -> float | None:
    """Distance along the ray (px, py) + t (dx, dy) to segment AB, or None."""
    ex, ey = bx - ax, by - ay
    denominator = dx * ey - dy * ex
    if abs(denominator) < 1e-12:
        return None
    t = ((ax - px) * ey - (ay - py) * ex) / denominator
    u = ((ax - px) * dy - (ay - py) * dx) / denominator
    if t >= 0 and 0.0 <= u <= 1.0:
        return t
    return None
