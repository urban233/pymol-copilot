# Copyright 2026 PyMOL Copilot contributors.
"""Grading a model's executed plan against a sample's stored assertions.

TaskSuccess, as this harness defines it (SPECIFICATION.md names the
metric but never defines it; docs/master_plan.md item 16 fixes the
definition, and Martin settled it):

    A sample is a TaskSuccess when the model's final plan executed with
    status ok in a fresh sidecar and every assertion stored with the
    sample holds for that execution:

    - resulting_snapshot: the resulting-state fingerprint equals the
      stored one;
    - selection_counts: the model's selections matched the same atom
      counts as the reference's, compared as a sorted multiset with
      selection names ignored, because the prompt leaves naming to the
      model;
    - commands_succeeded: every command the model's plan contains ran
      without error. The model's command count is not compared with the
      reference's; there is more than one correct plan.

Grading is on the resulting state, never on the plan's text: the gold
set's reference plan is one correct answer, not the only one
(`pmc_data.gold_set.GoldItem`). Two properties of the *sample*, not of
the model, qualify how much a pass means, and are reported alongside
it rather than folded in:

- `grading_complete` is False when the sample has no resulting-state
  assertion (the six `orient+select` gold items are graded on selection
  counts only, because the oracle declines to predict a camera move) or
  records assertions it could not make (`unsupported_assertions`). A
  plan can pass such a sample while doing something the stored
  assertions cannot see.
- `vacuous` is True when the sample predicts no change at all
  (`Sample.predicted_no_change`): any plan that changes nothing
  observable passes it.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from dataclasses import dataclass

from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import ExecutionReport
from pmc_core.plan import ActionPlan
from pmc_core.plan import NamedSelection
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.snapshot import ObjectSnapshot
from pmc_data.oracle import selected_serials
from pmc_data.oracle import unsupported_reasons
from pmc_data.sample import ASSERTION_COMMANDS_SUCCEEDED
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import ASSERTION_SELECTION_COUNTS
from pmc_data.sample import Assertion
from pmc_data.sample import Sample

#: The version of the grading rules above. Any change to what passes an
#: assertion, or to how the empty-selection flag is computed, is a bump.
GRADER_VERSION = 1

#: The empty-selection flag's three values. "unknown" is a target the
#: independent oracle cannot evaluate (a `polymer` term): reported apart,
#: never guessed to be empty or non-empty.
EMPTY_SELECTION_TRUE = "true"
EMPTY_SELECTION_FALSE = "false"
EMPTY_SELECTION_UNKNOWN = "unknown"


@dataclass(frozen=True)
class AssertionResult:
    """One stored assertion, checked against one execution.

    Attributes:
        kind: The assertion kind, one of `pmc_data.sample`'s
            `ASSERTION_*` constants.
        passed: Whether the execution satisfies it.
        expected: What the sample stored, in a form a reader can audit.
        observed: What the execution produced, in the same form.
    """

    kind: str
    passed: bool
    expected: str
    observed: str


@dataclass(frozen=True)
class Grade:
    """A model's executed plan, graded against one sample.

    Attributes:
        assertions: Every stored assertion, checked, in stored order.
        task_success: Whether every assertion passed.
        empty_selection: Whether some target in the plan resolved to no
            atom: one of the `EMPTY_SELECTION_*` values.
    """

    assertions: tuple[AssertionResult, ...]
    task_success: bool
    empty_selection: str


def grading_complete(sample: Sample) -> bool:
    """Report whether the stored assertions see the whole resulting state.

    Args:
        sample: The stored sample.

    Returns:
        True when the sample carries a resulting-state assertion and
        records no assertion it was unable to make.
    """
    kinds = {assertion.kind for assertion in sample.assertions}
    return (
        ASSERTION_RESULTING_SNAPSHOT in kinds
        and not sample.unsupported_assertions
    )


def is_vacuous(sample: Sample) -> bool:
    """Report whether any plan changing nothing would pass this sample.

    Args:
        sample: The stored sample.

    Returns:
        True when the sample predicts the structure unchanged.
    """
    return sample.predicted_no_change


def _check(
    assertion: Assertion,
    sample: Sample,
    report: ExecutionReport,
    plan: ActionPlan,
) -> AssertionResult:
    """Check one stored assertion against one execution.

    Args:
        assertion: The stored assertion to check.
        sample: The stored sample the assertion belongs to.
        report: The model plan's execution report.
        plan: The model's executed plan.

    Returns:
        The checked assertion.

    Raises:
        ValueError: If the assertion's kind is not one this grader knows
            how to check. A new assertion kind must be graded
            deliberately, never waved through.
    """
    kind = assertion.kind
    if kind == ASSERTION_RESULTING_SNAPSHOT:
        expected = assertion.detail
        observed = report.resulting_fingerprint or ""
        return AssertionResult(
            kind=kind,
            passed=bool(expected) and observed == expected,
            expected=expected,
            observed=observed,
        )
    if kind == ASSERTION_SELECTION_COUNTS:
        expected_counts = sorted(
            count for _, count in sample.verification.selection_counts
        )
        observed_counts = sorted(
            count.atom_count for count in report.selection_counts
        )
        return AssertionResult(
            kind=kind,
            passed=observed_counts == expected_counts,
            expected=repr(expected_counts),
            observed=repr(observed_counts),
        )
    if kind == ASSERTION_COMMANDS_SUCCEEDED:
        succeeded = sum(
            1
            for outcome in report.command_outcomes
            if outcome.status == OUTCOME_OK
        )
        total = len(plan.operations)
        return AssertionResult(
            kind=kind,
            passed=succeeded == total,
            expected=f"{total} commands",
            observed=f"{succeeded} succeeded",
        )
    raise ValueError(f"no grading rule for assertion kind {kind!r}")


def _expression_empty(
    snapshot: ObjectSnapshot, expression: SelectionExpression
) -> str:
    """Report whether one inline expression selects no atom.

    Args:
        snapshot: The structure the plan ran against.
        expression: The inline selection expression.

    Returns:
        One of the `EMPTY_SELECTION_*` values.
    """
    if unsupported_reasons(expression):
        return EMPTY_SELECTION_UNKNOWN
    if selected_serials(snapshot, expression):
        return EMPTY_SELECTION_FALSE
    return EMPTY_SELECTION_TRUE


def empty_selection(
    plan: ActionPlan, report: ExecutionReport, snapshot: ObjectSnapshot
) -> str:
    """Report whether any target in an executed plan matched no atom.

    Named selections are read from the executor's own counts, which
    PyMOL computed. An inline expression target has no count of its own,
    so it is evaluated by the independent oracle against the same
    structure. A `select` operation's expression is covered by its named
    selection's count and is not evaluated twice.

    Args:
        plan: The model's executed plan.
        report: Its successful execution report.
        snapshot: The structure it ran against.

    Returns:
        `EMPTY_SELECTION_TRUE` if any target matched nothing,
        `EMPTY_SELECTION_UNKNOWN` if none did but some target could not
        be evaluated, and `EMPTY_SELECTION_FALSE` otherwise.
    """
    flags = {
        EMPTY_SELECTION_TRUE if count.atom_count == 0 else EMPTY_SELECTION_FALSE
        for count in report.selection_counts
    }
    for operation in plan.operations:
        if isinstance(operation, SelectOperation):
            continue
        target = operation.target
        if isinstance(target, NamedSelection):
            continue
        flags.add(_expression_empty(snapshot, target))
    if EMPTY_SELECTION_TRUE in flags:
        return EMPTY_SELECTION_TRUE
    if EMPTY_SELECTION_UNKNOWN in flags:
        return EMPTY_SELECTION_UNKNOWN
    return EMPTY_SELECTION_FALSE


def grade(
    sample: Sample,
    report: ExecutionReport,
    plan: ActionPlan,
    snapshot: ObjectSnapshot,
) -> Grade:
    """Grade a model's successfully executed plan against a sample.

    See the module docstring for the TaskSuccess definition this applies.

    Args:
        sample: The stored sample, carrying the assertions to check.
        report: The model plan's execution report. Must be `STATUS_OK`:
            a plan that did not execute is an outcome of its own, never
            a graded one.
        plan: The model's executed plan.
        snapshot: The structure it ran against.

    Returns:
        The grade.

    Raises:
        ValueError: If `report` is not a successful execution.
    """
    if report.status != STATUS_OK:
        raise ValueError(
            f"only an executed plan is graded; status was {report.status!r}"
        )
    results = tuple(
        _check(assertion, sample, report, plan)
        for assertion in sample.assertions
    )
    return Grade(
        assertions=results,
        task_success=all(result.passed for result in results),
        empty_selection=empty_selection(plan, report, snapshot),
    )
