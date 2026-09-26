"""Unit tests for sim.py's readout logic — the part worth pinning down with
tests, since it has no dependency on the (huge, environment-specific,
gitignored) downloaded connectome. Everything else in this package is I/O
scripts (download/build/run) better exercised by actually running them."""
import numpy as np
import pandas as pd

from sim import Readout, build_readout, sensory_mask


def make_index() -> pd.DataFrame:
    return pd.DataFrame({
        "idx": [0, 1, 2, 3, 4, 5, 6, 7],
        "type": ["DNp09", "DNp09", "MDN", "MDN", "DNa02", "DNa02", "other", "other"],
        "somaSide": ["L", "R", "L", "R", "L", "R", "L", "R"],
        "superclass": ["descending_neuron", "descending_neuron", "descending_neuron",
                        "descending_neuron", "descending_neuron", "descending_neuron",
                        "ol_sensory", "vnc_sensory"],
    })


def test_build_readout_selects_expected_populations():
    readout = build_readout(make_index())
    assert sorted(readout.forward_idx.tolist()) == [0, 1]
    assert sorted(readout.backward_idx.tolist()) == [2, 3]
    assert readout.turn_left_idx.tolist() == [4]
    assert readout.turn_right_idx.tolist() == [5]


def test_sensory_mask_matches_superclass():
    mask = sensory_mask(make_index())
    assert mask.tolist() == [False, False, False, False, False, False, True, True]


def _readout() -> Readout:
    return Readout(forward_idx=np.array([0]), backward_idx=np.array([1]),
                    turn_left_idx=np.array([2]), turn_right_idx=np.array([3]))


def test_decode_stays_stopped_below_threshold():
    r = _readout()
    activity = np.array([0.1, 0.1, 0.1, 0.1])
    state, signals = r.decode(activity)
    assert state == "STOP"
    assert signals["forward"] == 0.1


def test_decode_forward_when_above_enter_threshold():
    r = _readout()
    state, _ = r.decode(np.array([0.9, 0.0, 0.0, 0.0]))
    assert state == "FORWARD"


def test_decode_hysteresis_holds_between_enter_and_exit():
    r = _readout()
    r.decode(np.array([0.9, 0.0, 0.0, 0.0]))  # enters FORWARD
    state, _ = r.decode(np.array([0.4, 0.0, 0.0, 0.0]))  # between exit (0.3) and enter (0.5)
    assert state == "FORWARD"


def test_decode_drops_below_exit_threshold():
    r = _readout()
    r.decode(np.array([0.9, 0.0, 0.0, 0.0]))  # enters FORWARD
    state, _ = r.decode(np.array([0.2, 0.0, 0.0, 0.0]))  # below exit (0.3)
    assert state == "STOP"


def test_decode_backward_wins_over_forward():
    r = _readout()
    state, _ = r.decode(np.array([0.9, 0.9, 0.0, 0.0]))
    assert state == "BACKWARD"


def test_decode_turn_direction_from_sign():
    r = _readout()
    state, signals = r.decode(np.array([0.0, 0.0, 0.0, 0.5]))  # right - left = 0.5
    assert state == "RIGHT"
    assert signals["turn"] == 0.5

    r2 = _readout()
    state2, signals2 = r2.decode(np.array([0.0, 0.0, 0.5, 0.0]))  # left - right = -0.5
    assert state2 == "LEFT"
    assert signals2["turn"] == -0.5
