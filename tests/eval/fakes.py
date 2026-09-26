# Copyright 2026 PyMOL Copilot contributors.
"""Scripted executors and completions for the hermetic harness tests.

A scripted executor replays a fixed sequence of reports, one per call,
and records every request it was given, so a test controls exactly what
the request graph sees from the sidecar -- the same discipline
`pmc_agent.inference.fake.FakeEngine` applies to the model.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Sequence

from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_core.errors import CATEGORY_UNKNOWN_COLOR
from pmc_core.errors import ERROR_ENVELOPE_VERSION
from pmc_core.errors import ExecutionErrorV1
from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import SelectionCount


def completion(text: str, stop_reason: str = STOP_END) -> CompletionResult:
    """Build one scripted model completion.

    Args:
        text: The completion text.
        stop_reason: Why generation stopped.

    Returns:
        The completion.
    """
    return CompletionResult(
        text=text, model_identity="fake-engine-v1", stop_reason=stop_reason
    )


def ok_report(
    *,
    fingerprint: str | None,
    counts: Sequence[tuple[str, int]] = (),
    commands: int = 1,
) -> ExecutionReport:
    """Build a successful sidecar report.

    Args:
        fingerprint: The resulting-state fingerprint.
        counts: Each named selection and its atom count.
        commands: How many commands ran, all successfully.

    Returns:
        The report.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:test",
        resulting_fingerprint=fingerprint,
        selection_counts=tuple(
            SelectionCount(name=name, atom_count=count)
            for name, count in counts
        ),
        command_outcomes=tuple(
            CommandOutcome(index=i, verb="color", status=OUTCOME_OK, error=None)
            for i in range(commands)
        ),
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=1.25,
    )


def command_failure_report(
    *, index: int = 0, category: str = CATEGORY_UNKNOWN_COLOR
) -> ExecutionReport:
    """Build a sidecar report of one PyMOL command failing.

    Args:
        index: The failing command's index.
        category: Its normalized error category.

    Returns:
        The report, carrying the command's error envelope.
    """
    envelope = ExecutionErrorV1(
        envelope_version=ERROR_ENVELOPE_VERSION,
        command_index=index,
        verb="color",
        category=category,
        message="unknown color",
    )
    return ExecutionReport(
        executor_version=1,
        status=STATUS_FAILED,
        reason=REASON_COMMAND_FAILURE,
        input_digest="sha256:test",
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(
            CommandOutcome(
                index=index,
                verb="color",
                status=OUTCOME_ERROR,
                error="unknown color",
                error_envelope=envelope,
            ),
        ),
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=1.25,
    )


def failed_report(reason: str) -> ExecutionReport:
    """Build a sidecar report failing for a reason other than a command.

    Args:
        reason: The executor reason, such as a timeout or a crash.

    Returns:
        The report.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_FAILED,
        reason=reason,
        input_digest="sha256:test",
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(),
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=30.0,
    )


class ScriptedExecutor:
    """An executor that replays a fixed sequence of reports."""

    def __init__(self, reports: Sequence[ExecutionReport]) -> None:
        """Create an executor that returns `reports` in order.

        Args:
            reports: One report per expected call.
        """
        self._reports = list(reports)
        self._calls: list[ExecutionRequest] = []

    @property
    def calls(self) -> tuple[ExecutionRequest, ...]:
        """Return every request received so far.

        Returns:
            The requests, in call order.
        """
        return tuple(self._calls)

    def __call__(self, request: ExecutionRequest) -> ExecutionReport:
        """Record `request` and return the next scripted report.

        Args:
            request: The execution request.

        Returns:
            The next report.

        Raises:
            AssertionError: If called more often than scripted.
        """
        if len(self._calls) >= len(self._reports):
            raise AssertionError(
                f"executor called {len(self._calls) + 1} times; only "
                f"{len(self._reports)} reports were scripted"
            )
        report = self._reports[len(self._calls)]
        self._calls.append(request)
        return report
