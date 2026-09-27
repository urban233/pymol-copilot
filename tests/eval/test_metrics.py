# Copyright 2026 PyMOL Copilot contributors.
"""Every reported rate counts what it says, over the denominator it says.

The fixtures are hand-built records, so each expected number here is
computed by hand rather than by the code under test.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses

import pytest

from pmc_data.audit import wilson_interval
from pmc_eval.metrics import aggregate
from pmc_eval.metrics import category_parts
from pmc_eval.metrics import render_markdown
from pmc_eval.record import OUTCOME_ABSTAINED
from pmc_eval.record import OUTCOME_DENIED_HOSTILE
from pmc_eval.record import OUTCOME_EXECUTED_WRONG
from pmc_eval.record import OUTCOME_SUCCESS
from pmc_eval.record import OUTCOME_SYNTAX_INVALID
from pmc_eval.record import OUTCOMES
from pmc_eval.record import AttemptRecord
from pmc_eval.record import SampleRecord
from pmc_eval.runner import CONDITION_GRAMMAR
from pmc_eval.runner import CONDITION_NO_GRAMMAR


def _attempt(
    number: int,
    outcome: str,
    *,
    syntax_valid: bool,
    hostile: tuple[str, ...] = (),
    category: str | None = None,
    newline_appended: bool = False,
) -> AttemptRecord:
    """Build one attempt record.

    Args:
        number: The attempt number.
        outcome: Its outcome.
        syntax_valid: Whether its completion parsed.
        hostile: The screen rules it tripped.
        category: Its failure category.
        newline_appended: Whether the harness appended a newline.

    Returns:
        The attempt.
    """
    return AttemptRecord(
        attempt=number,
        prompt_sha256="0" * 64,
        grammar_sent=False,
        completion="",
        stop_reason="end",
        newline_appended=newline_appended,
        outcome=outcome,
        category=category,
        command_index=None,
        hostile_reasons=hostile,
        syntax_valid=syntax_valid,
        plan_pml=None,
        execution=None,
    )


def _record(
    sample_id: str,
    attempts: tuple[AttemptRecord, ...],
    *,
    category: str = "color/resn/single",
    empty: str | None = None,
    grading_complete: bool = True,
    vacuous: bool = False,
    condition: str = CONDITION_NO_GRAMMAR,
) -> SampleRecord:
    """Build one sample record whose final outcome is its last attempt's.

    Args:
        sample_id: The sample identity.
        attempts: Its attempts.
        category: Its taxonomy category.
        empty: Its empty-selection flag.
        grading_complete: Whether its assertions see the whole state.
        vacuous: Whether it predicts no change.
        condition: The run's condition.

    Returns:
        The record.
    """
    final = attempts[-1].outcome
    return SampleRecord(
        sample_id=sample_id,
        category=category,
        difficulty="basic",
        spec_id="two_chains_hetatm",
        condition=condition,
        attempts=attempts,
        final_outcome=final,
        assertions=(),
        task_success=final == OUTCOME_SUCCESS,
        empty_selection=empty,
        grading_complete=grading_complete,
        vacuous=vacuous,
    )


#: Four samples, one of each kind of path:
#: s1 succeeds at once; s2 fails to parse, then is repaired to success;
#: s3 is prose, refused by the screen; s4 executes to the wrong state.
FIXTURE = (
    _record(
        "s1",
        (_attempt(1, OUTCOME_SUCCESS, syntax_valid=True),),
        empty="false",
    ),
    _record(
        "s2",
        (
            _attempt(
                1,
                OUTCOME_SYNTAX_INVALID,
                syntax_valid=False,
                category="unknown_verb",
                newline_appended=True,
            ),
            _attempt(2, OUTCOME_SUCCESS, syntax_valid=True),
        ),
        category="color+select/chain+resn/and",
        empty="false",
        grading_complete=False,
    ),
    _record(
        "s3",
        (
            _attempt(
                1,
                OUTCOME_DENIED_HOSTILE,
                syntax_valid=False,
                hostile=("character:'", "verb:set"),
            ),
        ),
        vacuous=True,
    ),
    _record(
        "s4",
        (_attempt(1, OUTCOME_EXECUTED_WRONG, syntax_valid=True),),
        empty="true",
    ),
)


def test_outcomes_partition_the_samples() -> None:
    """Every sample has exactly one attempt-1 and one final outcome."""
    report = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)

    for stage in ("attempt_1", "final"):
        assert set(report["outcomes"][stage]) == set(OUTCOMES)
        assert sum(report["outcomes"][stage].values()) == len(FIXTURE)
    assert report["outcomes"]["final"][OUTCOME_SUCCESS] == 2


def test_rates_on_a_hand_computed_fixture() -> None:
    """Each headline rate counts the samples it should."""
    overall = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)["overall"]

    assert overall["n"] == 4
    assert (overall["task_success"]["k"], overall["task_success"]["n"]) == (
        2,
        4,
    )
    assert overall["task_success_first_attempt"]["k"] == 1
    assert overall["syntax_valid"]["k"] == 2
    assert overall["policy_denied"]["k"] == 1
    assert overall["denied_hostile"]["k"] == 1
    assert overall["abstention"]["k"] == 0
    assert (
        overall["empty_selection"]["k"],
        overall["empty_selection"]["n"],
    ) == (
        1,
        3,
    )
    assert overall["repair"]["mean_attempts"] == 1.25
    assert overall["newline_appended"] == {"attempt_1": 1, "all_attempts": 1}


def test_wilson_matches_the_audit_helper() -> None:
    """The interval is the label audit's own, rounded."""
    rate = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)["overall"][
        "task_success"
    ]

    low, high = wilson_interval(2, 4)

    assert rate["rate"] == 0.5
    assert rate["wilson"] == [round(low, 6), round(high, 6)]


def test_repair_denominator_is_repairable_first_failures_only() -> None:
    """Only a sample the graph actually repaired counts toward repair."""
    repair = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)["overall"][
        "repair"
    ]

    assert repair["eligible"] == 1
    assert (repair["to_valid"]["k"], repair["to_valid"]["n"]) == (1, 1)
    assert (repair["to_success"]["k"], repair["to_success"]["n"]) == (1, 1)


def test_subsets_exclude_incomplete_and_vacuous() -> None:
    """The fully graded and non-vacuous rates drop exactly those samples."""
    overall = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)["overall"]

    graded = overall["task_success_fully_graded"]
    substantive = overall["task_success_non_vacuous"]

    assert (graded["k"], graded["n"]) == (1, 3)
    assert (substantive["k"], substantive["n"]) == (2, 3)


def test_failure_causes_are_tallied() -> None:
    """The report says why attempt 1 failed, not only that it did."""
    failures = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)[
        "attempt_1_failures"
    ]

    assert failures["syntax_invalid"] == {"unknown_verb": 1}
    assert failures["denied_hostile"] == {"character:'": 1, "verb:set": 1}


def test_zero_by_construction_rates_render_na() -> None:
    """A structural zero is labelled as one, never shown as model behaviour."""
    grammar = [
        dataclasses.replace(r, condition=CONDITION_GRAMMAR) for r in FIXTURE
    ]
    no_grammar = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)
    with_grammar = aggregate(grammar, condition=CONDITION_GRAMMAR)

    assert with_grammar["overall"]["abstention"]["by_construction"]
    assert not no_grammar["overall"]["abstention"]["by_construction"]
    assert no_grammar["overall"]["denied_policy"]["by_construction"]
    text = render_markdown(
        {"test_gold": {"no-grammar": no_grammar, "grammar": with_grammar}}
    )
    abstention = next(
        line for line in text.splitlines() if line.startswith("| Abstention")
    )
    cells = [cell.strip() for cell in abstention.strip("|").split("|")]
    assert cells[1].startswith("0/4 ")
    assert cells[2] == "n/a (0 by construction)"


def test_an_abstention_under_the_grammar_is_reported_not_hidden() -> None:
    """A nonzero count is never labelled structural, whatever the condition."""
    asked = _record(
        "s5",
        (_attempt(1, OUTCOME_ABSTAINED, syntax_valid=False),),
        condition=CONDITION_GRAMMAR,
    )

    abstention = aggregate([asked], condition=CONDITION_GRAMMAR)["overall"][
        "abstention"
    ]

    assert abstention["k"] == 1
    assert not abstention["by_construction"]


def test_a_sample_with_two_terms_counts_under_both() -> None:
    """The term breakout overlaps; the verb-set breakout partitions."""
    breakouts = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)["breakouts"]

    assert breakouts["term"]["chain"]["n"] == 1
    assert breakouts["term"]["resn"]["n"] == 4
    assert sum(group["n"] for group in breakouts["verb_set"].values()) == 4


def test_a_record_from_another_condition_is_refused() -> None:
    """One report describes one condition."""
    mixed = [
        *FIXTURE,
        _record(
            "s9",
            (_attempt(1, OUTCOME_SUCCESS, syntax_valid=True),),
            condition=CONDITION_GRAMMAR,
        ),
    ]

    with pytest.raises(ValueError, match="condition"):
        aggregate(mixed, condition=CONDITION_NO_GRAMMAR)


def test_category_parts_rejects_a_malformed_category() -> None:
    """A category must have its three parts."""
    assert category_parts("color+select/chain+resn/and") == (
        "color+select",
        ("chain", "resn"),
        "and",
    )
    with pytest.raises(ValueError, match="taxonomy category"):
        category_parts("color/resn")


def test_render_has_a_column_per_condition() -> None:
    """The rendered report puts the two conditions side by side."""
    report = aggregate(FIXTURE, condition=CONDITION_NO_GRAMMAR)
    grammar = aggregate(
        [dataclasses.replace(r, condition=CONDITION_GRAMMAR) for r in FIXTURE],
        condition=CONDITION_GRAMMAR,
    )

    text = render_markdown(
        {"test_gold": {"no-grammar": report, "grammar": grammar}}
    )

    assert text.startswith("## test_gold (4 samples)\n")
    assert "| Metric | no-grammar | grammar |" in text
    assert "| **TaskSuccess** | 2/4 (50.0%, " in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
