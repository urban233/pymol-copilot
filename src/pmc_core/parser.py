# Copyright 2026 PyMOL Copilot contributors.
"""Total dedicated tokenizer and parser for the restricted command language.

This module owns the boundary between untrusted native .pml text and the
immutable typed plan defined in pmc_core.plan. It is a dedicated restricted
tokenizer and parser; it never delegates untrusted text to Open-Source PyMOL
parsing facilities and never dispatches partial output.

The parser is total over arbitrary text: parse_pml never raises for any
input. It returns either a complete ActionPlan or a typed ParseRejection
carrying the command index and a stable category. Case variation, comments,
quoting, line continuations, and alternate whitespace forms are all rejected
-- none of them are normalized, because normalizing is the step at which a
parser starts accepting text its author never considered.

The accepted text of a plan is exactly its canonical rendering. The grammar
has no parentheses and no optional whitespace, so parse_pml(plan.render_pml())
returns that same plan and parse_pml(text).render_pml() returns that same
text. Expanding the accepted syntax requires accepted fixtures and security
evidence in the owning design.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from dataclasses import dataclass

from pmc_core.plan import ARGUMENT_FORM_COLOR
from pmc_core.plan import ARGUMENT_FORM_EXPRESSION
from pmc_core.plan import ARGUMENT_FORM_REPRESENTATION
from pmc_core.plan import ARGUMENT_FORM_SELECTION_NAME
from pmc_core.plan import ARGUMENT_FORM_TARGET
from pmc_core.plan import COLOR_ALLOWLIST
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import MAX_EXPRESSION_TERMS
from pmc_core.plan import MAX_INPUT_BYTES
from pmc_core.plan import MAX_RESIDUE_IDENTIFIER
from pmc_core.plan import OPERATION
from pmc_core.plan import REPRESENTATION_ALLOWLIST
from pmc_core.plan import SELECTION_NAME_PREFIX
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import HetatmTerm
from pmc_core.plan import HideOperation
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

#: The digits accepted in a residue identifier.
_DIGITS = frozenset("0123456789")

#: The greatest number of digits accepted in a residue identifier.
_MAX_RESIDUE_DIGITS = len(str(MAX_RESIDUE_IDENTIFIER))

#: The negation prefix, including its one separating space.
_NEGATION_PREFIX = "not "

#: The `or` separator, including its surrounding spaces.
_OR_SEPARATOR = " or "

#: The `and` separator, including its surrounding spaces.
_AND_SEPARATOR = " and "


@dataclass(frozen=True)
class ParseRejection:
    """A typed, indexed rejection of native .pml text.

    Attributes:
        command_index: The zero-based index of the command line that
            triggered the rejection, or None when the rejection describes
            the input as a whole rather than one command line.
        category: A stable, machine-readable rejection category.
        message: A human-readable explanation of the rejection. It never
            quotes enough of the input to leak a plan back through an error.
    """

    command_index: int | None
    category: str
    message: str


#: The result of parsing: either a complete plan or a typed rejection.
type PARSE_RESULT = ActionPlan | ParseRejection
# Preserve the original runtime name for callers importing this type alias.
globals()["ParseResult"] = PARSE_RESULT

#: The result of parsing one selection expression.
type EXPRESSION_RESULT = SelectionExpression | ParseRejection
# Preserve the original runtime name for callers importing this type alias.
globals()["ExpressionResult"] = EXPRESSION_RESULT

#: The result of parsing one selection term.
type TERM_RESULT = (
    ChainTerm | ResiTerm | ResnTerm | NameTerm | HetatmTerm | PolymerTerm
) | ParseRejection
# Preserve the original runtime name for callers importing this type alias.
globals()["TermResult"] = TERM_RESULT

#: The result of parsing one command line.
type COMMAND_RESULT = (
    SelectOperation
    | ColorOperation
    | ShowOperation
    | HideOperation
    | OrientOperation
) | ParseRejection
# Preserve the original runtime name for callers importing this type alias.
globals()["CommandResult"] = COMMAND_RESULT


def parse_pml(text: str) -> PARSE_RESULT:
    """Parse restricted native .pml text into an immutable typed plan.

    This function is total: it never raises and never returns a partial
    plan. Every input either produces the complete ActionPlan it describes
    or a ParseRejection naming the command index and the category.

    Args:
        text: The native .pml source text to parse.

    Returns:
        The immutable ActionPlan when text is an accepted plan, or a
        ParseRejection describing why it was rejected.
    """
    lines = _split_lines(text)
    if isinstance(lines, ParseRejection):
        return lines

    if len(lines) > MAX_COMMANDS:
        return ParseRejection(
            command_index=None,
            category="command_count",
            message=f"plan exceeds {MAX_COMMANDS} commands",
        )

    operations: list[OPERATION] = []
    defined: set[str] = set()
    for command_index, line in enumerate(lines):
        operation = _parse_command(line, command_index=command_index)
        if isinstance(operation, ParseRejection):
            return operation

        referenced = referenced_selection_name(operation)
        if referenced is not None and referenced not in defined:
            return ParseRejection(
                command_index=command_index,
                category="undefined_selection",
                message="command references a selection no earlier command "
                "created",
            )
        if isinstance(operation, SelectOperation):
            if operation.selection_name in defined:
                return ParseRejection(
                    command_index=command_index,
                    category="duplicate_selection_name",
                    message="selection name was already created by an "
                    "earlier command",
                )
            defined.add(operation.selection_name)
        operations.append(operation)

    try:
        return ActionPlan(operations=tuple(operations))
    except ValueError as error:
        return ParseRejection(
            command_index=None,
            category="invalid_plan_shape",
            message=str(error),
        )


def parse_selection_expression(text: str) -> EXPRESSION_RESULT:
    """Parse one selection expression outside the context of a plan.

    The wire protocol uses this so a decoded plan passes through the same
    total parser as parsed text, rather than rebuilding the term tree
    straight from JSON and creating a second entry point into the typed
    contract.

    Args:
        text: The selection expression text, with no surrounding whitespace.

    Returns:
        The immutable SelectionExpression, or a ParseRejection describing
        why the text was rejected.
    """
    if not isinstance(text, str):
        return ParseRejection(
            command_index=None,
            category="invalid_selection_expression",
            message="expression is not text",
        )
    hygiene = _check_line_hygiene(text, command_index=None)
    if hygiene is not None:
        return hygiene
    return _parse_expression(text, command_index=None)


def _split_lines(text: object) -> list[str] | ParseRejection:
    """Split text into command lines, rejecting alternate line forms.

    Args:
        text: The raw native .pml source text.

    Returns:
        The ordered command lines, or a ParseRejection when text is empty,
        oversized, or uses a line-ending or blank-line form outside the
        accepted grammar.
    """
    if not isinstance(text, str):
        return ParseRejection(
            command_index=None,
            category="invalid_syntax",
            message="input is not text",
        )
    if text == "":
        return ParseRejection(
            command_index=None,
            category="empty_input",
            message="input is empty",
        )
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        return ParseRejection(
            command_index=None,
            category="invalid_syntax",
            message="input is not valid text",
        )
    if size > MAX_INPUT_BYTES:
        return ParseRejection(
            command_index=None,
            category="input_too_large",
            message=f"input exceeds {MAX_INPUT_BYTES} bytes",
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
    if not text.endswith("\n"):
        return ParseRejection(
            command_index=None,
            category="alternate_whitespace",
            message="input must end with exactly one newline",
        )

    # The final element is always the empty string after a trailing newline.
    lines = text.split("\n")[:-1]
    if any(line == "" for line in lines):
        return ParseRejection(
            command_index=None,
            category="alternate_whitespace",
            message="blank command lines are not accepted",
        )
    return lines


def _check_line_hygiene(
    line: str, command_index: int | None
) -> ParseRejection | None:
    """Reject a line using a form the grammar never normalizes away.

    Args:
        line: The command line text, without a trailing newline.
        command_index: The zero-based index of line within the input, or
            None when the text is not part of a plan.

    Returns:
        A ParseRejection when the line uses a rejected form, or None when it
        is clean.
    """
    if line != line.strip():
        return ParseRejection(
            command_index=command_index,
            category="alternate_whitespace",
            message="leading or trailing whitespace is not accepted",
        )
    if "  " in line:
        return ParseRejection(
            command_index=command_index,
            category="alternate_whitespace",
            message="repeated whitespace is not accepted",
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
    if "\\" in line:
        return ParseRejection(
            command_index=command_index,
            category="continuation",
            message="backslashes are not accepted",
        )
    return None


def _parse_command(line: str, command_index: int) -> COMMAND_RESULT:
    """Parse one command line into one typed operation.

    Args:
        line: The command line text, without a trailing newline.
        command_index: The zero-based index of line within the input.

    Returns:
        The typed operation, or a ParseRejection describing why the line was
        rejected.
    """
    hygiene = _check_line_hygiene(line, command_index=command_index)
    if hygiene is not None:
        return hygiene

    verb, separator, remainder = line.partition(" ")
    if separator == "" or remainder == "":
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message="command must have a verb and at least one argument",
        )

    rule = COMMAND_ALLOWLIST.get(verb)
    if rule is None:
        return ParseRejection(
            command_index=command_index,
            category="unknown_verb",
            message="verb is not in the command allowlist",
        )

    arguments = _split_arguments(
        remainder,
        expected=len(rule.argument_forms),
        command_index=command_index,
    )
    if isinstance(arguments, ParseRejection):
        return arguments

    values: list[object] = []
    for form, argument in zip(rule.argument_forms, arguments, strict=True):
        value = _parse_argument(form, argument, command_index=command_index)
        if isinstance(value, ParseRejection):
            return value
        values.append(value)

    return _build_operation(rule.verb, values, command_index=command_index)


def _split_arguments(
    remainder: str, expected: int, command_index: int
) -> tuple[str, ...] | ParseRejection:
    """Split a command's argument text on its one accepted comma.

    Args:
        remainder: The command text after the verb and its one space.
        expected: The number of arguments the verb's allowlist row declares.
        command_index: The zero-based index of the command within the input.

    Returns:
        The ordered argument texts, or a ParseRejection when the comma shape
        does not match the verb's declared arity.
    """
    commas = remainder.count(",")
    if commas != expected - 1:
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message=f"command must contain exactly {expected - 1} commas",
        )
    if expected == 1:
        return (remainder,)

    head, _, tail = remainder.partition(",")
    if not tail.startswith(" "):
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message="comma must be followed by exactly one space",
        )
    tail = tail[1:]
    if head == "" or tail == "":
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message="command is missing an argument",
        )
    return (head, tail)


def _parse_argument(
    form: str, argument: str, command_index: int
) -> object | ParseRejection:
    """Parse one argument according to the form its verb declares for it.

    Args:
        form: The declared argument form, from the command allowlist.
        argument: The argument text.
        command_index: The zero-based index of the command within the input.

    Returns:
        The typed argument value, or a ParseRejection describing why the
        argument was rejected.
    """
    match form:
        case _ if form == ARGUMENT_FORM_COLOR:
            if argument not in COLOR_ALLOWLIST:
                return ParseRejection(
                    command_index=command_index,
                    category="unsupported_color",
                    message="color is not in the color allowlist",
                )
            return argument
        case _ if form == ARGUMENT_FORM_REPRESENTATION:
            if argument not in REPRESENTATION_ALLOWLIST:
                return ParseRejection(
                    command_index=command_index,
                    category="unsupported_representation",
                    message="representation is not in the representation "
                    "allowlist",
                )
            return argument
        case _ if form == ARGUMENT_FORM_SELECTION_NAME:
            return _parse_selection_name(argument, command_index=command_index)
        case _ if form == ARGUMENT_FORM_EXPRESSION:
            return _parse_expression(argument, command_index=command_index)
        case _ if form == ARGUMENT_FORM_TARGET:
            return _parse_target(argument, command_index=command_index)
        case _:
            return ParseRejection(
                command_index=command_index,
                category="invalid_syntax",
                message="argument form is not recognized",
            )


def _parse_selection_name(
    argument: str, command_index: int
) -> str | ParseRejection:
    """Parse the name a select command creates.

    Args:
        argument: The candidate selection name.
        command_index: The zero-based index of the command within the input.

    Returns:
        The selection name, or a ParseRejection when it is outside the
        accepted form.
    """
    try:
        NamedSelection(argument)
    except ValueError:
        return ParseRejection(
            command_index=command_index,
            category="invalid_selection_name",
            message="selection name is outside the accepted form",
        )
    return argument


def _parse_target(argument: str, command_index: int) -> object | ParseRejection:
    """Parse what a command acts on: a named selection or an expression.

    The two forms are told apart by the first token alone. Every selection
    name starts with SELECTION_NAME_PREFIX and no expression keyword can,
    so no lookahead is needed and no input is ambiguous.

    Args:
        argument: The candidate target text.
        command_index: The zero-based index of the command within the input.

    Returns:
        The typed target, or a ParseRejection describing why it was
        rejected.
    """
    if argument.startswith(SELECTION_NAME_PREFIX):
        try:
            return NamedSelection(argument)
        except ValueError:
            return ParseRejection(
                command_index=command_index,
                category="invalid_selection_name",
                message="selection name is outside the accepted form",
            )
    return _parse_expression(argument, command_index=command_index)


def _parse_expression(
    argument: str, command_index: int | None
) -> EXPRESSION_RESULT:
    """Parse one selection expression into its typed, nested form.

    Args:
        argument: The candidate expression text.
        command_index: The zero-based index of the command within the input,
            or None when the expression is not part of a plan.

    Returns:
        The immutable SelectionExpression, or a ParseRejection describing
        why the text was rejected.
    """
    if argument == "":
        return _expression_rejection(command_index)

    clauses: list[AndClause] = []
    term_count = 0
    for clause_text in argument.split(_OR_SEPARATOR):
        factors: list[Factor] = []
        for factor_text in clause_text.split(_AND_SEPARATOR):
            negated = factor_text.startswith(_NEGATION_PREFIX)
            term_text = (
                factor_text[len(_NEGATION_PREFIX) :] if negated else factor_text
            )
            term = _parse_term(term_text, command_index=command_index)
            if isinstance(term, ParseRejection):
                return term
            term_count += 1
            if term_count > MAX_EXPRESSION_TERMS:
                return ParseRejection(
                    command_index=command_index,
                    category="expression_too_complex",
                    message=f"expression exceeds {MAX_EXPRESSION_TERMS} terms",
                )
            factors.append(Factor(term=term, negated=negated))
        try:
            clauses.append(AndClause(factors=tuple(factors)))
        except ValueError:
            return _expression_rejection(command_index)

    try:
        return SelectionExpression(clauses=tuple(clauses))
    except ValueError:
        return _expression_rejection(command_index)


def _parse_term(term_text: str, command_index: int | None) -> TERM_RESULT:
    """Parse one selection term into its typed form.

    Args:
        term_text: The candidate term text, with any negation removed.
        command_index: The zero-based index of the command within the input,
            or None when the term is not part of a plan.

    Returns:
        The immutable term, or a ParseRejection describing why the text was
        rejected.
    """
    if term_text == "hetatm":
        return HetatmTerm()
    if term_text == "polymer":
        return PolymerTerm()

    keyword, separator, value = term_text.partition(" ")
    if separator == "":
        return _expression_rejection(command_index)

    try:
        match keyword:
            case "chain":
                return ChainTerm(value)
            case "resn":
                return ResnTerm(value)
            case "name":
                return NameTerm(value)
            case "resi":
                return _parse_residue_term(value, command_index=command_index)
            case _:
                return _expression_rejection(command_index)
    except ValueError:
        return _expression_rejection(command_index)


def _parse_residue_term(value: str, command_index: int | None) -> TERM_RESULT:
    """Parse a residue identifier or a closed residue range.

    Args:
        value: The text after the `resi` keyword.
        command_index: The zero-based index of the command within the input,
            or None when the term is not part of a plan.

    Returns:
        The immutable ResiTerm, or a ParseRejection describing why the text
        was rejected.
    """
    first_text, separator, last_text = value.partition("-")
    first = _parse_residue_number(first_text)
    if first is None:
        return _expression_rejection(command_index)
    if separator == "":
        return ResiTerm(first)

    last = _parse_residue_number(last_text)
    if last is None or last < first:
        return _expression_rejection(command_index)
    return ResiTerm(first, last)


def _parse_residue_number(text: str) -> int | None:
    """Parse one residue identifier in its single canonical spelling.

    A leading zero is rejected rather than stripped: `resi 007` and
    `resi 7` would otherwise be two spellings of one value, and the
    round-trip guarantee depends on there being only one.

    Args:
        text: The candidate residue identifier text.

    Returns:
        The residue identifier, or None when the text is not one.
    """
    if not 1 <= len(text) <= _MAX_RESIDUE_DIGITS:
        return None
    if not set(text) <= _DIGITS:
        return None
    if len(text) > 1 and text.startswith("0"):
        return None
    return int(text)


def _expression_rejection(command_index: int | None) -> ParseRejection:
    """Build the rejection used for every malformed selection expression.

    Args:
        command_index: The zero-based index of the command within the input,
            or None when the expression is not part of a plan.

    Returns:
        A ParseRejection in the invalid_selection_expression category.
    """
    return ParseRejection(
        command_index=command_index,
        category="invalid_selection_expression",
        message="selection expression is outside the accepted grammar",
    )


def _build_operation(
    verb: str, values: list[object], command_index: int
) -> COMMAND_RESULT:
    """Build the typed operation for one verb from its parsed arguments.

    The isinstance checks are not ceremony. _parse_argument is driven by the
    allowlist table and returns values by argument form, so nothing but this
    function relates a verb to the concrete types its constructor demands.
    Checking here keeps a mistaken allowlist row from reaching a constructor
    with the wrong kind of value.

    Args:
        verb: The verb, already checked against the command allowlist.
        values: The parsed argument values, in the order the allowlist row
            declares them.
        command_index: The zero-based index of the command within the input.

    Returns:
        The typed operation, or a ParseRejection when the typed contract
        refuses the combination of values.
    """
    try:
        match verb:
            case "select":
                name, expression = values
                if not isinstance(name, str) or not isinstance(
                    expression, SelectionExpression
                ):
                    return _argument_rejection(command_index)
                return SelectOperation(
                    selection_name=name, expression=expression
                )
            case "color":
                color, color_target = values
                if not isinstance(color, str) or not isinstance(
                    color_target, (NamedSelection, SelectionExpression)
                ):
                    return _argument_rejection(command_index)
                return ColorOperation(color=color, target=color_target)
            case "show" | "hide":
                representation, shown_target = values
                if not isinstance(representation, str) or not isinstance(
                    shown_target, (NamedSelection, SelectionExpression)
                ):
                    return _argument_rejection(command_index)
                if verb == "show":
                    return ShowOperation(
                        representation=representation, target=shown_target
                    )
                return HideOperation(
                    representation=representation, target=shown_target
                )
            case "orient":
                (target,) = values
                if not isinstance(
                    target, (NamedSelection, SelectionExpression)
                ):
                    return _argument_rejection(command_index)
                return OrientOperation(target=target)
            case _:
                return ParseRejection(
                    command_index=command_index,
                    category="unknown_verb",
                    message="verb is not in the command allowlist",
                )
    except ValueError as error:
        return ParseRejection(
            command_index=command_index,
            category="invalid_syntax",
            message=str(error),
        )


def _argument_rejection(command_index: int) -> ParseRejection:
    """Build the rejection for an argument of the wrong kind for its verb.

    Args:
        command_index: The zero-based index of the command within the input.

    Returns:
        A ParseRejection in the invalid_syntax category.
    """
    return ParseRejection(
        command_index=command_index,
        category="invalid_syntax",
        message="argument does not match the form this verb accepts",
    )
