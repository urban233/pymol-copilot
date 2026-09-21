# Copyright 2026 PyMOL Copilot contributors.
"""End-to-end generation through the real execution boundary.

Every collaborator here is the production one: the real
`pmc_core.executor.execute()`, which spawns a real
`pmc_sidecar.child` process, which reconstructs the structure in real
headless PyMOL and runs the plan. Nothing is injected.

What this proves that the hermetic promotion guard cannot is that the
oracle's prediction actually survives the round trip -- the executor
fails a run closed with REASON_FIDELITY_MISMATCH when the fingerprint
it computes differs from the one handed in, so a sample coming back
verified is real PyMOL agreeing with an expectation it did not
produce.

One plan per representative category rather than all of them: each
sample spawns its own PyMOL process, and the whole corpus is a
`bazel run`, not a test.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
import sys

import pytest

from pmc_core.executor import REASON_OK
from pmc_data.sample import Rejection
from pmc_data.generate import verify_sample
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import Sample
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures
from pmc_data.taxonomy import UNOBSERVABLE_REPRESENTATIONS
from pmc_data.taxonomy import PlanCandidate
from pmc_data.taxonomy import enumerate_plans

SEED = 20260921

SPEC = next(
    spec
    for spec in enumerate_structures(SEED)
    if spec.spec_id == "everything_small"
)
SNAPSHOT = build_structure(SPEC)
CANDIDATES = enumerate_plans(SNAPSHOT, seed=SPEC.seed)

#: One representative category per verb set and per boolean shape. Each
#: entry is matched against the derived category, so a taxonomy change
#: that dropped one of these fails here rather than silently narrowing
#: what end-to-end generation is known to cover.
REPRESENTATIVE_CATEGORIES = (
    "color+select/chain/single",
    "color/chain/single",
    "show/chain/single",
    "hide/chain/single",
    "orient+select/chain/single",
    "color+select+show/chain/single",
    "hide+show/chain/single",
    "color/hetatm/single",
    "color/chain/single+not",
    "color+select/chain+name/and",
)


def _first_with_category(category: str) -> PlanCandidate:
    """Find the first enumerated candidate in one exact category.

    Args:
        category: The derived category to look for.

    Returns:
        The matching plan candidate.

    Raises:
        AssertionError: If the taxonomy no longer produces it.
    """
    for candidate in CANDIDATES:
        if candidate.category == category:
            return candidate
    raise AssertionError(f"taxonomy no longer produces {category!r}")


@pytest.mark.parametrize("category", REPRESENTATIVE_CATEGORIES)
def test_a_sample_per_category_verifies(category: str) -> None:
    """A representative plan from each category must verify for real.

    Args:
        category: The derived category under test.
    """
    candidate = _first_with_category(category)

    result = verify_sample(
        SNAPSHOT, SPEC, candidate, sample_id=f"real_{category}"
    )

    assert isinstance(result, Sample), (
        f"{category}: {result.reason} / {result.detail}"
    )
    assert result.verification.reason == REASON_OK


def test_a_verified_sample_matched_the_oracles_own_fingerprint() -> None:
    """The executor must have compared against the prediction, and agreed.

    Equal expected and resulting fingerprints is the whole claim: a
    sample is real PyMOL agreeing with a value computed without it.
    """
    candidate = _first_with_category("color+select/chain/single")

    result = verify_sample(SNAPSHOT, SPEC, candidate, sample_id="real_fp")

    assert isinstance(result, Sample)
    assert result.verification.expected_fingerprint is not None
    assert (
        result.verification.resulting_fingerprint
        == result.verification.expected_fingerprint
    )
    assert ASSERTION_RESULTING_SNAPSHOT in {a.kind for a in result.assertions}


def test_an_orienting_plan_verifies_without_a_fingerprint() -> None:
    """Orient is kept on its selection counts, with the camera unclaimed."""
    candidate = _first_with_category("orient+select/chain/single")

    result = verify_sample(SNAPSHOT, SPEC, candidate, sample_id="real_orient")

    assert isinstance(result, Sample)
    assert result.unsupported_assertions == ("camera_view",)
    assert result.verification.expected_fingerprint is None


def test_an_unobservable_representation_still_verifies_and_says_so() -> None:
    """Showing a representation the snapshot cannot see is legal and graded.

    The resulting state is still fully predictable -- nothing
    observable changes -- so the fingerprint holds. What cannot be
    asserted is that the representation was applied, and the sample
    names that rather than implying it was checked.
    """
    candidate = next(
        c
        for c in CANDIDATES
        if any(
            line.startswith(f"show {rep},")
            for line in c.plan.render_pml().splitlines()
            for rep in UNOBSERVABLE_REPRESENTATIONS
        )
    )

    result = verify_sample(
        SNAPSHOT, SPEC, candidate, sample_id="real_unobservable"
    )

    assert isinstance(result, Sample), result.detail
    assert any(
        marker.startswith("unobservable_representation:")
        for marker in result.unsupported_assertions
    )


def test_a_polymer_plan_is_reported_unsupported_not_verified() -> None:
    """No ground truth exists, so no sample may claim one."""
    candidate = next(c for c in CANDIDATES if "polymer" in c.category)

    result = verify_sample(SNAPSHOT, SPEC, candidate, sample_id="real_polymer")

    assert isinstance(result, Rejection)
    assert "polymer_classification" in result.detail


if __name__ == "__main__":
    code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    # Real PyMOL runs in the spawned children; exit the same way the
    # other real-PyMOL modules here do so a failing code survives.
    os._exit(code)
