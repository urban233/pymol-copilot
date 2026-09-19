# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the error envelope: no PyMOL required.

Covers everything about pmc_core.errors that a checked-in corpus can
prove: the envelope's own construction rules, the message normalization
pipeline, the ordered classification table, and byte-for-byte agreement
between the normalizer and the corpus captured from real PyMOL.

The corpus under testdata/pymol_errors/ is produced by
tests/integration/capture_pymol_errors.py against a live PyMOL. The test
that re-derives it from a live PyMOL, and so fails when a PyMOL upgrade
rewords a message, is tests/integration/test_errors_real_pymol.py; this
module never launches PyMOL and never imports it.

It does import that package's pymol_error_cases, which imports no PyMOL
either. That table is what the capture drove, so it is the independent
source for the command index and verb each captured envelope is checked
against: taking them from the envelope itself, as this module first did,
left two of its five fields asserting nothing.
"""

import importlib
import json
import pathlib

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.errors import CATEGORIES
from pmc_core.errors import CATEGORY_UNKNOWN
from pmc_core.errors import CLASSIFICATION_RULES
from pmc_core.errors import ERROR_ENVELOPE_VERSION
from pmc_core.errors import MAX_MESSAGE_BYTES
from pmc_core.errors import REDACTION
from pmc_core.errors import TRUNCATION_MARKER
from pmc_core.errors import UNSPECIFIED_MESSAGE
from pmc_core.errors import UNSPECIFIED_TYPE_NAME
from pmc_core.errors import ExecutionErrorV1
from pmc_core.errors import classify
from pmc_core.errors import exception_type_name
from pmc_core.errors import normalize
from pmc_core.errors import normalize_message
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import SELECTION_NAME_PREFIX
from pymol_error_cases import Case
from pymol_error_cases import cases

#: The captured corpus, beside this module.
_CORPUS_DIRECTORY = pathlib.Path(__file__).parent / "testdata" / "pymol_errors"


def _corpus_files() -> list[pathlib.Path]:
    """List the corpus files.

    Returns:
        Every per-verb corpus file, in a stable order.
    """
    return sorted(_CORPUS_DIRECTORY.glob("*.json"))


def _corpus_cases() -> list[tuple[str, dict[str, object]]]:
    """Load every captured case.

    Returns:
        Pairs of test identifier and captured case, in a stable order.
    """
    collected: list[tuple[str, dict[str, object]]] = []
    for path in _corpus_files():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for case in payload["cases"]:
            collected.append((f"{case['verb']}/{case['case']}", case))
    return collected


_CASES = _corpus_cases()

#: Every driven case, keyed by its (verb, case) identity. This is where
#: the command index and verb a captured envelope is checked against come
#: from: reading them back out of the envelope under test would make those
#: two fields assert nothing.
_DRIVEN: dict[tuple[str, str], Case] = {
    (case.verb, case.case): case for case in cases()
}

#: The subsystems item 6 of the master plan requires to normalize a PyMOL
#: failure identically. Their call sites arrive with items 14 and 8; what
#: is checkable now is that neither has grown a boundary of its own.
_CONSUMER_PACKAGES = ("pmc_agent", "pmc_data")

#: Definitions that would mean a consumer had built a second normalizer
#: instead of reaching this one.
_NORMALIZER_DEFINITIONS = (
    "def normalize(",
    "def normalize_message(",
    "class ExecutionErrorV1",
)


def _consumer_sources() -> list[pathlib.Path]:
    """List every Python source shipped by the consumer packages.

    Read from each package's own `__path__` rather than from a repository
    path, so this works unchanged under Bazel's runfiles tree, where the
    test's working directory is not the source root.

    Returns:
        Every consumer source file, in a stable order.
    """
    sources: list[pathlib.Path] = []
    for name in _CONSUMER_PACKAGES:
        package = importlib.import_module(name)
        for directory in package.__path__:
            sources.extend(sorted(pathlib.Path(directory).rglob("*.py")))
    return sources


class _RecordedFailure(Exception):
    """Stands in for a PyMOL exception whose text was captured.

    Classification reads the exception's type name and its message. The
    type name is asserted separately against the corpus; this carries the
    message, so the normalizer can be exercised without importing PyMOL.
    """


def test_the_corpus_is_not_empty() -> None:
    """A corpus that silently emptied would make every case below vacuous."""
    assert _corpus_files(), "no corpus files were found"
    assert len(_CASES) >= len(COMMAND_ALLOWLIST)


def test_every_supported_verb_has_a_corpus_file() -> None:
    """Every verb in the language carries captured failure evidence."""
    captured = {path.stem for path in _corpus_files()}
    assert captured == set(COMMAND_ALLOWLIST)


@pytest.mark.parametrize(("label", "case"), _CASES, ids=[c[0] for c in _CASES])
def test_the_normalizer_reproduces_the_captured_envelope(
    label: str, case: dict[str, object]
) -> None:
    """Every captured raw message normalizes to exactly its recorded bytes.

    This is the byte-equality guarantee: one normalizer, one output, for a
    failure captured from real PyMOL. The command index and verb handed to
    the normalizer come from the shared case table rather than from the
    envelope being checked, so all five recorded fields are asserted
    against something independent of the file they live in.
    """
    del label
    expected = case["expected"]
    assert isinstance(expected, dict)
    driven = _DRIVEN[(str(case["verb"]), str(case["case"]))]
    envelope = normalize(
        _RecordedFailure(case["raw_message"]),
        command_index=driven.command_index,
        verb=driven.verb,
    )
    assert envelope.to_dict() == expected


def test_no_consumer_defines_a_normalizer_of_its_own() -> None:
    """Neither consumer may grow a second error boundary.

    The master plan's item 6 asks that the same PyMOL failure normalize
    identically "in the dataset pipeline and at runtime". Those two call
    sites arrive with item 14 and item 8, so no test here can yet prove
    that both *reach* this module. What is provable now, and what a
    divergence would have to defeat first, is that neither subsystem
    defines a normalizer or an envelope of its own -- see
    plans/05-error-envelope.md.
    """
    sources = _consumer_sources()
    assert sources, "no consumer sources were found to scan"
    for source in sources:
        body = source.read_text(encoding="utf-8")
        for definition in _NORMALIZER_DEFINITIONS:
            assert definition not in body, (
                f"{source.name} defines its own {definition.strip()}"
            )


def test_a_consumer_that_normalizes_reaches_this_module() -> None:
    """A consumer calling normalize() must call pmc_core.errors'.

    This is vacuous until item 14 and item 8 add their call sites, and
    that is the point: it turns into the real cross-subsystem assertion
    the moment either of them lands, rather than having to be remembered
    then.
    """
    for source in _consumer_sources():
        body = source.read_text(encoding="utf-8")
        if "normalize(" not in body:
            continue
        assert "pmc_core.errors" in body, (
            f"{source.name} normalizes without naming pmc_core.errors"
        )


def test_every_captured_case_is_driven_by_the_shared_table() -> None:
    """A corpus entry no case drives could record anything at all."""
    captured = {(str(case["verb"]), str(case["case"])) for _, case in _CASES}
    assert captured == set(_DRIVEN)


def test_every_category_is_backed_by_a_captured_case() -> None:
    """No category may exist that real PyMOL never produced."""
    observed = set()
    for _, case in _CASES:
        expected = case["expected"]
        assert isinstance(expected, dict)
        observed.add(expected["category"])
    assert observed == CATEGORIES


def test_no_normalized_message_leaks_plan_text() -> None:
    """No envelope message may carry the one guaranteed plan-derived token."""
    for label, case in _CASES:
        expected = case["expected"]
        assert isinstance(expected, dict)
        message = str(expected["message"])
        assert SELECTION_NAME_PREFIX not in message, label


def test_every_captured_category_is_what_classify_reports() -> None:
    """The recorded category is the classifier's, not a hand-written one."""
    for label, case in _CASES:
        expected = case["expected"]
        assert isinstance(expected, dict)
        message = normalize_message(str(case["raw_message"]))
        failure = _RecordedFailure(case["raw_message"])
        assert classify(failure, message) == expected["category"], label


def test_normalization_is_idempotent_over_the_corpus() -> None:
    """Normalizing a normalized message must return it unchanged."""
    for label, case in _CASES:
        once = normalize_message(str(case["raw_message"]))
        assert normalize_message(once) == once, label


def test_every_normalized_message_is_within_the_bound() -> None:
    """No captured case may produce a message past the byte bound."""
    for label, case in _CASES:
        message = normalize_message(str(case["raw_message"]))
        assert len(message.encode("utf-8")) <= MAX_MESSAGE_BYTES, label
        assert message, label


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('name "copilot_x"', f"name {REDACTION}"),
        ("rep 'sticks'", f"rep {REDACTION}"),
        ('unterminated "copilot_x', f"unterminated {REDACTION}"),
        ("a\nb", "a b"),
        ("a\t\t  b", "a b"),
        (" Error: Boom.", "boom."),
        (" Selector-Error: Boom.", "boom."),
        ("Error: Error: Boom.", "boom."),
        ("drop me<--", UNSPECIFIED_MESSAGE),
        ("keep\ndrop<--", "keep"),
        ("   ", UNSPECIFIED_MESSAGE),
        ("café", "caf?"),
    ],
)
def test_normalization_rules(raw: str, expected: str) -> None:
    """Each normalization rule does exactly what it claims, in order."""
    assert normalize_message(raw) == expected


def test_normalization_bounds_an_over_long_message() -> None:
    """A message past the bound truncates inside it, with a marker.

    No real captured message reaches the bound today, so this case is
    synthetic on purpose -- the truncation path must still be proven.
    """
    raw = "x" * (MAX_MESSAGE_BYTES * 3)
    message = normalize_message(raw)
    assert len(message.encode("utf-8")) == MAX_MESSAGE_BYTES
    assert message.endswith(TRUNCATION_MARKER)
    assert normalize_message(message) == message


def test_truncation_does_not_split_a_redaction() -> None:
    """A cut landing inside `"<redacted>"` would break idempotence.

    Truncating mid-token leaves a stray quote whose second normalization
    pass redacts it again, so the same failure would reach two boundaries
    as two different byte strings. The cut moves back instead.
    """
    raw = "x" * 243 + '"secret"' + "y" * 10
    once = normalize_message(raw)
    assert len(once.encode("utf-8")) <= MAX_MESSAGE_BYTES
    assert once.endswith(TRUNCATION_MARKER)
    assert normalize_message(once) == once
    assert REDACTION[:-1] not in once


@pytest.mark.parametrize(
    "raw",
    [
        "x" * 243 + '"secret"' + "y" * 10,
        "x" * 250 + '"secret"',
        '"a" ' * 200,
        "x" * 100 + f'"{SELECTION_NAME_PREFIX}x" ' * 40,
        f"{SELECTION_NAME_PREFIX}name " * 80,
    ],
)
def test_normalization_stays_idempotent_around_the_bound(raw: str) -> None:
    """Redaction and truncation must not interact into a second result."""
    once = normalize_message(raw)
    assert normalize_message(once) == once
    assert len(once.encode("utf-8")) <= MAX_MESSAGE_BYTES


@pytest.mark.parametrize(
    "raw",
    [
        f"command {SELECTION_NAME_PREFIX}secret failed",
        f"no such object: {SELECTION_NAME_PREFIX}secret.",
        f"{SELECTION_NAME_PREFIX}secret",
        f"unknown {SELECTION_NAME_PREFIX}SECRET here",
    ],
)
def test_no_unquoted_plan_name_survives_normalization(raw: str) -> None:
    """An unquoted selection name leaks exactly as a quoted one would.

    The `unknown` category preserves the text it does not recognize, so a
    message naming a selection without quoting it would carry plan text
    into a log or a repair prompt unless the prefix itself is redacted.
    """
    assert SELECTION_NAME_PREFIX not in normalize_message(raw)
    envelope = normalize(RuntimeError(raw), command_index=0, verb="select")
    assert SELECTION_NAME_PREFIX not in envelope.message


def test_no_normalized_message_leaks_a_plan_name_in_any_position() -> None:
    """The prefix may not survive whatever punctuation surrounds it."""
    for template in ("{0}", " {0} ", "({0})", "'{0}'", "at {0}, index 3"):
        raw = template.format(f"{SELECTION_NAME_PREFIX}secret")
        assert SELECTION_NAME_PREFIX not in normalize_message(raw), raw


class _UnprintableFailure(Exception):
    """An exception whose own message cannot be read.

    Real PyMOL does not raise one of these, but nothing in an except block
    can know that before calling str() on what it caught.
    """

    def __str__(self) -> str:
        """Refuse to describe this failure.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("this exception will not describe itself")


class _AnonymousMeta(type):
    """A metaclass that refuses to name the classes it creates."""

    @property
    def __module__(cls) -> str:
        """Refuse to report a defining module.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("this type will not name itself")


class _AnonymousFailure(Exception, metaclass=_AnonymousMeta):
    """An exception whose type cannot be named."""


def test_normalize_survives_an_exception_that_cannot_describe_itself() -> None:
    """A raising __str__ may not cost the caller the original failure."""
    envelope = normalize(_UnprintableFailure(), command_index=0, verb="select")
    assert envelope.category == CATEGORY_UNKNOWN
    assert envelope.message == UNSPECIFIED_MESSAGE


def test_normalize_survives_an_exception_that_cannot_name_its_type() -> None:
    """A raising type name may not cost the caller the original failure."""
    envelope = normalize(
        _AnonymousFailure("boom"), command_index=0, verb="select"
    )
    assert envelope.category == CATEGORY_UNKNOWN
    assert envelope.message == "boom"


def test_exception_type_name_survives_a_type_that_will_not_name_itself() -> (
    None
):
    """Naming is part of the boundary and so cannot raise either."""
    assert exception_type_name(_AnonymousFailure()) == UNSPECIFIED_TYPE_NAME


def test_normalization_accepts_a_non_string() -> None:
    """A message that is not a str becomes the unspecified message.

    None is what _message_text yields for an exception whose __str__
    raises, so this is the path a failure that cannot describe itself
    takes, not only a caller mistake.
    """
    assert normalize_message(None) == UNSPECIFIED_MESSAGE


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("something nobody has seen before"),
        KeyError("k"),
        ValueError(""),
        OSError(),
        Exception(),
    ],
)
def test_an_unrecognized_failure_becomes_unknown(
    error: BaseException,
) -> None:
    """The catch-all never drops a failure and never raises."""
    envelope = normalize(error, command_index=0, verb="select")
    assert envelope.category == CATEGORY_UNKNOWN
    assert envelope.message


def test_the_unknown_category_preserves_bounded_text() -> None:
    """Unrecognized text is kept, bounded, rather than discarded."""
    envelope = normalize(
        RuntimeError("a brand new failure mode"),
        command_index=0,
        verb="select",
    )
    assert envelope.category == CATEGORY_UNKNOWN
    assert envelope.message == "a brand new failure mode"


def test_classification_rules_only_name_known_categories() -> None:
    """A rule may not assign a category the envelope would reject."""
    for rule in CLASSIFICATION_RULES:
        assert rule.category in CATEGORIES
        assert rule.substring is None or rule.substring.islower()


def test_exception_type_name_is_module_qualified() -> None:
    """The recorded type identity is the one the corpus compares against."""
    assert exception_type_name(ValueError("x")) == "builtins.ValueError"


def test_an_envelope_constructs_from_accepted_values() -> None:
    """The positive case, so the negative cases below mean something."""
    envelope = ExecutionErrorV1(
        envelope_version=ERROR_ENVELOPE_VERSION,
        command_index=0,
        verb="select",
        category=CATEGORY_UNKNOWN,
        message="boom",
    )
    assert envelope.to_dict()["verb"] == "select"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("envelope_version", ERROR_ENVELOPE_VERSION + 1),
        ("envelope_version", "1"),
        ("envelope_version", True),
        ("envelope_version", float(ERROR_ENVELOPE_VERSION)),
        ("envelope_version", complex(ERROR_ENVELOPE_VERSION, 0)),
        ("command_index", -1),
        ("command_index", MAX_COMMANDS),
        ("command_index", True),
        ("command_index", "0"),
        ("verb", "load"),
        ("verb", "SELECT"),
        ("category", "made_up"),
        ("category", ""),
        ("message", ""),
        ("message", "x" * (MAX_MESSAGE_BYTES + 1)),
        ("message", "line\nbreak"),
        ("message", "café"),
    ],
)
def test_an_envelope_rejects_an_unaccepted_value(
    field: str, value: object
) -> None:
    """Every construction rule rejects, one field at a time."""
    accepted: dict[str, object] = {
        "envelope_version": ERROR_ENVELOPE_VERSION,
        "command_index": 0,
        "verb": "select",
        "category": CATEGORY_UNKNOWN,
        "message": "boom",
    }
    accepted[field] = value
    with pytest.raises(ValueError):
        ExecutionErrorV1(**accepted)  # pyrefly: ignore.


def test_normalize_rejects_a_verb_outside_the_language() -> None:
    """A caller naming an unsupported verb is a defect worth surfacing."""
    with pytest.raises(ValueError):
        normalize(RuntimeError("x"), command_index=0, verb="fetch")


def test_normalize_rejects_a_command_index_out_of_range() -> None:
    """An index no plan could carry is a caller defect, not a failure."""
    with pytest.raises(ValueError):
        normalize(RuntimeError("x"), command_index=MAX_COMMANDS, verb="select")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
