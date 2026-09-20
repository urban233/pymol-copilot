# Copyright 2026 PyMOL Copilot contributors.
"""Integration tests for the authenticated local plan transport."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import logging
from http import HTTPStatus
from http.client import HTTPConnection

import pytest

from pmc_client.transport import CREDENTIAL_HEADER
from pmc_client.transport import LOOPBACK_HOST
from pmc_client.transport import MAX_MESSAGE_BYTES
from pmc_client.transport import PLAN_PATH
from pmc_client.transport import LoopbackPlanClient
from pmc_client.transport import TransportError
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import Factor
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectionExpression
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import ExecutionReportV1
from pmc_core.protocol import ExecutionRequestV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1
from pmc_server.lifecycle import FIXTURE_PLAN
from pmc_server.transport import MAX_EXECUTION_REQUEST_BYTES
from pmc_server.transport import VALIDATE_PATH
from pmc_server.transport import LoopbackPlanServer
from pmc_server.validation import PlanValidationService

REQUEST_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"


def plan_request() -> PlanRequestV1:
    """Build the accepted V1 request fixture.

    Returns:
        The accepted plan request.
    """
    return PlanRequestV1(
        request_id=REQUEST_ID,
        session_id=SESSION_ID,
        created_at="2026-08-26T14:22:03.123Z",
        contract_manifest=ContractManifestV1("1", "1", "1"),
        intent="Select chain A and color it red.",
        snapshot=StructureSnapshotV1(
            schema_version="1",
            digest="sha256:example-chain-a-digest",
            object_name="one-object-chain-a-v1",
            atom_count=2,
            state_count=1,
        ),
        fidelity=FidelityOutcomeV1(
            status=FIDELITY_EXACT,
            reason=REASON_OK,
            mismatch_count=0,
            mismatches=(),
        ),
    )


def validated_response(request: PlanRequestV1) -> ValidatedPlanResponseV1:
    """Build the response matching a request's correlation values.

    Args:
        request: Request whose correlation values are copied.

    Returns:
        A successful typed response.
    """
    return ValidatedPlanResponseV1(
        request_id=request.request_id,
        session_id=request.session_id,
        received_at="2026-08-26T14:22:03.124Z",
        validated_at="2026-08-26T14:22:03.220Z",
        action_plan=FIXTURE_PLAN,
        validation=ValidationReportV1(
            "passed", "sha256:example-chain-a-digest", True, ()
        ),
        plan_id="33333333-3333-4333-8333-333333333333",
        snapshot_digest="sha256:example-chain-a-digest",
    )


def test_client_round_trips_authenticated_request_over_loopback() -> None:
    """The public client receives the typed response from a loopback server."""
    with LoopbackPlanServer("secret", validated_response) as server:
        response = LoopbackPlanClient(server.port, "secret").submit(
            plan_request()
        )

    assert server.host == LOOPBACK_HOST
    assert response.request_id == REQUEST_ID
    assert response.session_id == SESSION_ID


def test_server_rejects_wrong_credential_without_parsing_request() -> None:
    """A wrong credential cannot reach the request lifecycle callback."""
    requests: list[PlanRequestV1] = []

    def record_request(request: PlanRequestV1) -> ValidatedPlanResponseV1:
        """Record and respond to one decoded request.

        Args:
            request: Request to record and handle.

        Returns:
            A successful typed response.
        """
        requests.append(request)
        return validated_response(request)

    with LoopbackPlanServer("secret", record_request) as server:
        connection = HTTPConnection(LOOPBACK_HOST, server.port)
        connection.request(
            "POST",
            PLAN_PATH,
            body=b"{not valid JSON",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "15",
                CREDENTIAL_HEADER: "wrong-secret",
            },
        )
        response = connection.getresponse()
        response.read()
        connection.close()

    assert response.status == HTTPStatus.UNAUTHORIZED
    assert requests == []


def test_server_rejects_payload_larger_than_transport_limit() -> None:
    """An authenticated oversized payload cannot reach request decoding."""
    requests: list[PlanRequestV1] = []
    payload = b"x" * (MAX_MESSAGE_BYTES + 1)

    def record_request(request: PlanRequestV1) -> ValidatedPlanResponseV1:
        """Record and respond to one decoded request.

        Args:
            request: Request to record and handle.

        Returns:
            A successful typed response.
        """
        requests.append(request)
        return validated_response(request)

    with LoopbackPlanServer("secret", record_request) as server:
        connection = HTTPConnection(LOOPBACK_HOST, server.port)
        connection.request(
            "POST",
            PLAN_PATH,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
                CREDENTIAL_HEADER: "secret",
            },
        )
        response = connection.getresponse()
        response.read()
        connection.close()

    assert response.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert requests == []


def test_server_cannot_restart_after_its_socket_is_closed() -> None:
    """Closing the server makes its loopback socket lifecycle terminal."""
    server = LoopbackPlanServer("secret", validated_response)
    server.start()
    server.close()

    with pytest.raises(RuntimeError, match="closed"):
        server.start()


def test_server_logs_response_metadata_without_request_target(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An untrusted request target is excluded from transport logging.

    Args:
        caplog: Pytest log-capture fixture.
    """
    request_target = f"{PLAN_PATH}?intent=private-intent"
    caplog.set_level(logging.INFO, logger="pmc_server.transport")
    with LoopbackPlanServer("secret", validated_response) as server:
        connection = HTTPConnection(LOOPBACK_HOST, server.port)
        connection.request("POST", request_target)
        response = connection.getresponse()
        response.read()
        connection.close()

    assert response.status == HTTPStatus.NOT_FOUND
    assert "loopback HTTP response completed" in caplog.text
    assert request_target not in caplog.text


def test_client_rejects_response_with_mismatched_correlation() -> None:
    """The client does not accept a typed plan for another request."""

    def mismatched_response(request: PlanRequestV1) -> ValidatedPlanResponseV1:
        """Return a response with a different request identifier.

        Args:
            request: Request whose response should be modified.

        Returns:
            A response with mismatched request correlation.
        """
        response = validated_response(request)
        return ValidatedPlanResponseV1(
            request_id="44444444-4444-4444-8444-444444444444",
            session_id=response.session_id,
            received_at=response.received_at,
            validated_at=response.validated_at,
            action_plan=response.action_plan,
            validation=response.validation,
            plan_id=response.plan_id,
            snapshot_digest=response.snapshot_digest,
        )

    with (
        LoopbackPlanServer("secret", mismatched_response) as server,
        pytest.raises(TransportError, match="correlation"),
    ):
        LoopbackPlanClient(server.port, "secret").submit(plan_request())


def test_client_rejects_response_with_mismatched_session() -> None:
    """The client does not accept a typed plan from another session."""

    def mismatched_response(request: PlanRequestV1) -> ValidatedPlanResponseV1:
        """Return a response with a different session identifier.

        Args:
            request: Request whose response should be modified.

        Returns:
            A response with mismatched session correlation.
        """
        response = validated_response(request)
        return ValidatedPlanResponseV1(
            request_id=response.request_id,
            session_id="44444444-4444-4444-8444-444444444444",
            received_at=response.received_at,
            validated_at=response.validated_at,
            action_plan=response.action_plan,
            validation=response.validation,
            plan_id=response.plan_id,
            snapshot_digest=response.snapshot_digest,
        )

    with (
        LoopbackPlanServer("secret", mismatched_response) as server,
        pytest.raises(TransportError, match="correlation"),
    ):
        LoopbackPlanClient(server.port, "secret").submit(plan_request())


def test_client_rejects_response_for_a_different_snapshot() -> None:
    """The client does not accept a typed plan for a different snapshot."""

    def mismatched_response(request: PlanRequestV1) -> ValidatedPlanResponseV1:
        """Return a response with a different snapshot identifier.

        Args:
            request: Request whose response should be modified.

        Returns:
            A response with a mismatched snapshot identity.
        """
        response = validated_response(request)
        return ValidatedPlanResponseV1(
            request_id=response.request_id,
            session_id=response.session_id,
            received_at=response.received_at,
            validated_at=response.validated_at,
            action_plan=response.action_plan,
            validation=ValidationReportV1(
                response.validation.status,
                "sha256:different-snapshot",
                response.validation.applicable,
                response.validation.warnings,
            ),
            plan_id=response.plan_id,
            snapshot_digest="sha256:different-snapshot",
        )

    with (
        LoopbackPlanServer("secret", mismatched_response) as server,
        pytest.raises(TransportError, match="snapshot identity"),
    ):
        LoopbackPlanClient(server.port, "secret").submit(plan_request())


# --- /v1/validate: the sidecar executor's endpoint (item 4) ---------------


def chain_a() -> SelectionExpression:
    """Build the expression `chain A`.

    Returns:
        A one-term expression matching chain A.
    """
    return SelectionExpression(
        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
    )


def execution_request() -> ExecutionRequestV1:
    """Build an accepted execution request fixture.

    Returns:
        A well-formed request for the /v1/validate endpoint.
    """
    return ExecutionRequestV1(
        plan=ActionPlan(operations=(OrientOperation(target=chain_a()),)),
        plan_id="55555555-5555-4555-8555-555555555555",
        snapshot_digest="sha256:example-digest",
        snapshot_json='{"schema_version":1,"name":"fx"}',
    )


def fake_executor(_request: ExecutionRequest) -> ExecutionReport:
    """Return a fixed successful report, without spawning anything.

    Args:
        _request: The built ExecutionRequest, unused by this fake.

    Returns:
        A fixed successful report.
    """
    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status="ok",
        reason="ok",
        input_digest="sha256:example-digest",
        resulting_fingerprint="sha256:" + "1" * 64,
        selection_counts=(),
        command_outcomes=(CommandOutcome(0, "orient", "ok", None),),
        child_pid=12345,
        child_terminated=True,
        elapsed_seconds=0.05,
        warnings=(),
    )


def test_validate_endpoint_round_trips_over_loopback() -> None:
    """A real HTTP round trip through PlanValidationService's own mapping."""
    service = PlanValidationService(executor=fake_executor)
    with LoopbackPlanServer(
        "secret", validated_response, execution_handler=service
    ) as server:
        connection = HTTPConnection(LOOPBACK_HOST, server.port)
        body = json.dumps(execution_request().to_dict()).encode("utf-8")
        connection.request(
            "POST",
            VALIDATE_PATH,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                CREDENTIAL_HEADER: "secret",
            },
        )
        response = connection.getresponse()
        response_body = response.read()
        connection.close()

    assert response.status == HTTPStatus.OK
    report = ExecutionReportV1.from_dict(json.loads(response_body))
    assert report.status == "ok"
    assert report.reason == "ok"
    assert report.resulting_fingerprint == "sha256:" + "1" * 64
    assert len(report.command_outcomes) == 1
    assert report.command_outcomes[0].verb == "orient"


def test_validate_endpoint_accepts_body_past_plan_transport_limit() -> None:
    """A large snapshot reaches the executor's own typed size rejection."""
    oversized_snapshot = "x" * (MAX_MESSAGE_BYTES + 1)
    request = execution_request()
    request = ExecutionRequestV1(
        plan=request.plan,
        plan_id=request.plan_id,
        snapshot_digest=request.snapshot_digest,
        snapshot_json=oversized_snapshot,
    )
    service = PlanValidationService(max_snapshot_bytes=MAX_MESSAGE_BYTES)
    with LoopbackPlanServer(
        "secret", validated_response, execution_handler=service
    ) as server:
        connection = HTTPConnection(LOOPBACK_HOST, server.port)
        body = json.dumps(request.to_dict()).encode("utf-8")
        assert MAX_MESSAGE_BYTES < len(body) < MAX_EXECUTION_REQUEST_BYTES
        connection.request(
            "POST",
            VALIDATE_PATH,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                CREDENTIAL_HEADER: "secret",
            },
        )
        response = connection.getresponse()
        response_body = response.read()
        connection.close()

    assert response.status == HTTPStatus.OK
    report = ExecutionReportV1.from_dict(json.loads(response_body))
    assert report.status == "rejected"
    assert report.reason == "oversized_input"


def test_validate_endpoint_is_404_with_no_execution_handler_configured() -> (
    None
):
    """A server built without an execution_handler still 404s the path."""
    with LoopbackPlanServer("secret", validated_response) as server:
        connection = HTTPConnection(LOOPBACK_HOST, server.port)
        body = json.dumps(execution_request().to_dict()).encode("utf-8")
        connection.request(
            "POST",
            VALIDATE_PATH,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                CREDENTIAL_HEADER: "secret",
            },
        )
        response = connection.getresponse()
        response.read()
        connection.close()

    assert response.status == HTTPStatus.NOT_FOUND


def test_validate_endpoint_rejects_wrong_credential() -> None:
    """A wrong credential cannot reach the execution handler."""
    calls: list[ExecutionRequestV1] = []

    def counting_service(request: ExecutionRequestV1) -> ExecutionReportV1:
        """Record and forward to the real service.

        Args:
            request: The decoded execution request.

        Returns:
            The service's own mapped report.
        """
        calls.append(request)
        return PlanValidationService(executor=fake_executor)(request)

    with LoopbackPlanServer(
        "secret", validated_response, execution_handler=counting_service
    ) as server:
        connection = HTTPConnection(LOOPBACK_HOST, server.port)
        body = json.dumps(execution_request().to_dict()).encode("utf-8")
        connection.request(
            "POST",
            VALIDATE_PATH,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                CREDENTIAL_HEADER: "wrong-secret",
            },
        )
        response = connection.getresponse()
        response.read()
        connection.close()

    assert response.status == HTTPStatus.UNAUTHORIZED
    assert calls == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
