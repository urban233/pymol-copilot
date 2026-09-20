# Copyright 2026 PyMOL Copilot contributors.
"""Server-owned lifecycle for the sidecar executor's /v1/validate endpoint.

This is the "server-side service" docs/master_plan.md item 4 asks for
alongside `pmc_core.executor` itself: a thin, injectable-seamed wrapper
around `execute()`, following `pmc_server.lifecycle.PlanRequestLifecycle`'s
own shape, that maps a decoded `ExecutionRequestV1` to an
`ExecutionReportV1` for the transport layer to send back.

Unlike `PlanRequestLifecycle.__call__`, this service's `__call__` has no
`FailedPlanResponseV1` fallback: every fail-closed outcome `execute()`
itself can produce -- malformed input, a version mismatch, policy denial,
snapshot-digest mismatch, spawn failure, crash, command failure, and a
fidelity mismatch -- is already representable as an `ExecutionReportV1`,
and `ExecutionRequestV1`'s own wire decode validates its shape before this
service ever sees it. The executor still validates that the action plan's
`snapshotDigest` matches the digest it computes from `snapshotJson`; a
mismatch is a typed rejection, not a separate transport failure. `__call__`
therefore returns `ExecutionReportV1` unconditionally, exactly as
`execute()` itself never raises for any of its own documented failure modes.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Callable

from pmc_core.executor import DEFAULT_DEADLINE_SECONDS
from pmc_core.executor import DEFAULT_MAX_SNAPSHOT_BYTES
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import execute
from pmc_core.protocol import CommandOutcomeV1
from pmc_core.protocol import ExecutionReportV1
from pmc_core.protocol import ExecutionRequestV1
from pmc_core.protocol import SelectionCountV1

type EXECUTOR = Callable[[ExecutionRequest], ExecutionReport]

# Preserve the original public type-alias name.
globals()["Executor"] = EXECUTOR


def _to_wire_report(report: ExecutionReport) -> ExecutionReportV1:
    """Convert an in-process execution report to its V1 wire shape.

    Args:
        report: The report `execute()` returned.

    Returns:
        The report represented with wire-field names and wire sub-types.
    """
    return ExecutionReportV1(
        executor_version=report.executor_version,
        status=report.status,
        reason=report.reason,
        input_digest=report.input_digest,
        resulting_fingerprint=report.resulting_fingerprint,
        selection_counts=tuple(
            SelectionCountV1(name=count.name, atom_count=count.atom_count)
            for count in report.selection_counts
        ),
        command_outcomes=tuple(
            CommandOutcomeV1(
                index=outcome.index,
                verb=outcome.verb,
                status=outcome.status,
                error=outcome.error,
            )
            for outcome in report.command_outcomes
        ),
        elapsed_seconds=report.elapsed_seconds,
        warnings=report.warnings,
    )


class PlanValidationService:
    """Build a typed execution report for one decoded execution request."""

    def __init__(
        self,
        *,
        executor: EXECUTOR = execute,
        max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    ) -> None:
        """Create a service with injectable deterministic sources.

        Args:
            executor: Function that executes the built ExecutionRequest.
                Defaulted to the real `pmc_core.executor.execute`; a test
                injects a fake so it never needs a real spawned process,
                and can assert this service calls it exactly once.
            max_snapshot_bytes: The maximum accepted snapshot size this
                service enforces, independent of anything a caller's own
                wire request could otherwise ask to loosen -- the wire
                request carries no such field.
            deadline_seconds: The wall-clock deadline this service gives
                every attempt, for the same reason.
        """
        self._executor = executor
        self._max_snapshot_bytes = max_snapshot_bytes
        self._deadline_seconds = deadline_seconds

    def __call__(self, request: ExecutionRequestV1) -> ExecutionReportV1:
        """Execute one decoded request and report the outcome.

        Performs no retry of its own: exactly one call to this service's
        own executor per request, matching `execute()`'s own "no internal
        retry" guarantee and orchestration rule 8's "a fresh sidecar per
        attempt" one level up.

        Args:
            request: Decoded execution request to run.

        Returns:
            The typed execution report.
        """
        execution_request = ExecutionRequest(
            executor_version=EXECUTOR_VERSION,
            plan=request.plan,
            snapshot_json=request.snapshot_json,
            expected_snapshot_digest=request.snapshot_digest,
            max_snapshot_bytes=self._max_snapshot_bytes,
            deadline_seconds=self._deadline_seconds,
            expected_resulting_fingerprint=(
                request.expected_resulting_fingerprint
            ),
        )
        return _to_wire_report(self._executor(execution_request))
