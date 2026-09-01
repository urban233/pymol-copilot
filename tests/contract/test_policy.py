# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the typed default-deny policy.

These tests cover the deterministic policy decision over typed
ActionPlan operations only -- never raw .pml text. They demonstrate
that the exact parser-produced positive fixture is allowed, and that every
other typed operation or plan shape is denied with a stable reason code,
without any dispatcher boundary being reached.
"""

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.plan import ColorOperation
from pmc_core.plan import SelectOperation
from pmc_core.plan import initial_fixture_plan
from pmc_core.policy import REASON_ALLOWED_FIXTURE_OPERATION
from pmc_core.policy import REASON_UNSUPPORTED_COLOR_ARGUMENTS
from pmc_core.policy import REASON_UNSUPPORTED_OPERATION_TYPE
from pmc_core.policy import REASON_UNSUPPORTED_PLAN_SHAPE
from pmc_core.policy import REASON_UNSUPPORTED_SELECT_ARGUMENTS
from pmc_core.policy import PlanDecision
from pmc_core.policy import PolicyDecision
from pmc_core.policy import evaluate_operation
from pmc_core.policy import evaluate_plan

FIXTURE_PML = (
    "select copilot_selection, chain A\ncolor red, copilot_selection\n"
)


def test_initial_fixture_plan_is_allowed() -> None:
    """The exact recorded fixture plan is allowed by the policy."""
    decision = evaluate_plan(initial_fixture_plan())

    assert decision.allowed is True
    assert decision.decisions == (
        PolicyDecision(
            operation_index=0,
            allowed=True,
            reason=REASON_ALLOWED_FIXTURE_OPERATION,
        ),
        PolicyDecision(
            operation_index=1,
            allowed=True,
            reason=REASON_ALLOWED_FIXTURE_OPERATION,
        ),
    )


def test_parser_produced_fixture_plan_is_allowed() -> None:
    """The plan produced by parsing the exact fixture text is allowed."""
    plan = parse_pml(FIXTURE_PML)
    assert isinstance(plan, ActionPlan)

    decision = evaluate_plan(plan)

    assert decision.allowed is True


def test_evaluate_plan_is_deterministic() -> None:
    """Evaluating the same plan value repeatedly yields the same decision."""
    plan = initial_fixture_plan()

    assert evaluate_plan(plan) == evaluate_plan(plan)


def test_select_operation_matching_fixture_is_allowed() -> None:
    """A standalone select operation matching the fixture is allowed."""
    select_op = SelectOperation(
        selection_name="copilot_selection", expression="chain A"
    )

    decision = evaluate_operation(select_op, operation_index=0)

    assert decision == PolicyDecision(
        operation_index=0,
        allowed=True,
        reason=REASON_ALLOWED_FIXTURE_OPERATION,
    )


def test_color_operation_matching_fixture_is_allowed() -> None:
    """A standalone color operation matching the fixture is allowed."""
    color_op = ColorOperation(color="red", selection_name="copilot_selection")

    decision = evaluate_operation(color_op, operation_index=1)

    assert decision == PolicyDecision(
        operation_index=1,
        allowed=True,
        reason=REASON_ALLOWED_FIXTURE_OPERATION,
    )


class _NotAnOperation:
    """A structurally invalid stand-in for a typed operation."""


def test_non_operation_value_is_denied_by_default() -> None:
    """A value that is not a recorded operation type is denied by default."""
    decision = evaluate_operation(
        _NotAnOperation(),  # pyrefly: ignore.
        operation_index=0,
    )

    assert decision == PolicyDecision(
        operation_index=0,
        allowed=False,
        reason=REASON_UNSUPPORTED_OPERATION_TYPE,
    )


def test_string_value_is_denied_by_default() -> None:
    """A raw string, rather than a typed operation, is denied by default."""
    decision = evaluate_operation(
        "select copilot_selection, chain A",  # pyrefly: ignore.
        operation_index=0,
    )

    assert decision.allowed is False
    assert decision.reason == REASON_UNSUPPORTED_OPERATION_TYPE


def test_select_operation_with_unrecorded_arguments_is_denied() -> None:
    """A select operation outside the fixture value is denied."""
    select_op = object.__new__(SelectOperation)
    object.__setattr__(select_op, "selection_name", "other_selection")
    object.__setattr__(select_op, "expression", "chain A")

    decision = evaluate_operation(select_op, operation_index=0)

    assert decision == PolicyDecision(
        operation_index=0,
        allowed=False,
        reason=REASON_UNSUPPORTED_SELECT_ARGUMENTS,
    )


def test_color_operation_with_unrecorded_arguments_is_denied() -> None:
    """A color operation outside the fixture value is denied."""
    color_op = object.__new__(ColorOperation)
    object.__setattr__(color_op, "color", "blue")
    object.__setattr__(color_op, "selection_name", "copilot_selection")

    decision = evaluate_operation(color_op, operation_index=1)

    assert decision == PolicyDecision(
        operation_index=1,
        allowed=False,
        reason=REASON_UNSUPPORTED_COLOR_ARGUMENTS,
    )


def test_plan_with_wrong_operation_order_is_denied() -> None:
    """A plan beginning with color and ending with select is denied."""
    color_op = ColorOperation(color="red", selection_name="copilot_selection")
    select_op = SelectOperation(
        selection_name="copilot_selection", expression="chain A"
    )
    plan = object.__new__(ActionPlan)
    object.__setattr__(plan, "operations", (color_op, select_op))

    decision = evaluate_plan(plan)

    assert decision.allowed is False
    assert all(
        item.reason == REASON_UNSUPPORTED_PLAN_SHAPE
        for item in decision.decisions
    )


def test_plan_with_extra_operations_is_denied() -> None:
    """A plan with more operations than the accepted fixture is denied."""
    select_op = SelectOperation(
        selection_name="copilot_selection", expression="chain A"
    )
    color_op = ColorOperation(color="red", selection_name="copilot_selection")
    plan = object.__new__(ActionPlan)
    object.__setattr__(plan, "operations", (select_op, color_op, color_op))

    decision = evaluate_plan(plan)

    assert decision.allowed is False
    assert all(
        item.reason == REASON_UNSUPPORTED_PLAN_SHAPE
        for item in decision.decisions
    )


def test_plan_with_single_operation_is_denied() -> None:
    """A plan with only one operation is denied as an unsupported shape."""
    select_op = SelectOperation(
        selection_name="copilot_selection", expression="chain A"
    )
    plan = object.__new__(ActionPlan)
    object.__setattr__(plan, "operations", (select_op,))

    decision = evaluate_plan(plan)

    assert decision.allowed is False
    assert decision.decisions == (
        PolicyDecision(
            operation_index=0,
            allowed=False,
            reason=REASON_UNSUPPORTED_PLAN_SHAPE,
        ),
    )


def test_policy_evaluation_does_not_import_pymol() -> None:
    """Evaluating a denied plan does not import Open-Source PyMOL."""
    import sys

    assert "pymol" not in sys.modules

    select_op = SelectOperation(
        selection_name="copilot_selection", expression="chain A"
    )
    plan = object.__new__(ActionPlan)
    object.__setattr__(plan, "operations", (select_op,))

    decision = evaluate_plan(plan)

    assert isinstance(decision, PlanDecision)
    assert decision.allowed is False
    assert "pymol" not in sys.modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
