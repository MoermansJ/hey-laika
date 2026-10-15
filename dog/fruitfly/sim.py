"""Fruitfly bench spike (PERSONALITY_MODES_BRIEF.md F1, §6.1-§6.2): ticks a
leaky-rate simulation over the MaleCNS connectome and logs the decoded
locomotor command each tick. Headless — no robot, no arbiter, nothing sent
anywhere. This is the kill-criterion check (§6.6): does the readout look like
a legible forward/turn/stop signal, or noise?

Model: a Wilson-Cowan-style leaky-rate network, not a spiking LIF (simpler to
get right for a bench spike; the brief's own pseudocode — "activity[t+1] =
decay*activity[t] + f(W*activity[t] + drive[t] + noise)" — already reads as
a rate model). Each neuron's rate is bounded to [0, 1] by construction
(a convex combination of the previous rate and a sigmoid), so unlike a raw
weight-sum model this can't blow up regardless of GAIN/BIAS tuning — those
two constants only shape *how much* of the network lights up, which is
exactly the free parameter this bench spike exists to explore.

Drive (v1, open-loop per §6.1 point 3): tonic + gaussian noise injected into
the three sensory superclasses (ol_sensory/vnc_sensory/cb_sensory, ~17k
neurons) — nothing camera/ranger-grounded yet, matching the "I read neural
activity from it" framing the brief quotes, not a closed loop.

Motor readout (§6.2): the giant-fiber/moonwalker family the brief points to
resolves to concrete, named cell types once filtered to Traced neurons —
checked directly against the downloaded annotations, not guessed:
  - DNp09 (2 cells, L/R pair): the documented forward-walking command neuron
    (Bidaye et al. 2020).
  - MDN, "moonwalker descending neurons" (4 cells): drives backward walking
    (Bidaye et al. 2014). The brief's emitted set (§6.2) only lists
    FORWARD/LEFT/RIGHT/STOP; this sim also decodes BACKWARD since the
    population is right there and free to read — drop it at the F2 bridge if
    the arbiter side wants to hold to the brief's original 4-state contract.
  - DNa02 (2 cells, L/R pair): a lateralized steering neuron (Rayshubskiy et
    al. 2020); L-vs-R activity difference drives LEFT/RIGHT.
Thresholds use hysteresis (enter > exit) so activity hovering near a
threshold doesn't chatter the decoded command every tick.

Calibration (2026-09-20 bench run, checked directly rather than guessed):
swept gain x bias at a fixed drive; below gain~0.02 the readout populations
stay silent regardless of bias, above gain~0.1 most of the network (not just
the readout) saturates near 1.0 — neither is legible. gain=0.05, bias=2.0
sits in between: whole-network mean activity stays moderate (~0.2, not
saturated) while the readout populations themselves behave like sharp,
mostly-mutually-exclusive switches — BACKWARD/FORWARD/LEFT/RIGHT/STOP episodes
separated by clean STOP gaps, never several "on" at once. That is a pass on
the kill criterion (§6.6): legible, not noise. These defaults are a first
pass, not a calibrated model — rerun with --gain/--bias/--drive-mean if a
different regime is wanted.
"""
import argparse
import csv
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import build_matrix

DATA_DIR = Path(__file__).parent / "data"

SENSORY_SUPERCLASSES = {"ol_sensory", "vnc_sensory", "cb_sensory"}
FORWARD_TYPE = "DNp09"
BACKWARD_TYPE = "MDN"
TURN_TYPE = "DNa02"

STATES = ("STOP", "FORWARD", "BACKWARD", "LEFT", "RIGHT")


@dataclass
class Readout:
    forward_idx: np.ndarray
    backward_idx: np.ndarray
    turn_left_idx: np.ndarray
    turn_right_idx: np.ndarray
    enter: float = 0.5
    exit: float = 0.3
    turn_enter: float = 0.15
    turn_exit: float = 0.05
    state: str = "STOP"

    def decode(self, activity: np.ndarray) -> tuple[str, dict]:
        forward = float(activity[self.forward_idx].mean()) if len(self.forward_idx) else 0.0
        backward = float(activity[self.backward_idx].mean()) if len(self.backward_idx) else 0.0
        left = float(activity[self.turn_left_idx].mean()) if len(self.turn_left_idx) else 0.0
        right = float(activity[self.turn_right_idx].mean()) if len(self.turn_right_idx) else 0.0
        turn = right - left

        # Priority: backward (moonwalker is behaviorally near all-or-none) >
        # turning > forward > stop. Hysteresis is per-candidate: a candidate
        # already active needs to drop below `exit`, not just below `enter`,
        # to be abandoned.
        def active(value, was_active):
            threshold = self.exit if was_active else self.enter
            return value >= threshold

        if active(backward, self.state == "BACKWARD"):
            self.state = "BACKWARD"
        elif active(abs(turn), self.state in ("LEFT", "RIGHT")):
            self.state = "RIGHT" if turn > 0 else "LEFT"
        elif active(forward, self.state == "FORWARD"):
            self.state = "FORWARD"
        else:
            self.state = "STOP"
        return self.state, {"forward": forward, "backward": backward,
                            "left": left, "right": right, "turn": turn}


def build_readout(index) -> Readout:
    def ids(cell_type: str, soma_side: str | None = None) -> np.ndarray:
        mask = index["type"] == cell_type
        if soma_side is not None:
            mask &= index["somaSide"] == soma_side
        return index.loc[mask, "idx"].to_numpy()

    return Readout(
        forward_idx=ids(FORWARD_TYPE),
        backward_idx=ids(BACKWARD_TYPE),
        turn_left_idx=ids(TURN_TYPE, "L"),
        turn_right_idx=ids(TURN_TYPE, "R"),
    )


def sensory_mask(index) -> np.ndarray:
    return index["superclass"].isin(SENSORY_SUPERCLASSES).to_numpy()


def tick(matrix, activity: np.ndarray, readout: Readout, drive_idx: np.ndarray,
         n: int, gain: float, bias: float, alpha: float, drive_mean: float,
         drive_noise: float, rng: np.random.Generator) -> tuple[np.ndarray, str, dict]:
    """One leaky-rate update + decode. Factored out of `run()` so the F2 live
    server (server.py) ticks the exact same model instead of a reimplemented
    copy that could drift from the calibrated bench-spike behavior."""
    drive = np.zeros(n, dtype=np.float32)
    drive[drive_idx] = drive_mean + drive_noise * rng.standard_normal(len(drive_idx))
    x = np.clip(gain * (matrix @ activity) + drive - bias, -30.0, 30.0)
    fired = 1.0 / (1.0 + np.exp(-x))
    activity = (1 - alpha) * activity + alpha * fired
    state, signals = readout.decode(activity)
    return activity, state, signals


def run(seconds: float, hz: float, gain: float, bias: float, tau: float,
        drive_mean: float, drive_noise: float, seed: int, out_path: Path,
        quiet: bool) -> None:
    print("Loading connectome matrix ...")
    matrix, index = build_matrix.load()
    n = matrix.shape[0]
    readout = build_readout(index)
    print(f"Readout populations: forward={len(readout.forward_idx)} "
          f"backward={len(readout.backward_idx)} "
          f"turn_left={len(readout.turn_left_idx)} turn_right={len(readout.turn_right_idx)}")

    drive_idx = np.where(sensory_mask(index))[0]
    print(f"Sensory drive population: {len(drive_idx)} neurons")

    rng = np.random.default_rng(seed)
    activity = np.zeros(n, dtype=np.float32)
    dt = 1.0 / hz
    alpha = min(1.0, dt / tau)
    ticks = int(seconds * hz)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["tick", "t", "state", "forward", "backward", "left", "right", "turn"])
        print(f"Running {ticks} ticks at {hz:.1f} Hz "
              f"(gain={gain} bias={bias} tau={tau}s) -> {out_path}")
        start = time.time()
        prev_state = readout.state
        for tick_i in range(ticks):
            activity, state, signals = tick(matrix, activity, readout, drive_idx, n,
                                             gain, bias, alpha, drive_mean, drive_noise, rng)
            t = tick_i * dt
            writer.writerow([tick_i, f"{t:.3f}", state, *(f"{v:.4f}" for v in signals.values())])
            if not quiet and (tick_i == 0 or state != prev_state or tick_i % int(hz) == 0):
                print(f"t={t:6.2f}s  state={state:8s}  "
                      f"fwd={signals['forward']:.3f} bwd={signals['backward']:.3f} "
                      f"turn={signals['turn']:+.3f}")
            prev_state = state
        elapsed = time.time() - start
    print(f"Done: {ticks} ticks in {elapsed:.1f}s ({ticks / elapsed:.1f} Hz actual) -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=float, default=30.0, help="sim duration")
    parser.add_argument("--hz", type=float, default=10.0, help="tick rate (bench: ~34 Hz max on this CPU)")
    parser.add_argument("--gain", type=float, default=0.05, help="scales synaptic input into the sigmoid")
    parser.add_argument("--bias", type=float, default=2.0, help="baseline sigmoid offset (higher = quieter at rest)")
    parser.add_argument("--tau", type=float, default=0.05, help="rate time constant, seconds")
    parser.add_argument("--drive-mean", type=float, default=4.0, help="tonic drive into sensory neuropils")
    parser.add_argument("--drive-noise", type=float, default=1.0, help="stddev of per-tick drive noise")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=DATA_DIR / "sim_log.csv")
    parser.add_argument("--quiet", action="store_true", help="only print on command changes, not every second")
    args = parser.parse_args()
    run(args.seconds, args.hz, args.gain, args.bias, args.tau,
        args.drive_mean, args.drive_noise, args.seed, args.out, args.quiet)


if __name__ == "__main__":
    main()
