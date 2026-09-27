# Copyright 2026 PyMOL Copilot contributors.
"""The grader passes the right plans, fails the wrong ones, and says why.

Hermetic: every execution report here is constructed, not produced by
PyMOL. `test_reference_model_real_pymol.py` proves the same rules
against real executions.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses

import pytest

from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import SelectionCount
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import FINGERPRINT_PREFIX
from pmc_data.sample import Assertion
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_eval.grade import EMPTY_SELECTION_FALSE
from pmc_eval.grade import EMPTY_SELECTION_TRUE
from pmc_eval.grade import EMPTY_SELECTION_UNKNOWN
from pmc_eval.grade import grade
from pmc_eval.grade import grading_complete
from pmc_eval.grade import is_vacuous
from pmc_eval.prompt import snapshot_for

SAMPLES = {
    sample.sample_id: sample
    for sample in read_samples(DEFAULT_GOLD_SAMPLES_PATH)
}

#: "make the zinc ions magenta": one command, fingerprint-graded.
COLOR_ONLY = SAMPLES["gold_001"]

#: Select chain A, colour it: fingerprint and selection counts.
SELECT_AND_COLOR = SAMPLES["gold_014"]

#: Select chain B, orient on it: selection counts only.
ORIENT = SAMPLES["gold_062"]


def _plan(text: str) -> ActionPlan:
    """Parse a plan the test asserts is well formed.

    Args:
        text: The restricted `.pml` text.

    Returns:
        The parsed plan.
    """
    plan = parse_pml(text)
    assert isinstance(plan, ActionPlan)
    return plan


def _report(
    plan: ActionPlan,
    *,
    fingerprint: str | None,
    counts: tuple[tuple[str, int], ...] = (),
    succeeded: int | None = None,
) -> ExecutionReport:
    """Build the execution report a plan could have produced.

    Args:
        plan: The executed plan, which sets the command count.
        fingerprint: The resulting-state fingerprint.
        counts: The named selections' atom counts.
        succeeded: How many commands succeeded before one failed, or None
            for all of them.

    Returns:
        A successful report, or a command failure when `succeeded` is
        short of the plan.
    """
    total = len(plan.operations)
    ran = total if succeeded is None else succeeded
    outcomes = tuple(
        CommandOutcome(index=index, verb="color", status=OUTCOME_OK, error=None)
        for index in range(ran)
    )
    if ran < total:
        outcomes = (
            *outcomes,
            CommandOutcome(
                index=ran, verb="color", status=OUTCOME_ERROR, error="boom"
            ),
        )
    ok = ran == total
    return ExecutionReport(
        executor_version=1,
        status=STATUS_OK if ok else STATUS_FAILED,
        reason=REASON_OK if ok else REASON_COMMAND_FAILURE,
        input_digest=None,
        resulting_fingerprint=fingerprint,
        selection_counts=tuple(
            SelectionCount(name=name, atom_count=count)
            for name, count in counts
        ),
        command_outcomes=outcomes,
        child_pid=None,
        child_terminated=None,
        elapsed_seconds=0.0,
    )


def _reference(sample: Sample) -> tuple[ActionPlan, ExecutionReport]:
    """Build the reference plan and the report its verification recorded.

    Args:
        sample: The stored sample.

    Returns:
        Its plan and a report reproducing its verification.
    """
    plan = _plan(sample.plan_pml)
    return plan, _report(
        plan,
        fingerprint=sample.verification.resulting_fingerprint,
        counts=sample.verification.selection_counts,
    )


@pytest.mark.parametrize("sample", [COLOR_ONLY, SELECT_AND_COLOR, ORIENT])
def test_the_reference_execution_passes(sample: Sample) -> None:
    """Replaying what verified a sample is a TaskSuccess.

    Args:
        sample: A stored sample of each assertion shape.
    """
    plan, report = _reference(sample)

    result = grade(sample, report, plan, snapshot_for(sample))

    assert result.task_success
    assert all(assertion.passed for assertion in result.assertions)


def test_wrong_fingerprint_fails() -> None:
    """A plan that leaves a different state fails the snapshot assertion."""
    plan = _plan("color red, resn ZN\n")
    report = _report(plan, fingerprint="sha256:" + "f" * 64)

    result = grade(COLOR_ONLY, report, plan, snapshot_for(COLOR_ONLY))

    assert not result.task_success
    failed = [a.kind for a in result.assertions if not a.passed]
    assert failed == [ASSERTION_RESULTING_SNAPSHOT]


def test_renamed_selection_passes() -> None:
    """Selection names are the model's choice; only the counts are graded."""
    plan = _plan("select copilot_first, chain A\ncolor marine, copilot_first\n")
    report = _report(
        plan,
        fingerprint=SELECT_AND_COLOR.verification.resulting_fingerprint,
        counts=(("copilot_first", 24),),
    )

    result = grade(
        SELECT_AND_COLOR, report, plan, snapshot_for(SELECT_AND_COLOR)
    )

    assert result.task_success


def test_extra_selection_fails() -> None:
    """A selection the reference does not make changes the counts multiset."""
    plan = _plan(
        "select copilot_a, chain A\n"
        "select copilot_b, chain B\n"
        "color marine, copilot_a\n"
    )
    report = _report(
        plan,
        fingerprint=SELECT_AND_COLOR.verification.resulting_fingerprint,
        counts=(("copilot_a", 24), ("copilot_b", 24)),
    )

    result = grade(
        SELECT_AND_COLOR, report, plan, snapshot_for(SELECT_AND_COLOR)
    )

    assert not result.task_success


def test_command_count_is_not_compared() -> None:
    """A longer plan that reaches the same state still passes."""
    plan = _plan("color magenta, resn ZN\ncolor magenta, resn ZN\n")
    report = _report(
        plan, fingerprint=COLOR_ONLY.verification.resulting_fingerprint
    )

    result = grade(COLOR_ONLY, report, plan, snapshot_for(COLOR_ONLY))

    assert result.task_success


def test_a_command_with_no_ok_outcome_fails_the_commands_assertion() -> None:
    """Every command must report ok, whatever the fingerprint says."""
    plan, reference = _reference(COLOR_ONLY)
    report = dataclasses.replace(reference, command_outcomes=())

    result = grade(COLOR_ONLY, report, plan, snapshot_for(COLOR_ONLY))

    assert not result.task_success
    assert [a.passed for a in result.assertions] == [True, False]


def test_an_unexecuted_plan_is_not_graded() -> None:
    """A failed execution is an outcome of its own, never a graded one."""
    plan = _plan("color magenta, resn ZN\n")
    report = _report(plan, fingerprint=None, succeeded=0)

    with pytest.raises(ValueError, match="only an executed plan"):
        grade(COLOR_ONLY, report, plan, snapshot_for(COLOR_ONLY))


def test_counts_only_sample_is_flagged_incomplete() -> None:
    """An orient sample cannot see the camera, so its grading is partial."""
    assert not grading_complete(ORIENT)
    assert grading_complete(COLOR_ONLY)
    assert grading_complete(SELECT_AND_COLOR)


def test_no_change_sample_is_flagged_vacuous() -> None:
    """A sample predicting no change is passed by any no-op plan."""
    unchanged = FINGERPRINT_PREFIX + COLOR_ONLY.structure.snapshot_sha256
    no_change = dataclasses.replace(
        COLOR_ONLY,
        assertions=tuple(
            Assertion(kind=a.kind, detail=unchanged)
            if a.kind == ASSERTION_RESULTING_SNAPSHOT
            else a
            for a in COLOR_ONLY.assertions
        ),
        verification=dataclasses.replace(
            COLOR_ONLY.verification,
            expected_fingerprint=unchanged,
            resulting_fingerprint=unchanged,
        ),
    )

    assert is_vacuous(no_change)
    assert not is_vacuous(COLOR_ONLY)


def test_inline_empty_target_is_an_empty_selection() -> None:
    """An inline target naming a chain the structure lacks selects nothing."""
    plan = _plan("color red, chain Z\n")
    report = _report(plan, fingerprint="sha256:" + "0" * 64)

    result = grade(COLOR_ONLY, report, plan, snapshot_for(COLOR_ONLY))

    assert result.empty_selection == EMPTY_SELECTION_TRUE


def test_zero_count_selection_is_an_empty_selection() -> None:
    """A named selection PyMOL counted at zero atoms is empty."""
    plan = _plan("select copilot_z, chain Z\norient copilot_z\n")
    report = _report(plan, fingerprint=None, counts=(("copilot_z", 0),))

    result = grade(ORIENT, report, plan, snapshot_for(ORIENT))

    assert result.empty_selection == EMPTY_SELECTION_TRUE


def test_a_matching_plan_selects_something() -> None:
    """The reference plan's targets all match atoms."""
    plan, report = _reference(SELECT_AND_COLOR)

    result = grade(
        SELECT_AND_COLOR, report, plan, snapshot_for(SELECT_AND_COLOR)
    )

    assert result.empty_selection == EMPTY_SELECTION_FALSE


def test_polymer_target_is_unknown_not_empty() -> None:
    """The oracle cannot evaluate `polymer`, so it is not guessed either way."""
    plan = _plan("color red, polymer\n")
    report = _report(plan, fingerprint="sha256:" + "0" * 64)

    result = grade(COLOR_ONLY, report, plan, snapshot_for(COLOR_ONLY))

    assert result.empty_selection == EMPTY_SELECTION_UNKNOWN


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
