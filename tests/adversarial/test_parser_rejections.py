# Copyright 2026 PyMOL Copilot contributors.
"""Grammar-free adversarial coverage for the restricted parser boundary.

These tests run without any grammar or generator: every input is a literal
adversarial string. They cover the parser's total contract -- every input
either returns a complete ActionPlan or a typed, indexed ParseRejection, and
no input reaches Open-Source PyMOL.

There is one test per rejection category, and each asserts the category and,
where the rejection belongs to one command rather than the input as a whole,
the command index. Asserting the index matters: the specification requires a
denial to identify the offending command without exposing execution, and an
off-by-one there would send a repair attempt at the wrong line.

Positive round-trip coverage lives in tests/contract/test_parser.py.
"""

import sys

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import MAX_EXPRESSION_TERMS
from pmc_core.plan import MAX_INPUT_BYTES

#: A single quote, spelled indirectly so this module never has to escape one.
SINGLE_QUOTE = chr(39)

#: A backslash, spelled indirectly for the same reason.
BACKSLASH = chr(92)


def reject(text: str) -> ParseRejection:
    """Parse text and assert that it was rejected rather than accepted.

    Args:
        text: The adversarial input.

    Returns:
        The typed rejection, for the caller's further assertions.
    """
    result = parse_pml(text)

    assert isinstance(result, ParseRejection), (
        f"accepted adversarial input: {text!r}"
    )
    return result


def test_empty_input_is_rejected() -> None:
    """Empty input names its own category rather than a command."""
    rejection = reject("")

    assert rejection.category == "empty_input"
    assert rejection.command_index is None


def test_oversized_input_is_rejected_before_parsing() -> None:
    """Input past the byte bound is refused rather than walked."""
    rejection = reject("orient hetatm\n" * MAX_INPUT_BYTES)

    assert rejection.category == "input_too_large"
    assert rejection.command_index is None


def test_too_many_commands_are_rejected() -> None:
    """One command past the plan bound is refused, not truncated."""
    rejection = reject("orient hetatm\n" * (MAX_COMMANDS + 1))

    assert rejection.category == "command_count"
    assert rejection.command_index is None


@pytest.mark.parametrize(
    "text",
    [
        "# comment\norient hetatm\n",
        "orient hetatm # inline\n",
        "orient chain A\norient hetatm # inline\n",
    ],
    ids=["leading_comment", "inline_comment", "inline_comment_second_line"],
)
def test_comments_are_rejected(text: str) -> None:
    """Comments are rejected outright, never stripped or normalized.

    Args:
        text: Command text containing a comment.
    """
    assert reject(text).category == "comment"


@pytest.mark.parametrize(
    "text",
    [
        'orient "chain A"\n',
        "orient " + SINGLE_QUOTE + "chain A" + SINGLE_QUOTE + "\n",
        "select " + SINGLE_QUOTE + "copilot_a" + SINGLE_QUOTE + ", chain A\n",
        'color "red", chain A\n',
        "orient name C1" + SINGLE_QUOTE + "\n",
    ],
    ids=[
        "double_quoted_expression",
        "single_quoted_expression",
        "quoted_selection_name",
        "quoted_color",
        "primed_atom_name",
    ],
)
def test_quoting_is_rejected(text: str) -> None:
    """Quoted values are rejected rather than unquoted before matching.

    Args:
        text: Command text containing a quoted value.
    """
    rejection = reject(text)

    assert rejection.category == "quoting"
    assert rejection.command_index == 0


@pytest.mark.parametrize(
    "text",
    [
        "orient chain " + BACKSLASH + "\nA\n",
        "orient chain A" + BACKSLASH + "\norient hetatm\n",
        "orient chain A" + BACKSLASH + "\n",
    ],
    ids=[
        "continuation_within_command",
        "continuation_between_commands",
        "trailing_continuation",
    ],
)
def test_line_continuations_are_rejected(text: str) -> None:
    """Line continuations are rejected rather than joined before parsing.

    Args:
        text: Command text containing a line continuation.
    """
    assert reject(text).category == "continuation"


@pytest.mark.parametrize(
    "text",
    [
        "orient  chain A\n",
        " orient chain A\n",
        "orient chain A \n",
        "orient\tchain A\n",
        "orient chain A\r\n",
        "orient chain A",
        "\n",
        "orient chain A\n\norient hetatm\n",
        "orient chain A and  hetatm\n",
        "color red, \n",
    ],
    ids=[
        "repeated_internal_space",
        "leading_whitespace",
        "trailing_whitespace",
        "tab_separator",
        "carriage_return_line_ending",
        "missing_trailing_newline",
        "newline_only",
        "blank_line_between_commands",
        "repeated_space_in_expression",
        "empty_second_argument",
    ],
)
def test_alternate_whitespace_forms_are_rejected(text: str) -> None:
    """Alternate whitespace forms are rejected, never normalized away.

    Args:
        text: Command text using unsupported whitespace.
    """
    assert reject(text).category == "alternate_whitespace"


@pytest.mark.parametrize(
    "text",
    [
        "delete copilot_a\n",
        "SELECT copilot_a, chain A\n",
        "Select copilot_a, chain A\n",
        "COLOR red, chain A\n",
        "selects copilot_a, chain A\n",
        "orien chain A\n",
        "set ray_trace_mode, 1\n",
        "orient chain A\ndelete copilot_a\n",
    ],
    ids=[
        "unrelated_verb",
        "uppercase_verb",
        "capitalised_verb",
        "uppercase_second_verb",
        "verb_with_suffix",
        "verb_with_typo",
        "unreviewed_setting_verb",
        "unknown_verb_on_second_line",
    ],
)
def test_unknown_verbs_are_rejected(text: str) -> None:
    """A verb outside the allowlist is rejected, never partially run.

    Args:
        text: Command text containing an unknown verb.
    """
    assert reject(text).category == "unknown_verb"


def test_the_unknown_verb_rejection_names_its_command_index() -> None:
    """A rejection points at the command that caused it, not the first."""
    rejection = reject("orient chain A\norient hetatm\ndelete copilot_a\n")

    assert rejection.category == "unknown_verb"
    assert rejection.command_index == 2


@pytest.mark.parametrize(
    "text",
    [
        "orient\n",
        "orient chain A, chain B\n",
        "color red\n",
        "color red, chain A, chain B\n",
        "select copilot_a\n",
        "show cartoon\n",
        "color , chain A\n",
        "color red,chain A\n",
    ],
    ids=[
        "orient_with_no_argument",
        "orient_with_two_arguments",
        "color_with_one_argument",
        "color_with_three_arguments",
        "select_with_one_argument",
        "show_with_one_argument",
        "empty_first_argument",
        "missing_space_after_comma",
    ],
)
def test_wrong_command_arity_is_rejected(text: str) -> None:
    """A verb given the wrong number of arguments is rejected.

    Args:
        text: Command text with the wrong arity.
    """
    assert reject(text).category == "invalid_syntax"


@pytest.mark.parametrize(
    "text",
    [
        "color blurple, chain A\n",
        "color RED, chain A\n",
        "color Red, chain A\n",
        "color _deepsalmon, chain A\n",
        "color 0xff0000, chain A\n",
        "color red green, chain A\n",
    ],
    ids=[
        "invented_color",
        "uppercase_color",
        "capitalised_color",
        "internal_alias",
        "hex_color",
        "two_colors",
    ],
)
def test_colors_outside_the_allowlist_are_rejected(text: str) -> None:
    """A color the allowlist does not name is rejected before execution.

    Args:
        text: Command text naming a denied color.
    """
    assert reject(text).category == "unsupported_color"


@pytest.mark.parametrize(
    "text",
    [
        "show wireframe, chain A\n",
        "hide Cartoon, chain A\n",
        "show CARTOON, chain A\n",
        "show everything, chain A\n",
        "hide red, chain A\n",
    ],
    ids=[
        "invented_representation",
        "capitalised_representation",
        "uppercase_representation",
        "unknown_keyword",
        "color_where_a_representation_belongs",
    ],
)
def test_representations_outside_the_allowlist_are_rejected(
    text: str,
) -> None:
    """A representation the allowlist does not name is rejected.

    Args:
        text: Command text naming a denied representation.
    """
    assert reject(text).category == "unsupported_representation"


@pytest.mark.parametrize(
    "text",
    [
        "select sele, chain A\n",
        "select core, chain A\n",
        "select all, chain A\n",
        "select Copilot_a, chain A\n",
        "select copilot_, chain A\n",
        "select copilot_A, chain A\n",
        "select copilot_a-b, chain A\n",
        "select copilot_" + "x" * 25 + ", chain A\n",
        "orient copilot_\n",
        "orient copilot_A\n",
    ],
    ids=[
        "pymol_default_selection",
        "unprefixed_name",
        "reserved_keyword",
        "capitalised_prefix",
        "prefix_with_empty_body",
        "uppercase_body",
        "hyphen_in_body",
        "overlong_body",
        "target_prefix_with_empty_body",
        "target_with_uppercase_body",
    ],
)
def test_selection_names_outside_the_accepted_form_are_rejected(
    text: str,
) -> None:
    """A name that could shadow user state or the grammar is rejected.

    Args:
        text: Command text naming a denied selection name.
    """
    assert reject(text).category == "invalid_selection_name"


@pytest.mark.parametrize(
    "text",
    [
        "orient chain\n",
        "orient chain ABCDE\n",
        "orient Chain A\n",
        "orient resi\n",
        "orient resi -5\n",
        "orient resi 007\n",
        "orient resi 1000000\n",
        "orient resi 100-1\n",
        "orient resi 1-2-3\n",
        "orient resi 52A\n",
        "orient resn ala\n",
        "orient resn ALAN\n",
        "orient name ca\n",
        "orient HETATM\n",
        "orient hetatms\n",
        "orient not not hetatm\n",
        "orient not\n",
        "orient chain A and\n",
        "orient and chain A\n",
        "orient chain A or\n",
        "orient chain A AND hetatm\n",
        "orient chain A && hetatm\n",
        "orient byres chain A\n",
        "orient within 5 of chain A\n",
        "orient (chain A or chain B) and polymer\n",
        "orient all\n",
        "orient *\n",
    ],
    ids=[
        "chain_keyword_with_no_value",
        "overlong_chain",
        "capitalised_chain_keyword",
        "resi_keyword_with_no_value",
        "negative_residue",
        "residue_with_leading_zero",
        "residue_past_the_bound",
        "reversed_residue_range",
        "double_hyphen_range",
        "insertion_code",
        "lowercase_residue_name",
        "overlong_residue_name",
        "lowercase_atom_name",
        "uppercase_hetatm",
        "misspelled_hetatm",
        "double_negation",
        "dangling_not",
        "dangling_and",
        "leading_and",
        "dangling_or",
        "uppercase_operator",
        "shell_style_operator",
        "unsupported_byres_operator",
        "unsupported_within_operator",
        "parenthesised_grouping",
        "all_keyword",
        "wildcard",
    ],
)
def test_expressions_outside_the_grammar_are_rejected(text: str) -> None:
    """Only the six term forms and three operators are accepted.

    Args:
        text: Command text containing a denied selection expression.
    """
    assert reject(text).category == "invalid_selection_expression"


def test_expressions_past_the_term_bound_are_rejected() -> None:
    """One term past the complexity bound is refused, not truncated."""
    expression = " and ".join(["hetatm"] * (MAX_EXPRESSION_TERMS + 1))

    rejection = reject(f"orient {expression}\n")

    assert rejection.category == "expression_too_complex"
    assert rejection.command_index == 0


@pytest.mark.parametrize(
    ("text", "expected_index"),
    [
        ("color red, copilot_missing\n", 0),
        ("orient chain A\nshow cartoon, copilot_missing\n", 1),
        (
            "color red, copilot_a\nselect copilot_a, chain A\n",
            0,
        ),
        (
            "select copilot_a, chain A\nhide lines, copilot_b\n",
            1,
        ),
    ],
    ids=[
        "no_select_at_all",
        "reference_on_a_later_line",
        "reference_before_its_select",
        "reference_to_a_different_name",
    ],
)
def test_references_to_uncreated_selections_are_rejected(
    text: str, expected_index: int
) -> None:
    """A plan may only act on a selection it created earlier itself.

    Args:
        text: Command text referencing an uncreated selection.
        expected_index: The command index the rejection must name.
    """
    rejection = reject(text)

    assert rejection.category == "undefined_selection"
    assert rejection.command_index == expected_index


def test_creating_one_selection_name_twice_is_rejected() -> None:
    """A plan may not silently redefine a selection it already created."""
    rejection = reject("select copilot_a, chain A\nselect copilot_a, chain B\n")

    assert rejection.category == "duplicate_selection_name"
    assert rejection.command_index == 1


def test_a_rejection_never_echoes_the_input_back() -> None:
    """A rejection message explains the rule without quoting the plan.

    The specification requires a denial to identify the rule and the command
    index without exposing execution. A message that pasted the offending
    text back would leak model output through an error path.
    """
    secret = "copilot_" + "s" * 20
    rejection = reject(f"delete {secret}\n")

    assert secret not in rejection.message


def test_parser_rejection_does_not_import_pymol() -> None:
    """Rejected input does not import Open-Source PyMOL."""
    assert "pymol" not in sys.modules

    rejection = reject("delete everything\n")

    assert rejection.category == "unknown_verb"
    assert "pymol" not in sys.modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
