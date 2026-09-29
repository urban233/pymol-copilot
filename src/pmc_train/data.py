# Copyright 2026 PyMOL Copilot contributors.
"""Read the training set, and only the training set, and fix its order.

Training reads `train.jsonl` of the frozen split (item 15), after its
manifest's every hash has been recomputed. The held-out files are opened
only to read their ids, to prove none of their samples or structures is
in the training set: the split is by source structure, and a leak would
make the held-out comparison meaningless.

The order samples are visited in is explicit: one seeded permutation
per epoch, concatenated. The trainer visits that list sequentially, so
the run's order is a function of `data_seed` alone and is recorded as a
digest in the run manifest.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib
import json
import random
from pathlib import Path

from pmc_data.manifest import validate_manifest
from pmc_data.sample import Sample
from pmc_data.sample import read_samples

#: The one split file training reads samples from.
TRAIN_FILE = "train.jsonl"

#: The split files whose ids training must never share.
HELD_OUT_FILES = ("test_gold.jsonl", "heldout_synthetic.jsonl")


class SplitError(ValueError):
    """The split is not the configured one, or it leaks into training."""


def _held_out_ids(split_dir: Path) -> tuple[set[str], set[str]]:
    """Read the held-out files' sample ids and structure ids only.

    Args:
        split_dir: The split directory.

    Returns:
        The held-out sample ids and structure spec ids.
    """
    samples: set[str] = set()
    specs: set[str] = set()
    for name in HELD_OUT_FILES:
        for line in (split_dir / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                samples.add(row["sample_id"])
                specs.add(row["structure"]["spec_id"])
    return samples, specs


def load_train(split_dir: Path, split_id: str) -> tuple[Sample, ...]:
    """Read the configured split's training samples.

    Args:
        split_dir: The split directory.
        split_id: The id its manifest must carry.

    Returns:
        The training samples, in file order.

    Raises:
        SplitError: If the manifest names another split, or a training
            sample or structure is also held out.
    """
    manifest = validate_manifest(split_dir)
    if manifest["split_id"] != split_id:
        raise SplitError(
            f"{split_dir} is split {manifest['split_id']}, not {split_id}"
        )
    samples = read_samples(split_dir / TRAIN_FILE)
    held_samples, held_specs = _held_out_ids(split_dir)
    leaked = sorted(
        sample.sample_id
        for sample in samples
        if sample.sample_id in held_samples
        or sample.structure.spec_id in held_specs
    )
    if leaked:
        raise SplitError(
            f"held-out samples or structures in training: {leaked}"
        )
    return samples


def visit_order(count: int, data_seed: int, epochs: int) -> tuple[int, ...]:
    """Fix the order every sample is visited in, over every epoch.

    Args:
        count: The number of samples.
        data_seed: The seed.
        epochs: The number of passes.

    Returns:
        Sample indices: one seeded permutation per epoch, concatenated.
    """
    generator = random.Random(data_seed)
    order: list[int] = []
    for _ in range(epochs):
        epoch = list(range(count))
        generator.shuffle(epoch)
        order.extend(epoch)
    return tuple(order)


def order_digest(sample_ids: list[str]) -> str:
    """Digest a visiting order, for the run manifest.

    Args:
        sample_ids: The sample ids, in the order visited.

    Returns:
        The hex SHA-256 of the ids, one per line.
    """
    text = "".join(f"{sample_id}\n" for sample_id in sample_ids)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
