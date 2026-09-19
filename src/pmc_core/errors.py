# Copyright 2026 PyMOL Copilot contributors.
"""Normalization of raw PyMOL execution failures into a typed envelope.

One raw failure raised by PyMOL becomes exactly one `ExecutionErrorV1`: a
stable machine-readable category, the index and verb of the command that
failed, and a bounded, redacted, single-line message. The same raw failure
must normalize to the same bytes wherever it is caught -- in the dataset
pipeline and at runtime -- which is what makes a category countable across
both and what lets a repair attempt be fed something the model can act on.

This module imports no PyMOL. It classifies by the raised exception's
module-qualified type *name* and by substrings of its message, so it stays
in `pmc_core`'s hermetic half alongside `plan.py`, `policy.py` and
`snapshot.py`. The corpus of real PyMOL error strings this module is built
against lives in `tests/contract/testdata/pymol_errors/`, captured from
real PyMOL by `tests/integration/capture_pymol_errors.py`.

Three properties of real PyMOL shape everything below; each was measured
against PyMOL 3.2.0a rather than assumed.

Failures arrive as at least two unrelated exception types --
`pymol.CmdException` and `pymol.parsing.QuietException` -- from different
modules, with no common base this module may rely on. `normalize` therefore
accepts any `BaseException` and never raises on the basis of one, and the
`unknown` category preserves bounded text rather than dropping a failure it
does not recognize.

Raw messages are multi-line and quote the input back. A bad representation
reports PyMOL's entire 24-entry representation table across five lines; an
invalid selection name reports the name and then repeats it on a caret
line. Both would leak plan text into an error, which
`pmc_core.parser.ParseRejection` already refuses to do and which item 11 of
the master plan forbids outright.

`cmd.do()` cannot surface a failure at all: it returns None for every
failure and writes its text from C at the file-descriptor level on PyMOL's
own thread. Only the typed `cmd.*` API raises, so only the typed API
produces anything for this module to normalize.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from dataclasses import dataclass

from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import MAX_COMMANDS

#: This module's own envelope schema version, stamped into every envelope.
#: An int, matching pmc_core.snapshot.SNAPSHOT_VERSION: both version a
#: pmc_core value, where pmc_core.protocol.PROTOCOL_VERSION versions the
#: wire and is deliberately a different thing.
ERROR_ENVELOPE_VERSION = 1

#: The greatest length, in bytes, of a normalized message. The longest real
#: message for a supported verb is `show`'s representation table: 291 bytes
#: raw, 226 once whitespace is collapsed. The bound sits above that on
#: purpose -- item 8 feeds this message to a repair attempt, and the list of
#: valid representations is the part that makes the repair succeed, so
#: truncating it would cost more than it saves. No real message reaches the
#: bound today; the truncation path is covered by a synthetic case.
MAX_MESSAGE_BYTES = 256

#: Stable category for a color outside PyMOL's own color table.
CATEGORY_UNKNOWN_COLOR = "unknown_color"

#: Stable category for a representation PyMOL does not know.
CATEGORY_UNKNOWN_REPRESENTATION = "unknown_representation"

#: Stable category for a target naming a selection or object that does not
#: exist in the session the command ran against.
CATEGORY_INVALID_SELECTION_NAME = "invalid_selection_name"

#: Stable category for a selection expression PyMOL's own selector parser
#: rejected. Distinct from invalid_selection_name: the name resolution
#: succeeded or never happened, and the expression itself is malformed.
CATEGORY_SELECTION_SYNTAX = "selection_syntax"

#: The catch-all. A failure reaching this category keeps its bounded,
#: redacted text: an unrecognized failure must stay inspectable, because
#: the alternative is discarding the only evidence of a new failure mode.
CATEGORY_UNKNOWN = "unknown"

#: Every category this module can produce. An envelope carrying a category
#: outside this set does not construct.
CATEGORIES: frozenset[str] = frozenset(
    {
        CATEGORY_UNKNOWN_COLOR,
        CATEGORY_UNKNOWN_REPRESENTATION,
        CATEGORY_INVALID_SELECTION_NAME,
        CATEGORY_SELECTION_SYNTAX,
        CATEGORY_UNKNOWN,
    }
)

#: What a quoted span in a raw message is replaced by. Always spelled with
#: double quotes, whichever quote style the raw message used, so the same
#: failure reported through two different PyMOL code paths normalizes to
#: the same bytes.
REDACTION = '"<redacted>"'

#: Appended, inside MAX_MESSAGE_BYTES, to a message that was truncated.
TRUNCATION_MARKER = "..."

#: Substituted for a message that normalized away to nothing. A message is
#: never empty, because an empty message is indistinguishable from a
#: missing one.
UNSPECIFIED_MESSAGE = "unspecified pymol failure"

#: The quote characters a raw message may use around input it echoes back.
#: PyMOL uses double quotes for selection names and single quotes for
#: representation names, and both are plan-derived.
_QUOTE_CHARACTERS = frozenset("\"'")

#: PyMOL's caret marker. The line carrying it repeats the offending input
#: verbatim and unquoted, so the whole line is dropped rather than redacted.
_CARET_MARKER = "<--"

#: Leading labels stripped from a raw message, compared case-insensitively
#: and repeatedly, so a message labelled by two code paths in turn reduces
#: to the same text as one labelled by neither.
_ERROR_PREFIXES = ("selector-error:", "cmd-error:", "error:")

#: The printable ASCII range. Everything outside it is substituted, so a
#: normalized message is always safe to place in a terminal line.
_PRINTABLE = frozenset(chr(code) for code in range(0x20, 0x7F))

#: What replaces a character outside _PRINTABLE.
_SUBSTITUTE = "?"


@dataclass(frozen=True)
class _ClassificationRule:
    """One row of the ordered classification table.

    Attributes:
        category: The category assigned when this rule matches.
        type_name: A module-qualified exception type name that must match
            exactly, or None when the rule matches on message alone.
        substring: A lowercase substring the normalized message must
            contain, or None when the rule matches on type alone.
    """

    category: str
    type_name: str | None
    substring: str | None


#: The ordered classification table: the first matching rule wins, and a
#: failure matching none becomes CATEGORY_UNKNOWN. Substrings are compared
#: against the *normalized* message, which is already lowercased, so every
#: substring here is lowercase.
#:
#: Matching is by exception type *name* rather than by the type itself
#: because this module must not import pymol. That is weaker than an
#: isinstance check and deliberately so: the substring carries the real
#: discrimination, and the catch-all covers a PyMOL rename.
CLASSIFICATION_RULES: tuple[_ClassificationRule, ...] = (
    _ClassificationRule(
        category=CATEGORY_UNKNOWN_COLOR,
        type_name=None,
        substring="unknown color",
    ),
    _ClassificationRule(
        category=CATEGORY_UNKNOWN_REPRESENTATION,
        type_name=None,
        substring="unknown representation",
    ),
    _ClassificationRule(
        category=CATEGORY_INVALID_SELECTION_NAME,
        type_name=None,
        substring="invalid selection name",
    ),
    _ClassificationRule(
        category=CATEGORY_SELECTION_SYNTAX,
        type_name=None,
        substring="invalid selection",
    ),
    _ClassificationRule(
        category=CATEGORY_SELECTION_SYNTAX,
        type_name=None,
        substring="malformed selection",
    ),
)


def exception_type_name(error: BaseException) -> str:
    """Report an exception's module-qualified type name.

    This is the identity the classification table matches on and the
    identity the captured corpus records, so the corpus and the table
    always speak about a type the same way.

    Args:
        error: The raised failure to name.

    Returns:
        The type name, qualified by its defining module, for example
        "pymol.CmdException".
    """
    kind = type(error)
    return f"{kind.__module__}.{kind.__qualname__}"


def _redact_quoted(text: str) -> str:
    """Replace every quoted span with REDACTION.

    An unterminated quote redacts to the end of the text rather than being
    left alone: the tail of an unterminated span is still plan-derived, and
    leaving it would be a leak that the terminated case does not have.

    Scanning is a single left-to-right character pass rather than a regular
    expression, for the reason pmc_core.plan's module docstring gives: this
    runs on untrusted text and must have no pathological input.

    Args:
        text: The raw message text.

    Returns:
        The text with every quoted span replaced.
    """
    pieces: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character not in _QUOTE_CHARACTERS:
            pieces.append(character)
            index += 1
            continue
        closing = text.find(character, index + 1)
        pieces.append(REDACTION)
        if closing == -1:
            break
        index = closing + 1
    return "".join(pieces)


def _drop_caret_lines(text: str) -> str:
    """Drop every line carrying PyMOL's caret marker.

    Args:
        text: The message text, possibly spanning several lines.

    Returns:
        The text with caret-marked lines removed.
    """
    kept = [line for line in text.splitlines() if _CARET_MARKER not in line]
    return "\n".join(kept)


def _collapse_whitespace(text: str) -> str:
    """Collapse every whitespace run to one space and strip the ends.

    Args:
        text: The message text.

    Returns:
        The single-line, stripped text.
    """
    return " ".join(text.split())


def _strip_prefixes(text: str) -> str:
    """Strip every leading error label, repeatedly.

    Stripping repeats so that text labelled twice reduces to the same
    result as text labelled once, which is what makes normalization
    idempotent.

    Args:
        text: The single-line, lowercased message text.

    Returns:
        The text with leading labels removed.
    """
    stripped = text
    changed = True
    while changed:
        changed = False
        for prefix in _ERROR_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix) :].lstrip()
                changed = True
    return stripped


def _substitute_unprintable(text: str) -> str:
    """Replace every character outside printable ASCII.

    Args:
        text: The message text.

    Returns:
        The text with unprintable characters substituted.
    """
    return "".join(
        character if character in _PRINTABLE else _SUBSTITUTE
        for character in text
    )


def _truncate(text: str) -> str:
    """Bound the text to MAX_MESSAGE_BYTES, marker included.

    The text is printable ASCII by the time this runs, so one character is
    one byte and slicing cannot split a character.

    Args:
        text: The printable-ASCII message text.

    Returns:
        The text, truncated with TRUNCATION_MARKER if it was too long.
    """
    if len(text.encode("ascii")) <= MAX_MESSAGE_BYTES:
        return text
    keep = MAX_MESSAGE_BYTES - len(TRUNCATION_MARKER)
    return text[:keep] + TRUNCATION_MARKER


def normalize_message(raw: str) -> str:
    """Normalize a raw PyMOL message into a bounded, single-line form.

    The pipeline is total, deterministic and idempotent: normalizing an
    already-normalized message returns it unchanged. Idempotence is what
    lets a normalized message be re-normalized at another boundary without
    changing its bytes.

    Args:
        raw: The raw message text, as PyMOL raised it. A value that is not
            a str is treated as having no message at all.

    Returns:
        A non-empty, single-line, printable-ASCII message of at most
        MAX_MESSAGE_BYTES bytes, carrying no quoted plan text.
    """
    if not isinstance(raw, str):
        return UNSPECIFIED_MESSAGE
    text = _redact_quoted(raw)
    text = _drop_caret_lines(text)
    text = _collapse_whitespace(text)
    text = _strip_prefixes(text.lower())
    text = _substitute_unprintable(text)
    text = _truncate(text)
    if not text:
        return UNSPECIFIED_MESSAGE
    return text


@dataclass(frozen=True)
class ExecutionErrorV1:
    """One PyMOL execution failure, normalized and bounded.

    Attributes:
        envelope_version: This module's ERROR_ENVELOPE_VERSION at
            normalization time.
        command_index: The zero-based index, within the plan, of the
            command whose execution failed.
        verb: The verb of that command. Always a key of
            pmc_core.plan.COMMAND_ALLOWLIST, so an envelope can never name
            a verb the restricted language does not have.
        category: A stable, machine-readable category drawn from
            CATEGORIES.
        message: A bounded, single-line, redacted explanation. It carries
            no quoted plan text.
    """

    envelope_version: int
    command_index: int
    verb: str
    category: str
    message: str

    def __post_init__(self) -> None:
        """Reject an envelope outside the accepted shape.

        Raises:
            ValueError: If envelope_version is not ERROR_ENVELOPE_VERSION,
                command_index is not an int in range, verb is not an
                allowlisted verb, category is not in CATEGORIES, or
                message is empty, over-long, or not printable ASCII.
        """
        if self.envelope_version != ERROR_ENVELOPE_VERSION:
            raise ValueError(
                f"unsupported envelope version: {self.envelope_version!r}"
            )
        if isinstance(self.command_index, bool) or not isinstance(
            self.command_index, int
        ):
            raise ValueError(
                f"unsupported command index: {self.command_index!r}"
            )
        if not 0 <= self.command_index < MAX_COMMANDS:
            raise ValueError(
                f"unsupported command index: {self.command_index!r}"
            )
        if self.verb not in COMMAND_ALLOWLIST:
            raise ValueError(f"unsupported verb: {self.verb!r}")
        if self.category not in CATEGORIES:
            raise ValueError(f"unsupported category: {self.category!r}")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError(f"unsupported message: {self.message!r}")
        if len(self.message.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("message exceeds the bound")
        if not set(self.message) <= _PRINTABLE:
            raise ValueError("message carries unprintable characters")

    def to_dict(self) -> dict[str, object]:
        """Encode this envelope as a JSON-compatible mapping.

        Provided so the captured corpus can record an expected envelope and
        a test can compare against it field by field. There is no decoder:
        putting an envelope on the wire is item 8's contract, not this
        module's.

        Returns:
            The envelope's fields, keyed by field name.
        """
        return {
            "envelope_version": self.envelope_version,
            "command_index": self.command_index,
            "verb": self.verb,
            "category": self.category,
            "message": self.message,
        }


def classify(error: BaseException, normalized_message: str) -> str:
    """Report the category of one raw failure.

    Args:
        error: The raised failure.
        normalized_message: That failure's already-normalized message,
            which the table's substrings are compared against.

    Returns:
        The first matching rule's category, or CATEGORY_UNKNOWN.
    """
    type_name = exception_type_name(error)
    for rule in CLASSIFICATION_RULES:
        if rule.type_name is not None and rule.type_name != type_name:
            continue
        if (
            rule.substring is not None
            and rule.substring not in normalized_message
        ):
            continue
        return rule.category
    return CATEGORY_UNKNOWN


def normalize(
    error: BaseException, *, command_index: int, verb: str
) -> ExecutionErrorV1:
    """Turn a raw PyMOL execution failure into a typed envelope.

    No property of `error` can make this raise: it is called from an except
    block, where a second failure would lose the first. A `verb` or
    `command_index` the envelope does not accept still raises, because
    those come from the caller's own plan rather than from PyMOL, and a
    caller naming a verb outside the language is a defect to surface rather
    than to normalize away.

    Args:
        error: The failure PyMOL raised.
        command_index: The zero-based index of the failing command within
            its plan.
        verb: The failing command's verb.

    Returns:
        The normalized envelope.

    Raises:
        ValueError: If command_index or verb is not one an envelope
            accepts.
    """
    message = normalize_message(str(error))
    return ExecutionErrorV1(
        envelope_version=ERROR_ENVELOPE_VERSION,
        command_index=command_index,
        verb=verb,
        category=classify(error, message),
        message=message,
    )
