# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for the callable server request lifecycle."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import pytest

from pmc_core.plan import initial_fixture_plan
from pmc_core.policy import PlanDecision
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_server.lifecycle import PlanRequestLifecycle

REQUEST_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"


def request() -> PlanRequestV1:
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


def test_exact_fixture_returns_correlated_validated_plan() -> None:
    """The accepted fixture produces a passing typed plan response."""
    lifecycle = PlanRequestLifecycle(
        plan_id_source=lambda: "33333333-3333-4333-8333-333333333333",
        timestamp_source=iter(
            ("2026-08-26T14:22:03.124Z", "2026-08-26T14:22:03.220Z")
        ).__next__,
    )

    response = lifecycle(request())

    assert isinstance(response, ValidatedPlanResponseV1)
    assert response.request_id == REQUEST_ID
    assert response.session_id == SESSION_ID
    assert response.received_at == "2026-08-26T14:22:03.124Z"
    assert response.validated_at == "2026-08-26T14:22:03.220Z"
    assert response.plan_id == "33333333-3333-4333-8333-333333333333"
    assert response.snapshot_digest == "sha256:example-chain-a-digest"
    assert response.action_plan == initial_fixture_plan()
    assert response.validation.status == "passed"
    assert (
        response.validation.snapshot_digest == "sha256:example-chain-a-digest"
    )
    assert response.validation.warnings == ()


def test_semantic_request_mismatch_returns_typed_failure_without_plan() -> None:
    """A request outside the accepted fixture returns no partial plan."""
    invalid_request = request()
    invalid_request = PlanRequestV1(
        request_id=invalid_request.request_id,
        session_id=invalid_request.session_id,
        created_at=invalid_request.created_at,
        contract_manifest=invalid_request.contract_manifest,
        intent="Select chain B and color it red.",
        snapshot=invalid_request.snapshot,
    )

    response = PlanRequestLifecycle()(invalid_request)

    assert isinstance(response, FailedPlanResponseV1)
    assert response.request_id == REQUEST_ID
    assert response.session_id == SESSION_ID
    assert response.failure.category == "invalid_request"
    assert "actionPlan" not in response.to_dict()
    assert ".pml" not in response.failure.message


def test_policy_denial_returns_typed_failure_without_plan() -> None:
    """A policy denial returns no plan or executable text."""
    denied = PlanDecision(decisions=(), allowed=False)
    lifecycle = PlanRequestLifecycle(policy_validator=lambda _plan: denied)

    response = lifecycle(request())

    assert isinstance(response, FailedPlanResponseV1)
    assert response.failure.category == "policy_denied"
    assert "actionPlan" not in response.to_dict()
    assert ".pml" not in response.failure.message


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
