"""Disparity -> a thinned, coloured point cloud in the camera's frame.

Frame convention: +x right, +y up, +z forward (away from the lens), metres,
origin at the lens. The viewer rotates this into the room; nothing here
knows about Laika's pose, because phase 1 captures one frame at a time and
phase 4 is where poses start to matter.

Three things happen between a depth map and a cloud:

- **Scale.** The model's disparity is relative, so it is normalised over a
  robust percentile range and mapped linearly onto [nearM, farM]. That
  makes the cloud room-shaped, not room-sized; real scale comes from the
  ranger and the grid in phase 5.
- **Confidence.** Depth Anything emits no confidence channel, so the
  `confidenceCutoff` setting stands in for one: the farthest slice of the
  depth range is dropped (sky, windows, the end of a corridor, where
  monocular depth is least trustworthy), and pixels on a steep depth
  gradient are dropped too, because that is where a depth map bleeds one
  surface into another and sprays points through empty space.
- **Density.** QVGA is 76,800 points. `pointDensity` thins to a budget
  before anything is written or sent, deterministically (seeded), so the
  validation script sees the same cloud twice.
"""
import math
import struct
from pathlib import Path

import numpy as np


def intrinsics(width: int, height: int, hfov_deg: float) -> tuple[float, float, float, float]:
    """(fx, fy, cx, cy) for a pinhole camera with square pixels."""
    fx = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    return fx, fx, width / 2.0, height / 2.0


def normalise(disparity: np.ndarray) -> np.ndarray:
    """Disparity onto [0, 1] over a robust range; 1 = nearest."""
    low, high = np.percentile(disparity, [0.5, 99.5])
    if high - low < 1e-6:
        return np.zeros_like(disparity, dtype=np.float32)
    return np.clip((disparity - low) / (high - low), 0.0, 1.0).astype(np.float32)


def valid_mask(norm: np.ndarray, confidence_cutoff: float,
               edge_reject: float) -> np.ndarray:
    """Pixels worth turning into points: near enough to be trusted, and not
    sitting on a depth cliff."""
    keep = norm >= confidence_cutoff
    gy, gx = np.gradient(norm)
    gradient = np.hypot(gx, gy)
    return keep & (gradient <= edge_reject)


def to_points(disparity: np.ndarray, rgb: np.ndarray, settings: dict,
              seed: int = 0) -> tuple[np.ndarray, np.ndarray, dict]:
    """(xyz Nx3 float32 metres, rgb Nx3 uint8, stats). See the module docstring."""
    height, width = disparity.shape
    norm = normalise(disparity)
    mask = valid_mask(norm, settings["confidenceCutoff"], settings["edgeReject"])

    near, far = float(settings["nearM"]), float(settings["farM"])
    depth = far - norm * (far - near)               # high disparity = near

    fx, fy, cx, cy = intrinsics(width, height, settings["hfovDeg"])
    us, vs = np.meshgrid(np.arange(width, dtype=np.float32),
                         np.arange(height, dtype=np.float32))
    z = depth[mask]
    x = (us[mask] - cx) * z / fx
    y = -(vs[mask] - cy) * z / fy                   # image rows go down, y goes up

    xyz = np.stack([x, y, z], axis=1).astype(np.float32)
    colours = rgb[mask].astype(np.uint8)
    kept_before_thinning = int(xyz.shape[0])
    xyz, colours = thin(xyz, colours, int(settings["pointDensity"]), seed=seed)

    stats = {
        "pixels": int(height * width),
        "keptAfterConfidence": kept_before_thinning,
        "points": int(xyz.shape[0]),
        "rejectedPct": round(100.0 * (1.0 - kept_before_thinning / (height * width)), 1),
        "depthM": {"min": _round(z.min()), "max": _round(z.max()),
                   "mean": _round(z.mean())} if z.size else None,
        "extentM": _extent(xyz),
    }
    return xyz, colours, stats


def thin(xyz: np.ndarray, colours: np.ndarray, budget: int,
         seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Random subsample to `budget` points, deterministic for a given seed."""
    if xyz.shape[0] <= budget:
        return xyz, colours
    picked = np.random.default_rng(seed).choice(xyz.shape[0], size=budget,
                                                replace=False)
    picked.sort()
    return xyz[picked], colours[picked]


def write_ply(path: str | Path, xyz: np.ndarray, colours: np.ndarray) -> Path:
    """Binary little-endian PLY, the format every mesh viewer opens."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {xyz.shape[0]}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    with out.open("wb") as handle:
        handle.write(header)
        for (x, y, z), (r, g, b) in zip(xyz, colours):
            handle.write(struct.pack("<fffBBB", x, y, z, int(r), int(g), int(b)))
    return out


def to_binary_frame(xyz: np.ndarray, colours: np.ndarray) -> bytes:
    """The wire format for the viewer's websocket: a 16-byte header
    (magic 'FLYC', uint32 point count, uint32 stride bytes, uint32 reserved)
    followed by interleaved float32 x, y, z and uint8 r, g, b per point.

    Binary, not JSON: 20,000 points is 320 KB here against ~1.5 MB of JSON,
    and the browser hands the buffer straight to a BufferGeometry.
    """
    count = int(xyz.shape[0])
    header = struct.pack("<4sIII", b"FLYC", count, 15, 0)
    body = np.empty((count, 15), dtype=np.uint8)
    body[:, :12] = xyz.astype("<f4").view(np.uint8).reshape(count, 12)
    body[:, 12:] = colours.astype(np.uint8)
    return header + body.tobytes()


def write_preview(path: str | Path, rgb: np.ndarray,
                  disparity: np.ndarray) -> Path:
    """Frame beside its depth map as one PNG, so a human (or an agent with
    an image reader) can see whether the depth is sane at all."""
    from PIL import Image

    norm = normalise(disparity)
    coloured = _colourise(norm)
    side_by_side = np.concatenate([rgb, coloured], axis=1)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(side_by_side).save(out)
    return out


def _colourise(norm: np.ndarray) -> np.ndarray:
    """Near = warm, far = dark blue. A three-stop ramp, no matplotlib."""
    stops = np.array([[12, 18, 60], [40, 130, 160], [255, 235, 120]],
                     dtype=np.float32)
    position = np.clip(norm, 0.0, 1.0) * (len(stops) - 1)
    low = np.floor(position).astype(int)
    high = np.minimum(low + 1, len(stops) - 1)
    blend = (position - low)[..., None]
    return (stops[low] * (1 - blend) + stops[high] * blend).astype(np.uint8)


def _extent(xyz: np.ndarray) -> dict | None:
    if xyz.size == 0:
        return None
    low = xyz.min(axis=0)
    high = xyz.max(axis=0)
    return {"x": [_round(low[0]), _round(high[0])],
            "y": [_round(low[1]), _round(high[1])],
            "z": [_round(low[2]), _round(high[2])]}


def _round(value) -> float:
    return round(float(value), 2)
