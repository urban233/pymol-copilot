# Copyright 2026 PyMOL Copilot contributors.
"""Immutable typed plan and operation contracts for the restricted language.

This module defines the frozen domain values of the V1 restricted command
language: the six selection-expression terms, the boolean structure that
combines them, one operation dataclass per accepted verb, the explicit
allowlist table mapping each verb to its permitted argument forms, and the
canonical, idempotent rendering of a plan back to native .pml text.

No parser and no policy live here. Every value validates its own arguments at
construction time, so a typed operation that exists at all is one the
allowlist permits. pmc_core.parser turns untrusted text into these values and
pmc_core.policy re-derives its verdict from them independently; neither
trusts the other.

The grammar has no parentheses and no optional whitespace, so every plan value
has exactly one rendering and every accepted text has exactly one parse.
Operator precedence -- `not`, then `and`, then `or`, as in Open-Source PyMOL's
own selection algebra -- is encoded structurally by the SelectionExpression ->
AndClause -> Factor nesting rather than re-derived when rendering, which is
what makes rendering canonical by construction rather than by convention.

Validation here uses explicit character-set membership rather than regular
expressions. This is a security boundary evaluated on untrusted model output,
and a character-set test has no pathological input. Broadening any allowlist
in this module requires security evidence in the owning design.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

#: The required prefix for every selection name a plan creates. It keeps a
#: plan from replacing a selection the user built by hand, and it is what
#: makes a target unambiguous: no selection expression can begin with it, so
#: a target's first token decides whether it is a name or an expression.
SELECTION_NAME_PREFIX = "copilot_"

#: The maximum number of commands accepted in one plan.
MAX_COMMANDS = 128

#: The maximum number of terms accepted in one selection expression.
MAX_EXPRESSION_TERMS = 32

#: The maximum size, in bytes, of native .pml text the parser will consider.
MAX_INPUT_BYTES = 16384

#: The maximum length of the body that follows SELECTION_NAME_PREFIX.
MAX_SELECTION_NAME_BODY = 24

#: The largest accepted residue identifier. Residue identifiers are
#: non-negative in V1 so that the `resi N-M` range form splits on its one
#: hyphen without ambiguity; negative identifiers and insertion codes are
#: declared unsupported rather than silently mishandled.
MAX_RESIDUE_IDENTIFIER = 999999

#: The maximum length of a chain identifier.
MAX_CHAIN_IDENTIFIER = 4

#: The maximum length of a residue name.
MAX_RESIDUE_NAME = 3

#: The maximum length of an atom name. Primed nucleic-acid atom names such as
#: C1' are unsupported in V1: the apostrophe is denied by the parser's quoting
#: rule, and admitting it would reopen quote handling across the parser.
MAX_ATOM_NAME = 4

_LOWERCASE = frozenset("abcdefghijklmnopqrstuvwxyz")
_UPPERCASE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DIGITS = frozenset("0123456789")

#: Characters accepted in the body of a selection name.
_SELECTION_NAME_CHARACTERS = _LOWERCASE | _DIGITS | frozenset("_")

#: Characters accepted in a chain identifier. Chain identifiers are
#: case-sensitive in the PDB, so both cases are accepted here even though
#: every keyword in the language is lowercase-only.
_CHAIN_CHARACTERS = _LOWERCASE | _UPPERCASE | _DIGITS

#: Characters accepted in a residue name.
_RESIDUE_NAME_CHARACTERS = _UPPERCASE | _DIGITS

#: Characters accepted in an atom name.
_ATOM_NAME_CHARACTERS = _UPPERCASE | _DIGITS


def _check_token(
    value: object,
    *,
    allowed: frozenset[str],
    maximum: int,
    description: str,
) -> str:
    """Check one argument token against its accepted character set.

    Args:
        value: The candidate token. Rejected unless it is a str.
        allowed: The characters this token may contain.
        maximum: The greatest accepted length. The least is always one.
        description: The token's name, used in the raised message.

    Returns:
        The checked token.

    Raises:
        ValueError: If value is not a str, is empty, is longer than maximum,
            or contains a character outside allowed.
    """
    if not isinstance(value, str):
        raise ValueError(f"unsupported {description}: {value!r}")
    if not 1 <= len(value) <= maximum:
        raise ValueError(f"unsupported {description}: {value!r}")
    if not set(value) <= allowed:
        raise ValueError(f"unsupported {description}: {value!r}")
    return value


def _check_selection_name(value: object) -> str:
    """Check a selection name against the prefix and character rules.

    Args:
        value: The candidate selection name.

    Returns:
        The checked selection name.

    Raises:
        ValueError: If value is not a str, does not start with
            SELECTION_NAME_PREFIX, or has a body outside the accepted
            character set or length.
    """
    if not isinstance(value, str) or not value.startswith(
        SELECTION_NAME_PREFIX
    ):
        raise ValueError(f"unsupported selection name: {value!r}")
    body = value[len(SELECTION_NAME_PREFIX) :]
    try:
        _check_token(
            body,
            allowed=_SELECTION_NAME_CHARACTERS,
            maximum=MAX_SELECTION_NAME_BODY,
            description="selection name",
        )
    except ValueError:
        raise ValueError(f"unsupported selection name: {value!r}")
    return value


@dataclass(frozen=True)
class ChainTerm:
    """A selection term matching one chain identifier.

    Attributes:
        chain_id: The chain identifier this term matches.
    """

    chain_id: str

    def __post_init__(self) -> None:
        """Reject a chain identifier outside the accepted form.

        Raises:
            ValueError: If chain_id is outside the accepted form.
        """
        _check_token(
            self.chain_id,
            allowed=_CHAIN_CHARACTERS,
            maximum=MAX_CHAIN_IDENTIFIER,
            description="chain identifier",
        )

    def render(self) -> str:
        """Render this term as its one canonical spelling.

        Returns:
            The canonical term text.
        """
        return f"chain {self.chain_id}"


@dataclass(frozen=True)
class ResiTerm:
    """A selection term matching one residue identifier or a closed range.

    Attributes:
        first: The residue identifier, or the start of the range.
        last: The inclusive end of the range, or None for a single residue.
    """

    first: int
    last: int | None = None

    def __post_init__(self) -> None:
        """Reject a residue identifier or range outside the accepted form.

        Raises:
            ValueError: If either bound is not an int in range, or if the
                range end precedes its start.
        """
        for bound in (self.first, self.last):
            if bound is None:
                continue
            if isinstance(bound, bool) or not isinstance(bound, int):
                raise ValueError(f"unsupported residue identifier: {bound!r}")
            if not 0 <= bound <= MAX_RESIDUE_IDENTIFIER:
                raise ValueError(f"unsupported residue identifier: {bound!r}")
        if self.last is not None and self.last < self.first:
            raise ValueError(
                f"unsupported residue range: {self.first}-{self.last}"
            )

    def render(self) -> str:
        """Render this term as its one canonical spelling.

        Returns:
            The canonical term text.
        """
        if self.last is None:
            return f"resi {self.first}"
        return f"resi {self.first}-{self.last}"


@dataclass(frozen=True)
class ResnTerm:
    """A selection term matching one residue name.

    Attributes:
        residue_name: The residue name this term matches.
    """

    residue_name: str

    def __post_init__(self) -> None:
        """Reject a residue name outside the accepted form.

        Raises:
            ValueError: If residue_name is outside the accepted form.
        """
        _check_token(
            self.residue_name,
            allowed=_RESIDUE_NAME_CHARACTERS,
            maximum=MAX_RESIDUE_NAME,
            description="residue name",
        )

    def render(self) -> str:
        """Render this term as its one canonical spelling.

        Returns:
            The canonical term text.
        """
        return f"resn {self.residue_name}"


@dataclass(frozen=True)
class NameTerm:
    """A selection term matching one atom name.

    Attributes:
        atom_name: The atom name this term matches.
    """

    atom_name: str

    def __post_init__(self) -> None:
        """Reject an atom name outside the accepted form.

        Raises:
            ValueError: If atom_name is outside the accepted form.
        """
        _check_token(
            self.atom_name,
            allowed=_ATOM_NAME_CHARACTERS,
            maximum=MAX_ATOM_NAME,
            description="atom name",
        )

    def render(self) -> str:
        """Render this term as its one canonical spelling.

        Returns:
            The canonical term text.
        """
        return f"name {self.atom_name}"


@dataclass(frozen=True)
class HetatmTerm:
    """A selection term matching every hetero atom."""

    def render(self) -> str:
        """Render this term as its one canonical spelling.

        Returns:
            The canonical term text.
        """
        return "hetatm"


@dataclass(frozen=True)
class PolymerTerm:
    """A selection term matching every polymer atom."""

    def render(self) -> str:
        """Render this term as its one canonical spelling.

        Returns:
            The canonical term text.
        """
        return "polymer"


#: The accepted selection-expression terms.
type TERM = (
    ChainTerm | ResiTerm | ResnTerm | NameTerm | HetatmTerm | PolymerTerm
)
# Preserve the original runtime name for callers importing this type alias.
globals()["Term"] = TERM

#: The concrete term types, for isinstance checks that must not rely on the
#: type alias being introspectable at runtime.
TERM_TYPES: tuple[type, ...] = (
    ChainTerm,
    ResiTerm,
    ResnTerm,
    NameTerm,
    HetatmTerm,
    PolymerTerm,
)


@dataclass(frozen=True)
class Factor:
    """One term, optionally negated. The tightest-binding expression node.

    Attributes:
        term: The term this factor matches.
        negated: Whether the term's match is inverted.
    """

    term: TERM
    negated: bool = False

    def __post_init__(self) -> None:
        """Reject a factor that does not wrap an accepted term.

        Raises:
            ValueError: If term is not an accepted term type, or if negated
                is not a bool.
        """
        if not isinstance(self.term, TERM_TYPES):
            raise ValueError(f"unsupported selection term: {self.term!r}")
        if not isinstance(self.negated, bool):
            raise ValueError(f"unsupported negation flag: {self.negated!r}")

    def render(self) -> str:
        """Render this factor as its one canonical spelling.

        Returns:
            The canonical factor text.
        """
        if self.negated:
            return f"not {self.term.render()}"
        return self.term.render()


@dataclass(frozen=True)
class AndClause:
    """One or more factors combined with `and`.

    Attributes:
        factors: The ordered factors this clause intersects.
    """

    factors: tuple[Factor, ...]

    def __post_init__(self) -> None:
        """Reject a clause that is empty or holds a non-factor.

        Raises:
            ValueError: If factors is not a non-empty tuple of Factor values.
        """
        if not isinstance(self.factors, tuple) or not self.factors:
            raise ValueError("and clause must contain at least one factor")
        for factor in self.factors:
            if not isinstance(factor, Factor):
                raise ValueError(f"unsupported factor: {factor!r}")

    def render(self) -> str:
        """Render this clause as its one canonical spelling.

        Returns:
            The canonical clause text.
        """
        return " and ".join(factor.render() for factor in self.factors)


@dataclass(frozen=True)
class SelectionExpression:
    """One or more and-clauses combined with `or`.

    The nesting is the precedence: `not` binds inside a Factor, `and` inside
    an AndClause, and `or` across clauses. `chain A and resi 1-100 or hetatm`
    is therefore two clauses, matching Open-Source PyMOL's own precedence.

    Attributes:
        clauses: The ordered clauses this expression unions.
    """

    clauses: tuple[AndClause, ...]

    def __post_init__(self) -> None:
        """Reject an expression that is empty, malformed, or too complex.

        Raises:
            ValueError: If clauses is not a non-empty tuple of AndClause
                values, or if the expression holds more than
                MAX_EXPRESSION_TERMS terms.
        """
        if not isinstance(self.clauses, tuple) or not self.clauses:
            raise ValueError("expression must contain at least one clause")
        for clause in self.clauses:
            if not isinstance(clause, AndClause):
                raise ValueError(f"unsupported and clause: {clause!r}")
        if self.term_count > MAX_EXPRESSION_TERMS:
            raise ValueError(f"expression exceeds {MAX_EXPRESSION_TERMS} terms")

    @property
    def term_count(self) -> int:
        """Count every term in this expression.

        Returns:
            The total number of terms across every clause.
        """
        return sum(len(clause.factors) for clause in self.clauses)

    def render(self) -> str:
        """Render this expression as its one canonical spelling.

        Returns:
            The canonical expression text.
        """
        return " or ".join(clause.render() for clause in self.clauses)


@dataclass(frozen=True)
class NamedSelection:
    """A reference to a selection an earlier command in the plan created.

    Attributes:
        name: The referenced selection name.
    """

    name: str

    def __post_init__(self) -> None:
        """Reject a selection name outside the accepted form.

        Raises:
            ValueError: If name is outside the accepted form.
        """
        _check_selection_name(self.name)

    def render(self) -> str:
        """Render this reference as its one canonical spelling.

        Returns:
            The canonical reference text.
        """
        return self.name


#: What may stand where a command expects something to act on: either a
#: selection an earlier command created, or a selection expression.
type TARGET = NamedSelection | SelectionExpression
# Preserve the original runtime name for callers importing this type alias.
globals()["Target"] = TARGET

#: The concrete target types, for isinstance checks.
TARGET_TYPES: tuple[type, ...] = (NamedSelection, SelectionExpression)


#: Every color name Open-Source PyMOL defines, excluding its one
#: underscore-prefixed internal alias. Generated once from
#: cmd.get_color_indices() against pymol-open-source-whl 3.2.0.2 and frozen
#: here: pmc_core must never import PyMOL, so this list cannot be read from
#: PyMOL at runtime. tests/integration/test_real_pymol_allowlist.py proves
#: every name below is still a color PyMOL knows.
COLOR_ALLOWLIST: tuple[str, ...] = (
    "actinium",
    "aluminum",
    "americium",
    "antimony",
    "aquamarine",
    "argon",
    "arsenic",
    "astatine",
    "barium",
    "berkelium",
    "beryllium",
    "bismuth",
    "black",
    "blue",
    "bluewhite",
    "bohrium",
    "boron",
    "brightorange",
    "bromine",
    "brown",
    "cadmium",
    "calcium",
    "californium",
    "carbon",
    "cerium",
    "cesium",
    "chartreuse",
    "chlorine",
    "chocolate",
    "chromium",
    "cobalt",
    "copper",
    "curium",
    "cyan",
    "darksalmon",
    "dash",
    "deepblue",
    "deepolive",
    "deeppurple",
    "deepsalmon",
    "deepteal",
    "density",
    "deuterium",
    "dirtyviolet",
    "dubnium",
    "dysprosium",
    "einsteinium",
    "erbium",
    "europium",
    "fermium",
    "firebrick",
    "fluorine",
    "forest",
    "francium",
    "gadolinium",
    "gallium",
    "germanium",
    "gold",
    "gray",
    "green",
    "greencyan",
    "grey",
    "hafnium",
    "hassium",
    "helium",
    "holmium",
    "hotpink",
    "hydrogen",
    "indium",
    "iodine",
    "iridium",
    "iron",
    "krypton",
    "lanthanum",
    "lawrencium",
    "lead",
    "lightblue",
    "lightmagenta",
    "lightorange",
    "lightpink",
    "lightteal",
    "lime",
    "limegreen",
    "limon",
    "lithium",
    "lonepair",
    "lutetium",
    "magenta",
    "magnesium",
    "manganese",
    "marine",
    "meitnerium",
    "mendelevium",
    "mercury",
    "molybdenum",
    "neodymium",
    "neon",
    "neptunium",
    "nickel",
    "niobium",
    "nitrogen",
    "nobelium",
    "olive",
    "orange",
    "osmium",
    "oxygen",
    "palecyan",
    "palegreen",
    "paleyellow",
    "palladium",
    "phosphorus",
    "pink",
    "platinum",
    "plutonium",
    "polonium",
    "potassium",
    "praseodymium",
    "promethium",
    "protactinium",
    "pseudoatom",
    "purple",
    "purpleblue",
    "radium",
    "radon",
    "raspberry",
    "red",
    "rhenium",
    "rhodium",
    "rubidium",
    "ruby",
    "ruthenium",
    "rutherfordium",
    "salmon",
    "samarium",
    "sand",
    "scandium",
    "seaborgium",
    "selenium",
    "silicon",
    "silver",
    "skyblue",
    "slate",
    "smudge",
    "sodium",
    "splitpea",
    "strontium",
    "sulfur",
    "tantalum",
    "teal",
    "technetium",
    "tellurium",
    "terbium",
    "thallium",
    "thorium",
    "thulium",
    "tin",
    "titanium",
    "tungsten",
    "tv_blue",
    "tv_green",
    "tv_orange",
    "tv_red",
    "tv_yellow",
    "uranium",
    "vanadium",
    "violet",
    "violetpurple",
    "warmpink",
    "wheat",
    "white",
    "xenon",
    "yellow",
    "yelloworange",
    "ytterbium",
    "yttrium",
    "zinc",
    "zirconium",
)

#: Every representation Open-Source PyMOL defines, in the order
#: tests/discovery/h02/harness.py queries them. The two lists are the same
#: list by intent: when item 3 promotes that harness into
#: pmc_core.snapshot, the snapshot extractor should import this tuple rather
#: than keep a second copy that can drift from it.
REPRESENTATION_ALLOWLIST: tuple[str, ...] = (
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


def _check_color(value: object) -> None:
    """Check a color value against the color allowlist.

    Args:
        value: The candidate color value.

    Raises:
        ValueError: If value is not a name in COLOR_ALLOWLIST.
    """
    if not isinstance(value, str) or value not in COLOR_ALLOWLIST:
        raise ValueError(f"unsupported color value: {value!r}")


def _check_representation(value: object) -> None:
    """Check a representation against the representation allowlist.

    Args:
        value: The candidate representation.

    Raises:
        ValueError: If value is not a name in REPRESENTATION_ALLOWLIST.
    """
    if not isinstance(value, str) or value not in REPRESENTATION_ALLOWLIST:
        raise ValueError(f"unsupported representation: {value!r}")


def _check_target(value: object) -> None:
    """Check that a command's target is an accepted target value.

    Args:
        value: The candidate target.

    Raises:
        ValueError: If value is neither a NamedSelection nor a
            SelectionExpression.
    """
    if not isinstance(value, TARGET_TYPES):
        raise ValueError(f"unsupported target: {value!r}")


@dataclass(frozen=True)
class SelectOperation:
    """A select command, creating a named selection from an expression.

    Attributes:
        selection_name: The name of the selection this command creates.
        expression: The selection expression assigned to selection_name. A
            select always takes an expression, never a reference to another
            selection.
    """

    selection_name: str
    expression: SelectionExpression

    def __post_init__(self) -> None:
        """Reject arguments outside the accepted forms for select.

        Raises:
            ValueError: If selection_name or expression is outside its
                accepted form.
        """
        _check_selection_name(self.selection_name)
        if not isinstance(self.expression, SelectionExpression):
            raise ValueError(
                f"unsupported selection expression: {self.expression!r}"
            )

    def render(self) -> str:
        """Render this operation as one canonical native .pml line.

        Returns:
            The canonical select command text, without a trailing newline.
        """
        return f"select {self.selection_name}, {self.expression.render()}"


@dataclass(frozen=True)
class ColorOperation:
    """A color command, applying one color to a target.

    Attributes:
        color: The color value applied to target.
        target: What this command colors.
    """

    color: str
    target: TARGET

    def __post_init__(self) -> None:
        """Reject arguments outside the accepted forms for color.

        Raises:
            ValueError: If color or target is outside its accepted form.
        """
        _check_color(self.color)
        _check_target(self.target)

    def render(self) -> str:
        """Render this operation as one canonical native .pml line.

        Returns:
            The canonical color command text, without a trailing newline.
        """
        return f"color {self.color}, {self.target.render()}"


@dataclass(frozen=True)
class ShowOperation:
    """A show command, enabling one representation on a target.

    Attributes:
        representation: The representation enabled on target.
        target: What this command shows.
    """

    representation: str
    target: TARGET

    def __post_init__(self) -> None:
        """Reject arguments outside the accepted forms for show.

        Raises:
            ValueError: If representation or target is outside its accepted
                form.
        """
        _check_representation(self.representation)
        _check_target(self.target)

    def render(self) -> str:
        """Render this operation as one canonical native .pml line.

        Returns:
            The canonical show command text, without a trailing newline.
        """
        return f"show {self.representation}, {self.target.render()}"


@dataclass(frozen=True)
class HideOperation:
    """A hide command, disabling one representation on a target.

    Attributes:
        representation: The representation disabled on target.
        target: What this command hides.
    """

    representation: str
    target: TARGET

    def __post_init__(self) -> None:
        """Reject arguments outside the accepted forms for hide.

        Raises:
            ValueError: If representation or target is outside its accepted
                form.
        """
        _check_representation(self.representation)
        _check_target(self.target)

    def render(self) -> str:
        """Render this operation as one canonical native .pml line.

        Returns:
            The canonical hide command text, without a trailing newline.
        """
        return f"hide {self.representation}, {self.target.render()}"


@dataclass(frozen=True)
class OrientOperation:
    """An orient command, framing the view on a target.

    Attributes:
        target: What this command orients the view onto. orient always takes
            a target; there is no whole-scene form in this language.
    """

    target: TARGET

    def __post_init__(self) -> None:
        """Reject arguments outside the accepted forms for orient.

        Raises:
            ValueError: If target is outside its accepted form.
        """
        _check_target(self.target)

    def render(self) -> str:
        """Render this operation as one canonical native .pml line.

        Returns:
            The canonical orient command text, without a trailing newline.
        """
        return f"orient {self.target.render()}"


#: The ordered operation types accepted in an ActionPlan.
type OPERATION = (
    SelectOperation
    | ColorOperation
    | ShowOperation
    | HideOperation
    | OrientOperation
)
# Preserve the original runtime name for callers importing this type alias.
globals()["Operation"] = OPERATION

#: The concrete operation types, for isinstance checks.
OPERATION_TYPES: tuple[type, ...] = (
    SelectOperation,
    ColorOperation,
    ShowOperation,
    HideOperation,
    OrientOperation,
)

#: The argument form naming a selection this command creates.
ARGUMENT_FORM_SELECTION_NAME = "selection_name"

#: The argument form naming a selection expression.
ARGUMENT_FORM_EXPRESSION = "expression"

#: The argument form naming what a command acts on.
ARGUMENT_FORM_TARGET = "target"

#: The argument form naming a color value.
ARGUMENT_FORM_COLOR = "color"

#: The argument form naming a representation.
ARGUMENT_FORM_REPRESENTATION = "representation"


@dataclass(frozen=True)
class VerbRule:
    """One row of the command allowlist.

    Attributes:
        verb: The verb this rule permits.
        argument_forms: The ordered argument forms the verb accepts, one per
            comma-separated argument.
        operation_type: The typed operation this verb produces.
    """

    verb: str
    argument_forms: tuple[str, ...]
    operation_type: type


#: The explicit allowlist: every verb the language accepts, and the argument
#: forms each one permits. This is the security boundary of the language --
#: a verb absent from this table cannot be parsed and cannot be allowed.
#:
#: pmc_core.parser reads it to dispatch and pmc_core.policy reads it to
#: re-check. Sharing one declarative table does not weaken the policy's
#: independence: what must not be shared is the decision path, and the policy
#: re-derives its verdict from a typed operation's own fields rather than
#: from anything the parser computed.
COMMAND_ALLOWLIST: Mapping[str, VerbRule] = MappingProxyType(
    {
        "select": VerbRule(
            verb="select",
            argument_forms=(
                ARGUMENT_FORM_SELECTION_NAME,
                ARGUMENT_FORM_EXPRESSION,
            ),
            operation_type=SelectOperation,
        ),
        "color": VerbRule(
            verb="color",
            argument_forms=(ARGUMENT_FORM_COLOR, ARGUMENT_FORM_TARGET),
            operation_type=ColorOperation,
        ),
        "show": VerbRule(
            verb="show",
            argument_forms=(
                ARGUMENT_FORM_REPRESENTATION,
                ARGUMENT_FORM_TARGET,
            ),
            operation_type=ShowOperation,
        ),
        "hide": VerbRule(
            verb="hide",
            argument_forms=(
                ARGUMENT_FORM_REPRESENTATION,
                ARGUMENT_FORM_TARGET,
            ),
            operation_type=HideOperation,
        ),
        "orient": VerbRule(
            verb="orient",
            argument_forms=(ARGUMENT_FORM_TARGET,),
            operation_type=OrientOperation,
        ),
    }
)


def referenced_selection_name(operation: OPERATION) -> str | None:
    """Report the selection name an operation references, if any.

    A select creates a name rather than referencing one, and a command whose
    target is an expression references nothing.

    Args:
        operation: The typed operation to inspect.

    Returns:
        The referenced selection name, or None when the operation references
        no existing selection.
    """
    match operation:
        case (
            ColorOperation()
            | ShowOperation()
            | HideOperation()
            | OrientOperation()
        ):
            # Read through getattr: pmc_core.policy calls this with values
            # that may have been assembled without ever running __init__,
            # and a missing field must report "references nothing" rather
            # than raise. The policy denies such a value on its own terms.
            target = getattr(operation, "target", None)
            if isinstance(target, NamedSelection):
                name = getattr(target, "name", None)
                return name if isinstance(name, str) else None
            return None
        case _:
            return None


@dataclass(frozen=True)
class ActionPlan:
    """An immutable, ordered plan over the accepted operations.

    Attributes:
        operations: The ordered operations that make up this plan. Every
            referenced selection must have been created by an earlier
            operation in the same plan, so a plan can never act on a
            selection it did not itself define.
    """

    operations: tuple[OPERATION, ...]

    def __post_init__(self) -> None:
        """Reject an operation sequence outside the accepted plan shape.

        Raises:
            ValueError: If operations is empty, longer than MAX_COMMANDS,
                holds a value that is not an accepted operation, defines one
                selection name twice, or references a selection no earlier
                operation created.
        """
        if not isinstance(self.operations, tuple) or not self.operations:
            raise ValueError("plan must contain at least one command")
        if len(self.operations) > MAX_COMMANDS:
            raise ValueError(f"plan exceeds {MAX_COMMANDS} commands")

        defined: set[str] = set()
        for operation in self.operations:
            if not isinstance(operation, OPERATION_TYPES):
                raise ValueError(f"unsupported operation: {operation!r}")
            referenced = referenced_selection_name(operation)
            if referenced is not None and referenced not in defined:
                raise ValueError(
                    f"undefined selection reference: {referenced!r}"
                )
            if isinstance(operation, SelectOperation):
                if operation.selection_name in defined:
                    raise ValueError(
                        "selection name defined twice: "
                        f"{operation.selection_name!r}"
                    )
                defined.add(operation.selection_name)

        # A plan whose own canonical rendering exceeds the parser's input
        # bound could not be read back, which would break the round-trip
        # guarantee render_pml documents below. MAX_COMMANDS alone does not
        # imply it: 32 maximal commands already render past the bound.
        rendered = "\n".join(
            operation.render() for operation in self.operations
        )
        if len(rendered.encode("utf-8")) + 1 > MAX_INPUT_BYTES:
            raise ValueError(
                f"plan renders to more than {MAX_INPUT_BYTES} bytes"
            )

    def render_pml(self) -> str:
        """Render this plan as canonical native .pml text.

        Rendering is idempotent: rendering the same plan value always
        produces the same bytes, and those bytes describe exactly the
        commands that will execute in order. Because the grammar has no
        parentheses and no optional whitespace, the rendered text is also the
        only text that parses back to this plan.

        Returns:
            The canonical .pml text, one command per line, terminated by a
            single trailing newline.
        """
        lines = (operation.render() for operation in self.operations)
        return "\n".join(lines) + "\n"
