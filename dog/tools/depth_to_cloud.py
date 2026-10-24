"""Step 1a of the Fly View brief: one frame in, one point cloud out.

The proof that the vendor model works on this hardware and on this camera,
run before any service exists (FLY_VIEW_BRIEF.md §Phase 1). It is a thin
CLI over dog/reconstruction/, so the sidecar later runs the same code path
rather than a second copy of it.

    # once: the environment and the weights
    python -m venv dog/reconstruction/.venv
    dog/reconstruction/.venv/Scripts/pip install -r dog/reconstruction/requirements.txt
    dog/reconstruction/.venv/Scripts/python dog/tools/download_depth_model.py

    # a saved frame
    dog/reconstruction/.venv/Scripts/python dog/tools/depth_to_cloud.py \
        --image dog/tests/fixtures/person.jpg --preview

    # a live frame from the dog, through the adapter's cache
    ... depth_to_cloud.py --from-url http://localhost:8080 --robot-id bittle-1

Writes a binary PLY (any mesh viewer opens it), optionally a side-by-side
PNG of the frame and its depth map, and prints the provider, the timings
and the cloud's statistics as JSON.
"""
import argparse
import json
import sys
import time
from pathlib import Path

DOG_DIR = Path(__file__).resolve().parent.parent
if str(DOG_DIR) not in sys.path:
    sys.path.insert(0, str(DOG_DIR))

from reconstruction import cloud, depth, fixtures, frames, settings as settings_module  # noqa: E402

OUT_DIR = DOG_DIR / "reconstruction" / "out"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--image", help="a saved JPEG")
    source.add_argument("--from-url", dest="from_url",
                        help="orchestrator or adapter base URL; pulls "
                             "/api/robots/<id>/eyes/snap?fresh=1")
    source.add_argument("--fixture", choices=["person", "room"],
                        help="a built-in frame (default: person)")
    parser.add_argument("--robot-id", default=frames.DEFAULTS["robotId"])
    parser.add_argument("--out", default=str(OUT_DIR / "cloud.ply"))
    parser.add_argument("--preview", action="store_true",
                        help="also write <out>.preview.png")
    parser.add_argument("--cpu", action="store_true",
                        help="force CPUExecutionProvider")
    parser.add_argument("--model", default=settings_module.DEFAULTS["model"],
                        choices=sorted(settings_module.MODELS))
    parser.add_argument("--density", type=int,
                        default=settings_module.DEFAULTS["pointDensity"])
    parser.add_argument("--confidence", type=float,
                        default=settings_module.DEFAULTS["confidenceCutoff"])
    parser.add_argument("--edge-reject", type=float, dest="edge_reject",
                        default=settings_module.DEFAULTS["edgeReject"])
    parser.add_argument("--hfov", type=float,
                        default=settings_module.DEFAULTS["hfovDeg"])
    parser.add_argument("--near", type=float,
                        default=settings_module.DEFAULTS["nearM"])
    parser.add_argument("--far", type=float,
                        default=settings_module.DEFAULTS["farM"])
    return parser.parse_args()


def load_frame(args: argparse.Namespace) -> tuple[bytes, str]:
    if args.image:
        return frames.from_file(args.image), args.image
    if args.from_url:
        source = frames.FrameSource({"baseUrl": args.from_url,
                                     "robotId": args.robot_id})
        return source.fetch(fresh=True), source.snap_url
    if args.fixture == "room":
        return fixtures.synthetic_room(), "fixture:room"
    return fixtures.person_frame(), f"fixture:person ({fixtures.PERSON_JPG.name})"


def main() -> int:
    args = parse_args()
    resolved, notes = settings_module.resolve({
        "model": args.model, "pointDensity": args.density,
        "confidenceCutoff": args.confidence, "edgeReject": args.edge_reject,
        "hfovDeg": args.hfov, "nearM": args.near, "farM": args.far,
    })
    for note in notes:
        print(f"note: {note}", file=sys.stderr)

    jpeg, origin = load_frame(args)
    model = depth.build_model(resolved["model"],
                              providers=["CPUExecutionProvider"] if args.cpu else None)
    started = time.time()
    disparity, rgb = model.infer(jpeg)
    points, colours, stats = cloud.to_points(disparity, rgb, resolved)

    out = cloud.write_ply(args.out, points, colours)
    report = {
        "frame": {"source": origin, "bytes": len(jpeg),
                  "size": [int(rgb.shape[1]), int(rgb.shape[0])]},
        "model": {"name": resolved["model"], "file": model.model_name,
                  "provider": model.provider,
                  "inferenceMs": model.stats["inferenceMs"]},
        "cloud": stats,
        "settings": resolved,
        "wroteMs": round((time.time() - started) * 1000.0, 1),
        "out": str(out),
    }
    if args.preview:
        report["preview"] = str(cloud.write_preview(
            Path(args.out).with_suffix(".preview.png"), rgb, disparity))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
