# Copyright 2026 PyMOL Copilot contributors.
"""Total dedicated tokenizer and parser for the initial restricted plan.

This module owns the boundary between untrusted native `.pml` text and the
immutable typed plan defined in `pmc_core.plan`. It is a dedicated restricted
tokenizer and parser; it never delegates untrusted text to Open-Source PyMOL
parsing facilities and never dispatches partial output.

The parser is total over arbitrary text: `parse_pml` never raises for any
input. It returns either the complete `ActionPlan` for the exact accepted
fixture or a typed, indexed `ParseRejection` describing why the input was
rejected. Case variation, comments, quoting, line continuations, and
alternate whitespace forms are all rejected -- none of them are normalized.
Expanding the accepted syntax requires accepted fixtures and security
evidence in the owning design.
"""

from __future__ import annotations

from dataclasses import dataclass

from pmc_core.plan import ActionPlan, ColorOperation, SelectOperation

#: The only verb accepted on the first command line.
_SELECT_VERB = "select"

#: The only verb accepted on the second command line.
_COLOR_VERB = "color"

#: The exact number of commands accepted by the initial fixture.
_EXPECTED_COMMAND_COUNT = 2


@dataclass(frozen=True)
class ParseRejection:
    """A typed, indexed rejection of native `.pml` text.

    Attributes:
        command_index: The zero-based index of the command line that
            triggered the rejection, or `None` when the rejection describes
            the input as a whole rather than one command line.
        category: A stable, machine-readable rejection category.
        message: A human-readable explanation of the rejection.
    """

    command_index: int | None
    category: str
    message: str


#: The result of parsing: either a complete plan or a typed rejection.
ParseResult = ActionPlan | ParseRejection


def parse_pml(text: str) -> ParseResult:
    """Parse restricted native `.pml` text into an immutable typed plan.

    This function is total: it never raises and never returns a partial
    plan. It accepts only the exact recorded fixture -- one `select`
    command line followed by one `color` command line, each in the exact
    accepted canonical form -- and rejects every other input.

    Args:
        text: The native `.pml` source text to parse.

    Returns:
        The immutable `ActionPlan` when `text` is exactly the accepted
        fixture, or a `ParseRejection` describing why it was rejected.
    """
    lines = _split_lines(text)
    if isinstance(lines, ParseRejection):
        return lines

    if len(lines) != _EXPECTED_COMMAND_COUNT:
        return ParseRejection(
            command_index=None,
            category="command_count",
            message=(
                f"expected exactly {_EXPECTED_COMMAND_COUNT} commands, "
                f"found {len(lines)}"
            ),
        )

    select_command = _tokenize_command(lines[0], command_index=0)
    if isinstance(select_command, ParseRejection):
        return select_command
    verb, arguments = select_command
    if verb != _SELECT_VERB:
        return ParseRejection(
            command_index=0,
            category="unknown_verb",
            message=f"unknown verb: {verb!r}",
        )
    try:
        select_operation = SelectOperation(
            selection_name=arguments[0], expression=arguments[1]
        )
    except ValueError as error:
        return ParseRejection(
            command_index=0, category="unsupported_value", message=str(error)
        )

    color_command = _tokenize_command(lines[1], command_index=1)
    if isinstance(color_command, ParseRejection):
        return color_command
    verb, arguments = color_command
    if verb != _COLOR_VERB:
        return ParseRejection(
            command_index=1,
            category="unknown_verb",
            message=f"unknown verb: {verb!r}",
        )
    try:
        color_operation = ColorOperation(
            color=arguments[0], selection_name=arguments[1]
        )
    except ValueError as error:
        return ParseRejection(
            command_index=1, category="unsupported_value", message=str(error)
        )

    try:
        return ActionPlan(operations=(select_operation, color_operation))
    except ValueError as error:
        return ParseRejection(
            command_index=None, category="unsupported_value", message=str(error)
        )


def _split_lines(text: str) -> list[str] | ParseRejection:
    """Split `text` into command lines, rejecting alternate line forms.

    Args:
        text: The raw native `.pml` source text.

    Returns:
        The ordered command lines, or a `ParseRejection` when `text` is
        empty or uses a line-ending or blank-line form outside the
        accepted fixture.
    """
    if text == "":
        return ParseRejection(
            command_index=None, category="empty_input", message="input is empty"
        )
    if "\r" in text:
        return ParseRejection(
            command_index=None,
            category="alternate_whitespace",
            message="carriage returns are not accepted",
        )
    if "\t" in text:
        return ParseRejection(
            command_index=None,
            category="alternate_whitespace",
            message="tab characters are not accepted",
        )
    if "\\\n" in text:
        return ParseRejection(
            command_index=None,
            category="continuation",
            message="line continuations are not accepted",
        )
    if "#" in text:
        return ParseRejection(
            command_index=None,
            category="comment",
            message="comments are not accepted",
        )

    lines = text.split("\n")
    if lines and lines[-1] == "":
        # A single trailing newline is the only accepted line-ending form.
        lines = lines[:-1]
    if any(line == "" for line in lines):
        return ParseRejection(
            command_index=None,
            category="alternate_whitespace",
            message="blank command lines are not accepted",
        )
    return lines


def _tokenize_command(
    line: str, command_index: int
) -> tuple[str, tuple[str, str]] | ParseRejection:
    """Tokenize one command line into a verb and its two arguments.

    Args:
        line: The command line text, without a trailing newline.
        command_index: The zero-based index of `line` within the input.

    Returns:
        A `(verb, (first_argument, second_argument))` pair when `line`
        matches the accepted `"<verb> <argument>, <argument>"` shape, or a
        `ParseRejection` describing why it does not.
    """
    if line != line.strip():
        return ParseRejection(
            command_index=command_index,
            category="alternate_whitespace",
            message="leading or trailing whitespace is not accepted",
        )
    if "#" in line:
        return ParseRejection(
            command_index=command_index,
            category="comment",
            message="comments are not accepted",
        )
    if "'" in line or '"' in line:
        return ParseRejection(
            command_index=command_index,
            category="quoting",
            message="quoted values are not accepted",
        )
    if line.endswith("\\"):
        return ParseRejection(
            command_index=command_index,
            category="continuation",
            message="line continuations are not accepted",
        )
    if "  " in line:
        return ParseRejection(
            command_index=command_index,
            category="alternate_whitespace",
            message="repeated whitespace is not accepted",
        )
    if line.count(",") != 1:
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message="command must contain exactly one comma",
        )

    head, _, tail = line.partition(",")
    if not tail.startswith(" "):
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message="comma must be followed by exactly one space",
        )
    tail = tail[1:]
    if " " not in head:
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message="command must contain a verb and a first argument",
        )

    verb, _, first_argument = head.partition(" ")
    if verb == "" or first_argument == "" or tail == "":
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message="command is missing a verb or an argument",
        )
    return verb, (first_argument, tail)
