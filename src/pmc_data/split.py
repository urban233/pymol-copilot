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

import hashlib
import json
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Literal

from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.decontam import METHOD
from pmc_data.decontam import NearDuplicate
from pmc_data.decontam import find_near_duplicates
from pmc_data.decontam import normalize_intent
from pmc_data.decontam import sensitivity
from pmc_data.decontam import structure_vocabulary
from pmc_data.gold_set import GoldItem
from pmc_data.gold_set import reference_plan
from pmc_data.sample import Sample
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

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


class InvalidSplitError(ValueError):
    """Raised when the inputs to a split cannot be trusted.

    Every refusal names what is wrong. A split is the evidence every
    later result rests on, so it is built from checked inputs or not
    at all.
    """


@dataclass(frozen=True)
class SplitResult:
    """The four parts a split divides its inputs into.

    Attributes:
        train: Corpus samples on training structures that survived
            decontamination.
        test_gold: The verified gold samples: the test split.
        heldout_synthetic: Corpus samples on held-out structures, kept
            as a secondary evaluation set with templated intents.
        dropped: Corpus samples on training structures whose intent
            near-duplicated a gold intent, each with the match.
        sensitivity: How many training samples each configured
            threshold would drop.
        template_overlap: How many training samples would be dropped by
            exact normalized-intent match alone if the templated
            held-out intents were counted as test intents too. The
            datasheet reports it as the reason they are not.
    """

    train: tuple[Sample, ...]
    test_gold: tuple[Sample, ...]
    heldout_synthetic: tuple[Sample, ...]
    dropped: tuple[tuple[Sample, NearDuplicate], ...]
    sensitivity: Mapping[str, int]
    template_overlap: int


def _check_gold(items: Sequence[GoldItem], samples: Sequence[Sample]) -> None:
    """Refuse a gold set that is unreviewed, stale or on training structures.

    Args:
        items: The authored gold records.
        samples: The committed verified gold samples.

    Raises:
        InvalidSplitError: If any record is unreviewed, the samples do
            not correspond one-to-one and in order to the records, or a
            gold item sits on a training structure.
    """
    unreviewed = [item.gold_id for item in items if not item.reviewed]
    if unreviewed:
        raise InvalidSplitError(
            f"{len(unreviewed)} gold items are not reviewed: "
            f"{', '.join(unreviewed)}"
        )
    if [s.sample_id for s in samples] != [i.gold_id for i in items]:
        raise InvalidSplitError(
            "gold samples do not match the gold items one-to-one; rerun "
            "`bazel run //src/pmc_data:gold_cli`"
        )
    for item, sample in zip(items, samples, strict=True):
        if (
            sample.intent != item.intent
            or sample.plan_pml != reference_plan(item).render_pml()
            or sample.structure.spec_id != item.spec_id
        ):
            raise InvalidSplitError(
                f"gold sample {item.gold_id!r} is stale against its item; "
                "rerun `bazel run //src/pmc_data:gold_cli`"
            )
        if side_of(item.spec_id) != SIDE_TEST:
            raise InvalidSplitError(
                f"gold item {item.gold_id!r} is on training structure "
                f"{item.spec_id!r}"
            )


def _check_lineage(samples: Sequence[Sample], seed: int) -> None:
    """Refuse any sample whose structure is not the one its spec builds.

    A sample records its spec and the hash of the structure it ran
    against. Both have to agree with the matrix at the configured seed,
    or the sample was generated against something this split does not
    know about -- and a structure it does not know cannot be assigned
    to a side.

    Args:
        samples: Every sample the split is built from.
        seed: The corpus seed.

    Raises:
        InvalidSplitError: If a sample names an unknown spec, records a
            spec that differs from the matrix's, or records a structure
            hash or digest that the rebuilt spec does not produce.
    """
    specs = {spec.spec_id: spec for spec in enumerate_structures(seed)}
    expected: dict[str, tuple[str, str]] = {}
    for spec_id, spec in specs.items():
        snapshot = build_structure(spec)
        expected[spec_id] = (
            hashlib.sha256(to_json(snapshot).encode("utf-8")).hexdigest(),
            structure_digest(snapshot),
        )
    for sample in samples:
        identity = sample.structure
        spec = specs.get(identity.spec_id)
        if spec is None:
            raise InvalidSplitError(
                f"{sample.sample_id!r}: unknown structure spec "
                f"{identity.spec_id!r}"
            )
        if dict(identity.spec) != spec.to_dict():
            raise InvalidSplitError(
                f"{sample.sample_id!r}: recorded spec differs from the "
                f"matrix at seed {seed}"
            )
        if (identity.snapshot_sha256, identity.structure_digest) != expected[
            identity.spec_id
        ]:
            raise InvalidSplitError(
                f"{sample.sample_id!r}: recorded structure does not match "
                f"what spec {identity.spec_id!r} builds"
            )


def build_split(
    *,
    corpus: Sequence[Sample],
    corpus_complete: bool,
    gold_items: Sequence[GoldItem],
    gold_samples: Sequence[Sample],
    config: SplitConfig,
) -> SplitResult:
    """Divide a corpus and the gold set into train, test and held-out.

    Args:
        corpus: The generated corpus's verified samples.
        corpus_complete: Whether the corpus run made every attempt.
        gold_items: The authored gold records.
        gold_samples: The committed verified gold samples.
        config: The frozen split settings.

    Returns:
        The split. Every corpus sample lands in exactly one of train,
        heldout_synthetic and dropped.

    Raises:
        InvalidSplitError: If the corpus is incomplete, the gold set is
            unreviewed, stale or misplaced, any sample's lineage is
            broken, or sample ids collide.
    """
    if not corpus_complete:
        raise InvalidSplitError(
            "the corpus report says the run was incomplete; a partial "
            "corpus is not split"
        )
    _check_gold(gold_items, gold_samples)
    _check_lineage((*corpus, *gold_samples), config.seed)
    ids = [s.sample_id for s in (*corpus, *gold_samples)]
    if len(ids) != len(set(ids)):
        raise InvalidSplitError("sample ids are not unique across the inputs")

    heldout = tuple(
        s for s in corpus if side_of(s.structure.spec_id) == SIDE_TEST
    )
    candidates = tuple(
        s for s in corpus if side_of(s.structure.spec_id) == SIDE_TRAIN
    )
    vocabulary = structure_vocabulary(
        build_structure(spec) for spec in enumerate_structures(config.seed)
    )
    train_pairs = [(s.sample_id, s.intent) for s in candidates]
    gold_pairs = [(s.sample_id, s.intent) for s in gold_samples]
    duplicates = find_near_duplicates(
        train_pairs,
        gold_pairs,
        threshold=config.decontam_threshold,
        vocabulary=vocabulary,
    )
    held_intents = {normalize_intent(s.intent) for s in heldout}
    return SplitResult(
        train=tuple(s for s in candidates if s.sample_id not in duplicates),
        test_gold=tuple(gold_samples),
        heldout_synthetic=heldout,
        dropped=tuple(
            (s, duplicates[s.sample_id])
            for s in candidates
            if s.sample_id in duplicates
        ),
        sensitivity=sensitivity(
            train_pairs,
            gold_pairs,
            thresholds=config.decontam_sensitivity,
            vocabulary=vocabulary,
        ),
        template_overlap=sum(
            normalize_intent(s.intent) in held_intents for s in candidates
        ),
    )
