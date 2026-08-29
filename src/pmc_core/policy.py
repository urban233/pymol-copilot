# Copyright 2026 PyMOL Copilot contributors.
"""Deterministic default-deny policy over typed ActionPlan operations.

This module evaluates only the immutable typed operations defined in
pmc_core.plan; it never inspects raw .pml text and never delegates a
decision to Open-Source PyMOL. The V1 policy permits exactly the
parser-produced initial fixture -- one SelectOperation that creates
copilot_selection from chain A, followed by one ColorOperation that applies
red to that selection -- and denies every other operation or
argument shape with a stable, machine-readable reason code.

Because SelectOperation, ColorOperation, and ActionPlan already reject
any value outside the recorded fixture at construction time (see
pmc_core.plan), every typed operation this policy can ever receive already
matches the fixture. The policy still evaluates each operation explicitly
so that broadening the typed contract in the future cannot silently bypass
default-deny enforcement here.
"""

from __future__ import annotations

from dataclasses import dataclass

from pmc_core.plan import ActionPlan
from pmc_core.plan import ColorOperation
from pmc_core.plan import FIXTURE_COLOR_VALUE
from pmc_core.plan import FIXTURE_SELECTION_EXPRESSION
from pmc_core.plan import FIXTURE_SELECTION_NAME
from pmc_core.plan import OPERATION
from pmc_core.plan import SelectOperation

#: Stable reason code for an operation matching the accepted fixture.
REASON_ALLOWED_FIXTURE_OPERATION = "allowed_fixture_operation"

#: Stable reason code for an operation type outside the accepted fixture.
REASON_UNSUPPORTED_OPERATION_TYPE = "unsupported_operation_type"

#: Stable reason code for a select operation with an unrecorded argument.
REASON_UNSUPPORTED_SELECT_ARGUMENTS = "unsupported_select_arguments"

#: Stable reason code for a color operation with an unrecorded argument.
REASON_UNSUPPORTED_COLOR_ARGUMENTS = "unsupported_color_arguments"

#: Stable reason code for an unsupported plan shape.
REASON_UNSUPPORTED_PLAN_SHAPE = "unsupported_plan_shape"


@dataclass(frozen=True)
class PolicyDecision:
    """A deterministic allow/deny decision for one typed operation.

    Attributes:
        operation_index: The zero-based index of the evaluated operation
            within its ActionPlan.
        allowed: Whether the operation is permitted.
        reason: A stable, machine-readable reason code for the decision.
    """

    operation_index: int
    allowed: bool
    reason: str


@dataclass(frozen=True)
class PlanDecision:
    """The aggregate policy decision for an entire ActionPlan.

    Attributes:
        decisions: The ordered per-operation decisions.
        allowed: Whether every operation in the plan is allowed. False
            when any per-operation decision denies, or when the plan shape
            itself is outside the accepted fixture.
    """

    decisions: tuple[PolicyDecision, ...]
    allowed: bool


def evaluate_operation(
    operation: OPERATION, *, operation_index: int
) -> PolicyDecision:
    """Evaluate one typed operation against the default-deny policy.

    Args:
        operation: The typed operation to evaluate. Never raw text.
        operation_index: The zero-based index of operation within its
            ActionPlan.

    Returns:
        A PolicyDecision that allows the operation only when it is
        exactly the recorded fixture value for its operation type, and
        denies it with a stable reason code otherwise.
    """
    match operation:
        case SelectOperation() if (
            operation.selection_name == FIXTURE_SELECTION_NAME
            and operation.expression == FIXTURE_SELECTION_EXPRESSION
        ):
            return PolicyDecision(
                operation_index=operation_index,
                allowed=True,
                reason=REASON_ALLOWED_FIXTURE_OPERATION,
            )
        case SelectOperation():
            return PolicyDecision(
                operation_index=operation_index,
                allowed=False,
                reason=REASON_UNSUPPORTED_SELECT_ARGUMENTS,
            )
        case ColorOperation() if (
            operation.color == FIXTURE_COLOR_VALUE
            and operation.selection_name == FIXTURE_SELECTION_NAME
        ):
            return PolicyDecision(
                operation_index=operation_index,
                allowed=True,
                reason=REASON_ALLOWED_FIXTURE_OPERATION,
            )
        case ColorOperation():
            return PolicyDecision(
                operation_index=operation_index,
                allowed=False,
                reason=REASON_UNSUPPORTED_COLOR_ARGUMENTS,
            )
        case _:
            return PolicyDecision(
                operation_index=operation_index,
                allowed=False,
                reason=REASON_UNSUPPORTED_OPERATION_TYPE,
            )


def evaluate_plan(plan: ActionPlan) -> PlanDecision:
    """Evaluate every operation in plan against the default-deny policy.

    Args:
        plan: The immutable typed plan to evaluate. Never raw text.

    Returns:
        A PlanDecision describing the per-operation decisions and the
        aggregate allow/deny outcome. The plan as a whole is allowed only
        when it has exactly the accepted two-operation select-then-color
        shape and every operation decision allows.
    """
    decisions = tuple(
        evaluate_operation(operation, operation_index=index)
        for index, operation in enumerate(plan.operations)
    )

    if (
        len(decisions) != 2
        or not isinstance(plan.operations[0], SelectOperation)
        or not isinstance(plan.operations[1], ColorOperation)
    ):
        denied_shape_decisions = tuple(
            PolicyDecision(
                operation_index=decision.operation_index,
                allowed=False,
                reason=REASON_UNSUPPORTED_PLAN_SHAPE,
            )
            for decision in decisions
        )
        return PlanDecision(decisions=denied_shape_decisions, allowed=False)

    allowed = all(decision.allowed for decision in decisions)
    return PlanDecision(decisions=decisions, allowed=allowed)
