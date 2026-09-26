# Copyright 2026 PyMOL Copilot contributors.
"""The committed gold samples must still verify against real PyMOL.

`src/pmc_data/gold/gold_samples.jsonl` is the test split every offline
evaluation rests on. It is replayed here the way the conformance slice
is: each sample's structure is rebuilt from the spec it records, its
plan is parsed back out of its canonical .pml, and a fresh
`pmc_sidecar.child` must reproduce the selection counts the sample was
verified against, and the fingerprint wherever the oracle predicted
one. Contract drift that
would silently re-grade the test split fails here instead.

It also checks the samples still correspond to the reviewed items, one
to one: a gold item edited after its sample was written means the
committed test split is no longer what was reviewed.

Regenerate the samples with:

    bazel run //src/pmc_data:gold_cli
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import pytest

from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_OK
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import execute
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.gold_set import DEFAULT_GOLD_ITEMS_PATH
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.gold_set import load_gold_items
from pmc_data.gold_set import reference_plan
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure

ITEMS = load_gold_items(DEFAULT_GOLD_ITEMS_PATH)
SAMPLES = read_samples(DEFAULT_GOLD_SAMPLES_PATH)


def test_samples_match_the_reviewed_items() -> None:
    """One sample per reviewed item, in order, with its own intent and plan."""
    assert all(item.reviewed for item in ITEMS)
    assert [s.sample_id for s in SAMPLES] == [i.gold_id for i in ITEMS]
    for item, sample in zip(ITEMS, SAMPLES, strict=True):
        assert sample.intent == item.intent, item.gold_id
        assert sample.plan_pml == reference_plan(item).render_pml(), (
            item.gold_id
        )
        assert sample.structure.spec_id == item.spec_id, item.gold_id


@pytest.mark.parametrize(
    "sample", SAMPLES, ids=[sample.sample_id for sample in SAMPLES]
)
def test_every_gold_item_still_verifies(sample: Sample) -> None:
    """A committed gold sample reproduces its fingerprint and its counts.

    Args:
        sample: The committed gold sample being replayed.
    """
    snapshot = build_structure(StructureSpec.from_dict(sample.structure.spec))
    plan = parse_pml(sample.plan_pml)
    assert isinstance(plan, ActionPlan), sample.sample_id

    report = execute(
        ExecutionRequest(
            executor_version=EXECUTOR_VERSION,
            plan=plan,
            snapshot_json=to_json(snapshot),
            expected_snapshot_digest=structure_digest(snapshot),
            expected_resulting_fingerprint=(
                sample.verification.expected_fingerprint
            ),
        )
    )

    assert report.reason == REASON_OK, report
    if sample.verification.expected_fingerprint is not None:
        # Only where the oracle made a claim. An orienting plan carries
        # no expected fingerprint -- the oracle declines to predict a
        # camera move -- and its resulting view matrix is not the same
        # on every platform: gold_062 to gold_065 reproduce on macOS
        # and differ on ubuntu-24.04 and windows-2025. Those samples
        # were graded on their selection counts, which are compared
        # below on every platform.
        assert report.resulting_fingerprint == (
            sample.verification.resulting_fingerprint
        )
    assert (
        tuple((c.name, c.atom_count) for c in report.selection_counts)
        == sample.verification.selection_counts
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
