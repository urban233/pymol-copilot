# Copyright 2026 PyMOL Copilot contributors.
"""Grammar-free adversarial coverage for the restricted parser boundary.

These tests run without any grammar or generator: every input is a literal
adversarial string. They cover the parser's total contract -- every input
either returns the exact accepted `ActionPlan` fixture or a typed indexed
`ParseRejection`, and no input reaches Open-Source PyMOL. Categories match
the shared adversarial corpus called for by the plan-and-execution design:
unknown verbs, comments, quoting, continuations, case variation,
expression-like content, truncation, and extra commands.
"""

import pytest

from pmc_core.parser import ParseRejection, parse_pml
from pmc_core.plan import ActionPlan, initial_fixture_plan

FIXTURE_PML = (
    "select copilot_selection, chain A\ncolor red, copilot_selection\n"
)


def test_exact_positive_fixture_parses_to_the_accepted_plan() -> None:
    """The exact accepted fixture text parses to the accepted `ActionPlan`."""
    result = parse_pml(FIXTURE_PML)

    assert result == initial_fixture_plan()
    assert isinstance(result, ActionPlan)


@pytest.mark.parametrize(
    "text",
    [
        "delete copilot_selection, chain A\ncolor red, copilot_selection\n",
        "select copilot_selection, chain A\nhide red, copilot_selection\n",
        "fetch copilot_selection, chain A\ncolor red, copilot_selection\n",
    ],
    ids=["unknown_first_verb", "unknown_second_verb", "unrelated_verb"],
)
def test_unknown_verbs_are_rejected(text: str) -> None:
    """A verb outside `select`/`color` is rejected, never partially run."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)
    assert result.category == "unknown_verb"


@pytest.mark.parametrize(
    "text",
    [
        "# comment\nselect copilot_selection, chain A\n"
        "color red, copilot_selection\n",
        "select copilot_selection, chain A # inline\n"
        "color red, copilot_selection\n",
        "select copilot_selection, chain A\n"
        "color red, copilot_selection # inline\n",
    ],
    ids=["leading_comment", "inline_comment_first", "inline_comment_second"],
)
def test_comments_are_rejected(text: str) -> None:
    """Comments are rejected outright, never stripped or normalized."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)
    assert result.category == "comment"


@pytest.mark.parametrize(
    "text",
    [
        'select copilot_selection, "chain A"\ncolor red, copilot_selection\n',
        "select copilot_selection, 'chain A'\ncolor red, copilot_selection\n",
        "select 'copilot_selection', chain A\ncolor red, copilot_selection\n",
        "select copilot_selection, chain A\ncolor 'red', copilot_selection\n",
    ],
    ids=[
        "double_quoted_expression",
        "single_quoted_expression",
        "quoted_selection_name",
        "quoted_color",
    ],
)
def test_quoting_is_rejected(text: str) -> None:
    """Quoted values are rejected rather than unquoted before matching."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)
    assert result.category == "quoting"


@pytest.mark.parametrize(
    "text",
    [
        "select copilot_selection, chain \\\nA\ncolor red, copilot_selection\n",
        "select copilot_selection, chain A\\\ncolor red, copilot_selection\n",
    ],
    ids=["continuation_within_command", "continuation_between_commands"],
)
def test_line_continuations_are_rejected(text: str) -> None:
    """Line continuations are rejected rather than joined before parsing."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)
    assert result.category == "continuation"


@pytest.mark.parametrize(
    "text",
    [
        "SELECT copilot_selection, chain A\ncolor red, copilot_selection\n",
        "select copilot_selection, chain A\nCOLOR red, copilot_selection\n",
        "Select copilot_selection, Chain A\ncolor red, copilot_selection\n",
        "select copilot_selection, chain A\ncolor RED, copilot_selection\n",
    ],
    ids=[
        "uppercase_first_verb",
        "uppercase_second_verb",
        "mixed_case_expression",
        "uppercase_color_value",
    ],
)
def test_case_variation_is_rejected(text: str) -> None:
    """Case variation anywhere in the command is rejected, never folded."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)


@pytest.mark.parametrize(
    "text",
    [
        "select copilot_selection, chain A and resn ALA\n"
        "color red, copilot_selection\n",
        "select copilot_selection, chain A or chain B\n"
        "color red, copilot_selection\n",
        "select copilot_selection, __import__('os')\n"
        "color red, copilot_selection\n",
    ],
    ids=[
        "boolean_expression_extension",
        "alternate_boolean_expression",
        "python_evaluating_expression",
    ],
)
def test_expression_like_content_is_rejected(text: str) -> None:
    """Any expression beyond the exact fixture value is rejected."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "select copilot_selection, chain A\n",
        "select copilot_selection, chain A",
        "color red, copilot_selection\n",
    ],
    ids=[
        "empty_input",
        "missing_second_command",
        "missing_trailing_newline_and_second_command",
        "missing_first_command",
    ],
)
def test_truncated_input_is_rejected(text: str) -> None:
    """Truncated input never yields a partial plan."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)


@pytest.mark.parametrize(
    "text",
    [
        "select copilot_selection, chain A\ncolor red, copilot_selection\n"
        "color red, copilot_selection\n",
        "select copilot_selection, chain A\n"
        "select copilot_selection, chain A\ncolor red, copilot_selection\n",
        "select copilot_selection, chain A\ncolor red, copilot_selection\n"
        "delete copilot_selection\n",
    ],
    ids=[
        "repeated_color_command",
        "repeated_select_command",
        "extra_unrelated_command",
    ],
)
def test_extra_commands_are_rejected(text: str) -> None:
    """Extra commands beyond the exact two-command fixture are rejected."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)
    assert result.category == "command_count"


@pytest.mark.parametrize(
    "text",
    [
        "select  copilot_selection, chain A\ncolor red, copilot_selection\n",
        " select copilot_selection, chain A\ncolor red, copilot_selection\n",
        "select copilot_selection, chain A\ncolor red, copilot_selection \n",
        "select copilot_selection,chain A\ncolor red, copilot_selection\n",
        "select\tcopilot_selection, chain A\ncolor red, copilot_selection\n",
        "select copilot_selection, chain A\r\ncolor red, copilot_selection\r\n",
    ],
    ids=[
        "repeated_internal_space",
        "leading_whitespace",
        "trailing_whitespace",
        "missing_space_after_comma",
        "tab_separator",
        "carriage_return_line_ending",
    ],
)
def test_alternate_whitespace_forms_are_rejected(text: str) -> None:
    """Alternate whitespace forms are rejected, never normalized away."""
    result = parse_pml(text)

    assert isinstance(result, ParseRejection)


def test_rejection_never_calls_pymol() -> None:
    """Rejected input never imports or calls into Open-Source PyMOL."""
    import sys

    assert "pymol" not in sys.modules

    result = parse_pml("delete everything\n")

    assert isinstance(result, ParseRejection)
    assert "pymol" not in sys.modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
