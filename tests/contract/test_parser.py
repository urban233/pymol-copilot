# Copyright 2026 PyMOL Copilot contributors.
"""Positive round-trip contract tests for the restricted parser.

Every accepted plan has exactly one spelling, so the round trip is provable
in both directions: parsing canonical text and rendering it returns the same
bytes, and rendering a plan and parsing it returns the same plan. Both are
asserted for every case here, because only the pair of them rules out a
parser that quietly normalizes its input.

Negative coverage lives in tests/adversarial/.
"""

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import HetatmTerm
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import MAX_EXPRESSION_TERMS
from pmc_core.plan import NamedSelection
from pmc_core.plan import OrientOperation
from pmc_core.plan import PolymerTerm
from pmc_core.plan import ResiTerm
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression


def assert_round_trips(text: str) -> ActionPlan:
    """Assert that text round-trips through the parser in both directions.

    Args:
        text: Canonical native .pml text.

    Returns:
        The parsed plan, for any further assertions the caller needs.
    """
    plan = parse_pml(text)

    assert isinstance(plan, ActionPlan), plan
    assert plan.render_pml() == text
    assert parse_pml(plan.render_pml()) == plan
    return plan


@pytest.mark.parametrize(
    "text",
    [
        "select copilot_core, chain A\n",
        "color red, chain A\n",
        "show cartoon, chain A\n",
        "hide lines, chain A\n",
        "orient chain A\n",
    ],
    ids=["select", "color", "show", "hide", "orient"],
)
def test_each_verb_round_trips(text: str) -> None:
    """Every verb in the allowlist parses and renders back byte for byte.

    Args:
        text: Canonical one-command .pml text.
    """
    assert_round_trips(text)


@pytest.mark.parametrize(
    "text",
    [
        "select copilot_a, chain A\ncolor red, copilot_a\n",
        "select copilot_a, chain A\nshow sticks, copilot_a\n",
        "select copilot_a, chain A\nhide surface, copilot_a\n",
        "select copilot_a, chain A\norient copilot_a\n",
    ],
    ids=["color", "show", "hide", "orient"],
)
def test_each_target_verb_accepts_a_named_selection(text: str) -> None:
    """A target may be a name an earlier select in the plan created.

    Args:
        text: Canonical two-command .pml text.
    """
    assert_round_trips(text)


@pytest.mark.parametrize(
    "expression",
    [
        "chain A",
        "chain AB12",
        "resi 5",
        "resi 0",
        "resi 1-100",
        "resi 999999",
        "resn ALA",
        "resn HOH",
        "resn A",
        "name CA",
        "name OXT",
        "hetatm",
        "polymer",
    ],
    ids=[
        "chain_single",
        "chain_multi",
        "resi_single",
        "resi_zero",
        "resi_range",
        "resi_largest",
        "resn_standard",
        "resn_water",
        "resn_one_character",
        "name_two_character",
        "name_three_character",
        "hetatm",
        "polymer",
    ],
)
def test_every_term_form_round_trips(expression: str) -> None:
    """Each of the six term forms parses and renders back unchanged.

    Args:
        expression: A canonical one-term selection expression.
    """
    assert_round_trips(f"orient {expression}\n")


@pytest.mark.parametrize(
    "expression",
    [
        "not hetatm",
        "not chain A",
        "chain A and polymer",
        "chain A or chain B",
        "chain A and not hetatm",
        "chain A and resi 1-100 or hetatm",
        "not hetatm and polymer or resn ALA and name CA",
        "chain A and chain B and chain C and chain D",
        "chain A or chain B or chain C or chain D",
    ],
    ids=[
        "negated_keyword_term",
        "negated_keyword_argument_term",
        "single_and",
        "single_or",
        "and_with_negation",
        "mixed_precedence",
        "mixed_precedence_with_negation",
        "repeated_and",
        "repeated_or",
    ],
)
def test_boolean_expressions_round_trip(expression: str) -> None:
    """and, or and not combine and render back in one canonical spelling.

    Args:
        expression: A canonical boolean selection expression.
    """
    assert_round_trips(f"orient {expression}\n")


def test_precedence_parses_as_or_over_and() -> None:
    """`chain A and resi 1-100 or hetatm` groups the `and` tighter."""
    plan = assert_round_trips("orient chain A and resi 1-100 or hetatm\n")
    operation = plan.operations[0]
    assert isinstance(operation, OrientOperation)
    target = operation.target

    assert isinstance(target, SelectionExpression)
    assert target == SelectionExpression(
        clauses=(
            AndClause(
                factors=(Factor(ChainTerm("A")), Factor(ResiTerm(1, 100)))
            ),
            AndClause(factors=(Factor(HetatmTerm()),)),
        )
    )


def test_negation_binds_to_one_term_only() -> None:
    """`not hetatm and polymer` negates hetatm and not the whole clause."""
    plan = assert_round_trips("orient not hetatm and polymer\n")
    operation = plan.operations[0]
    assert isinstance(operation, OrientOperation)
    target = operation.target

    assert target == SelectionExpression(
        clauses=(
            AndClause(
                factors=(
                    Factor(HetatmTerm(), negated=True),
                    Factor(PolymerTerm()),
                )
            ),
        )
    )


def test_a_realistic_multi_command_plan_round_trips() -> None:
    """A plan that defines two selections and acts on both round-trips."""
    text = (
        "select copilot_core, chain A and polymer\n"
        "select copilot_ligands, hetatm and not resn HOH\n"
        "show cartoon, copilot_core\n"
        "color marine, copilot_core\n"
        "show sticks, copilot_ligands\n"
        "color yellow, copilot_ligands\n"
        "orient copilot_core\n"
    )

    plan = assert_round_trips(text)

    assert len(plan.operations) == 7


def test_the_parser_accepts_a_plan_at_the_command_limit() -> None:
    """A plan of exactly MAX_COMMANDS commands parses."""
    text = "orient chain A\n" * MAX_COMMANDS

    plan = assert_round_trips(text)

    assert len(plan.operations) == MAX_COMMANDS


def test_the_parser_accepts_an_expression_at_the_term_limit() -> None:
    """An expression of exactly MAX_EXPRESSION_TERMS terms parses."""
    expression = " and ".join(["hetatm"] * MAX_EXPRESSION_TERMS)

    plan = assert_round_trips(f"orient {expression}\n")
    operation = plan.operations[0]
    assert isinstance(operation, OrientOperation)
    target = operation.target

    assert isinstance(target, SelectionExpression)
    assert target.term_count == MAX_EXPRESSION_TERMS


def test_a_selection_may_be_referenced_more_than_once() -> None:
    """One select can serve several later commands."""
    text = (
        "select copilot_a, chain A\n"
        "color red, copilot_a\n"
        "show cartoon, copilot_a\n"
        "orient copilot_a\n"
    )

    assert_round_trips(text)


def test_a_plan_built_by_hand_renders_to_text_the_parser_accepts() -> None:
    """The plan-to-text-to-plan direction holds for a hand-built plan."""
    plan = ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_core",
                expression=SelectionExpression(
                    clauses=(
                        AndClause(factors=(Factor(ChainTerm("A")),)),
                        AndClause(
                            factors=(Factor(HetatmTerm(), negated=True),)
                        ),
                    )
                ),
            ),
            ColorOperation(
                color="deepteal", target=NamedSelection("copilot_core")
            ),
        )
    )

    assert parse_pml(plan.render_pml()) == plan


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
