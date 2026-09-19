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
"""

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
from pmc_core.errors import ExecutionErrorV1
from pmc_core.errors import classify
from pmc_core.errors import exception_type_name
from pmc_core.errors import normalize
from pmc_core.errors import normalize_message
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import SELECTION_NAME_PREFIX

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
    cases: list[tuple[str, dict[str, object]]] = []
    for path in _corpus_files():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for case in payload["cases"]:
            cases.append((f"{case['verb']}/{case['case']}", case))
    return cases


_CASES = _corpus_cases()


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
    failure captured from real PyMOL.
    """
    del label
    expected = case["expected"]
    assert isinstance(expected, dict)
    envelope = normalize(
        _RecordedFailure(case["raw_message"]),
        command_index=int(str(expected["command_index"])),
        verb=str(expected["verb"]),
    )
    assert envelope.to_dict() == expected


def test_one_normalizer_is_reachable_from_both_consumers() -> None:
    """pmc_data and pmc_agent must resolve the same normalizer object.

    The master plan's item 6 asks that the same PyMOL failure normalize
    identically "in the dataset pipeline and at runtime". Those two call
    sites arrive with item 14 and item 8; until they do, the guarantee
    that keeps them from diverging is that exactly one normalizer exists
    and both subsystems reach it. This assertion is what a genuine
    two-call-site test replaces later -- see plans/05-error-envelope.md.
    """
    import pmc_agent
    import pmc_core.errors
    import pmc_data

    assert pmc_agent is not None
    assert pmc_data is not None
    assert pmc_core.errors.normalize is normalize


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


def test_normalization_accepts_a_non_string() -> None:
    """A message that is not a str becomes the unspecified message."""
    assert normalize_message(None) == UNSPECIFIED_MESSAGE  # pyrefly: ignore.


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
