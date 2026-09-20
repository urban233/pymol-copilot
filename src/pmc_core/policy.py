# Copyright 2026 PyMOL Copilot contributors.
"""Deterministic default-deny policy over typed ActionPlan operations.

This module evaluates only the immutable typed operations defined in
pmc_core.plan; it never inspects raw .pml text and never delegates a
decision to Open-Source PyMOL. It permits exactly the five allowlisted verbs
carrying allowlisted arguments, and denies every other operation, argument
shape, or plan shape with a stable, machine-readable reason code.

This policy assumes the typed value it is handed may be a lie. The operation
dataclasses in pmc_core.plan validate their own arguments at construction,
but construction can be bypassed -- object.__new__ plus object.__setattr__
reaches a frozen dataclass without ever running __post_init__, and that is
exactly the shape a bug or an attacker would produce. So every check here is
re-derived from the operation's own fields against the declarative allowlist
tables, never inherited from whatever pmc_core.parser concluded. The parser
and this module reach the same verdict by two separate routes; neither is
evidence for the other.

Leaf values are re-validated by reconstructing them through their own
dataclass rules rather than by restating those rules here, so a charset or
range rule cannot drift between the two modules. The structure around those
leaves -- clause nesting, term counts, plan length, and the rule that a plan
may only act on a selection it created -- is checked explicitly.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import fields
from dataclasses import is_dataclass

from pmc_core.plan import COLOR_ALLOWLIST
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import MAX_EXPRESSION_TERMS
from pmc_core.plan import OPERATION
from pmc_core.plan import REPRESENTATION_ALLOWLIST
from pmc_core.plan import TERM_TYPES
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import HideOperation
from pmc_core.plan import NamedSelection
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.plan import ShowOperation
from pmc_core.plan import referenced_selection_name

#: This module's own command-policy contract version. An int, matching
#: pmc_core.plan's tables that it re-derives its verdict from, and stamped
#: into every prompt by pmc_core.prompt so a generated sample records the
#: policy that was in force when it was made. Bump it for any change to
#: the allowlist tables or to a verdict evaluate_plan() returns for input
#: it previously accepted -- a narrowing invalidates earlier samples, and
#: a reader has to be able to tell which side of the change one came from.
#: pmc_data.gold_case.ContractVersions.plan_version records the same idea
#: as a free-form string today; item 14 rewrites that module and is where
#: the two should be joined up.
POLICY_VERSION = 1

#: Stable reason code for an operation the allowlist permits.
REASON_ALLOWED_OPERATION = "allowed_operation"

#: Stable reason code for an operation type outside the allowlist.
REASON_UNSUPPORTED_OPERATION_TYPE = "unsupported_operation_type"

#: Stable reason code for a select operation with a denied argument.
REASON_UNSUPPORTED_SELECT_ARGUMENTS = "unsupported_select_arguments"

#: Stable reason code for a color operation with a denied argument.
REASON_UNSUPPORTED_COLOR_ARGUMENTS = "unsupported_color_arguments"

#: Stable reason code for a show operation with a denied argument.
REASON_UNSUPPORTED_SHOW_ARGUMENTS = "unsupported_show_arguments"

#: Stable reason code for a hide operation with a denied argument.
REASON_UNSUPPORTED_HIDE_ARGUMENTS = "unsupported_hide_arguments"

#: Stable reason code for an orient operation with a denied argument.
REASON_UNSUPPORTED_ORIENT_ARGUMENTS = "unsupported_orient_arguments"

#: Stable reason code for an unsupported plan shape.
REASON_UNSUPPORTED_PLAN_SHAPE = "unsupported_plan_shape"

#: Stable reason code for a command acting on a selection no earlier
#: command in the same plan created.
REASON_UNDEFINED_SELECTION_REFERENCE = "undefined_selection_reference"

#: Stable reason code for a plan creating one selection name twice.
REASON_DUPLICATE_SELECTION_NAME = "duplicate_selection_name"

#: Returned when a value does not carry a field at all. A value assembled
#: without running __init__ can be missing any field, and reading one must
#: produce a denial rather than an AttributeError: this module is called on
#: decoded input, where a crash is a worse outcome than a deny.
_MISSING: object = object()


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
            itself is outside the accepted form.
    """

    decisions: tuple[PolicyDecision, ...]
    allowed: bool


def _field(value: object, name: str) -> object:
    """Read one field from a value that may never have been constructed.

    Args:
        value: The value to read from.
        name: The field name.

    Returns:
        The field's value, or a sentinel that fails every type check below
        when the value does not carry that field at all.
    """
    return getattr(value, name, _MISSING)


def _reconstructs(value: object, expected_type: type) -> bool:
    """Re-run a value's construction rules, as its allowlisted type defines.

    Calling the value's own type with its own current field values runs
    __init__ and therefore __post_init__ again, so a value assembled without
    ever running those checks is caught here. Re-running the value's own
    rules rather than restating them keeps a charset or range rule from
    drifting between pmc_core.plan and this module.

    The type must match exactly rather than by isinstance, and the rules
    re-run are the allowlisted type's own. A subclass overriding
    __post_init__ would otherwise supply its own validator and pass:
    isinstance admits it, and reconstructing through type(value) would call
    the override rather than the real check. That is outside this module's
    primary threat model, which is construction bypass rather than
    attacker-controlled classes, but the module's claim is that every check
    is re-derived from the allowlist, and a value choosing its own validator
    would make that claim false.

    Args:
        value: The frozen dataclass value to re-validate.
        expected_type: The allowlisted type the value must be, exactly.

    Returns:
        True when the allowlisted type's own rules accept these fields.
    """
    # Both callers today already pin the exact type before calling this, so
    # mutation testing reports this line as redundant -- removing it alone
    # changes no test. It stays because this is a general helper and the
    # next caller may not pin it, and because the cost of the redundancy is
    # one identity comparison against the cost of a value that validates
    # itself.
    if type(value) is not expected_type:
        return False
    if not is_dataclass(value) or isinstance(value, type):
        return False
    constructor: Callable[..., object] = expected_type
    try:
        arguments = {
            field.name: getattr(value, field.name) for field in fields(value)
        }
        constructor(**arguments)
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _term_is_allowed(term: object) -> bool:
    """Check that a value is an accepted selection term.

    Args:
        term: The candidate term.

    Returns:
        True when term is an allowlisted term type whose own rules accept
        its current fields.
    """
    term_type = type(term)
    if term_type not in TERM_TYPES:
        return False
    return _reconstructs(term, term_type)


def _expression_is_allowed(expression: object) -> bool:
    """Check that a value is a well-formed, bounded selection expression.

    Args:
        expression: The candidate expression.

    Returns:
        True when expression is a SelectionExpression of non-empty clauses
        of non-empty factors over allowlisted terms, within the term bound.
    """
    if type(expression) is not SelectionExpression:
        return False
    clauses = _field(expression, "clauses")
    if not isinstance(clauses, tuple) or not clauses:
        return False

    term_count = 0
    for clause in clauses:
        if type(clause) is not AndClause:
            return False
        factors = _field(clause, "factors")
        if not isinstance(factors, tuple) or not factors:
            return False
        for factor in factors:
            if type(factor) is not Factor:
                return False
            if not isinstance(_field(factor, "negated"), bool):
                return False
            if not _term_is_allowed(_field(factor, "term")):
                return False
            term_count += 1
    return term_count <= MAX_EXPRESSION_TERMS


def _target_is_allowed(target: object) -> bool:
    """Check that a value is an accepted command target.

    Args:
        target: The candidate target.

    Returns:
        True when target is a well-formed named selection or a well-formed
        selection expression.
    """
    if type(target) is NamedSelection:
        return _reconstructs(target, NamedSelection)
    return _expression_is_allowed(target)


def _select_is_allowed(operation: SelectOperation) -> bool:
    """Check a select operation's arguments against the allowlist.

    Args:
        operation: The select operation to check.

    Returns:
        True when the created name and the assigned expression are both
        within their accepted forms.
    """
    if type(operation) is not SelectOperation:
        return False
    selection_name = _field(operation, "selection_name")
    if not isinstance(selection_name, str):
        return False
    try:
        NamedSelection(selection_name)
    except ValueError:
        return False
    return _expression_is_allowed(_field(operation, "expression"))


def _color_is_allowed(operation: ColorOperation) -> bool:
    """Check a color operation's arguments against the allowlist.

    Args:
        operation: The color operation to check.

    Returns:
        True when the color is in COLOR_ALLOWLIST and the target is
        well formed.
    """
    if type(operation) is not ColorOperation:
        return False
    color = _field(operation, "color")
    if not isinstance(color, str):
        return False
    if color not in COLOR_ALLOWLIST:
        return False
    return _target_is_allowed(_field(operation, "target"))


def _representation_is_allowed(
    operation: ShowOperation | HideOperation,
) -> bool:
    """Check a show or hide operation's arguments against the allowlist.

    Args:
        operation: The show or hide operation to check.

    Returns:
        True when the representation is in REPRESENTATION_ALLOWLIST and the
        target is well formed.
    """
    if type(operation) not in (ShowOperation, HideOperation):
        return False
    representation = _field(operation, "representation")
    if not isinstance(representation, str):
        return False
    if representation not in REPRESENTATION_ALLOWLIST:
        return False
    return _target_is_allowed(_field(operation, "target"))


def _decide(
    *, operation_index: int, allowed: bool, denial_reason: str
) -> PolicyDecision:
    """Build the decision for one operation whose type is allowlisted.

    Args:
        operation_index: The zero-based index of the evaluated operation.
        allowed: Whether the operation's arguments passed every check.
        denial_reason: The stable reason code to record when they did not.

    Returns:
        The PolicyDecision for this operation.
    """
    if allowed:
        return PolicyDecision(
            operation_index=operation_index,
            allowed=True,
            reason=REASON_ALLOWED_OPERATION,
        )
    return PolicyDecision(
        operation_index=operation_index,
        allowed=False,
        reason=denial_reason,
    )


def evaluate_operation(
    operation: OPERATION, *, operation_index: int
) -> PolicyDecision:
    """Evaluate one typed operation against the default-deny policy.

    Args:
        operation: The typed operation to evaluate. Never raw text.
        operation_index: The zero-based index of operation within its
            ActionPlan.

    Returns:
        A PolicyDecision that allows the operation only when its type is one
        of the five allowlisted verbs and every one of its arguments is
        within its allowlisted form, and denies it with a stable reason code
        otherwise.
    """
    match operation:
        case SelectOperation():
            return _decide(
                operation_index=operation_index,
                allowed=_select_is_allowed(operation),
                denial_reason=REASON_UNSUPPORTED_SELECT_ARGUMENTS,
            )
        case ColorOperation():
            return _decide(
                operation_index=operation_index,
                allowed=_color_is_allowed(operation),
                denial_reason=REASON_UNSUPPORTED_COLOR_ARGUMENTS,
            )
        case ShowOperation():
            return _decide(
                operation_index=operation_index,
                allowed=_representation_is_allowed(operation),
                denial_reason=REASON_UNSUPPORTED_SHOW_ARGUMENTS,
            )
        case HideOperation():
            return _decide(
                operation_index=operation_index,
                allowed=_representation_is_allowed(operation),
                denial_reason=REASON_UNSUPPORTED_HIDE_ARGUMENTS,
            )
        case OrientOperation():
            return _decide(
                operation_index=operation_index,
                allowed=type(operation) is OrientOperation
                and _target_is_allowed(_field(operation, "target")),
                denial_reason=REASON_UNSUPPORTED_ORIENT_ARGUMENTS,
            )
        case _:
            return PolicyDecision(
                operation_index=operation_index,
                allowed=False,
                reason=REASON_UNSUPPORTED_OPERATION_TYPE,
            )


def _denied_plan_shape(count: int) -> PlanDecision:
    """Build the aggregate decision for a plan whose shape is denied.

    Args:
        count: The number of operations the plan claimed to hold.

    Returns:
        A denying PlanDecision with one shape denial per operation.
    """
    return PlanDecision(
        decisions=tuple(
            PolicyDecision(
                operation_index=index,
                allowed=False,
                reason=REASON_UNSUPPORTED_PLAN_SHAPE,
            )
            for index in range(count)
        ),
        allowed=False,
    )


def evaluate_plan(plan: ActionPlan) -> PlanDecision:
    """Evaluate every operation in plan against the default-deny policy.

    The plan-level rules are re-derived here rather than trusted from
    whatever produced the plan: a plan must hold between one and
    MAX_COMMANDS operations, must not create one selection name twice, and
    must never act on a selection no earlier operation in the same plan
    created.

    Args:
        plan: The immutable typed plan to evaluate. Never raw text.

    Returns:
        A PlanDecision describing the per-operation decisions and the
        aggregate allow/deny outcome.
    """
    if type(plan) is not ActionPlan:
        return _denied_plan_shape(0)
    operations = _field(plan, "operations")
    if not isinstance(operations, tuple):
        return _denied_plan_shape(0)
    if not 1 <= len(operations) <= MAX_COMMANDS:
        return _denied_plan_shape(len(operations))

    decisions = [
        evaluate_operation(operation, operation_index=index)
        for index, operation in enumerate(operations)
    ]

    defined: set[str] = set()
    for index, operation in enumerate(operations):
        referenced = referenced_selection_name(operation)
        if referenced is not None and referenced not in defined:
            decisions[index] = PolicyDecision(
                operation_index=index,
                allowed=False,
                reason=REASON_UNDEFINED_SELECTION_REFERENCE,
            )
        selection_name = _field(operation, "selection_name")
        if isinstance(operation, SelectOperation) and isinstance(
            selection_name, str
        ):
            if selection_name in defined:
                decisions[index] = PolicyDecision(
                    operation_index=index,
                    allowed=False,
                    reason=REASON_DUPLICATE_SELECTION_NAME,
                )
            defined.add(selection_name)

    allowed = all(decision.allowed for decision in decisions)
    return PlanDecision(decisions=tuple(decisions), allowed=allowed)
