# Copyright 2026 PyMOL Copilot contributors.
"""Training reads only the verified training set, in a seeded order."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import shutil
from pathlib import Path

import pytest

import pmc_train.data as data
from pmc_data.manifest import InvalidManifestError
from pmc_train.config import TrainConfig
from pmc_train.data import SplitError
from pmc_train.data import load_train
from pmc_train.data import order_digest
from pmc_train.data import visit_order

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def split_dir(config: TrainConfig) -> Path:
    """The committed split directory.

    Args:
        config: The committed training config.

    Returns:
        Its path.
    """
    return ROOT / config.split.dir


def test_loads_the_training_set(split_dir: Path, config: TrainConfig) -> None:
    """The configured split yields its 2,389 training samples."""
    samples = load_train(split_dir, config.split.split_id)
    assert len(samples) == 2389
    assert all(sample.plan_pml.endswith("\n") for sample in samples)


def test_only_the_training_file_is_read_as_samples(
    split_dir: Path, config: TrainConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No held-out file is ever decoded into samples."""
    read: list[str] = []
    original = data.read_samples

    def spy(path: Path) -> object:
        read.append(path.name)
        return original(path)

    monkeypatch.setattr(data, "read_samples", spy)
    load_train(split_dir, config.split.split_id)
    assert read == ["train.jsonl"]


def test_another_split_id_is_refused(
    split_dir: Path, config: TrainConfig
) -> None:
    """A split directory holding another split is refused."""
    del config
    with pytest.raises(SplitError, match="not f6c24e0f8463359c"):
        load_train(split_dir, "f6c24e0f8463359c")


def _copy(split_dir: Path, tmp_path: Path) -> Path:
    """Copy the split so a test may tamper with it.

    Args:
        split_dir: The committed split.
        tmp_path: A scratch directory.

    Returns:
        The copy's directory.
    """
    copy = tmp_path / split_dir.name
    shutil.copytree(split_dir, copy)
    return copy


def test_a_tampered_training_file_is_refused(
    split_dir: Path, config: TrainConfig, tmp_path: Path
) -> None:
    """Changing one byte of train.jsonl fails the manifest check."""
    copy = _copy(split_dir, tmp_path)
    train = copy / "train.jsonl"
    train.write_bytes(train.read_bytes().replace(b"chain A", b"chain B", 1))
    with pytest.raises(InvalidManifestError):
        load_train(copy, config.split.split_id)


def test_a_held_out_leak_is_refused(
    split_dir: Path, config: TrainConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A training sample whose id is held out stops the load."""
    samples = data.read_samples(split_dir / "train.jsonl")
    first = json.loads(
        (split_dir / "test_gold.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )

    def leaky_ids(directory: Path) -> tuple[set[str], set[str]]:
        del directory
        return {samples[0].sample_id}, {first["structure"]["spec_id"]}

    monkeypatch.setattr(data, "_held_out_ids", leaky_ids)
    with pytest.raises(SplitError, match=samples[0].sample_id):
        load_train(split_dir, config.split.split_id)


def test_held_out_structures_are_disjoint_from_training(
    split_dir: Path, config: TrainConfig
) -> None:
    """The real split holds out whole structures."""
    samples = load_train(split_dir, config.split.split_id)
    _, held_specs = data._held_out_ids(split_dir)
    assert held_specs
    assert not held_specs & {sample.structure.spec_id for sample in samples}


def test_visit_order_is_seeded_and_covers_every_epoch() -> None:
    """Each epoch is a permutation; the seed alone fixes the order."""
    order = visit_order(10, 7, 2)
    assert sorted(order[:10]) == list(range(10))
    assert sorted(order[10:]) == list(range(10))
    assert order[:10] != order[10:]
    assert order == visit_order(10, 7, 2)
    assert order != visit_order(10, 8, 2)


def test_order_digest_depends_on_order() -> None:
    """The recorded digest changes when the order does."""
    assert order_digest(["a", "b"]) != order_digest(["b", "a"])
    assert order_digest(["a", "b"]) == order_digest(["a", "b"])
