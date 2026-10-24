"""Rule-based crawl gait for Bittle. No learning involved — every parameter
here is a number you can edit directly to change how the walk looks.

Joint order (from BittleManual.getJoints(), used throughout the sim scripts):
  0 left-back-shoulder   1 left-back-knee
  2 left-front-shoulder  3 left-front-knee
  4 right-back-shoulder  5 right-back-knee
  6 right-front-shoulder 7 right-front-knee

Crawl gait: only one leg lifts and swings forward at a time, while the other
three stay planted and sweep slowly backward together to push the body
forward. This keeps 3 feet on the ground at all times, which is far more
stable for an open-loop (no balance feedback) controller than a trot.
"""
import numpy as np

# --- Tunable rules -----------------------------------------------------
PARAMS = {
    "frequency_hz": 0.4,        # full gait cycles (all 4 legs) per second
    "stride_amplitude": 0.35,   # rad, how far the shoulder swings forward/back
    "lift_amplitude": 0.5,      # rad, how much the knee bends to lift the foot during swing
    "swing_fraction": 0.25,     # fraction of the cycle each leg spends swinging (vs. planted)
    "direction": 1,             # +1 forward, -1 backward (flip if it walks the wrong way)
}

# leg: (shoulder_idx, knee_idx, side_sign, phase_offset in [0,1))
# side_sign mirrors left/right (URDF is built symmetric about the center line)
# phase_offset staggers which leg swings when — only one leg swings at a time
LEGS = {
    "left_front":  (2, 3, +1, 0.00),
    "right_back":  (4, 5, -1, 0.25),
    "right_front": (6, 7, -1, 0.50),
    "left_back":   (0, 1, +1, 0.75),
}


def leg_targets(t, params=PARAMS):
    """Return an 8-element array of target joint angles (radians) at time t."""
    angles = np.zeros(8)
    swing_frac = params["swing_fraction"]
    cycle_pos = (t * params["frequency_hz"]) % 1.0  # leg order is fixed; direction reverses the sweep itself, below
    for shoulder_idx, knee_idx, side_sign, phase_offset in LEGS.values():
        phi = (cycle_pos + phase_offset) % 1.0
        if phi < swing_frac:
            # Swing phase: lift and sweep quickly (back -> front, or front -> back if direction is reversed)
            s = phi / swing_frac
            shoulder = -1.0 + 2.0 * s
            knee = np.sin(np.pi * s)
        else:
            # Stance phase: planted, sweep slowly the other way, pushing the body along
            s = (phi - swing_frac) / (1.0 - swing_frac)
            shoulder = 1.0 - 2.0 * s
            knee = 0.0
        angles[shoulder_idx] = side_sign * params["stride_amplitude"] * shoulder * params["direction"]
        angles[knee_idx] = side_sign * params["lift_amplitude"] * knee
    return angles
