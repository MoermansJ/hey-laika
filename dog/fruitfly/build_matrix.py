"""Builds and caches the signed sparse connectivity matrix for the Fruitfly
bench spike (PERSONALITY_MODES_BRIEF.md F1, §6.1 point 1).

Neuron universe: bodies with status == "Traced" in the body-annotations
feather (`download.py`'s output) — 165,122 of them, matching the brief's
"166,700 neurons" figure closely. Restricting to this set, rather than every
body in the raw flat-connectome export (~1.8M once orphans/fragments/glia
are counted), also reproduces the brief's "25.6M synapses" figure almost
exactly (25,563,197 edges land inside this set once both endpoints are
required to be Traced) — strong confirmation this is the intended reading of
male-cns:v1.0, checked directly against the downloaded data rather than
assumed from the brief's numbers alone.

Sign convention (excitatory/inhibitory by presynaptic neurotransmitter,
matching the whole-brain leaky/rate literature the brief cites, e.g. Shiu et
al. 2024's connectome-constrained model): acetylcholine, dopamine, serotonin,
octopamine -> +1 (excitatory; the three aminergic neuromodulators are lumped
in as weakly excitatory here, a simplification and not a claim about their
real receptor pharmacology). gaba, glutamate, histamine -> -1 (inhibitory;
glutamate and histamine are inhibitory at most central Drosophila synapses,
unlike in vertebrates). Only 3,602 of the 165,122 traced neurons (2.2%) have
no confident neurotransmitter call ("unclear" or missing) and default to +1
— small enough not to dominate the network's overall balance.

W[post, pre] = sign(pre) * weight, so `W @ activity` in sim.py's update reads
as "each neuron's total signed synaptic input this tick."
"""
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.feather as feather
import scipy.sparse as sp

DATA_DIR = Path(__file__).parent / "data"
ANNOTATIONS = DATA_DIR / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
NEUROTRANSMITTERS = DATA_DIR / "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS = DATA_DIR / "connectome-weights-male-cns-v1.0-minconf-0.5.feather"

MATRIX_CACHE = DATA_DIR / "connectome_matrix.npz"
INDEX_CACHE = DATA_DIR / "neuron_index.feather"

INHIBITORY_NT = {"gaba", "glutamate", "histamine"}


def build(force: bool = False) -> tuple[sp.csr_matrix, pd.DataFrame]:
    if not force and MATRIX_CACHE.exists() and INDEX_CACHE.exists():
        print(f"Using cached matrix at {MATRIX_CACHE} (force=True to rebuild)")
        return load()
    for path in (ANNOTATIONS, NEUROTRANSMITTERS, WEIGHTS):
        if not path.exists():
            raise FileNotFoundError(f"{path} missing — run download.py first")

    print("Loading annotations ...")
    ann = feather.read_table(ANNOTATIONS, columns=[
        "bodyId", "status", "type", "superclass", "somaSide",
    ]).to_pandas()
    traced = ann[ann["status"] == "Traced"].reset_index(drop=True)
    n = len(traced)
    print(f"{n} traced neurons")

    print("Loading neurotransmitter predictions ...")
    nt = feather.read_table(NEUROTRANSMITTERS, columns=["body", "consensus_nt"]).to_pandas()
    nt_by_body = nt.drop_duplicates("body").set_index("body")["consensus_nt"]
    traced_nt = nt_by_body.reindex(traced["bodyId"]).fillna("unclear").to_numpy()
    sign_by_neuron = np.where(np.isin(traced_nt, list(INHIBITORY_NT)), -1.0, 1.0).astype(np.float32)

    print("Loading synapse weights ...")
    w = feather.read_table(WEIGHTS, columns=["body_pre", "body_post", "weight"]).to_pandas()

    # Vectorized bodyId -> neuron-index lookup via binary search: body ids run
    # past 1.5e9 (fragment/orphan bookkeeping ids), so a dense lookup table
    # would need gigabytes; a sorted-array searchsorted does it in ~n log n.
    sorted_order = np.argsort(traced["bodyId"].to_numpy())
    sorted_ids = traced["bodyId"].to_numpy()[sorted_order]

    def to_index(body_ids: np.ndarray) -> np.ndarray:
        pos = np.searchsorted(sorted_ids, body_ids)
        pos = np.clip(pos, 0, len(sorted_ids) - 1)
        found = sorted_ids[pos] == body_ids
        idx = np.where(found, sorted_order[pos], -1)
        return idx.astype(np.int32)

    pre_idx = to_index(w["body_pre"].to_numpy())
    post_idx = to_index(w["body_post"].to_numpy())
    keep = (pre_idx >= 0) & (post_idx >= 0)
    pre_idx, post_idx = pre_idx[keep], post_idx[keep]
    weight = w["weight"].to_numpy(dtype=np.float32)[keep]
    print(f"{len(weight)} edges among traced neurons (of {len(w)} total)")

    signed_weight = weight * sign_by_neuron[pre_idx]
    matrix = sp.csr_matrix((signed_weight, (post_idx, pre_idx)), shape=(n, n), dtype=np.float32)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sp.save_npz(MATRIX_CACHE, matrix)
    index = traced.copy()
    index["idx"] = np.arange(n, dtype=np.int32)
    index["nt"] = traced_nt
    feather.write_feather(index, INDEX_CACHE)
    print(f"Cached matrix {matrix.shape}, {matrix.nnz} nonzeros -> {MATRIX_CACHE}")
    print(f"Cached neuron index -> {INDEX_CACHE}")
    return matrix, index


def load() -> tuple[sp.csr_matrix, pd.DataFrame]:
    if not MATRIX_CACHE.exists() or not INDEX_CACHE.exists():
        raise FileNotFoundError("no cached matrix — call build() or run this script first")
    matrix = sp.load_npz(MATRIX_CACHE)
    index = feather.read_feather(INDEX_CACHE)
    return matrix, index


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild even if a cache exists")
    args = parser.parse_args()
    start = time.time()
    build(force=args.force)
    print(f"Done in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
