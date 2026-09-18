# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the typed default-deny policy.

The policy evaluates typed ActionPlan operations only -- never raw .pml
text. Its job is to reach the same verdict as the parser by a separate
route, so most of these tests hand it values that could never have come from
the parser: operations assembled with object.__new__ and object.__setattr__,
which reaches a frozen dataclass without ever running its __post_init__
checks. That is the shape a bug or a bypass would produce, and it is the
only way to prove the policy is doing its own work rather than inheriting a
guarantee from construction.

tests/contract/test_policy_sabotage.py runs this module against a copy of
pmc_core whose default-deny branch has been flipped to allow, and requires
test_non_operation_value_is_denied_by_default to fail. Do not rename that
test without updating the sabotage check.
"""

import sys
from dataclasses import dataclass
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import HetatmTerm
from pmc_core.plan import HideOperation
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import MAX_EXPRESSION_TERMS
from pmc_core.plan import NamedSelection
from pmc_core.plan import OrientOperation
from pmc_core.plan import ResiTerm
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.plan import ShowOperation
from pmc_core.policy import REASON_ALLOWED_OPERATION
from pmc_core.policy import REASON_DUPLICATE_SELECTION_NAME
from pmc_core.policy import REASON_UNDEFINED_SELECTION_REFERENCE
from pmc_core.policy import REASON_UNSUPPORTED_COLOR_ARGUMENTS
from pmc_core.policy import REASON_UNSUPPORTED_HIDE_ARGUMENTS
from pmc_core.policy import REASON_UNSUPPORTED_OPERATION_TYPE
from pmc_core.policy import REASON_UNSUPPORTED_ORIENT_ARGUMENTS
from pmc_core.policy import REASON_UNSUPPORTED_PLAN_SHAPE
from pmc_core.policy import REASON_UNSUPPORTED_SELECT_ARGUMENTS
from pmc_core.policy import REASON_UNSUPPORTED_SHOW_ARGUMENTS
from pmc_core.policy import evaluate_operation
from pmc_core.policy import evaluate_plan


class _NotAnOperation:
    """A structurally invalid stand-in for a typed operation."""


def chain_a() -> SelectionExpression:
    """Build the expression `chain A`.

    Returns:
        A one-term expression matching chain A.
    """
    return SelectionExpression(
        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
    )


def bypass(operation_type: type, **fields: object) -> Any:
    """Assemble a frozen dataclass without running its own checks.

    This is how a bug, or a caller reaching past the typed contract, would
    produce a value the constructors would have refused.

    Args:
        operation_type: The frozen dataclass to assemble.
        **fields: The field values to install directly.

    Returns:
        The assembled value, with no validation performed. Typed Any so the
        deliberately invalid values below reach the functions under test
        rather than being refused by the type checker first.
    """
    value = object.__new__(operation_type)
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    return value


# --- allow paths ----------------------------------------------------------


@pytest.mark.parametrize(
    "operation",
    [
        SelectOperation(selection_name="copilot_a", expression=chain_a()),
        ColorOperation(color="red", target=chain_a()),
        ColorOperation(color="red", target=NamedSelection("copilot_a")),
        ShowOperation(representation="cartoon", target=chain_a()),
        HideOperation(representation="surface", target=chain_a()),
        OrientOperation(target=chain_a()),
    ],
    ids=[
        "select",
        "color_expression_target",
        "color_named_target",
        "show",
        "hide",
        "orient",
    ],
)
def test_allowlisted_operations_are_allowed(operation: Any) -> None:
    """Each allowlisted verb with allowlisted arguments is permitted.

    Args:
        operation: The operation under test.
    """
    decision = evaluate_operation(operation, operation_index=0)

    assert decision.allowed
    assert decision.reason == REASON_ALLOWED_OPERATION
    assert decision.operation_index == 0


def test_a_parser_produced_plan_is_allowed() -> None:
    """The policy agrees with the parser on a plan the parser accepted."""
    plan = parse_pml(
        "select copilot_core, chain A and not hetatm\n"
        "show cartoon, copilot_core\n"
        "color marine, copilot_core\n"
        "orient resi 1-100\n"
    )

    assert isinstance(plan, ActionPlan)
    decision = evaluate_plan(plan)

    assert decision.allowed
    assert len(decision.decisions) == 4
    assert all(
        item.reason == REASON_ALLOWED_OPERATION for item in decision.decisions
    )


def test_evaluate_plan_is_deterministic() -> None:
    """Evaluating the same plan value twice yields the same decision."""
    plan = ActionPlan(operations=(OrientOperation(target=chain_a()),))

    assert evaluate_plan(plan) == evaluate_plan(plan)


def test_the_allowlist_table_matches_the_policy_dispatch() -> None:
    """Each allowlist row names the operation type the policy evaluates.

    The policy dispatches on concrete operation types while the parser
    dispatches on the table. This is what keeps those two from drifting.
    """
    assert {
        verb: rule.operation_type for verb, rule in COMMAND_ALLOWLIST.items()
    } == {
        "select": SelectOperation,
        "color": ColorOperation,
        "show": ShowOperation,
        "hide": HideOperation,
        "orient": OrientOperation,
    }


# --- default deny ---------------------------------------------------------


def test_non_operation_value_is_denied_by_default() -> None:
    """A structurally invalid value is denied, never allowed by omission."""
    not_an_operation: Any = _NotAnOperation()

    decision = evaluate_operation(not_an_operation, operation_index=0)

    assert not decision.allowed
    assert decision.reason == REASON_UNSUPPORTED_OPERATION_TYPE


@pytest.mark.parametrize(
    "value",
    [
        "select copilot_a, chain A",
        None,
        42,
        chain_a(),
        ChainTerm("A"),
        NamedSelection("copilot_a"),
        ("select", "copilot_a"),
    ],
    ids=[
        "raw_command_text",
        "none",
        "integer",
        "bare_expression",
        "bare_term",
        "bare_named_selection",
        "tuple_of_strings",
    ],
)
def test_values_outside_the_operation_types_are_denied(value: Any) -> None:
    """Nothing but an allowlisted operation type can be allowed.

    Args:
        value: The non-operation value under test.
    """
    decision = evaluate_operation(value, operation_index=3)

    assert not decision.allowed
    assert decision.reason == REASON_UNSUPPORTED_OPERATION_TYPE
    assert decision.operation_index == 3


# --- bypassed construction ------------------------------------------------


@pytest.mark.parametrize(
    ("operation", "expected_reason"),
    [
        (
            bypass(
                SelectOperation,
                selection_name="sele",
                expression=chain_a(),
            ),
            REASON_UNSUPPORTED_SELECT_ARGUMENTS,
        ),
        (
            bypass(
                SelectOperation,
                selection_name="copilot_a",
                expression="chain A",
            ),
            REASON_UNSUPPORTED_SELECT_ARGUMENTS,
        ),
        (
            bypass(
                SelectOperation,
                selection_name="copilot_a",
                expression=SelectionExpression.__new__(SelectionExpression),
            ),
            REASON_UNSUPPORTED_SELECT_ARGUMENTS,
        ),
        (
            bypass(ColorOperation, color="blurple", target=chain_a()),
            REASON_UNSUPPORTED_COLOR_ARGUMENTS,
        ),
        (
            bypass(ColorOperation, color="_deepsalmon", target=chain_a()),
            REASON_UNSUPPORTED_COLOR_ARGUMENTS,
        ),
        (
            bypass(ColorOperation, color="red", target="chain A"),
            REASON_UNSUPPORTED_COLOR_ARGUMENTS,
        ),
        (
            bypass(ShowOperation, representation="wireframe", target=chain_a()),
            REASON_UNSUPPORTED_SHOW_ARGUMENTS,
        ),
        (
            bypass(HideOperation, representation="", target=chain_a()),
            REASON_UNSUPPORTED_HIDE_ARGUMENTS,
        ),
        (
            bypass(OrientOperation, target=None),
            REASON_UNSUPPORTED_ORIENT_ARGUMENTS,
        ),
        (
            bypass(OrientOperation, target=bypass(NamedSelection, name="sele")),
            REASON_UNSUPPORTED_ORIENT_ARGUMENTS,
        ),
        (
            bypass(
                OrientOperation,
                target=bypass(
                    SelectionExpression,
                    clauses=(
                        bypass(
                            AndClause,
                            factors=(
                                bypass(
                                    Factor,
                                    term=bypass(ChainTerm, chain_id="A;B"),
                                    negated=False,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            REASON_UNSUPPORTED_ORIENT_ARGUMENTS,
        ),
        (
            bypass(
                OrientOperation,
                target=bypass(
                    SelectionExpression,
                    clauses=(
                        bypass(
                            AndClause,
                            factors=(
                                bypass(
                                    Factor,
                                    term=bypass(ResiTerm, first=-5, last=None),
                                    negated=False,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            REASON_UNSUPPORTED_ORIENT_ARGUMENTS,
        ),
        (
            bypass(
                OrientOperation,
                target=bypass(SelectionExpression, clauses=()),
            ),
            REASON_UNSUPPORTED_ORIENT_ARGUMENTS,
        ),
        (
            bypass(
                OrientOperation,
                target=bypass(
                    SelectionExpression,
                    clauses=(bypass(AndClause, factors=()),),
                ),
            ),
            REASON_UNSUPPORTED_ORIENT_ARGUMENTS,
        ),
        (
            bypass(
                OrientOperation,
                target=bypass(
                    SelectionExpression,
                    clauses=(
                        bypass(
                            AndClause,
                            factors=(
                                bypass(
                                    Factor,
                                    term=HetatmTerm(),
                                    negated="yes",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            REASON_UNSUPPORTED_ORIENT_ARGUMENTS,
        ),
    ],
    ids=[
        "select_name_without_prefix",
        "select_expression_is_raw_text",
        "select_expression_missing_its_fields",
        "color_outside_allowlist",
        "color_internal_alias",
        "color_target_is_raw_text",
        "show_representation_outside_allowlist",
        "hide_representation_empty",
        "orient_target_is_none",
        "orient_named_target_without_prefix",
        "orient_term_with_metacharacter",
        "orient_term_with_negative_residue",
        "orient_expression_with_no_clauses",
        "orient_clause_with_no_factors",
        "orient_factor_with_non_boolean_negation",
    ],
)
def test_operations_that_bypassed_construction_are_denied(
    operation: Any, expected_reason: str
) -> None:
    """The policy re-derives argument validity instead of assuming it.

    Args:
        operation: An operation assembled without its own checks.
        expected_reason: The stable reason code the policy must record.
    """
    decision = evaluate_operation(operation, operation_index=0)

    assert not decision.allowed
    assert decision.reason == expected_reason


# --- plan shape -----------------------------------------------------------


@pytest.mark.parametrize(
    "operations",
    [
        (),
        tuple(
            OrientOperation(target=chain_a()) for _ in range(MAX_COMMANDS + 1)
        ),
    ],
    ids=["empty_plan", "past_the_command_limit"],
)
def test_plans_outside_the_length_bounds_are_denied(
    operations: tuple[Any, ...],
) -> None:
    """A plan shorter or longer than the accepted bounds is denied.

    Args:
        operations: The operation tuple installed on the bypassed plan.
    """
    plan = bypass(ActionPlan, operations=operations)

    decision = evaluate_plan(plan)

    assert not decision.allowed
    assert all(
        item.reason == REASON_UNSUPPORTED_PLAN_SHAPE
        for item in decision.decisions
    )


def test_a_plan_acting_on_a_selection_it_never_created_is_denied() -> None:
    """A reference with no earlier select is denied at the plan level."""
    plan = bypass(
        ActionPlan,
        operations=(
            ColorOperation(color="red", target=NamedSelection("copilot_a")),
        ),
    )

    decision = evaluate_plan(plan)

    assert not decision.allowed
    assert decision.decisions[0].reason == (
        REASON_UNDEFINED_SELECTION_REFERENCE
    )


def test_a_plan_referencing_a_later_selection_is_denied() -> None:
    """Order matters: a selection must exist before it is acted on."""
    plan = bypass(
        ActionPlan,
        operations=(
            ColorOperation(color="red", target=NamedSelection("copilot_a")),
            SelectOperation(selection_name="copilot_a", expression=chain_a()),
        ),
    )

    decision = evaluate_plan(plan)

    assert not decision.allowed
    assert decision.decisions[0].reason == (
        REASON_UNDEFINED_SELECTION_REFERENCE
    )
    assert decision.decisions[1].allowed


def test_a_plan_creating_one_selection_name_twice_is_denied() -> None:
    """A plan may not redefine a name it already created."""
    select = SelectOperation(selection_name="copilot_a", expression=chain_a())
    plan = bypass(ActionPlan, operations=(select, select))

    decision = evaluate_plan(plan)

    assert not decision.allowed
    assert decision.decisions[1].reason == REASON_DUPLICATE_SELECTION_NAME


@pytest.mark.parametrize(
    "value",
    [None, "select copilot_a, chain A", 0],
    ids=["none", "raw_text", "integer"],
)
def test_values_that_are_not_plans_are_denied(value: Any) -> None:
    """evaluate_plan denies anything that is not an ActionPlan at all.

    Args:
        value: The non-plan value under test.
    """
    decision = evaluate_plan(value)

    assert not decision.allowed


def test_one_denied_operation_denies_the_whole_plan() -> None:
    """A plan is allowed only when every one of its commands is allowed."""
    plan = bypass(
        ActionPlan,
        operations=(
            OrientOperation(target=chain_a()),
            bypass(ColorOperation, color="blurple", target=chain_a()),
        ),
    )

    decision = evaluate_plan(plan)

    assert not decision.allowed
    assert decision.decisions[0].allowed
    assert not decision.decisions[1].allowed


def test_policy_evaluation_does_not_import_pymol() -> None:
    """Evaluating a denied plan never imports Open-Source PyMOL."""
    assert "pymol" not in sys.modules

    decision = evaluate_plan(
        bypass(
            ActionPlan,
            operations=(bypass(ColorOperation, color="!", target=None),),
        )
    )

    assert not decision.allowed
    assert "pymol" not in sys.modules


def test_a_value_that_merely_looks_like_a_plan_is_denied() -> None:
    """Duck typing is not enough: the policy requires the real type.

    The earlier test only passed values with no `operations` field at all,
    so it was satisfied by the missing-field fallback and never exercised
    the type check itself.
    """

    @dataclass(frozen=True)
    class LooksLikeAPlan:
        """A value carrying the right field name and the wrong type."""

        operations: tuple[Any, ...]

    looks_like_a_plan: Any = LooksLikeAPlan(
        operations=(OrientOperation(target=chain_a()),)
    )

    decision = evaluate_plan(looks_like_a_plan)

    assert not decision.allowed


@dataclass(frozen=True)
class _LooksLikeAFactor:
    """A value with a Factor's fields and not its type."""

    term: Any
    negated: bool


@dataclass(frozen=True)
class _LooksLikeAClause:
    """A value with an AndClause's fields and not its type."""

    factors: tuple[Any, ...]


def test_a_duck_typed_clause_is_denied() -> None:
    """An expression's clauses must be AndClause, not merely clause-shaped.

    The clause here holds a genuine Factor, so the factor guard cannot be
    what denies it. Isolating the two guards matters: a test whose fake
    clause also held a fake factor would pass with either guard removed, and
    would therefore protect neither.
    """
    operation = bypass(
        OrientOperation,
        target=bypass(
            SelectionExpression,
            clauses=(_LooksLikeAClause(factors=(Factor(HetatmTerm()),)),),
        ),
    )

    decision = evaluate_operation(operation, operation_index=0)

    assert not decision.allowed
    assert decision.reason == REASON_UNSUPPORTED_ORIENT_ARGUMENTS


def test_a_duck_typed_factor_is_denied() -> None:
    """A clause's factors must be Factor, not merely factor-shaped.

    The clause here is a genuine AndClause carrying a fake factor, so the
    clause guard cannot be what denies it.
    """
    operation = bypass(
        OrientOperation,
        target=bypass(
            SelectionExpression,
            clauses=(
                bypass(
                    AndClause,
                    factors=(
                        _LooksLikeAFactor(term=HetatmTerm(), negated=False),
                    ),
                ),
            ),
        ),
    )

    decision = evaluate_operation(operation, operation_index=0)

    assert not decision.allowed
    assert decision.reason == REASON_UNSUPPORTED_ORIENT_ARGUMENTS


def test_a_subclass_cannot_supply_its_own_validator() -> None:
    """A term subclass overriding __post_init__ is denied, not trusted.

    isinstance would admit it and re-running `type(value)`'s own rules would
    call the override. The policy pins the exact allowlisted type instead,
    because a value that validates itself makes the module's whole claim
    false. Without this, the subclass below smuggles a second command line
    into the rendered .pml.
    """

    class UnvalidatedChain(ChainTerm):
        """A ChainTerm that skips its own charset rules."""

        def __post_init__(self) -> None:
            """Accept anything."""

    smuggled: Any = UnvalidatedChain("A\nrun /tmp/evil.py")
    plan = bypass(
        ActionPlan,
        operations=(
            OrientOperation(
                target=SelectionExpression(
                    clauses=(AndClause(factors=(Factor(smuggled),)),)
                )
            ),
        ),
    )

    assert "\n" in plan.operations[0].render()
    assert not evaluate_plan(plan).allowed


def test_the_policy_enforces_the_expression_term_bound_itself() -> None:
    """The policy re-derives the complexity bound, not just the parser.

    This is one of two bounds the policy is meant to enforce independently.
    A bypassed expression is the only way to reach it, because the parser
    refuses to build one this large in the first place.
    """
    factors = tuple(
        Factor(HetatmTerm()) for _ in range(MAX_EXPRESSION_TERMS + 1)
    )
    operation = bypass(
        OrientOperation,
        target=bypass(
            SelectionExpression,
            clauses=(bypass(AndClause, factors=factors),),
        ),
    )

    decision = evaluate_operation(operation, operation_index=0)

    assert not decision.allowed
    assert decision.reason == REASON_UNSUPPORTED_ORIENT_ARGUMENTS


def test_a_denied_plan_shape_denies_every_operation_individually() -> None:
    """The shape denial sets each per-operation flag, not only the total."""
    plan = bypass(ActionPlan, operations=())

    decision = evaluate_plan(
        bypass(
            ActionPlan,
            operations=tuple(
                OrientOperation(target=chain_a())
                for _ in range(MAX_COMMANDS + 1)
            ),
        )
    )

    assert not evaluate_plan(plan).allowed
    assert decision.decisions
    assert all(not item.allowed for item in decision.decisions)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
