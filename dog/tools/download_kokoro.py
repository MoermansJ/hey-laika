"""One-time download of the Kokoro-82M model files for the adapter's mouth
(mouth.py). No ML deps needed, just a plain HTTPS fetch; run it once on the
PC (or inside the container, but the files survive a rebuild better living
on disk already, same as yolov8n.onnx):

    dog/.venv/Scripts/python dog/tools/download_kokoro.py

Fetches the fp16 variant (164 MB, 0.999 spectral correlation against fp32)
plus the 28 MB voices file into dog/models/. KOKORO_MODEL_PATH /
KOKORO_VOICES_PATH in .env point elsewhere if the files are moved; their
absence is how default_tts() falls back to espeak-ng rather than failing.
"""
import argparse
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
ASSETS = {
    "kokoro-v1.0.fp16.onnx": f"{RELEASE}/kokoro-v1.0.fp16.onnx",
    "voices-v1.0.bin": f"{RELEASE}/voices-v1.0.bin",
}


def fetch(url: str, out: Path) -> None:
    if out.is_file():
        print(f"skip {out.name} (already present, {out.stat().st_size // 1024} KB)")
        return
    print(f"fetching {out.name} ...")
    tmp = out.with_suffix(out.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(MODELS_DIR))
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, url in ASSETS.items():
        fetch(url, out_dir / name)


if __name__ == "__main__":
    main()
