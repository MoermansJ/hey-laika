"""One-time export of YOLOv8-nano to ONNX for the adapter's eyes (eyes.py).

The adapter runs the model with onnxruntime, which faster-whisper already
brings into the image; only this export step needs ultralytics + torch, so
run it once on the PC, never inside the container:

    python -m venv .yolo && .yolo/Scripts/pip install ultralytics onnx
    .yolo/Scripts/python dog/tools/export_yolo.py            # -> dog/models/yolov8n.onnx

The default image size is 320: the satellite streams QVGA and a 320 px
model runs ~4x faster on a CPU than the 640 px default. EYES_MODEL in the
adapter's .env points elsewhere if the file is moved.
"""
import argparse
import shutil
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--weights", default="yolov8n.pt",
                        help="ultralytics weights (downloaded on first use)")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--out", default=str(MODELS_DIR / "yolov8n.onnx"))
    args = parser.parse_args()

    from ultralytics import YOLO

    exported = YOLO(args.weights).export(format="onnx", imgsz=args.imgsz,
                                         opset=12, simplify=True, dynamic=False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(exported), out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, imgsz={args.imgsz})")


if __name__ == "__main__":
    main()
