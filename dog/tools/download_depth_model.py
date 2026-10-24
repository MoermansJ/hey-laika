"""One-time download of the Depth Anything V2 ONNX weights for the
reconstruction sidecar (dog/reconstruction/). No ML deps needed, just a
plain HTTPS fetch, same as download_kokoro.py:

    dog/reconstruction/.venv/Scripts/python dog/tools/download_depth_model.py
    ... --model base            # the bigger one, for quality comparisons
    ... --model small-fp16      # half the file, DirectML likes fp16

Pre-exported ONNX from onnx-community, so nothing here needs torch or
ultralytics (which is why there is no `export_depth.py` of the kind
STATIONARY_SENSING_BRIEF.md §3 imagined). Files land in dog/models/ beside
yolov8n.onnx and are gitignored; `model` in the sidecar's settings picks
between them by name.
"""
import argparse
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
HF = "https://huggingface.co/onnx-community"

ASSETS = {
    "small": ("depth-anything-v2-small.onnx",
              f"{HF}/depth-anything-v2-small/resolve/main/onnx/model.onnx"),
    "small-fp16": ("depth-anything-v2-small-fp16.onnx",
                   f"{HF}/depth-anything-v2-small/resolve/main/onnx/model_fp16.onnx"),
    "base": ("depth-anything-v2-base.onnx",
             f"{HF}/depth-anything-v2-base/resolve/main/onnx/model.onnx"),
    "base-fp16": ("depth-anything-v2-base-fp16.onnx",
                  f"{HF}/depth-anything-v2-base/resolve/main/onnx/model_fp16.onnx"),
}


def fetch(url: str, out: Path) -> None:
    if out.is_file():
        print(f"skip {out.name} (already present, {out.stat().st_size // 1024} KB)")
        return
    print(f"fetching {out.name} ...")
    tmp = out.with_suffix(out.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", nargs="+", default=["small"], dest="models",
                        choices=sorted(ASSETS),
                        help="one or more variants; defaults to small only")
    parser.add_argument("--out", default=str(MODELS_DIR))
    args = parser.parse_args()

    wanted = args.models
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in dict.fromkeys(wanted):
        filename, url = ASSETS[name]
        fetch(url, out_dir / filename)


if __name__ == "__main__":
    main()
