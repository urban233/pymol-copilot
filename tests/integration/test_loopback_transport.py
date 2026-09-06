# Copyright 2026 PyMOL Copilot contributors.
"""Integration tests for the authenticated local plan transport."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

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
from pmc_core.plan import initial_fixture_plan
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1
from pmc_server.transport import LoopbackPlanServer

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
            "1", "sha256:example-chain-a-digest", "one-object-chain-a-v1"
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
        action_plan=initial_fixture_plan(),
        validation=ValidationReportV1(
            "passed", "sha256:example-chain-a-digest", ()
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
