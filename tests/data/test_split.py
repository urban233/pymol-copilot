# Copyright 2026 PyMOL Copilot contributors.
"""The held-out split is balanced, real, disjoint and frozen.

Four failure modes, one test each. A feature on only one side changes
what the split measures. A held-out name that no longer exists in the
structure matrix silently empties the test side. Two specs that build
the same structure under different names would put one structure on
both sides. And an edited held-out set without a version bump would
change the test split after inspection began.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib

import pytest

from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.split import ALL_FEATURES
from pmc_data.split import HELD_OUT_SPEC_IDS
from pmc_data.split import SIDE_TEST
from pmc_data.split import SIDE_TRAIN
from pmc_data.split import SPLIT_VERSION
from pmc_data.split import features_of
from pmc_data.split import side_of
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

#: The corpus seed, from configs/generation/corpus.json.
SEED = 20260921

SPECS = enumerate_structures(SEED)


def test_every_feature_is_on_both_sides() -> None:
    """Each structural feature has a training spec and a test spec."""
    train: set[str] = set()
    test: set[str] = set()
    for spec in SPECS:
        side = test if side_of(spec.spec_id) == SIDE_TEST else train
        side.update(features_of(spec))

    assert train == ALL_FEATURES
    assert test == ALL_FEATURES


def test_held_out_ids_exist_in_the_matrix() -> None:
    """A renamed spec must not silently drop out of the test side."""
    matrix = {spec.spec_id for spec in SPECS}

    assert matrix >= HELD_OUT_SPEC_IDS


def test_both_sides_are_non_empty() -> None:
    """The split has something on each side."""
    sides = {side_of(spec.spec_id) for spec in SPECS}

    assert sides == {SIDE_TRAIN, SIDE_TEST}


def test_structures_are_disjoint_by_content() -> None:
    """No training structure is byte- or digest-equal to a test structure.

    Split by name alone would miss two specs that build the same
    structure, which would put one structure on both sides.
    """
    hashes: dict[str, set[str]] = {SIDE_TRAIN: set(), SIDE_TEST: set()}
    digests: dict[str, set[str]] = {SIDE_TRAIN: set(), SIDE_TEST: set()}
    for spec in SPECS:
        snapshot = build_structure(spec)
        side = side_of(spec.spec_id)
        hashes[side].add(
            hashlib.sha256(to_json(snapshot).encode("utf-8")).hexdigest()
        )
        digests[side].add(structure_digest(snapshot))

    assert not hashes[SIDE_TRAIN] & hashes[SIDE_TEST]
    assert not digests[SIDE_TRAIN] & digests[SIDE_TEST]


def test_split_is_frozen() -> None:
    """The held-out set cannot change without a version bump.

    Update both literals together, deliberately, and only before a
    split has been inspected.
    """
    assert (SPLIT_VERSION, tuple(sorted(HELD_OUT_SPEC_IDS))) == (
        1,
        (
            "altloc_two_residues",
            "everything_bonded",
            "insertion_codes_two_chains",
            "longer_two_chains",
            "three_states",
            "two_chains_hetatm",
        ),
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
