# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the immutable plan, its terms, and its allowlists.

These tests exercise the typed domain values directly, without the parser.
They cover the three properties the rest of the system leans on: every value
validates its own arguments at construction, every value has exactly one
canonical rendering, and a plan can never reference a selection it did not
itself create.
"""

from collections.abc import Callable
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.plan import ARGUMENT_FORM_COLOR
from pmc_core.plan import ARGUMENT_FORM_EXPRESSION
from pmc_core.plan import ARGUMENT_FORM_REPRESENTATION
from pmc_core.plan import ARGUMENT_FORM_SELECTION_NAME
from pmc_core.plan import ARGUMENT_FORM_TARGET
from pmc_core.plan import COLOR_ALLOWLIST
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import MAX_EXPRESSION_TERMS
from pmc_core.plan import REPRESENTATION_ALLOWLIST
from pmc_core.plan import SELECTION_NAME_PREFIX
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import HetatmTerm
from pmc_core.plan import HideOperation
from pmc_core.plan import OPERATION
from pmc_core.plan import TERM
from pmc_core.plan import NamedSelection
from pmc_core.plan import NameTerm
from pmc_core.plan import OrientOperation
from pmc_core.plan import PolymerTerm
from pmc_core.plan import ResiTerm
from pmc_core.plan import ResnTerm
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.plan import ShowOperation
from pmc_core.plan import referenced_selection_name


def bad(value: object) -> Any:
    """Launder a deliberately wrong-typed value past the type checker.

    Every call site below is a negative case where the value's *type* is
    wrong, not merely its content, and the point of the test is that
    construction refuses it at run time. Without this the type checker would
    reject the test instead of the code under test, and the check would be
    deleted rather than kept.

    Args:
        value: The deliberately invalid value.

    Returns:
        The same value, with its static type erased.
    """
    return value


#: A single-quote character, spelled without a literal quote so the parser's
#: own adversarial corpus and this module never disagree about escaping.
SINGLE_QUOTE = chr(39)


def one_term(term: TERM) -> SelectionExpression:
    """Wrap one term in the smallest expression that holds it.

    Args:
        term: The term to wrap.

    Returns:
        A one-clause, one-factor expression over term.
    """
    return SelectionExpression(clauses=(AndClause(factors=(Factor(term),)),))


def chain_a() -> SelectionExpression:
    """Build the expression `chain A`.

    Returns:
        A one-term expression matching chain A.
    """
    return one_term(ChainTerm("A"))


# --- terms ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        (ChainTerm("A"), "chain A"),
        (ChainTerm("AB12"), "chain AB12"),
        (ResiTerm(5), "resi 5"),
        (ResiTerm(1, 100), "resi 1-100"),
        (ResiTerm(7, 7), "resi 7-7"),
        (ResnTerm("ALA"), "resn ALA"),
        (ResnTerm("HOH"), "resn HOH"),
        (NameTerm("CA"), "name CA"),
        (NameTerm("OXT"), "name OXT"),
        (HetatmTerm(), "hetatm"),
        (PolymerTerm(), "polymer"),
    ],
    ids=[
        "chain_single",
        "chain_multi",
        "resi_single",
        "resi_range",
        "resi_degenerate_range",
        "resn_standard",
        "resn_water",
        "name_two_character",
        "name_three_character",
        "hetatm",
        "polymer",
    ],
)
def test_each_term_renders_its_canonical_spelling(
    term: TERM, expected: str
) -> None:
    """Every term renders the one spelling the grammar accepts for it.

    Args:
        term: The term under test.
        expected: The canonical text that term must render.
    """
    assert term.render() == expected


@pytest.mark.parametrize(
    "build",
    [
        lambda: ChainTerm(""),
        lambda: ChainTerm("ABCDE"),
        lambda: ChainTerm("A B"),
        lambda: ChainTerm("A;"),
        lambda: ChainTerm(bad(1)),
        lambda: ResiTerm(-1),
        lambda: ResiTerm(1000000),
        lambda: ResiTerm(100, 1),
        lambda: ResiTerm(True),
        lambda: ResiTerm(bad("5")),
        lambda: ResnTerm("ala"),
        lambda: ResnTerm("ALAN"),
        lambda: ResnTerm(""),
        lambda: NameTerm("ca"),
        lambda: NameTerm("C1" + SINGLE_QUOTE),
        lambda: NameTerm("ATOMS"),
    ],
    ids=[
        "empty_chain",
        "overlong_chain",
        "chain_with_space",
        "chain_with_metacharacter",
        "non_string_chain",
        "negative_resi",
        "overlarge_resi",
        "reversed_resi_range",
        "bool_resi",
        "string_resi",
        "lowercase_resn",
        "overlong_resn",
        "empty_resn",
        "lowercase_atom_name",
        "primed_atom_name",
        "overlong_atom_name",
    ],
)
def test_terms_reject_arguments_outside_their_accepted_form(
    build: Callable[[], object],
) -> None:
    """A term outside its accepted character set or range cannot exist.

    Args:
        build: A zero-argument callable constructing the rejected term.
    """
    with pytest.raises(ValueError):
        build()


# --- expressions ----------------------------------------------------------


def test_precedence_is_encoded_structurally_not_re_derived() -> None:
    """`and` binds tighter than `or`, and `not` tighter than both."""
    expression = SelectionExpression(
        clauses=(
            AndClause(
                factors=(Factor(ChainTerm("A")), Factor(ResiTerm(1, 100)))
            ),
            AndClause(factors=(Factor(HetatmTerm(), negated=True),)),
        )
    )

    assert expression.render() == "chain A and resi 1-100 or not hetatm"
    assert expression.term_count == 3


def test_negation_renders_inside_its_clause() -> None:
    """`not hetatm and polymer` negates only the term it precedes."""
    expression = SelectionExpression(
        clauses=(
            AndClause(
                factors=(
                    Factor(HetatmTerm(), negated=True),
                    Factor(PolymerTerm()),
                )
            ),
        )
    )

    assert expression.render() == "not hetatm and polymer"


def test_expression_rendering_is_idempotent() -> None:
    """Rendering the same expression twice produces identical text."""
    expression = chain_a()

    assert expression.render() == expression.render()


@pytest.mark.parametrize(
    "build",
    [
        lambda: AndClause(factors=()),
        lambda: SelectionExpression(clauses=()),
        lambda: AndClause(factors=bad((ChainTerm("A"),))),
        lambda: SelectionExpression(clauses=bad((Factor(ChainTerm("A")),))),
        lambda: Factor(term=bad("chain A")),
        lambda: Factor(term=ChainTerm("A"), negated=bad("yes")),
    ],
    ids=[
        "empty_and_clause",
        "empty_expression",
        "clause_holding_a_bare_term",
        "expression_holding_a_bare_factor",
        "factor_holding_raw_text",
        "non_boolean_negation",
    ],
)
def test_malformed_expression_structures_are_rejected(
    build: Callable[[], object],
) -> None:
    """An expression node that does not hold its own node type is rejected.

    Args:
        build: A zero-argument callable constructing the rejected value.
    """
    with pytest.raises(ValueError):
        build()


def test_expression_at_the_term_limit_is_accepted() -> None:
    """An expression holding exactly MAX_EXPRESSION_TERMS terms is valid."""
    factors = tuple(Factor(HetatmTerm()) for _ in range(MAX_EXPRESSION_TERMS))

    expression = SelectionExpression(clauses=(AndClause(factors=factors),))

    assert expression.term_count == MAX_EXPRESSION_TERMS


def test_expression_past_the_term_limit_is_rejected() -> None:
    """One term beyond MAX_EXPRESSION_TERMS is rejected, not truncated."""
    factors = tuple(
        Factor(HetatmTerm()) for _ in range(MAX_EXPRESSION_TERMS + 1)
    )

    with pytest.raises(ValueError, match="terms"):
        SelectionExpression(clauses=(AndClause(factors=factors),))


# --- selection names ------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["copilot_a", "copilot_core", "copilot_chain_a_1", "copilot_" + "x" * 24],
    ids=["shortest", "typical", "underscored", "longest"],
)
def test_accepted_selection_names(name: str) -> None:
    """A prefixed, lowercase name inside the length bound is accepted.

    Args:
        name: The selection name under test.
    """
    assert NamedSelection(name).render() == name


@pytest.mark.parametrize(
    "name",
    [
        "sele",
        "core",
        "and",
        "Copilot_a",
        "copilot_",
        "copilot_A",
        "copilot_a-b",
        "copilot_" + "x" * 25,
        "chain",
        "",
    ],
    ids=[
        "pymol_default_selection",
        "unprefixed",
        "reserved_word",
        "capitalised_prefix",
        "prefix_with_empty_body",
        "uppercase_body",
        "hyphen_in_body",
        "overlong_body",
        "keyword",
        "empty",
    ],
)
def test_rejected_selection_names(name: str) -> None:
    """A name that could shadow user state or the grammar is rejected.

    Args:
        name: The selection name under test.
    """
    with pytest.raises(ValueError, match="selection name"):
        NamedSelection(name)


def test_the_prefix_makes_names_and_expressions_disjoint() -> None:
    """No expression keyword can begin a name, which is what disambiguates.

    A target is either a name or an expression and the parser decides from
    the first token alone. That is only sound while the two first-token sets
    cannot overlap.
    """
    keywords = ("chain", "resi", "resn", "name", "hetatm", "polymer", "not")

    for keyword in keywords:
        assert not keyword.startswith(SELECTION_NAME_PREFIX)
        assert not SELECTION_NAME_PREFIX.startswith(keyword)


# --- allowlists -----------------------------------------------------------


def test_color_allowlist_is_a_sorted_unique_lowercase_set() -> None:
    """The frozen color list is well formed and holds no internal alias."""
    assert len(COLOR_ALLOWLIST) == 177
    assert len(set(COLOR_ALLOWLIST)) == len(COLOR_ALLOWLIST)
    assert list(COLOR_ALLOWLIST) == sorted(COLOR_ALLOWLIST)
    for color in COLOR_ALLOWLIST:
        assert not color.startswith("_")
        assert color == color.lower()
        assert color.replace("_", "").isalnum()


def test_representation_allowlist_matches_the_snapshot_extractor() -> None:
    """The representation list is the harness list, in the harness order."""
    assert REPRESENTATION_ALLOWLIST == (
        "lines",
        "sticks",
        "spheres",
        "dots",
        "surface",
        "mesh",
        "nonbonded",
        "nb_spheres",
        "cartoon",
        "ribbon",
        "labels",
        "slice",
        "ellipsoids",
        "volume",
    )


def test_command_allowlist_holds_exactly_the_five_accepted_verbs() -> None:
    """The allowlist table is the whole language, and nothing else."""
    assert set(COMMAND_ALLOWLIST) == {
        "select",
        "color",
        "show",
        "hide",
        "orient",
    }


@pytest.mark.parametrize(
    ("verb", "argument_forms"),
    [
        (
            "select",
            (ARGUMENT_FORM_SELECTION_NAME, ARGUMENT_FORM_EXPRESSION),
        ),
        ("color", (ARGUMENT_FORM_COLOR, ARGUMENT_FORM_TARGET)),
        (
            "show",
            (ARGUMENT_FORM_REPRESENTATION, ARGUMENT_FORM_TARGET),
        ),
        (
            "hide",
            (ARGUMENT_FORM_REPRESENTATION, ARGUMENT_FORM_TARGET),
        ),
        ("orient", (ARGUMENT_FORM_TARGET,)),
    ],
    ids=["select", "color", "show", "hide", "orient"],
)
def test_each_verb_declares_its_permitted_argument_forms(
    verb: str, argument_forms: tuple[str, ...]
) -> None:
    """Each allowlist row names the argument forms its verb accepts.

    Args:
        verb: The verb under test.
        argument_forms: The argument forms that verb must declare.
    """
    rule = COMMAND_ALLOWLIST[verb]

    assert rule.verb == verb
    assert rule.argument_forms == argument_forms


def test_command_allowlist_cannot_be_mutated() -> None:
    """The allowlist is a read-only mapping, not a dict a caller can edit."""
    with pytest.raises(TypeError):
        COMMAND_ALLOWLIST["delete"] = COMMAND_ALLOWLIST[  # pyrefly: ignore
            "select"
        ]


# --- operations -----------------------------------------------------------


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (
            SelectOperation(
                selection_name="copilot_core", expression=chain_a()
            ),
            "select copilot_core, chain A",
        ),
        (
            ColorOperation(color="red", target=NamedSelection("copilot_a")),
            "color red, copilot_a",
        ),
        (
            ColorOperation(color="marine", target=chain_a()),
            "color marine, chain A",
        ),
        (
            ShowOperation(representation="cartoon", target=chain_a()),
            "show cartoon, chain A",
        ),
        (
            HideOperation(
                representation="nb_spheres",
                target=NamedSelection("copilot_a"),
            ),
            "hide nb_spheres, copilot_a",
        ),
        (
            OrientOperation(target=one_term(HetatmTerm())),
            "orient hetatm",
        ),
    ],
    ids=[
        "select",
        "color_named_target",
        "color_expression_target",
        "show",
        "hide",
        "orient",
    ],
)
def test_each_operation_renders_one_canonical_line(
    operation: OPERATION, expected: str
) -> None:
    """Every accepted operation renders the one line the grammar accepts.

    Args:
        operation: The operation under test.
        expected: The canonical command text.
    """
    assert operation.render() == expected


@pytest.mark.parametrize(
    "build",
    [
        lambda: SelectOperation(selection_name="sele", expression=chain_a()),
        lambda: SelectOperation(
            selection_name="copilot_a", expression=bad("chain A")
        ),
        lambda: SelectOperation(
            selection_name="copilot_a",
            expression=bad(NamedSelection("copilot_b")),
        ),
        lambda: ColorOperation(color="blurple", target=chain_a()),
        lambda: ColorOperation(color="RED", target=chain_a()),
        lambda: ColorOperation(color="_deepsalmon", target=chain_a()),
        lambda: ColorOperation(color="red", target=bad("chain A")),
        lambda: ShowOperation(representation="wireframe", target=chain_a()),
        lambda: ShowOperation(representation="Cartoon", target=chain_a()),
        lambda: HideOperation(representation="", target=chain_a()),
        lambda: OrientOperation(target=bad("chain A")),
        lambda: OrientOperation(target=bad(None)),
    ],
    ids=[
        "select_unprefixed_name",
        "select_raw_text_expression",
        "select_named_selection_as_expression",
        "color_outside_allowlist",
        "color_wrong_case",
        "color_internal_alias",
        "color_raw_text_target",
        "show_outside_allowlist",
        "show_wrong_case",
        "hide_empty_representation",
        "orient_raw_text_target",
        "orient_missing_target",
    ],
)
def test_operations_reject_arguments_outside_the_allowlist(
    build: Callable[[], object],
) -> None:
    """An operation holding an argument the allowlist forbids cannot exist.

    Args:
        build: A zero-argument callable constructing the rejected operation.
    """
    with pytest.raises(ValueError):
        build()


def test_select_is_the_only_verb_that_names_a_selection() -> None:
    """Only select creates a name; the other four reference or act inline."""
    select = SelectOperation(selection_name="copilot_a", expression=chain_a())
    referencing = ColorOperation(
        color="red", target=NamedSelection("copilot_a")
    )
    inline = ColorOperation(color="red", target=chain_a())

    assert referenced_selection_name(select) is None
    assert referenced_selection_name(referencing) == "copilot_a"
    assert referenced_selection_name(inline) is None


# --- plans ----------------------------------------------------------------


def test_plan_renders_one_command_per_line_with_a_trailing_newline() -> None:
    """A plan renders as the exact commands that will execute, in order."""
    plan = ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_core", expression=chain_a()
            ),
            ColorOperation(color="red", target=NamedSelection("copilot_core")),
            OrientOperation(target=NamedSelection("copilot_core")),
        )
    )

    assert plan.render_pml() == (
        "select copilot_core, chain A\n"
        "color red, copilot_core\n"
        "orient copilot_core\n"
    )


def test_plan_rendering_is_idempotent() -> None:
    """Rendering the same plan value always produces the same bytes."""
    plan = ActionPlan(operations=(OrientOperation(target=chain_a()),))

    assert plan.render_pml() == plan.render_pml()


def test_equivalent_plans_are_equal_and_render_identically() -> None:
    """Two separately built but equal plans are indistinguishable."""
    first = ActionPlan(operations=(OrientOperation(target=chain_a()),))
    second = ActionPlan(operations=(OrientOperation(target=chain_a()),))

    assert first == second
    assert first.render_pml() == second.render_pml()


def test_plan_and_its_operations_are_immutable() -> None:
    """Neither a plan nor the values inside it can be mutated in place."""
    plan = ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_core", expression=chain_a()
            ),
        )
    )

    with pytest.raises(AttributeError):
        plan.operations = ()  # pyrefly: ignore
    with pytest.raises(AttributeError):
        plan.operations[0].selection_name = "copilot_other"  # pyrefly: ignore


def test_single_command_plan_is_accepted() -> None:
    """A one-command plan is valid; the language has no required preamble."""
    plan = ActionPlan(operations=(OrientOperation(target=chain_a()),))

    assert plan.render_pml() == "orient chain A\n"


def test_plan_at_the_command_limit_is_accepted() -> None:
    """A plan of exactly MAX_COMMANDS commands is valid."""
    operations = tuple(
        OrientOperation(target=chain_a()) for _ in range(MAX_COMMANDS)
    )

    assert len(ActionPlan(operations=operations).operations) == MAX_COMMANDS


@pytest.mark.parametrize(
    "build",
    [
        lambda: ActionPlan(operations=()),
        lambda: ActionPlan(
            operations=tuple(
                OrientOperation(target=chain_a())
                for _ in range(MAX_COMMANDS + 1)
            )
        ),
        lambda: ActionPlan(operations=bad((ChainTerm("A"),))),
        lambda: ActionPlan(operations=bad(("orient chain A",))),
        lambda: ActionPlan(
            operations=(
                ColorOperation(color="red", target=NamedSelection("copilot_a")),
            )
        ),
        lambda: ActionPlan(
            operations=(
                ColorOperation(color="red", target=NamedSelection("copilot_a")),
                SelectOperation(
                    selection_name="copilot_a", expression=chain_a()
                ),
            )
        ),
        lambda: ActionPlan(
            operations=(
                SelectOperation(
                    selection_name="copilot_a", expression=chain_a()
                ),
                SelectOperation(
                    selection_name="copilot_a", expression=chain_a()
                ),
            )
        ),
    ],
    ids=[
        "empty_plan",
        "past_the_command_limit",
        "operation_that_is_a_term",
        "operation_that_is_raw_text",
        "reference_with_no_select_at_all",
        "reference_before_its_select",
        "selection_name_defined_twice",
    ],
)
def test_malformed_plan_shapes_are_rejected(
    build: Callable[[], object],
) -> None:
    """A plan cannot act on a selection it did not itself create.

    Args:
        build: A zero-argument callable constructing the rejected plan.
    """
    with pytest.raises(ValueError):
        build()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
