# Copyright 2026 PyMOL Copilot contributors.
"""Integration tests for the non-mutating client command seam."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import uuid

from pmc_client.command import FIXTURE_INTENT
from pmc_client.command import CopilotCommandClient
from pmc_core.plan import initial_fixture_plan
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.protocol import ValidatedPlanResponseV1

SESSION_ID = "22222222-2222-4222-8222-222222222222"
CREATED_AT = "2026-08-26T14:22:03.123Z"
FIXTURE_PML = (
    "select copilot_selection, chain A\ncolor red, copilot_selection\n"
)


@dataclass
class RecordingTransport:
    """Record requests and return a supplied typed response."""

    response_factory: Callable[
        [PlanRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1
    ]
    requests: list[PlanRequestV1]

    def submit(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Record and handle one request."""
        self.requests.append(request)
        return self.response_factory(request)


@dataclass
class RecordingCmd:
    """Minimal command registry double."""

    name: str | None = None
    callback: Callable[[str], None] | None = None

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Record the registered command."""
        self.name = name
        self.callback = callback


def validated_response(request: PlanRequestV1) -> ValidatedPlanResponseV1:
    """Build a successful response correlated to a request."""
    return ValidatedPlanResponseV1(
        request_id=request.request_id,
        session_id=request.session_id,
        received_at=CREATED_AT,
        validated_at=CREATED_AT,
        action_plan=initial_fixture_plan(),
        validation=ValidationReportV1("passed", request.snapshot.digest, ()),
        plan_id="55555555-5555-4555-8555-555555555555",
        snapshot_digest=request.snapshot.digest,
    )


def uuid_factory() -> Callable[[], uuid.UUID]:
    """Return a deterministic sequence of UUIDv4 values."""
    values = iter(
        (
            uuid.UUID(SESSION_ID),
            uuid.UUID("33333333-3333-4333-8333-333333333333"),
            uuid.UUID("44444444-4444-4444-8444-444444444444"),
        )
    )
    return lambda: next(values)


def test_command_builds_fixture_request_and_reports_canonical_plan() -> None:
    """The command submits the accepted fixture and reports its PML."""
    requests: list[PlanRequestV1] = []
    transport = RecordingTransport(validated_response, requests)
    output: list[str] = []
    client = CopilotCommandClient(
        transport,
        output.append,
        uuid_factory=uuid_factory(),
        timestamp_factory=lambda: CREATED_AT,
    )

    client.copilot(FIXTURE_INTENT)

    request = requests[0]
    assert request.request_id == "33333333-3333-4333-8333-333333333333"
    assert request.session_id == SESSION_ID
    assert request.created_at == CREATED_AT
    assert request.intent == FIXTURE_INTENT
    assert request.contract_manifest.to_dict() == {
        "planVersion": "1",
        "policyVersion": "1",
        "snapshotVersion": "1",
    }
    assert request.snapshot.to_dict() == {
        "schemaVersion": "1",
        "digest": "sha256:example-chain-a-digest",
        "fixtureId": "one-object-chain-a-v1",
    }
    assert output == ["copilot validation: passed", FIXTURE_PML]


def test_client_reuses_session_and_generates_unique_request_ids() -> None:
    """One client reuses its session while requests receive new IDs."""
    requests: list[PlanRequestV1] = []
    transport = RecordingTransport(validated_response, requests)
    client = CopilotCommandClient(
        transport,
        lambda _text: None,
        uuid_factory=uuid_factory(),
        timestamp_factory=lambda: CREATED_AT,
    )

    client.copilot(FIXTURE_INTENT)
    client.copilot(FIXTURE_INTENT)

    assert requests[0].session_id == requests[1].session_id == client.session_id
    assert requests[0].request_id != requests[1].request_id
    assert all(
        uuid.UUID(request.request_id).version == 4 for request in requests
    )


def test_registers_only_the_non_mutating_copilot_command() -> None:
    """Registration exposes only the intended command name and callback."""
    cmd = RecordingCmd()
    client = CopilotCommandClient(
        RecordingTransport(validated_response, []), lambda _text: None
    )

    client.register(cmd)

    assert cmd.name == "copilot"
    assert cmd.callback == client.copilot


def test_typed_failure_reports_diagnostic_without_plan_text() -> None:
    """A typed failure reports a diagnostic without a plan."""

    def failed_response(request: PlanRequestV1) -> FailedPlanResponseV1:
        """Build a correlated typed policy failure."""
        return FailedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            failure=FailureEnvelopeV1("policy", "command denied", False),
        )

    output: list[str] = []
    client = CopilotCommandClient(
        RecordingTransport(failed_response, []), output.append
    )

    client.copilot(FIXTURE_INTENT)

    assert output == ["copilot failed (policy; not retryable): command denied"]


def test_failed_validation_reports_status_without_rendering_plan() -> None:
    """A non-passing validation status prevents plan rendering."""

    def failed_validation(
        request: PlanRequestV1,
    ) -> ValidatedPlanResponseV1:
        """Build a correlated response with failed validation."""
        response = validated_response(request)
        return ValidatedPlanResponseV1(
            request_id=response.request_id,
            session_id=response.session_id,
            received_at=response.received_at,
            validated_at=response.validated_at,
            action_plan=response.action_plan,
            validation=ValidationReportV1(
                "failed", request.snapshot.digest, ()
            ),
            plan_id=response.plan_id,
            snapshot_digest=response.snapshot_digest,
        )

    output: list[str] = []
    client = CopilotCommandClient(
        RecordingTransport(failed_validation, []), output.append
    )

    client.copilot(FIXTURE_INTENT)

    assert output == [
        "copilot validation failed: "
        "status=failed; snapshot=sha256:example-chain-a-digest"
    ]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__]))
