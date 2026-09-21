# Copyright 2026 PyMOL Copilot contributors.
"""The committed slice must still verify against today's contracts.

The full corpus is a `bazel run`, not a test: a few thousand samples is
a few thousand spawned PyMOL processes. But contract drift -- a bumped
CARD_VERSION, a changed colour index, an altered snapshot field, a
structure that stopped reconstructing faithfully -- breaks every sample
at once, so a small committed slice catches it in a minute rather than
letting it surface in a months-old corpus.

The slice is two files. `samples.jsonl` holds what verified;
`rejections.jsonl` holds what did not, which for the slice is the one
deliberately ungradable attempt. A slice with only the first would be
evidence that the happy path still works and no evidence at all that
the pipeline still refuses to grade what it cannot.

Each committed sample is replayed from its own record and nothing
else: the structure is rebuilt from the spec the record carries, the
plan is parsed back out of its canonical .pml by `pmc_core.parser`,
and the run is bound to the fingerprint the record was verified
against. A sample that cannot be replayed from what it wrote down is
not an auditable record, whatever it claims.

Regenerate the slice with:

    bazel run //src/pmc_data:corpus_cli -- --slice
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import os
import sys
from pathlib import Path

import pytest

from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_OK
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import execute
from pmc_core.grammar import GRAMMAR_VERSION
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.policy import POLICY_VERSION
from pmc_core.prompt import build_for_data
from pmc_core.protocol import PROTOCOL_VERSION
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.sample import REASON_NOT_GRADABLE
from pmc_data.sample import STATUS_UNSUPPORTED
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

#: The committed slice, beside the package it describes.
SLICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "pmc_data" / "conformance"
)
SLICE_PATH = SLICE_DIR / "samples.jsonl"
REJECTIONS_PATH = SLICE_DIR / "rejections.jsonl"

#: Any seed builds the same structure matrix under the same names: a
#: spec's own derived seed varies with it, but which specs exist and
#: what they are called does not, and it is the names the coverage
#: check below compares against.
MATRIX_SEED = 0

SAMPLES = read_samples(SLICE_PATH)
REJECTIONS = tuple(
    json.loads(line)
    for line in REJECTIONS_PATH.read_text(encoding="utf-8").splitlines()
    if line
)


def _replayed_plan(sample: Sample) -> ActionPlan:
    """Recover a sample's typed plan from its own recorded text.

    Args:
        sample: The committed sample.

    Returns:
        The parsed plan.

    Raises:
        AssertionError: If the recorded .pml no longer parses. The
            parser is the only authority on what text is legal, so a
            record it rejects is no longer a legal plan.
    """
    parsed = parse_pml(sample.plan_pml)
    if not isinstance(parsed, ActionPlan):
        raise AssertionError(
            f"{sample.sample_id}: recorded plan no longer parses: {parsed}"
        )
    return parsed


@pytest.mark.parametrize(
    "sample", SAMPLES, ids=[sample.sample_id for sample in SAMPLES]
)
def test_every_committed_sample_still_verifies(sample: Sample) -> None:
    """A committed sample must still reproduce its own fingerprint.

    Args:
        sample: The committed sample being replayed.
    """
    snapshot = build_structure(StructureSpec.from_dict(sample.structure.spec))
    plan = _replayed_plan(sample)

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

    assert report.reason == REASON_OK, (
        f"{sample.sample_id}: {report.reason} {report.command_outcomes}"
    )
    assert report.resulting_fingerprint == (
        sample.verification.resulting_fingerprint
    )


@pytest.mark.parametrize(
    "sample", SAMPLES, ids=[sample.sample_id for sample in SAMPLES]
)
def test_every_committed_structure_is_still_what_it_records(
    sample: Sample,
) -> None:
    """The recorded digest must still describe the rebuilt structure.

    A structure builder change that altered a field would otherwise be
    discovered only as a wall of fidelity mismatches.

    Args:
        sample: The committed sample being replayed.
    """
    snapshot = build_structure(StructureSpec.from_dict(sample.structure.spec))

    assert structure_digest(snapshot) == sample.structure.structure_digest


def test_every_committed_prompt_is_still_what_the_seam_builds() -> None:
    """The dataset prompt seam must still produce the recorded bytes.

    Item 13 exists so the dataset and the runtime share one prompt
    builder. A silent change here means a model trained against one
    prompt and served another.
    """
    drifted = [
        sample.sample_id
        for sample in SAMPLES
        if build_for_data(
            build_structure(StructureSpec.from_dict(sample.structure.spec)),
            sample.intent,
        ).text()
        != sample.prompt_text
    ]

    assert drifted == []


def test_the_committed_versions_match_todays_contracts() -> None:
    """A bumped contract version invalidates the slice, loudly.

    Every recorded version is checked, not only the card's: a sample
    built under a different policy or snapshot schema is evidence
    about a different system.
    """
    for sample in SAMPLES:
        versions = sample.versions
        assert versions.grammar_version == GRAMMAR_VERSION
        assert versions.policy_version == POLICY_VERSION
        assert versions.snapshot_version == SNAPSHOT_VERSION
        assert versions.executor_version == EXECUTOR_VERSION
        assert versions.protocol_version == PROTOCOL_VERSION


def test_committed_slice_covers_every_category_kind() -> None:
    """The slice has not silently lost a verb, term or boolean shape.

    A category dropping out of the slice produces no failure at all --
    only a narrower thing being checked than the name suggests.
    """
    verbs = {
        verb
        for sample in SAMPLES
        for verb in sample.category.split("/")[0].split("+")
    }
    keywords = {
        keyword
        for sample in SAMPLES
        for keyword in sample.category.split("/")[1].split("+")
    }
    shapes = {sample.category.split("/")[2] for sample in SAMPLES}

    assert verbs == set(COMMAND_ALLOWLIST)
    # polymer is absent on purpose: it is ungradable, so it can never
    # appear on a *verified* sample. Every other term must be here.
    assert keywords == {"chain", "resi", "resn", "name", "hetatm"}
    assert {"single", "and", "or", "and_or"} <= shapes
    assert any("not" in shape for shape in shapes)


def test_the_slice_records_both_kinds_of_unsupported_assertion() -> None:
    """The unsupported path must be exercised, not only the happy one."""
    markers = {
        marker for sample in SAMPLES for marker in sample.unsupported_assertions
    }

    assert "camera_view" in markers
    assert any(
        marker.startswith("unobservable_representation:") for marker in markers
    )


def test_the_slice_records_the_ungradable_attempt_it_made() -> None:
    """The slice must carry its own evidence of the ungradable path.

    An attempt naming the polymer flag is generated on purpose, so that
    the pipeline is seen to classify it as unsupported rather than
    guess at it. It can never appear in `samples.jsonl` -- it is not a
    verified sample -- so the only place it can be committed is beside
    it, and a slice that dropped it would look exactly like a pipeline
    that had quietly stopped generating it at all.
    """
    polymer = [
        rejection
        for rejection in REJECTIONS
        if "polymer" in rejection["category"]
    ]

    assert len(polymer) == 1, REJECTIONS
    assert polymer[0]["status"] == STATUS_UNSUPPORTED
    assert polymer[0]["reason"] == REASON_NOT_GRADABLE


def test_every_committed_structure_appears_in_the_slice() -> None:
    """No controlled structure may drop out of the replayed set.

    The slice exists partly to catch a structure that stopped
    reconstructing faithfully, which it can only do for a structure it
    actually contains. One dropping out is silent: the remaining
    samples all still pass.
    """
    covered = {sample.structure.spec_id for sample in SAMPLES}

    assert covered == {
        spec.spec_id for spec in enumerate_structures(MATRIX_SEED)
    }


def test_the_slice_is_not_empty_and_is_bounded() -> None:
    """Small enough for CI, large enough to mean something."""
    assert 20 <= len(SAMPLES) <= 80


if __name__ == "__main__":
    code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    # Real PyMOL runs in the spawned children; exit the same way the
    # other real-PyMOL modules here do so a failing code survives.
    os._exit(code)
