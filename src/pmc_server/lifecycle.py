# Copyright 2026 PyMOL Copilot contributors.
"""Server-owned lifecycle for the deterministic V1 plan fixture."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from datetime import timezone
import uuid

from pmc_core.plan import ActionPlan
from pmc_core.plan import initial_fixture_plan
from pmc_core.policy import PlanDecision
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import PROTOCOL_VERSION
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.protocol import ValidatedPlanResponseV1

FIXTURE_INTENT = "Select chain A and color it red."
FIXTURE_SNAPSHOT = StructureSnapshotV1(
    "1", "sha256:example-chain-a-digest", "one-object-chain-a-v1"
)
FIXTURE_MANIFEST = ContractManifestV1("1", "1", "1")

type PlanIdSource = Callable[[], str]
type TimestampSource = Callable[[], str]
type PolicyValidator = Callable[[ActionPlan], PlanDecision]


def _new_plan_id() -> str:
    return str(uuid.uuid4())


def _server_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class PlanRequestLifecycle:
    """Build a typed response for one decoded V1 plan request."""

    def __init__(
        self,
        *,
        plan_id_source: PlanIdSource = _new_plan_id,
        timestamp_source: TimestampSource = _server_timestamp,
        policy_validator: PolicyValidator = evaluate_plan,
    ) -> None:
        """Create a lifecycle with injectable deterministic sources."""
        self._plan_id_source = plan_id_source
        self._timestamp_source = timestamp_source
        self._policy_validator = policy_validator

    def __call__(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Handle a request without producing raw model text or partial plans."""
        received_at = self._timestamp_source()
        if not self._matches_fixture(request):
            return self._failure(
                request,
                category="invalid_request",
                message="request does not match the accepted V1 fixture",
            )

        plan = initial_fixture_plan()
        decision = self._policy_validator(plan)
        if not decision.allowed:
            return self._failure(
                request,
                category="policy_denied",
                message="plan was denied by server policy",
            )

        return ValidatedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            received_at=received_at,
            validated_at=self._timestamp_source(),
            action_plan=plan,
            validation=ValidationReportV1(
                status="passed",
                snapshot_digest=request.snapshot.digest,
                warnings=(),
            ),
            plan_id=self._plan_id_source(),
            snapshot_digest=request.snapshot.digest,
        )

    @staticmethod
    def _matches_fixture(request: PlanRequestV1) -> bool:
        return (
            request.protocol_version == PROTOCOL_VERSION
            and request.contract_manifest == FIXTURE_MANIFEST
            and request.intent == FIXTURE_INTENT
            and request.snapshot == FIXTURE_SNAPSHOT
        )

    @staticmethod
    def _failure(
        request: PlanRequestV1, *, category: str, message: str
    ) -> FailedPlanResponseV1:
        return FailedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            failure=FailureEnvelopeV1(
                category=category,
                message=message,
                retryable=False,
            ),
        )
