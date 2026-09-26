"""One cheap call to confirm NEUPRINT_TOKEN actually authenticates against
the neuPrint API, before F2 leans on it to look up descending-neuron cell
types. Not needed for download.py (the feather files are public)."""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

SERVER = "https://neuprint.janelia.org"
DATASET = "male-cns:v1.0"


def main() -> int:
    token = os.getenv("NEUPRINT_TOKEN")
    if not token:
        print("NEUPRINT_TOKEN is not set in dog/.env")
        return 1

    from neuprint import Client

    try:
        client = Client(SERVER, dataset=DATASET, token=token)
        version = client.fetch_version()
        print(f"OK: authenticated against {SERVER} ({DATASET}), server version {version}")
        return 0
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        print("Grab the actual 'Auth Token' field from your neuPrint account "
              "page (https://neuprint.janelia.org, click your name) and retry.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
