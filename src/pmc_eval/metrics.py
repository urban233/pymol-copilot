# Copyright 2026 PyMOL Copilot contributors.
"""Aggregating evaluated samples into the rates item 16 reports.

`aggregate` is a pure function of a run's `SampleRecord`s, so a
committed report can be recomputed from its committed samples and must
come out identical. Every rate carries its count, its denominator and a
Wilson 95% interval (`pmc_data.audit.wilson_interval`, the same one the
label audit uses): with 68 gold samples, an interval is the honest way
to state a rate, and per-category counts of one or two are only ever
descriptive.

Two rates are zero by construction, and the report says so rather than
presenting a zero as something the model did:

- A policy denial: `pmc_core.parser` and `pmc_core.policy` enforce the
  same allowlist independently, so a plan that parses cannot be denied
  (`pmc_agent.graph`'s `validating` docstring).
- An abstention under the grammar: `pmc_core.grammar`'s root rule is
  `command+`, with no way to write `ask:` or nothing at all.

Every abstention that does occur is a false one: no evaluation sample
is ambiguous, so none calls for a question.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections import Counter
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from pmc_data.audit import wilson_interval
from pmc_eval.grade import EMPTY_SELECTION_TRUE
from pmc_eval.grade import EMPTY_SELECTION_UNKNOWN
from pmc_eval.record import EXECUTED_OUTCOMES
from pmc_eval.record import OUTCOME_ABSTAINED
from pmc_eval.record import OUTCOME_DENIED_HOSTILE
from pmc_eval.record import OUTCOME_DENIED_POLICY
from pmc_eval.record import OUTCOME_EXECUTION_FAILED
from pmc_eval.record import OUTCOME_SUCCESS
from pmc_eval.record import OUTCOME_SYNTAX_INVALID
from pmc_eval.record import OUTCOME_TRUNCATED
from pmc_eval.record import OUTCOMES
from pmc_eval.record import SampleRecord
from pmc_eval.runner import CONDITION_GRAMMAR
from pmc_eval.runner import CONDITION_NO_GRAMMAR

#: The version of the report shape and of every rate's definition. Any
#: change to what a rate counts, or to its denominator, is a bump.
REPORT_VERSION = 1

#: The digits a rate or bound is rounded to, so a recomputed report is
#: byte-identical to the stored one.
_DIGITS = 6

#: How the rendered report orders its breakouts, and titles each.
BREAKOUTS: tuple[tuple[str, str], ...] = (
    ("verb_set", "verb set"),
    ("term", "selection term"),
    ("shape", "expression shape"),
    ("difficulty", "difficulty"),
    ("spec", "held-out structure"),
    ("category", "category"),
)


def category_parts(category: str) -> tuple[str, tuple[str, ...], str]:
    """Split a `pmc_data.taxonomy.categorize` category into its parts.

    Args:
        category: A category, `<verbs>/<terms>/<shape>`.

    Returns:
        The verb set, the selection terms, and the shape.

    Raises:
        ValueError: If the category does not have exactly three parts.
    """
    parts = category.split("/")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"not a taxonomy category: {category!r}")
    verbs, terms, shape = parts
    return verbs, tuple(terms.split("+")), shape


def _rate(k: int, n: int) -> dict[str, Any]:
    """State one proportion with its interval.

    Args:
        k: The count.
        n: The denominator.

    Returns:
        The count, denominator, rate and Wilson 95% bounds; the rate and
        bounds are None when the denominator is zero.
    """
    if n == 0:
        return {"k": k, "n": n, "rate": None, "wilson": None}
    low, high = wilson_interval(k, n)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, _DIGITS),
        "wilson": [round(low, _DIGITS), round(high, _DIGITS)],
    }


def _count(
    records: Iterable[SampleRecord], predicate: Callable[[SampleRecord], bool]
) -> int:
    """Count the records a predicate holds for.

    Args:
        records: The records to count over.
        predicate: The condition to count.

    Returns:
        How many records satisfy it.
    """
    return sum(1 for record in records if predicate(record))


def _block(records: Sequence[SampleRecord], condition: str) -> dict[str, Any]:
    """Compute every rate over one group of records.

    Args:
        records: The group.
        condition: The run's condition, which decides what is zero by
            construction.

    Returns:
        The group's rates.
    """
    n = len(records)
    graded = [r for r in records if r.grading_complete]
    substantive = [r for r in records if not r.vacuous]
    executed = [r for r in records if r.final_outcome in EXECUTED_OUTCOMES]
    eligible = [r for r in records if len(r.attempts) > 1]

    def first(outcomes: frozenset[str]) -> int:
        return _count(records, lambda r: r.attempts[0].outcome in outcomes)

    denied_policy = _rate(first(frozenset({OUTCOME_DENIED_POLICY})), n)
    denied_policy["by_construction"] = denied_policy["k"] == 0
    abstention = _rate(
        _count(records, lambda r: r.final_outcome == OUTCOME_ABSTAINED), n
    )
    abstention["by_construction"] = (
        condition == CONDITION_GRAMMAR and abstention["k"] == 0
    )
    empty = _rate(
        _count(executed, lambda r: r.empty_selection == EMPTY_SELECTION_TRUE),
        len(executed),
    )
    empty["unknown"] = _count(
        executed, lambda r: r.empty_selection == EMPTY_SELECTION_UNKNOWN
    )
    return {
        "n": n,
        "task_success": _rate(_count(records, lambda r: r.task_success), n),
        "task_success_first_attempt": _rate(
            first(frozenset({OUTCOME_SUCCESS})), n
        ),
        "task_success_fully_graded": _rate(
            _count(graded, lambda r: r.task_success), len(graded)
        ),
        "task_success_non_vacuous": _rate(
            _count(substantive, lambda r: r.task_success), len(substantive)
        ),
        "syntax_valid": _rate(
            _count(records, lambda r: r.attempts[0].syntax_valid), n
        ),
        "policy_denied": _rate(
            first(frozenset({OUTCOME_DENIED_HOSTILE, OUTCOME_DENIED_POLICY})),
            n,
        ),
        "denied_hostile": _rate(first(frozenset({OUTCOME_DENIED_HOSTILE})), n),
        "denied_policy": denied_policy,
        "abstention": abstention,
        "truncated": _rate(
            _count(records, lambda r: r.final_outcome == OUTCOME_TRUNCATED), n
        ),
        "empty_selection": empty,
        "repair": {
            "eligible": len(eligible),
            "to_valid": _rate(
                _count(
                    eligible, lambda r: r.final_outcome in EXECUTED_OUTCOMES
                ),
                len(eligible),
            ),
            "to_success": _rate(
                _count(eligible, lambda r: r.task_success), len(eligible)
            ),
            "mean_attempts": (
                round(sum(len(r.attempts) for r in records) / n, _DIGITS)
                if n
                else None
            ),
        },
        "newline_appended": {
            "attempt_1": _count(
                records, lambda r: r.attempts[0].newline_appended
            ),
            "all_attempts": sum(
                1 for r in records for a in r.attempts if a.newline_appended
            ),
        },
    }


def _groups(
    records: Sequence[SampleRecord], breakout: str
) -> dict[str, list[SampleRecord]]:
    """Group records by one breakout.

    A sample using several selection terms is counted under each of them,
    so the term groups overlap; every other breakout partitions.

    Args:
        records: The records to group.
        breakout: One of the `BREAKOUTS` keys.

    Returns:
        Each group's key and its records, keys sorted.

    Raises:
        ValueError: If `breakout` is not one of `BREAKOUTS`.
    """
    groups: dict[str, list[SampleRecord]] = {}
    for record in records:
        verbs, terms, shape = category_parts(record.category)
        if breakout == "verb_set":
            keys: tuple[str, ...] = (verbs,)
        elif breakout == "term":
            keys = terms
        elif breakout == "shape":
            keys = (shape,)
        elif breakout == "difficulty":
            keys = (record.difficulty,)
        elif breakout == "spec":
            keys = (record.spec_id,)
        elif breakout == "category":
            keys = (record.category,)
        else:
            raise ValueError(f"unknown breakout {breakout!r}")
        for key in keys:
            groups.setdefault(key, []).append(record)
    return dict(sorted(groups.items()))


def aggregate(
    records: Sequence[SampleRecord], *, condition: str
) -> dict[str, Any]:
    """Compute a run's full report from its records.

    Args:
        records: Every record of one run.
        condition: The run's condition.

    Returns:
        The report: overall rates, every breakout, the outcome
        distributions, and the failure-category tallies.

    Raises:
        ValueError: If a record belongs to another condition, a sample
            appears twice, or the condition is unknown.
    """
    if condition not in {CONDITION_NO_GRAMMAR, CONDITION_GRAMMAR}:
        raise ValueError(f"unknown condition {condition!r}")
    if any(record.condition != condition for record in records):
        raise ValueError(f"a record is not from the {condition} condition")
    identities = [record.sample_id for record in records]
    if len(set(identities)) != len(identities):
        raise ValueError("a sample appears more than once")
    ordered = sorted(records, key=lambda record: record.sample_id)
    first_attempts = [record.attempts[0] for record in ordered]
    return {
        "report_version": REPORT_VERSION,
        "condition": condition,
        "overall": _block(ordered, condition),
        "breakouts": {
            breakout: {
                key: _block(group, condition)
                for key, group in _groups(ordered, breakout).items()
            }
            for breakout, _ in BREAKOUTS
        },
        "outcomes": {
            "attempt_1": {
                outcome: sum(1 for a in first_attempts if a.outcome == outcome)
                for outcome in OUTCOMES
            },
            "final": {
                outcome: sum(1 for r in ordered if r.final_outcome == outcome)
                for outcome in OUTCOMES
            },
        },
        "attempt_1_failures": {
            "syntax_invalid": dict(
                sorted(
                    Counter(
                        a.category or "none"
                        for a in first_attempts
                        if a.outcome == OUTCOME_SYNTAX_INVALID
                    ).items()
                )
            ),
            "denied_hostile": dict(
                sorted(
                    Counter(
                        reason
                        for a in first_attempts
                        if a.outcome == OUTCOME_DENIED_HOSTILE
                        for reason in a.hostile_reasons
                    ).items()
                )
            ),
            "execution_failed": dict(
                sorted(
                    Counter(
                        a.category or "none"
                        for a in first_attempts
                        if a.outcome == OUTCOME_EXECUTION_FAILED
                    ).items()
                )
            ),
        },
    }


def _format_rate(rate: Mapping[str, Any]) -> str:
    """Render one rate as `k/n (p%, lo-hi%)`.

    Args:
        rate: A rate from `_rate`.

    Returns:
        The rendered rate, or `n/a` for an empty denominator.
    """
    if rate["n"] == 0:
        return "n/a (no samples)"
    if rate.get("by_construction"):
        return "n/a (0 by construction)"
    low, high = rate["wilson"]
    return (
        f"{rate['k']}/{rate['n']} ({100 * rate['rate']:.1f}%, "
        f"{100 * low:.1f}-{100 * high:.1f}%)"
    )


#: The rows of each set's headline table: a label and how to find the
#: rate in an overall block.
_HEADLINE_ROWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("**TaskSuccess**", ("task_success",)),
    ("TaskSuccess, attempt 1", ("task_success_first_attempt",)),
    ("TaskSuccess, fully graded samples", ("task_success_fully_graded",)),
    ("TaskSuccess, non-vacuous samples", ("task_success_non_vacuous",)),
    ("Syntax-valid, attempt 1", ("syntax_valid",)),
    ("Policy-denied, attempt 1", ("policy_denied",)),
    ("— of which hostile screen", ("denied_hostile",)),
    ("— of which policy", ("denied_policy",)),
    ("Abstention (false)", ("abstention",)),
    ("Truncated", ("truncated",)),
    ("Empty selection, executed plans", ("empty_selection",)),
    ("Repair to a valid plan", ("repair", "to_valid")),
    ("Repair to TaskSuccess", ("repair", "to_success")),
)


def _lookup(block: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    """Follow a key path into a report block.

    Args:
        block: An overall or breakout block.
        path: The keys to follow.

    Returns:
        The value at the end of the path.
    """
    value: Any = block
    for key in path:
        value = value[key]
    return value


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    """Render one Markdown table.

    Args:
        header: The column titles.
        rows: The rows, each as long as the header.

    Returns:
        The table's lines.
    """
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def render_markdown(
    reports: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> str:
    """Render reports side by side, one section per evaluation set.

    Args:
        reports: For each set name, each condition's report.

    Returns:
        The Markdown text.
    """
    lines: list[str] = []
    for set_name, by_condition in reports.items():
        conditions = [
            c
            for c in (CONDITION_NO_GRAMMAR, CONDITION_GRAMMAR)
            if c in by_condition
        ]
        overall = {c: by_condition[c]["overall"] for c in conditions}
        n = next(iter(overall.values()))["n"] if overall else 0
        lines += [f"## {set_name} ({n} samples)", ""]
        lines += _table(
            ["Metric", *conditions],
            (
                [label]
                + [_format_rate(_lookup(overall[c], path)) for c in conditions]
                for label, path in _HEADLINE_ROWS
            ),
        )
        lines += [
            "",
            "Mean attempts per sample: "
            + ", ".join(
                f"{c} {overall[c]['repair']['mean_attempts']}"
                for c in conditions
            )
            + ". Completions missing their final newline (attempt 1, "
            "normalized by the harness): "
            + ", ".join(
                f"{c} {overall[c]['newline_appended']['attempt_1']}"
                for c in conditions
            )
            + ".",
            "",
            "### Outcomes",
            "",
        ]
        lines += _table(
            [
                "Outcome",
                *(f"{c} attempt 1" for c in conditions),
                *(f"{c} final" for c in conditions),
            ],
            (
                [outcome]
                + [
                    str(by_condition[c]["outcomes"]["attempt_1"][outcome])
                    for c in conditions
                ]
                + [
                    str(by_condition[c]["outcomes"]["final"][outcome])
                    for c in conditions
                ]
                for outcome in OUTCOMES
            ),
        )
        lines += ["", "### Attempt-1 failures, by cause", ""]
        for kind in ("syntax_invalid", "denied_hostile", "execution_failed"):
            causes = sorted(
                {
                    cause
                    for c in conditions
                    for cause in by_condition[c]["attempt_1_failures"][kind]
                }
            )
            if not causes:
                continue
            lines += [f"`{kind}`:", ""]
            lines += _table(
                ["Cause", *conditions],
                (
                    [f"`{cause}`"]
                    + [
                        str(
                            by_condition[c]["attempt_1_failures"][kind].get(
                                cause, 0
                            )
                        )
                        for c in conditions
                    ]
                    for cause in causes
                ),
            )
            lines.append("")
        for breakout, title in BREAKOUTS:
            keys = sorted(
                {
                    key
                    for c in conditions
                    for key in by_condition[c]["breakouts"][breakout]
                }
            )
            lines += [f"### TaskSuccess by {title}", ""]
            lines += _table(
                [title.capitalize(), "n", *conditions],
                (
                    [
                        f"`{key}`",
                        str(
                            by_condition[conditions[0]]["breakouts"][breakout][
                                key
                            ]["n"]
                        ),
                    ]
                    + [
                        _format_rate(
                            by_condition[c]["breakouts"][breakout][key][
                                "task_success"
                            ]
                        )
                        for c in conditions
                    ]
                    for key in keys
                ),
            )
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
