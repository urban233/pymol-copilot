# Copyright 2026 PyMOL Copilot contributors.
"""Server-owned lifecycle for the deterministic V1 plan fixture."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import uuid
from collections.abc import Callable
from datetime import UTC
from datetime import datetime

from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import NamedSelection
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.policy import PlanDecision
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import PROTOCOL_VERSION
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1

FIXTURE_INTENT = "Select chain A and color it red."

#: The plan this fixture lifecycle answers with, built from pmc_core's typed
#: values. It is local to this module on purpose: master_plan.md item 8
#: replaces this whole lifecycle with the LangGraph request graph, which will
#: generate a plan rather than return a constant, so there is nothing here
#: worth sharing with another package first.
FIXTURE_PLAN = ActionPlan(
    operations=(
        SelectOperation(
            selection_name="copilot_selection",
            expression=SelectionExpression(
                clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
            ),
        ),
        ColorOperation(color="red", target=NamedSelection("copilot_selection")),
    )
)
#: Must stay byte-identical to pmc_client.command.FIXTURE_SNAPSHOT: this
#: fixture lifecycle still gates on exact snapshot equality
#: (_matches_fixture below), which docs/master_plan.md item 7 has not yet
#: replaced with real per-session data on the client side -- that is item
#: 7's own step 7 in plans/06-live-extraction-and-fidelity-gate.md, and
#: item 8's LangGraph request graph replaces this whole lifecycle in turn.
FIXTURE_SNAPSHOT = StructureSnapshotV1(
    schema_version="1",
    digest="sha256:example-chain-a-digest",
    object_name="one-object-chain-a-v1",
    atom_count=2,
    state_count=1,
)
FIXTURE_MANIFEST = ContractManifestV1("1", "1", "1")

type PLAN_ID_SOURCE = Callable[[], str]
type TIMESTAMP_SOURCE = Callable[[], str]
type POLICY_VALIDATOR = Callable[[ActionPlan], PlanDecision]

# Preserve the original public type-alias names.
globals()["PlanIdSource"] = PLAN_ID_SOURCE
globals()["TimestampSource"] = TIMESTAMP_SOURCE
globals()["PolicyValidator"] = POLICY_VALIDATOR


def _new_plan_id() -> str:
    """Return a new UUIDv4 plan identifier.

    Returns:
        A string containing a UUIDv4 identifier.
    """
    return str(uuid.uuid4())


def _server_timestamp() -> str:
    """Return the current time in the protocol's RFC3339 UTC form.

    Returns:
        The current timestamp in the protocol wire format.
    """
    return (
        datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class PlanRequestLifecycle:
    """Build a typed response for one decoded V1 plan request."""

    def __init__(
        self,
        *,
        plan_id_source: PLAN_ID_SOURCE = _new_plan_id,
        timestamp_source: TIMESTAMP_SOURCE = _server_timestamp,
        policy_validator: POLICY_VALIDATOR = evaluate_plan,
    ) -> None:
        """Create a lifecycle with injectable deterministic sources.

        Args:
            plan_id_source: Source for generated plan identifiers.
            timestamp_source: Source for response timestamps.
            policy_validator: Function that evaluates the generated plan.
        """
        self._plan_id_source = plan_id_source
        self._timestamp_source = timestamp_source
        self._policy_validator = policy_validator

    def __call__(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Handle a request without producing raw model text or partial plans.

        Args:
            request: Decoded plan request to validate and evaluate.

        Returns:
            A validated plan response or a typed failure response.
        """
        received_at = self._timestamp_source()
        if not self._matches_fixture(request):
            return self._failure(
                request,
                category="invalid_request",
                message="request does not match the accepted V1 fixture",
            )

        plan = FIXTURE_PLAN
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
                # A fixed True, not yet derived from request.fidelity: this
                # fixture lifecycle predates docs/master_plan.md item 7's
                # fidelity gate. Deriving it for real
                # (`applicable = request.fidelity.status == FIDELITY_EXACT`)
                # is step 8 of plans/06-live-extraction-and-fidelity-gate.md.
                applicable=True,
                warnings=(),
            ),
            plan_id=self._plan_id_source(),
            snapshot_digest=request.snapshot.digest,
        )

    @staticmethod
    def _matches_fixture(request: PlanRequestV1) -> bool:
        """Return whether a request matches the accepted V1 fixture.

        Args:
            request: Request to compare with the fixture.

        Returns:
            True when every fixture field matches.
        """
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
        """Build a correlated typed failure response.

        Args:
            request: Request whose identifiers should be echoed.
            category: Stable failure category.
            message: Human-readable failure message.

        Returns:
            A failure response with no executable plan.
        """
        return FailedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            failure=FailureEnvelopeV1(
                category=category,
                message=message,
                retryable=False,
            ),
        )
