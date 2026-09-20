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
from pmc_core.protocol import FIDELITY_EXACT
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
#: `_matches_fixture` below no longer compares this wholesale against a
#: request's own snapshot: docs/master_plan.md item 7 makes the client
#: send a real, per-session snapshot identity
#: (`pmc_client.session.extract_live_snapshot`), which varies with
#: whatever object is actually loaded and essentially never equals a
#: fixed literal. Only `schema_version` is still checked. Item 8's
#: LangGraph request graph replaces this whole lifecycle, snapshot
#: handling included.
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
                # The server's whole share of orchestration rule 9
                # (SPECIFICATION.md:539): never upgrade or re-derive the
                # request's own fidelity outcome -- this lifecycle has no
                # live session to compare against, only what the client
                # already reported. A request that claims "exact" while
                # the client's own local gate disagrees still fails at
                # the client's own AND
                # (pmc_client.command._report_validated).
                applicable=request.fidelity.status == FIDELITY_EXACT,
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
            True when every fixed fixture field matches and the request's
            own (now real, per-session) snapshot declares a schema version
            this lifecycle understands.
        """
        return (
            request.protocol_version == PROTOCOL_VERSION
            and request.contract_manifest == FIXTURE_MANIFEST
            and request.intent == FIXTURE_INTENT
            and request.snapshot.schema_version
            == FIXTURE_SNAPSHOT.schema_version
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
