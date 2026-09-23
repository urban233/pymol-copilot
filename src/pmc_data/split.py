# Copyright 2026 PyMOL Copilot contributors.
"""The held-out split: which controlled structures only the test side sees.

The split is by source structure, as master plan item 15 asks, so no
structure a test item is asked about appears anywhere in training. Six
of the 24 specs `pmc_data.structures.enumerate_structures` builds are
held out, chosen so every structural feature -- several chains, hetero
atoms, several states, alternate locations, insertion codes, bonds and
a longer chain -- occurs on *both* sides. A feature present only in the
test split would measure whether the model can handle something it was
never shown, which is a different question from whether it generalizes
to a new structure.

What this split does and does not establish is stated plainly in the
datasheet: every spec shares one residue vocabulary (ALA, SER, GLY,
VAL, LEU, with ZN and HOH), so it tests generalization across feature
combinations and coordinates, not to new chemistry. It is a split by
spec, not by sequence cluster.

The held-out set is frozen. The spec says test splits are immutable
after inspection begins, so changing `HELD_OUT_SPEC_IDS` must bump
`SPLIT_VERSION`, and `tests/data/test_split.py` pins both together so a
silent edit fails CI.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from typing import Literal

from pmc_data.structures import StructureSpec

#: The split's own version. Bump it whenever HELD_OUT_SPEC_IDS changes.
SPLIT_VERSION = 1

#: The specs whose structures only the test side may see.
HELD_OUT_SPEC_IDS: frozenset[str] = frozenset(
    (
        "altloc_two_residues",
        "everything_bonded",
        "insertion_codes_two_chains",
        "longer_two_chains",
        "three_states",
        "two_chains_hetatm",
    )
)

#: The side a structure belongs to.
type SIDE = Literal["train", "test"]

SIDE_TRAIN: SIDE = "train"
SIDE_TEST: SIDE = "test"

#: The structural features the split balances across its two sides.
FEATURE_MULTI_CHAIN = "multi_chain"
FEATURE_HETATM = "hetatm"
FEATURE_MULTI_STATE = "multi_state"
FEATURE_ALTLOC = "altloc"
FEATURE_INSERTION = "insertion"
FEATURE_BONDS = "bonds"
FEATURE_LONG_CHAIN = "long_chain"

ALL_FEATURES = frozenset(
    (
        FEATURE_MULTI_CHAIN,
        FEATURE_HETATM,
        FEATURE_MULTI_STATE,
        FEATURE_ALTLOC,
        FEATURE_INSERTION,
        FEATURE_BONDS,
        FEATURE_LONG_CHAIN,
    )
)

#: The residues per chain `enumerate_structures` uses by default; a
#: spec with more carries the long-chain feature.
_DEFAULT_RESIDUES_PER_CHAIN = 4


def features_of(spec: StructureSpec) -> frozenset[str]:
    """Name the structural features one spec exercises.

    Args:
        spec: The structure spec.

    Returns:
        The features, drawn from ALL_FEATURES.
    """
    features: set[str] = set()
    if spec.chain_count > 1:
        features.add(FEATURE_MULTI_CHAIN)
    if spec.hetero_residues > 0:
        features.add(FEATURE_HETATM)
    if spec.state_count > 1:
        features.add(FEATURE_MULTI_STATE)
    if spec.altloc_residues > 0:
        features.add(FEATURE_ALTLOC)
    if spec.insertion_residues > 0:
        features.add(FEATURE_INSERTION)
    if spec.with_bonds:
        features.add(FEATURE_BONDS)
    if spec.residues_per_chain > _DEFAULT_RESIDUES_PER_CHAIN:
        features.add(FEATURE_LONG_CHAIN)
    return frozenset(features)


def side_of(spec_id: str) -> SIDE:
    """Say which side of the split a structure belongs to.

    Args:
        spec_id: The structure spec's identity.

    Returns:
        SIDE_TEST for a held-out spec, SIDE_TRAIN otherwise.
    """
    return SIDE_TEST if spec_id in HELD_OUT_SPEC_IDS else SIDE_TRAIN
