# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for the callable server-side validation service."""

from __future__ import annotations

from typing import Any

import pytest

from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import SelectionCount
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import Factor
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectionExpression
from pmc_core.protocol import ExecutionRequestV1
from pmc_server.validation import PlanValidationService

_PLAN_ID = "11111111-1111-4111-8111-111111111111"


def chain_a() -> SelectionExpression:
    """Build the expression `chain A`.

    Returns:
        A one-term expression matching chain A.
    """
    return SelectionExpression(
        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
    )


def sample_request(**overrides: Any) -> ExecutionRequestV1:
    """Build a well-formed ExecutionRequestV1, with fields overridden.

    Args:
        **overrides: Fields to override on the well-formed default.

    Returns:
        The constructed request.
    """
    fields: dict[str, Any] = {
        "plan": ActionPlan(operations=(OrientOperation(target=chain_a()),)),
        "plan_id": _PLAN_ID,
        "snapshot_digest": "sha256:example-digest",
        "snapshot_json": '{"schema_version":1,"name":"fx"}',
        "expected_resulting_fingerprint": None,
    }
    fields.update(overrides)
    return ExecutionRequestV1(**fields)


def sample_report(**overrides: Any) -> ExecutionReport:
    """Build a well-formed ExecutionReport, with fields overridden.

    Args:
        **overrides: Fields to override on the well-formed default.

    Returns:
        The constructed report.
    """
    fields: dict[str, Any] = {
        "executor_version": EXECUTOR_VERSION,
        "status": "ok",
        "reason": "ok",
        "input_digest": "sha256:example-digest",
        "resulting_fingerprint": "sha256:" + "1" * 64,
        "selection_counts": (SelectionCount("copilot_sel", 4),),
        "command_outcomes": (CommandOutcome(0, "orient", "ok", None),),
        "child_pid": 12345,
        "child_terminated": True,
        "elapsed_seconds": 0.05,
        "warnings": (),
    }
    fields.update(overrides)
    return ExecutionReport(**fields)


def test_service_calls_executor_exactly_once_and_maps_the_report() -> None:
    """The injected executor runs once; its report maps field for field."""
    calls: list[ExecutionRequest] = []

    def fake_executor(request: ExecutionRequest) -> ExecutionReport:
        calls.append(request)
        return sample_report()

    service = PlanValidationService(executor=fake_executor)

    report = service(sample_request())

    assert len(calls) == 1
    assert report.executor_version == EXECUTOR_VERSION
    assert report.status == "ok"
    assert report.reason == "ok"
    assert report.input_digest == "sha256:example-digest"
    assert report.resulting_fingerprint == "sha256:" + "1" * 64
    assert len(report.selection_counts) == 1
    assert report.selection_counts[0].name == "copilot_sel"
    assert report.selection_counts[0].atom_count == 4
    assert len(report.command_outcomes) == 1
    assert report.command_outcomes[0].index == 0
    assert report.command_outcomes[0].verb == "orient"
    assert report.elapsed_seconds == 0.05
    # child_pid/child_terminated are process-identity evidence, not part
    # of the wire report (ExecutionReportV1 has no such fields).
    assert not hasattr(report, "child_pid")


def test_service_passes_through_snapshot_json_and_plan() -> None:
    """The service builds its ExecutionRequest from the wire request."""
    calls: list[ExecutionRequest] = []

    def fake_executor(request: ExecutionRequest) -> ExecutionReport:
        calls.append(request)
        return sample_report()

    service = PlanValidationService(executor=fake_executor)
    wire_request = sample_request()

    service(wire_request)

    assert len(calls) == 1
    assert calls[0].plan == wire_request.plan
    assert calls[0].snapshot_json == wire_request.snapshot_json
    assert calls[0].expected_snapshot_digest == wire_request.snapshot_digest
    assert calls[0].executor_version == EXECUTOR_VERSION


def test_service_passes_through_expected_resulting_fingerprint() -> None:
    """A caller-supplied expected fingerprint reaches the executor."""
    calls: list[ExecutionRequest] = []

    def fake_executor(request: ExecutionRequest) -> ExecutionReport:
        calls.append(request)
        return sample_report()

    service = PlanValidationService(executor=fake_executor)
    expected = "sha256:" + "0" * 64

    service(sample_request(expected_resulting_fingerprint=expected))

    assert calls[0].expected_resulting_fingerprint == expected


def test_service_enforces_its_own_max_snapshot_bytes_and_deadline() -> None:
    """The service's own limits apply -- the wire request carries none."""
    calls: list[ExecutionRequest] = []

    def fake_executor(request: ExecutionRequest) -> ExecutionReport:
        calls.append(request)
        return sample_report()

    service = PlanValidationService(
        executor=fake_executor,
        max_snapshot_bytes=1024,
        deadline_seconds=5.0,
    )

    service(sample_request())

    assert calls[0].max_snapshot_bytes == 1024
    assert calls[0].deadline_seconds == 5.0


def test_service_maps_every_fail_closed_reason() -> None:
    """Every one of execute()'s own fail-closed outcomes maps through."""
    for status, reason in [
        ("rejected", "malformed_input"),
        ("rejected", "oversized_input"),
        ("rejected", "unsupported_schema_version"),
        ("rejected", "policy_denied"),
        ("rejected", "snapshot_digest_mismatch"),
        ("failed", "spawn_or_load_failure"),
        ("failed", "timeout"),
        ("failed", "child_crash"),
        ("failed", "command_failure"),
        ("failed", "fidelity_mismatch"),
    ]:
        service = PlanValidationService(
            executor=lambda _request, status=status, reason=reason: (
                sample_report(
                    status=status,
                    reason=reason,
                    input_digest=None,
                    resulting_fingerprint=None,
                    selection_counts=(),
                    command_outcomes=(),
                    child_pid=None,
                    child_terminated=None,
                )
            )
        )

        report = service(sample_request())

        assert report.status == status
        assert report.reason == reason


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
