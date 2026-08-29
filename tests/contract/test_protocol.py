# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for strict V1 client-server protocol codecs."""

import pytest

from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ProtocolDecodeError
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import decode_json
from pmc_core.protocol import encode_json
from pmc_core.plan import initial_fixture_plan

REQUEST_IDS = {
    "requestId": "11111111-1111-4111-8111-111111111111",
    "sessionId": "22222222-2222-4222-8222-222222222222",
}


def request() -> PlanRequestV1:
    """Build the accepted request fixture."""
    return PlanRequestV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        created_at="2026-08-26T14:22:03.123Z",
        contract_manifest=ContractManifestV1("1", "1", "1"),
        intent="Select chain A and color it red.",
        snapshot=StructureSnapshotV1(
            "1", "sha256:example-chain-a-digest", "one-object-chain-a-v1"
        ),
    )


def response() -> ValidatedPlanResponseV1:
    """Build the accepted validated response fixture."""
    return ValidatedPlanResponseV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        received_at="2026-08-26T14:22:03.124Z",
        validated_at="2026-08-26T14:22:03.220Z",
        action_plan=initial_fixture_plan(),
        validation=ValidationReportV1(
            "passed", "sha256:example-chain-a-digest", ()
        ),
        plan_id="33333333-3333-4333-8333-333333333333",
        snapshot_digest="sha256:example-chain-a-digest",
    )


def test_request_fixture_round_trips_as_strict_json() -> None:
    """The accepted request survives JSON encoding and decoding."""
    assert decode_json(encode_json(request())) == request()


def test_request_rejects_unknown_fields() -> None:
    """Requests with unknown fields are rejected."""
    payload = request().to_dict()
    payload["unexpected"] = True

    with pytest.raises(ProtocolDecodeError):
        PlanRequestV1.from_dict(payload)


@pytest.mark.parametrize("field", ["requestId", "sessionId"])
def test_request_rejects_non_v4_identifiers(field: str) -> None:
    """Requests with non-v4 identifiers are rejected."""
    payload = request().to_dict()
    payload[field] = "11111111-1111-3111-8111-111111111111"

    with pytest.raises(ProtocolDecodeError, match="UUIDv4"):
        PlanRequestV1.from_dict(payload)


def test_request_rejects_non_utc_timestamp() -> None:
    """Requests with non-UTC timestamps are rejected."""
    payload = request().to_dict()
    payload["createdAt"] = "2026-08-26T14:22:03.123+01:00"

    with pytest.raises(ProtocolDecodeError, match="RFC 3339 UTC"):
        PlanRequestV1.from_dict(payload)


def test_request_rejects_unsupported_protocol_version() -> None:
    """Requests for unsupported protocol versions are rejected."""
    payload = request().to_dict()
    payload["protocolVersion"] = "2"

    with pytest.raises(ProtocolDecodeError, match="unsupported protocol"):
        PlanRequestV1.from_dict(payload)


def test_validated_response_round_trips_typed_action_plan() -> None:
    """A validated response decodes into the immutable typed plan."""
    decoded = decode_json(encode_json(response()), response=True)

    assert isinstance(decoded, ValidatedPlanResponseV1)
    assert decoded == response()
    assert decoded.action_plan.render_pml() == (
        "select copilot_selection, chain A\ncolor red, copilot_selection\n"
    )


def test_failure_response_has_no_partial_action_plan() -> None:
    """A failure response cannot carry a partial action plan."""
    failure = FailedPlanResponseV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        failure=FailureEnvelopeV1("invalid_request", "bad request", False),
    )

    payload = failure.to_dict()
    assert "actionPlan" not in payload
    assert decode_json(encode_json(failure), response=True) == failure


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
