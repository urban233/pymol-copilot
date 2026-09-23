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

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Literal

from pmc_data.decontam import METHOD
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


class InvalidSplitConfigError(ValueError):
    """Raised when the split configuration is incomplete or unknown."""


@dataclass(frozen=True)
class SplitConfig:
    """The frozen settings a split is built with.

    Attributes:
        seed: The corpus seed the structure matrix derives from.
        decontam_method: The near-duplicate rule, by name.
        decontam_threshold: The frame similarity at which two intents
            with equal entities are duplicates.
        decontam_sensitivity: Further thresholds to report drop counts
            for, so the dependence on the frozen one is visible.
        audit_sample_size: How many training labels the audit draws.
        audit_seed: The seed the audit draw derives from.
    """

    seed: int
    decontam_method: str
    decontam_threshold: float
    decontam_sensitivity: tuple[float, ...]
    audit_sample_size: int
    audit_seed: int


def _section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Read a required nested section.

    Args:
        data: The raw configuration.
        key: The section name.

    Returns:
        The section.

    Raises:
        InvalidSplitConfigError: If the section is missing.
    """
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise InvalidSplitConfigError(f"missing section: {key!r}")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    """Read a required number, refusing booleans.

    Args:
        data: The mapping to read from.
        key: The field name.

    Returns:
        The number.

    Raises:
        InvalidSplitConfigError: If the field is missing or not a number.
    """
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidSplitConfigError(f"field {key!r} must be a number")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    """Read a required integer, refusing booleans.

    Args:
        data: The mapping to read from.
        key: The field name.

    Returns:
        The integer.

    Raises:
        InvalidSplitConfigError: If the field is missing or not an int.
    """
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidSplitConfigError(f"field {key!r} must be an integer")
    return value


def load_split_config(path: Path) -> SplitConfig:
    """Read and validate `configs/generation/split.json`.

    Args:
        path: The configuration file.

    Returns:
        The validated settings.

    Raises:
        InvalidSplitConfigError: If a field is missing or malformed, or
            the file names a decontamination method this code does not
            implement.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    decontam = _section(data, "decontam")
    audit = _section(data, "audit")
    method = decontam.get("method")
    if method != METHOD:
        raise InvalidSplitConfigError(
            f"unknown decontamination method {method!r}; this code "
            f"implements {METHOD!r}"
        )
    raw_sensitivity = decontam.get("sensitivity")
    if not isinstance(raw_sensitivity, list):
        raise InvalidSplitConfigError("'sensitivity' must be a list")
    threshold = _number(decontam, "threshold")
    if not 0.0 < threshold <= 1.0:
        raise InvalidSplitConfigError(
            f"threshold must be in (0, 1], not {threshold}"
        )
    size = _integer(audit, "sample_size")
    if size < 1:
        raise InvalidSplitConfigError(
            f"audit sample_size must be at least 1, not {size}"
        )
    return SplitConfig(
        seed=_integer(data, "seed"),
        decontam_method=method,
        decontam_threshold=float(threshold),
        decontam_sensitivity=tuple(
            float(_number({"t": t}, "t")) for t in raw_sensitivity
        ),
        audit_sample_size=size,
        audit_seed=_integer(audit, "seed"),
    )
