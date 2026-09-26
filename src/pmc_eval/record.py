# Copyright 2026 PyMOL Copilot contributors.
"""The evidence one evaluated sample leaves behind, and its JSON form.

Every attempt keeps the model's raw completion, so a stored run can be
re-screened, re-parsed and re-aggregated without the model -- which is
what lets `tests/eval/test_committed_baseline.py` prove the committed
report was computed from the committed samples, and still classifies
the same way under today's parser and screen.

Timings are deliberately not part of a record's JSON form: they differ
on every run, and a rerun over the same completions must reproduce a
run's `samples.jsonl` byte for byte. They travel beside it instead.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from pmc_eval.grade import AssertionResult

#: Attempt and sample outcomes, in the request graph's own order of
#: checks. Together they partition every attempt that reached the model.
OUTCOME_TRUNCATED = "truncated"
OUTCOME_ABSTAINED = "abstained"
OUTCOME_DENIED_HOSTILE = "denied_hostile"
OUTCOME_SYNTAX_INVALID = "syntax_invalid"
OUTCOME_DENIED_POLICY = "denied_policy"
OUTCOME_EXECUTION_FAILED = "execution_failed"
OUTCOME_EXECUTED_WRONG = "executed_wrong"
OUTCOME_SUCCESS = "success"

#: Every outcome, in the order reports list them.
OUTCOMES: tuple[str, ...] = (
    OUTCOME_TRUNCATED,
    OUTCOME_ABSTAINED,
    OUTCOME_DENIED_HOSTILE,
    OUTCOME_SYNTAX_INVALID,
    OUTCOME_DENIED_POLICY,
    OUTCOME_EXECUTION_FAILED,
    OUTCOME_EXECUTED_WRONG,
    OUTCOME_SUCCESS,
)

#: The outcomes of a plan that executed with status ok. The grade
#: decides between them.
EXECUTED_OUTCOMES = frozenset({OUTCOME_EXECUTED_WRONG, OUTCOME_SUCCESS})


class InvalidRecordError(ValueError):
    """A stored record is incomplete or malformed."""


def _require(data: Mapping[str, Any], key: str) -> Any:
    """Return one required key of a stored record.

    Args:
        data: The decoded record.
        key: The key that must be present.

    Returns:
        The key's value.

    Raises:
        InvalidRecordError: If the key is absent.
    """
    if key not in data:
        raise InvalidRecordError(f"record is missing {key!r}")
    return data[key]


@dataclass(frozen=True)
class ExecutionSummary:
    """What one sidecar execution reported, without its timing.

    Attributes:
        status: The executor's status.
        reason: The executor's reason.
        resulting_fingerprint: The resulting-state fingerprint, if any.
        selection_counts: Each named selection and its atom count, in
            first-appearance order.
        failed_command_index: The first failing command's index, if any.
        failed_category: That command's normalized error category, if
            PyMOL raised one.
    """

    status: str
    reason: str
    resulting_fingerprint: str | None
    selection_counts: tuple[tuple[str, int], ...]
    failed_command_index: int | None
    failed_category: str | None

    def to_dict(self) -> dict[str, Any]:
        """Render as a JSON-safe mapping.

        Returns:
            The summary's fields.
        """
        return {
            "status": self.status,
            "reason": self.reason,
            "resulting_fingerprint": self.resulting_fingerprint,
            "selection_counts": [list(pair) for pair in self.selection_counts],
            "failed_command_index": self.failed_command_index,
            "failed_category": self.failed_category,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionSummary:
        """Rebuild from `to_dict`'s form.

        Args:
            data: The decoded mapping.

        Returns:
            The summary.
        """
        return cls(
            status=_require(data, "status"),
            reason=_require(data, "reason"),
            resulting_fingerprint=_require(data, "resulting_fingerprint"),
            selection_counts=tuple(
                (str(name), int(count))
                for name, count in _require(data, "selection_counts")
            ),
            failed_command_index=_require(data, "failed_command_index"),
            failed_category=_require(data, "failed_category"),
        )


@dataclass(frozen=True)
class AttemptRecord:
    """One generation and everything the request graph did with it.

    Attributes:
        attempt: The attempt's number, from 1.
        prompt_sha256: SHA-256 of the exact prompt sent.
        grammar_sent: Whether a grammar was sent with it.
        completion: The model's raw completion, before the harness's
            newline normalization.
        stop_reason: Why generation stopped.
        newline_appended: Whether the harness appended the missing final
            newline before the graph saw the completion.
        outcome: One of `OUTCOMES`.
        category: The failure category, when there is one: the parse
            rejection's, the policy reason, the PyMOL error envelope's,
            `engine_incomplete`, or `execution_<reason>`.
        command_index: The command the failure names, if any.
        hostile_reasons: Which screen rules fired, for `denied_hostile`.
        syntax_valid: Whether `parse_pml` accepts the normalized
            completion, decided independently of the screen.
        plan_pml: The canonical plan, when the completion parsed.
        execution: The sidecar's report, when the plan was executed.
    """

    attempt: int
    prompt_sha256: str
    grammar_sent: bool
    completion: str
    stop_reason: str
    newline_appended: bool
    outcome: str
    category: str | None
    command_index: int | None
    hostile_reasons: tuple[str, ...]
    syntax_valid: bool
    plan_pml: str | None
    execution: ExecutionSummary | None

    def to_dict(self) -> dict[str, Any]:
        """Render as a JSON-safe mapping.

        Returns:
            The attempt's fields.
        """
        return {
            "attempt": self.attempt,
            "prompt_sha256": self.prompt_sha256,
            "grammar_sent": self.grammar_sent,
            "completion": self.completion,
            "stop_reason": self.stop_reason,
            "newline_appended": self.newline_appended,
            "outcome": self.outcome,
            "category": self.category,
            "command_index": self.command_index,
            "hostile_reasons": list(self.hostile_reasons),
            "syntax_valid": self.syntax_valid,
            "plan_pml": self.plan_pml,
            "execution": (
                None if self.execution is None else self.execution.to_dict()
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AttemptRecord:
        """Rebuild from `to_dict`'s form.

        Args:
            data: The decoded mapping.

        Returns:
            The attempt.

        Raises:
            InvalidRecordError: If the outcome is not one of `OUTCOMES`.
        """
        outcome = _require(data, "outcome")
        if outcome not in OUTCOMES:
            raise InvalidRecordError(f"unknown attempt outcome {outcome!r}")
        execution = _require(data, "execution")
        return cls(
            attempt=_require(data, "attempt"),
            prompt_sha256=_require(data, "prompt_sha256"),
            grammar_sent=_require(data, "grammar_sent"),
            completion=_require(data, "completion"),
            stop_reason=_require(data, "stop_reason"),
            newline_appended=_require(data, "newline_appended"),
            outcome=outcome,
            category=_require(data, "category"),
            command_index=_require(data, "command_index"),
            hostile_reasons=tuple(_require(data, "hostile_reasons")),
            syntax_valid=_require(data, "syntax_valid"),
            plan_pml=_require(data, "plan_pml"),
            execution=(
                None
                if execution is None
                else ExecutionSummary.from_dict(execution)
            ),
        )


@dataclass(frozen=True)
class AttemptTiming:
    """How long one attempt's engine call and sidecar run took.

    Attributes:
        engine_seconds: Wall-clock seconds in the engine call.
        executor_seconds: Seconds the sidecar reported, if it ran.
    """

    engine_seconds: float
    executor_seconds: float | None


@dataclass(frozen=True)
class SampleRecord:
    """One sample, evaluated under one condition.

    Attributes:
        sample_id: The stored sample's identity.
        category: Its plan category, `<verbs>/<terms>/<shape>`.
        difficulty: Its difficulty.
        spec_id: The structure it was verified on.
        condition: The condition it was evaluated under.
        attempts: Every attempt, in order.
        final_outcome: The last attempt's outcome.
        assertions: Every stored assertion, checked against the final
            execution; empty unless the final plan executed.
        task_success: Whether the final outcome is `success`.
        empty_selection: The final executed plan's empty-selection flag,
            or None when it did not execute.
        grading_complete: Whether the sample's assertions see the whole
            resulting state (`pmc_eval.grade.grading_complete`).
        vacuous: Whether a plan changing nothing passes the sample.
        timings: Per-attempt timings. Not part of `to_dict`.
    """

    sample_id: str
    category: str
    difficulty: str
    spec_id: str
    condition: str
    attempts: tuple[AttemptRecord, ...]
    final_outcome: str
    assertions: tuple[AssertionResult, ...]
    task_success: bool
    empty_selection: str | None
    grading_complete: bool
    vacuous: bool
    timings: tuple[AttemptTiming, ...] = field(default=(), compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Render as a JSON-safe mapping, without timings.

        Returns:
            The record's fields.
        """
        return {
            "sample_id": self.sample_id,
            "category": self.category,
            "difficulty": self.difficulty,
            "spec_id": self.spec_id,
            "condition": self.condition,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "final_outcome": self.final_outcome,
            "assertions": [
                {
                    "kind": a.kind,
                    "passed": a.passed,
                    "expected": a.expected,
                    "observed": a.observed,
                }
                for a in self.assertions
            ],
            "task_success": self.task_success,
            "empty_selection": self.empty_selection,
            "grading_complete": self.grading_complete,
            "vacuous": self.vacuous,
        }

    def timings_dict(self) -> dict[str, Any]:
        """Render this record's timings, keyed by its identity.

        Returns:
            The sample identity, condition and per-attempt timings.
        """
        return {
            "sample_id": self.sample_id,
            "condition": self.condition,
            "attempts": [
                {
                    "engine_seconds": timing.engine_seconds,
                    "executor_seconds": timing.executor_seconds,
                }
                for timing in self.timings
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SampleRecord:
        """Rebuild from `to_dict`'s form.

        Args:
            data: The decoded mapping.

        Returns:
            The record, with no timings.

        Raises:
            InvalidRecordError: If the final outcome is unknown, or
                disagrees with the last attempt or with `task_success`.
        """
        attempts = tuple(
            AttemptRecord.from_dict(attempt)
            for attempt in _require(data, "attempts")
        )
        final_outcome = _require(data, "final_outcome")
        if not attempts or attempts[-1].outcome != final_outcome:
            raise InvalidRecordError(
                f"final outcome {final_outcome!r} is not the last attempt's"
            )
        task_success = _require(data, "task_success")
        if task_success != (final_outcome == OUTCOME_SUCCESS):
            raise InvalidRecordError(
                "task_success disagrees with the final outcome"
            )
        return cls(
            sample_id=_require(data, "sample_id"),
            category=_require(data, "category"),
            difficulty=_require(data, "difficulty"),
            spec_id=_require(data, "spec_id"),
            condition=_require(data, "condition"),
            attempts=attempts,
            final_outcome=final_outcome,
            assertions=tuple(
                AssertionResult(
                    kind=_require(a, "kind"),
                    passed=_require(a, "passed"),
                    expected=_require(a, "expected"),
                    observed=_require(a, "observed"),
                )
                for a in _require(data, "assertions")
            ),
            task_success=task_success,
            empty_selection=_require(data, "empty_selection"),
            grading_complete=_require(data, "grading_complete"),
            vacuous=_require(data, "vacuous"),
        )


@dataclass(frozen=True)
class InfraFailure:
    """A sample the run could not score, because infrastructure failed.

    Never scored: an unavailable engine or a crashed sidecar says nothing
    about the model. A run is not finalized while any remain.

    Attributes:
        sample_id: The sample that could not be scored.
        condition: The condition it was being evaluated under.
        category: The engine failure category, or `execution_<reason>`.
        message: A bounded explanation.
    """

    sample_id: str
    condition: str
    category: str
    message: str
