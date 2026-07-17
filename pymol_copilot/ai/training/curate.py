# curate.py
"""
GPU-accelerated exact + fuzzy deduplication with NeMo Curator, run AFTER
build_conversations.py has produced valid, schema-checked ChatML rows.

Fixes vs. the original draft:
  - id_field is now the unique `id` (UUID) column, not `pdb_id`. pdb_id
    repeats by construction (it's a sampled category), so using it as the
    dedup identifier will incorrectly collapse distinct, legitimate rows.
  - Fuzzy (MinHash/LSH) dedup is actually implemented, not just mentioned.
    Free-tier LLMs paraphrase the same handful of scenarios; exact-match
    dedup alone will miss most of the near-duplicates.
  - Adds a simple train/val split at the end -- the original pipeline had
    no output usable directly for an SFT run.
  - Notes a CPU fallback: for a few thousand short rows, spinning up a
    LocalCUDACluster is a lot of infrastructure. If you don't have a GPU
    box handy, backend="pandas" instead of "cudf" works with the same
    NeMo Curator API (just slower), so this step doesn't hard-require GPU
    access for a dataset this small.
  - For 100 k-scale runs the fuzzy-dedup cache and cluster parameters
    must be tuned; see the inline comments below.
"""
from __future__ import annotations

import json
import pathlib
import random

import dask_cuda
import distributed
import nemo_curator
from nemo_curator import datasets as nc_datasets

RAW_PATH = "output_raw/cbiomol_pymol_sft_conversations.jsonl"
CLEAN_DIR = "output_clean/"
TRAIN_PATH = "output_clean/train.jsonl"
VAL_PATH = "output_clean/val.jsonl"
VAL_FRACTION = 0.05


def run_gpu_sanitization_pipeline(use_gpu: bool = True) -> None:
    """Run the full deduplication and train/val split pipeline.

    Performs exact deduplication first (cheap), then fuzzy MinHash/LSH
    deduplication (catches near-paraphrases from free-tier LLMs), writes
    the curated dataset, and splits it into train and val sets.

    At 100 k-scale: use a multi-GPU LocalCUDACluster (n_workers= number
    of GPUs) and increase num_buckets/hashes_per_bucket to tighten the
    LSH band threshold.  The write step should also switch from
    ``to_json`` to ``to_parquet`` for better I/O throughput.

    Args:
      use_gpu: If True, use cudf backend on a LocalCUDACluster.
        If False, use pandas backend for CPU-only deduplication
        (slower but functional without a GPU).
    """
    tmp_backend = "cudf" if use_gpu else "pandas"

    if use_gpu:
        tmp_cluster = dask_cuda.LocalCUDACluster()
        # The client must stay alive for the entire Dask computation graph.
        _client = distributed.Client(tmp_cluster)  # noqa: F841

    print(f"Ingesting {RAW_PATH} with backend={tmp_backend}...")
    tmp_dataset = nc_datasets.DocumentDataset.read_json(
        RAW_PATH, backend=tmp_backend
    )

    # 1. Exact dedup first (cheap) -- catches literal repeats.
    # NOTE: text_field points at `dedup_text` (the flat user-query string),
    # not `conversations` (a list of role/content dicts) -- NeMo Curator's
    # hashing expects a plain string column.
    print("Running exact deduplication...")
    tmp_exact_dup = nemo_curator.ExactDuplicates(
        id_field="id", text_field="dedup_text"
    )
    tmp_exact_dup_ids = tmp_exact_dup.identify_duplicates(tmp_dataset)
    tmp_dataset = tmp_exact_dup.remove(tmp_dataset, tmp_exact_dup_ids)

    # 2. Fuzzy (MinHash + LSH) dedup -- catches near-paraphrases, which is
    #    the dominant failure mode with small free-tier models re-sampling
    #    a limited scenario space.
    #    At 100 k scale: raise num_buckets to 40 and hashes_per_bucket to
    #    20 to reduce false-positive rate; the cache_dir should be on fast
    #    NVMe storage.
    print("Running fuzzy deduplication...")
    tmp_fuzzy_config = nemo_curator.FuzzyDuplicatesConfig(
        cache_dir="./fuzzy_dedup_cache",
        id_field="id",
        text_field="dedup_text",
        seed=42,
        char_ngrams=24,
        num_buckets=20,
        hashes_per_bucket=13,
        perform_removal=True,
    )
    tmp_fuzzy_dup = nemo_curator.FuzzyDuplicates(
        config=tmp_fuzzy_config, logger="./"
    )
    tmp_dataset = tmp_fuzzy_dup(tmp_dataset)

    # 3. Write curated output, then split train/val.
    print(f"Writing curated dataset to {CLEAN_DIR}...")
    tmp_dataset.to_json(CLEAN_DIR, write_header=True)

    _split_train_val()


def _split_train_val() -> None:
    """Split the curated JSONL output into train and val sets.

    Reads all JSONL/JSON files from CLEAN_DIR, drops the ``dedup_text``
    field (needed only for NeMo Curator, not for SFT data loaders),
    shuffles with a fixed seed for reproducibility, and writes
    TRAIN_PATH and VAL_PATH.
    """
    tmp_clean = pathlib.Path(CLEAN_DIR)
    tmp_rows: list[dict] = []
    for tmp_path in list(tmp_clean.glob("*.jsonl")) + list(
        tmp_clean.glob("*.json")
    ):
        with open(tmp_path, "r", encoding="utf-8") as tmp_fh:
            tmp_rows.extend(
                json.loads(tmp_line)
                for tmp_line in tmp_fh
                if tmp_line.strip()
            )

    # dedup_text was only needed for the dedup step above; drop it here so
    # it doesn't leak into the SFT data loader.
    for tmp_row in tmp_rows:
        tmp_row.pop("dedup_text", None)

    random.Random(42).shuffle(tmp_rows)
    tmp_n_val = max(1, int(len(tmp_rows) * VAL_FRACTION))
    tmp_val_rows = tmp_rows[:tmp_n_val]
    tmp_train_rows = tmp_rows[tmp_n_val:]

    with open(TRAIN_PATH, "w", encoding="utf-8") as tmp_fh:
        for tmp_row in tmp_train_rows:
            tmp_fh.write(json.dumps(tmp_row, ensure_ascii=False) + "\n")
    with open(VAL_PATH, "w", encoding="utf-8") as tmp_fh:
        for tmp_row in tmp_val_rows:
            tmp_fh.write(json.dumps(tmp_row, ensure_ascii=False) + "\n")

    print(
        f"Final split: {len(tmp_train_rows)} train / "
        f"{len(tmp_val_rows)} val -> {TRAIN_PATH}, {VAL_PATH}"
    )


if __name__ == "__main__":
    run_gpu_sanitization_pipeline(use_gpu=True)
