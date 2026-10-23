"""Settings for the reconstruction sidecar, in one place.

Everything the demo may want to tweak lives here with a default and a
clamp, because the tuning panel (phase 6) and the CLI (dog/tools/
depth_to_cloud.py) both set the same names. `resolve()` is total: it never
raises on a bad value, it clamps and reports, so a slider dragged to an
absurd place during a presentation cannot take the service down.

Scale note: monocular depth has no true scale, so `nearM`/`farM` are a
placeholder mapping that makes the cloud room-sized rather than correct.
Real scale arrives in phase 5, from the ultrasonic ranger and the
occupancy grid (orchestrator/docs/design/STATIONARY_SENSING_BRIEF.md §3
pins the beam-centre pixel to a measured range).
"""

MODELS = {
    # name -> file under dog/models/, fetched by dog/tools/download_depth_model.py
    "small": "depth-anything-v2-small.onnx",
    "small-fp16": "depth-anything-v2-small-fp16.onnx",
    "base": "depth-anything-v2-base.onnx",
    "base-fp16": "depth-anything-v2-base-fp16.onnx",
}

DEFAULTS = {
    "model": "small",           # MODELS key
    "confidenceCutoff": 0.05,   # drop the farthest fraction of the depth range
    "edgeReject": 0.10,         # drop pixels whose depth gradient exceeds this
    "pointDensity": 20000,      # max points kept after thinning (QVGA is 76800)
    "hfovDeg": 65.0,            # OV2640 horizontal field of view, uncalibrated
    "nearM": 0.4,               # placeholder scale: nearest point in the cloud
    "farM": 6.0,                # placeholder scale: farthest point in the cloud
    "captureIntervalS": 0.0,    # 0 = manual capture only; >0 arms the loop
}

LIMITS = {
    "confidenceCutoff": (0.0, 0.9),
    "edgeReject": (0.01, 1.0),
    "pointDensity": (500, 76800),
    "hfovDeg": (20.0, 140.0),
    "nearM": (0.05, 5.0),
    "farM": (0.5, 50.0),
    "captureIntervalS": (0.0, 60.0),
}


def resolve(overrides: dict | None = None) -> tuple[dict, list[str]]:
    """Merge overrides onto the defaults. Returns (settings, notes); notes
    names every value that was clamped or rejected."""
    settings = dict(DEFAULTS)
    notes: list[str] = []
    for key, value in (overrides or {}).items():
        if key not in DEFAULTS:
            notes.append(f"unknown setting {key!r} ignored")
            continue
        if key == "model":
            if value not in MODELS:
                notes.append(f"unknown model {value!r}, kept {settings['model']!r}")
            else:
                settings[key] = value
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            notes.append(f"{key}={value!r} is not a number, kept {settings[key]}")
            continue
        low, high = LIMITS[key]
        clamped = min(max(number, low), high)
        if clamped != number:
            notes.append(f"{key}={number} clamped to {clamped}")
        settings[key] = int(clamped) if key == "pointDensity" else clamped
    if settings["farM"] <= settings["nearM"]:
        settings["farM"] = settings["nearM"] + 0.5
        notes.append(f"farM must exceed nearM, raised to {settings['farM']}")
    return settings, notes
