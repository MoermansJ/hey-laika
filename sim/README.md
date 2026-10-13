# sim — Bittle PyBullet visualization

A visual PyBullet simulation of the Bittle robot dog: load the URDF, run a
hand-written crawl gait, watch it walk. This is a separate concern from the
rest of `hey-laika` (which drives the real hardware) — nothing in here talks
to real motors, and nothing outside `sim/` should be touched for this to
work.

It's a rule-based-gait MVP, not RL. `bittle-simulation/` (the cloned repo
below) has `bittle_env.py` / `bittle_train.py` / `bittle_watch.py` for a
future reinforcement-learning phase, but those aren't set up or exercised
here — **not yet in scope**.

## Files

- `gait.py` — pure-math crawl-gait trajectory generator (numpy only, no
  PyBullet dependency). `PARAMS` and `LEGS` at the top are meant to be
  hand-edited; see "Tuning the gait" below.
- `bittle_walk.py` — main live demo. Opens a PyBullet GUI window, loads the
  URDF, runs `gait.py` in a real-time loop, colors the robot (orange body,
  cyan legs) and ground (green) for visibility, and auto-sizes the camera to
  the robot's bounding box so it stays in frame.
- `calibrate_gait.py` — headless (`p.DIRECT`, no window) ~10s sanity check:
  runs the gait both directions and prints end position + whether the robot
  fell over. Use this to test a `gait.py` parameter change quickly without
  watching the GUI.
- `verify_render.py` — one-off diagnostic that loads the URDF and saves a
  screenshot (`render_check.png`) via `getCameraImage`. Was used once to
  confirm the URDF loads with sane proportions; not needed for normal use.
- `bittle-simulation/` — **gitignored**, third-party clone (see setup
  below). Provides the URDF (`models/bittle_modified.urdf`, the one in use)
  and the upstream repo's own scripts: `bittle_manual.py` (slider-based
  manual joint control) plus the RL scripts mentioned above.
- `conda-env/` — **gitignored** local Python environment (Windows path
  only; see below). Not a named conda env — created with `conda create -p
  <path>` so it lives inside the project folder.

## Windows needs conda; Mac/Linux can use plain pip

`pybullet` has **no prebuilt Windows wheel on PyPI**, for any version
(checked 2.9.8 through 3.2.7 — PyPI only ships manylinux wheels for Windows).
A plain `pip install pybullet` on Windows tries to compile from source and
fails unless you have MSVC Build Tools installed.

The fix: install Miniconda (or Anaconda/Mambaforge) and create an env from
the **conda-forge** channel, which publishes prebuilt `pybullet` (currently
3.25) for win-64 across Python 3.8–3.12.

On **Mac and Linux**, PyPI *does* publish manylinux wheels for pybullet, so a
plain `venv` + `pip install -r requirements.txt` works fine — conda is a
Windows-specific workaround here, not a general requirement.

### Setup — Windows (conda)

```powershell
winget install --id Anaconda.Miniconda3 -e --accept-package-agreements --accept-source-agreements

# From sim/:
& "$env:USERPROFILE\miniconda3\Scripts\conda.exe" env create -f environment.yml -p .\conda-env

# Run scripts via the env's interpreter directly — no need to `conda activate`:
.\conda-env\python.exe bittle_walk.py
```

If you ever create the env by hand instead of from `environment.yml`, pass
`--override-channels -c conda-forge` explicitly — without it, conda
consults the default Anaconda channels and a non-interactive `conda create`
hangs on a Terms-of-Service prompt.

### Setup — Mac/Linux (pip)

```bash
cd sim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python bittle_walk.py
```

### Both platforms: get the URDF

```bash
cd sim
git clone https://github.com/jasonjabbour/bittle-simulation.git
```

## Running

- `bittle_walk.py` — the demo. Opens a GUI window; close it or Ctrl+C to
  stop.
- `calibrate_gait.py` — headless, prints results and exits after ~20s (both
  directions).
- `verify_render.py` — headless-ish diagnostic, writes `render_check.png`
  into `sim/` and exits.

All three expect `bittle-simulation/models/bittle_modified.urdf` to exist
relative to `sim/`, and are run with the env's own interpreter (conda's
`python.exe`, or the activated venv's `python`).

## Tuning the gait

Everything in `gait.PARAMS` is a plain number you edit and rerun — no
training involved:

- `frequency_hz` — full gait cycles per second.
- `stride_amplitude` — how far the shoulder swings forward/back (rad).
- `lift_amplitude` — how much the knee bends to lift the foot during swing
  (rad).
- `swing_fraction` — fraction of the cycle each leg spends swinging vs.
  planted.
- `direction` — `+1` forward, `-1` backward.

`LEGS` maps each leg to `(shoulder_idx, knee_idx, side_sign,
phase_offset)` — the phase offsets (0.00/0.25/0.50/0.75) stagger which leg
swings when, so only one leg is ever off the ground at a time (a crawl
gait, not a trot — three feet planted is more stable for an open-loop
controller with no balance feedback). Run `calibrate_gait.py` after any
change to sanity-check it before watching the full GUI demo.

## Moving to another machine

A plain `git pull`/`git clone` of `hey-laika` brings `gait.py`,
`bittle_walk.py`, `calibrate_gait.py`, `verify_render.py`, and this README —
nothing else in `sim/`. Two things are gitignored on purpose and need to be
redone on the new machine:

1. **Re-clone the URDF repo**: `cd sim && git clone
   https://github.com/jasonjabbour/bittle-simulation.git`
2. **Recreate the Python env**: Windows → `conda env create -f
   environment.yml -p .\conda-env`; Mac/Linux → `venv` + `pip install -r
   requirements.txt` (see Setup above). Python envs aren't portable as
   files, which is why they're gitignored instead of committed.
