# Copyright 2026 PyMOL Copilot contributors.
"""Evidence that the per-category report is honest.

"Honest" here has three specific meanings, and each is a way the
numbers could mislead if the aggregation were written carelessly.

An unsupported category is not a failure: nothing could have been
asserted about it, so counting it as a rejection would manufacture a
defect rate out of a contract limitation. A category with nothing kept
must still appear, because a category vanishing from the corpus
produces no error anywhere -- only an absence. And a rate over no
gradable attempts is None rather than zero, because zero reads as
"nothing went wrong" where nothing was measured.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path

import pytest

from pmc_data.sample import REASON_NOT_GRADABLE
from pmc_data.generate import REASON_SELECTION_COUNT_MISMATCH
from pmc_data.sample import STATUS_UNSUPPORTED
from pmc_data.sample import Rejection
from pmc_data.report import build_report
from pmc_data.report import render_table
from pmc_data.report import write_rejections
from pmc_data.report import write_report
from pmc_data.sample import ASSERTION_COMMANDS_SUCCEEDED
from pmc_data.sample import FINGERPRINT_PREFIX
from pmc_data.sample import Assertion
from pmc_data.sample import PINNED_PYMOL_VERSION
from pmc_data.sample import Sample
from pmc_data.sample import SampleVersions
from pmc_data.sample import StructureIdentity
from pmc_data.sample import VerificationRecord
from pmc_data.structures import enumerate_structures

SEED = 20260921

#: A real spec from the standing matrix, so the recorded structure is
#: one that could actually be rebuilt from the record.
SPEC = next(
    spec
    for spec in enumerate_structures(20260921)
    if spec.spec_id == "everything_small"
)


def _sample(
    category: str,
    *,
    unsupported: tuple[str, ...] = (),
    no_change: bool = False,
    empty_selection: bool = False,
) -> Sample:
    """Build a kept sample in one category.

    Args:
        category: The category to record.
        unsupported: Assertion markers the sample could not evaluate.
        no_change: Whether the predicted result equals the structure
            the plan started from, which is recorded as a fingerprint
            over the very bytes the structure identity already hashes.
        empty_selection: Whether to record a selection matching no atom.

    Returns:
        The assembled sample.
    """
    return Sample(
        sample_id=f"s_{category}_{len(unsupported)}",
        intent="Color chain A red.",
        category=category,
        difficulty="basic",
        structure=StructureIdentity(
            spec_id=SPEC.spec_id,
            seed=SPEC.seed,
            spec=SPEC.to_dict(),
            snapshot_sha256="a" * 64,
            structure_digest="sha256:" + "b" * 64,
        ),
        versions=SampleVersions(
            card_version=1,
            prompt_version=1,
            grammar_version=1,
            policy_version=1,
            snapshot_version=1,
            executor_version=1,
            protocol_version="1",
            pymol_version=PINNED_PYMOL_VERSION,
        ),
        plan_pml="color red, chain A\n",
        plan_json=({"verb": "color"},),
        prompt_text="prompt-version=1\n",
        assertions=(
            Assertion(kind=ASSERTION_COMMANDS_SUCCEEDED, detail="1 command"),
        ),
        unsupported_assertions=unsupported,
        verification=VerificationRecord(
            status="ok",
            reason="ok",
            expected_fingerprint=FINGERPRINT_PREFIX + "a" * 64
            if no_change
            else None,
            resulting_fingerprint=None,
            selection_counts=(("copilot_sel0001", 0),)
            if empty_selection
            else (),
            command_verbs=("color",),
        ),
    )


def _rejection(category: str, *, status: str, reason: str) -> Rejection:
    """Build a rejection in one category.

    Args:
        category: The category to record.
        status: The status to record.
        reason: The reason to record.

    Returns:
        The assembled rejection.
    """
    return Rejection(
        sample_id=f"r_{category}",
        category=category,
        difficulty="basic",
        status=status,
        reason=reason,
        detail="detail",
    )


def test_rates_are_computed_per_category() -> None:
    """Each category's rate must come from its own attempts only."""
    report = build_report(
        [_sample("a"), _sample("a"), _sample("b")],
        [
            _rejection(
                "a", status="failed", reason=REASON_SELECTION_COUNT_MISMATCH
            ),
            _rejection("b", status="failed", reason="fidelity_mismatch"),
            _rejection("b", status="failed", reason="fidelity_mismatch"),
            _rejection("b", status="failed", reason="fidelity_mismatch"),
        ],
        seed=SEED,
    )

    by_name = {c.category: c for c in report.categories}
    assert by_name["a"].rejection_rate == pytest.approx(1 / 3)
    assert by_name["b"].rejection_rate == pytest.approx(3 / 4)
    assert report.rejection_rate == pytest.approx(4 / 7)


def test_unsupported_is_reported_separately_and_never_inflates_the_rate() -> (
    None
):
    """An ungradable category is a contract limit, not a defect."""
    report = build_report(
        [_sample("a")],
        [
            _rejection(
                "a", status=STATUS_UNSUPPORTED, reason=REASON_NOT_GRADABLE
            )
        ],
        seed=SEED,
    )

    category = report.categories[0]
    assert category.attempted == 2
    assert category.kept == 1
    assert category.unsupported == 1
    assert category.rejected == 0
    assert category.rejection_rate == 0.0
    assert report.unsupported == 1


def test_a_wholly_unsupported_category_reports_no_rate_rather_than_zero() -> (
    None
):
    """Zero would read as "nothing went wrong" where nothing was measured."""
    report = build_report(
        [],
        [
            _rejection(
                "poly", status=STATUS_UNSUPPORTED, reason=REASON_NOT_GRADABLE
            )
        ],
        seed=SEED,
    )

    assert report.categories[0].rejection_rate is None
    assert report.rejection_rate is None
    assert "n/a" in render_table(report)


def test_a_category_with_nothing_kept_still_appears() -> None:
    """A category vanishing from the corpus produces no error, only absence."""
    report = build_report(
        [_sample("kept_one")],
        [_rejection("all_failed", status="failed", reason="child_crash")],
        seed=SEED,
    )

    assert [c.category for c in report.categories] == [
        "all_failed",
        "kept_one",
    ]
    assert report.categories[0].kept == 0
    assert report.categories[0].rejection_rate == 1.0


def test_each_rejection_reason_is_counted_under_its_own_name() -> None:
    """Merging reasons would hide an oracle disagreement among crashes."""
    report = build_report(
        [],
        [
            _rejection("a", status="failed", reason="fidelity_mismatch"),
            _rejection("a", status="failed", reason="command_failure"),
            _rejection("a", status="failed", reason="command_failure"),
        ],
        seed=SEED,
    )

    assert report.categories[0].rejected_by_reason == {
        "command_failure": 2,
        "fidelity_mismatch": 1,
    }


def test_unsupported_markers_on_kept_samples_are_reported() -> None:
    """A verified sample can still carry an assertion it never made.

    An oriented plan is kept on its selection counts while its camera
    assertion is not made at all; the report has to surface that rather
    than let "kept" imply "fully checked".
    """
    report = build_report(
        [
            _sample("orient", unsupported=("camera_view",)),
            _sample("orient", unsupported=("camera_view",)),
        ],
        [],
        seed=SEED,
    )

    assert report.categories[0].unsupported_assertions == {"camera_view": 2}
    assert report.categories[0].rejection_rate == 0.0


def test_the_written_report_round_trips_as_json(tmp_path: Path) -> None:
    """A report that cannot be read back cannot be audited.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    report = build_report([_sample("a")], [], seed=SEED)
    path = tmp_path / "report.json"

    write_report(path, report)

    assert json.loads(path.read_text(encoding="utf-8")) == report.to_dict()


def test_every_rejection_is_written_not_just_summarized(
    tmp_path: Path,
) -> None:
    """A summary alone would let an individual rejection disappear.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    rejections = [
        _rejection("a", status="failed", reason="child_crash"),
        _rejection("b", status=STATUS_UNSUPPORTED, reason=REASON_NOT_GRADABLE),
    ]
    path = tmp_path / "rejections.jsonl"

    assert write_rejections(path, rejections) == 2

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["reason"] for line in lines] == [
        "child_crash",
        REASON_NOT_GRADABLE,
    ]


def test_a_sample_that_predicts_no_change_is_counted_apart() -> None:
    """A rate of 0% over such samples is not evidence the oracle is right.

    The plan ran, the two sides agreed, and the sample is genuinely
    kept -- but what they agreed on is that the structure was
    unchanged, which any oracle at all would have predicted correctly
    by saying nothing ever happens.
    """
    report = build_report(
        [_sample("a"), _sample("a", no_change=True)],
        [],
        seed=SEED,
    )

    category = report.categories[0]
    assert category.kept == 2
    assert category.no_op == 1
    assert category.vacuous == 1
    assert category.substantive == 1
    assert report.no_op == 1
    assert report.substantive == 1


def test_a_sample_that_grades_an_empty_selection_is_counted_apart() -> None:
    """An expected count of zero is met by zero however it was computed."""
    report = build_report(
        [_sample("a", empty_selection=True), _sample("a")],
        [],
        seed=SEED,
    )

    category = report.categories[0]
    assert category.empty_selection == 1
    assert category.no_op == 0
    assert category.vacuous == 1
    assert category.substantive == 1


def test_a_sample_that_is_vacuous_twice_over_is_counted_once() -> None:
    """`vacuous` is the union of the two, not their sum.

    Summing them would let a category report more vacuous samples than
    it kept, and `substantive` would go negative.
    """
    report = build_report(
        [_sample("a", no_change=True, empty_selection=True)],
        [],
        seed=SEED,
    )

    category = report.categories[0]
    assert category.no_op == 1
    assert category.empty_selection == 1
    assert category.vacuous == 1
    assert category.substantive == 0


def test_a_report_says_when_its_run_did_not_finish() -> None:
    """Partial counts read as a whole run unless the report says otherwise.

    A run that dies partway still writes what it measured, which is
    worth far more than nothing after hours of spawned PyMOL
    processes -- but only if nobody mistakes it for the whole corpus.
    """
    whole = build_report([_sample("a")], [], seed=SEED)
    partial = build_report([_sample("a")], [], seed=SEED, complete=False)

    assert whole.complete is True
    assert whole.to_dict()["complete"] is True
    assert "INCOMPLETE" not in render_table(whole)

    assert partial.complete is False
    assert partial.to_dict()["complete"] is False
    assert "INCOMPLETE" in render_table(partial)


def test_the_table_totals_match_the_report() -> None:
    """A printed total that disagreed with the JSON would mislead a reader."""
    report = build_report(
        [_sample("a"), _sample("b")],
        [_rejection("a", status="failed", reason="child_crash")],
        seed=SEED,
    )

    table = render_table(report)

    assert "TOTAL" in table
    assert f"{report.attempted:>6}" in table
    assert sum(c.attempted for c in report.categories) == report.attempted


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
