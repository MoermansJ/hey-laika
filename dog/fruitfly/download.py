"""Pulls the minimal MaleCNS v1.0 connectome subset needed for the Fruitfly
bench spike (PERSONALITY_MODES_BRIEF.md F1): neuron-to-neuron connectivity
weights, cell-type annotations, and predicted neurotransmitters. These are
public objects in Janelia's flyem-male-cns GCS bucket — no auth needed,
unlike the neuPrint API itself.

Skips a file whose local size already matches the server's Content-Length,
so a rerun after an interrupted download only resumes what's missing (not
byte-range resumed, just skip-if-complete).
"""
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
FILES = [
    "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
    "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "body-neurotransmitters-male-cns-v1.0.feather",
]
DATA_DIR = Path(__file__).parent / "data"


def remote_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req) as resp:
        return int(resp.headers["Content-Length"])


def download(name: str) -> int:
    url = f"{BASE}/{name}"
    dest = DATA_DIR / name
    size = remote_size(url)
    if dest.exists() and dest.stat().st_size == size:
        print(f"{name}: already present ({size / 1e6:.1f} MB), skipping")
        return size

    print(f"{name}: downloading {size / 1e6:.1f} MB ...")
    start = time.time()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as out:
        downloaded = 0
        chunk = resp.read(1024 * 1024)
        while chunk:
            out.write(chunk)
            downloaded += len(chunk)
            print(f"\r  {downloaded / 1e6:8.1f} / {size / 1e6:.1f} MB", end="", flush=True)
            chunk = resp.read(1024 * 1024)
    print()
    tmp.rename(dest)
    elapsed = time.time() - start
    print(f"{name}: done in {elapsed:.1f}s ({size / 1e6 / max(elapsed, 0.01):.1f} MB/s)")
    return size


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in FILES:
        total += download(name)
    print(f"\nTotal on disk: {total / 1e9:.3f} GB in {DATA_DIR}")
    return total


if __name__ == "__main__":
    main()
