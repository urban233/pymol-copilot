# Copyright 2026 PyMOL Copilot contributors.
"""Server-owned lifecycle for the LangGraph request graph.

docs/master_plan.md item 8's own replacement for the hardcoded fixture this
module used to hold: `PlanRequestLifecycle` pattern-matched one exact
request shape and answered with one constant plan, never called a model,
and held no per-session state. `RequestGraphLifecycle` instead routes every
decoded request into `pmc_agent.session.RequestGraphSession`, which owns
the compiled request graph, its checkpointer, and the per-session lock that
makes "at most one active request per session" real under
`pmc_server.transport.LoopbackPlanServer`'s threaded concurrency. This
module's only remaining job is translating between the graph's own result
mapping and this protocol's typed wire responses -- every state, every
transition, and every terminal are `pmc_agent.graph`'s.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Callable
from datetime import UTC
from datetime import datetime

from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.graph import STATE_APPLYING
from pmc_agent.graph import TERMINAL_ASK
from pmc_agent.graph import TERMINAL_CANCELLED
from pmc_agent.graph import TERMINAL_EXPIRED
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import TERMINAL_SUPERSEDED
from pmc_agent.session import RequestGraphSession
from pmc_core.plan import ActionPlan
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import CancelRequestV1
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1

type TIMESTAMP_SOURCE = Callable[[], str]
type PLAN_RESPONSE = ValidatedPlanResponseV1 | FailedPlanResponseV1
type REJECT_RESPONSE = FailedPlanResponseV1
type CANCEL_RESPONSE = FailedPlanResponseV1
type APPLY_RESPONSE = ValidatedPlanResponseV1 | FailedPlanResponseV1

#: Terminals this lifecycle reports as retryable: the plan itself is gone,
#: but nothing about the request that produced it was wrong. `rejected`,
#: `failed`, and `ask` are not in this set -- see `_to_terminal_response`.
_RETRYABLE_TERMINALS: frozenset[str] = frozenset(
    {TERMINAL_EXPIRED, TERMINAL_SUPERSEDED, TERMINAL_CANCELLED}
)

#: `reject`/`cancel`'s own failure category when `RequestGraphSession`
#: refuses to touch the thread at all: no plan is pending, or (`reject`
#: only) the named plan id does not match the one actually pending. Item
#: 10's client keeps its own local pending-plan cache specifically so an
#: ordinary `copilot_reject`/`copilot_apply` mismatch never reaches the
#: server at all (mirroring `copilot_apply`'s existing refusal table);
#: reaching this category regardless means a stale or racing caller, which
#: is why it is not retryable.
FAILURE_NO_PENDING_PLAN = "no_pending_plan"


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


class RequestGraphLifecycle:
    """Route decoded V1 requests into the request graph and back."""

    def __init__(
        self,
        *,
        session: RequestGraphSession,
        timestamp_source: TIMESTAMP_SOURCE = _server_timestamp,
    ) -> None:
        """Create a lifecycle bound to one session's compiled graph.

        Args:
            session: Owns the compiled graph, its checkpointer, and the
                per-session lock every call below goes through.
            timestamp_source: Source for the server-side timestamps this
                lifecycle itself stamps (`received_at`, `validated_at`).
                Every other timestamp in a response comes from the request
                or from the graph's own injected clock.
        """
        self._session = session
        self._timestamp_source = timestamp_source

    def __call__(self, request: PlanRequestV1) -> PLAN_RESPONSE:
        """Submit one decoded plan request to the graph and answer it.

        Args:
            request: Decoded plan request to submit.

        Returns:
            A validated plan response when the graph parks at
            `pending_approval`; a typed failure response for every other
            terminal it reaches.
        """
        received_at = self._timestamp_source()
        result = self._session.submit(
            request_id=request.request_id,
            session_id=request.session_id,
            created_at=request.created_at,
            intent=request.intent,
            contract_manifest=request.contract_manifest,
            snapshot_identity=request.snapshot,
            snapshot_json=request.snapshot_json,
            fidelity=request.fidelity,
        )
        return self._to_plan_response(request, received_at, result)

    def reject(self, request: RejectRequestV1) -> REJECT_RESPONSE:
        """Reject a session's pending plan, if it matches.

        Args:
            request: Decoded reject request to submit.

        Returns:
            A typed failure response naming the terminal the graph
            reached, or `FAILURE_NO_PENDING_PLAN` when there was no plan
            matching `request.plan_id` pending for `request.session_id`.
        """
        result = self._session.reject(
            session_id=request.session_id, plan_id=request.plan_id
        )
        if result is None:
            return self._no_pending_plan(request.request_id, request.session_id)
        return self._to_terminal_response(
            request.request_id, request.session_id, result
        )

    def cancel(self, request: CancelRequestV1) -> CANCEL_RESPONSE:
        """Cancel a session's pending plan.

        Args:
            request: Decoded cancel request to submit.

        Returns:
            A typed failure response naming the terminal the graph
            reached, or `FAILURE_NO_PENDING_PLAN` when there was no plan
            pending for `request.session_id`.
        """
        result = self._session.cancel(session_id=request.session_id)
        if result is None:
            return self._no_pending_plan(request.request_id, request.session_id)
        return self._to_terminal_response(
            request.request_id, request.session_id, result
        )

    def apply(self, request: ApplyRequestV1) -> APPLY_RESPONSE:
        """Record approval and return the server's canonical plan."""
        result = self._session.approve(
            session_id=request.session_id, plan_id=request.plan_id
        )
        if result is None:
            return self._no_pending_plan(request.request_id, request.session_id)
        if result.get("status") != STATE_APPLYING:
            return self._to_terminal_response(
                request.request_id, request.session_id, result
            )
        plan = result["plan"]
        assert isinstance(plan, ActionPlan)
        expires_at = result["expires_at"]
        model_identity = result["model_identity"]
        snapshot_digest = result["snapshot_digest"]
        applicable = result["validation_applicable"]
        assert isinstance(expires_at, str) and isinstance(model_identity, str)
        assert isinstance(snapshot_digest, str) and isinstance(applicable, bool)
        return ValidatedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            received_at=self._timestamp_source(),
            validated_at=self._timestamp_source(),
            action_plan=plan,
            validation=ValidationReportV1(
                "passed", snapshot_digest, applicable, ()
            ),
            plan_id=request.plan_id,
            snapshot_digest=snapshot_digest,
            expires_at=expires_at,
            model_identity=model_identity,
        )

    def report_apply_outcome(
        self, request: ApplyOutcomeRequestV1
    ) -> FailedPlanResponseV1:
        """Record a terminal client apply outcome."""
        result = self._session.report_apply_outcome(
            session_id=request.session_id,
            plan_id=request.plan_id,
            outcome=request.outcome,
        )
        if result is None:
            return self._no_pending_plan(request.request_id, request.session_id)
        return self._to_terminal_response(
            request.request_id, request.session_id, result
        )

    def _to_plan_response(
        self,
        request: PlanRequestV1,
        received_at: str,
        result: dict[str, object],
    ) -> PLAN_RESPONSE:
        """Build a plan response from one graph invocation's own result.

        Args:
            request: The plan request that produced `result`.
            received_at: When this lifecycle accepted `request`.
            result: The graph's own result mapping.

        Returns:
            A validated response when the graph parked at
            `pending_approval`; a typed failure response for every other
            terminal.
        """
        if result.get("status") == STATE_PENDING_APPROVAL:
            plan = result["plan"]
            assert isinstance(plan, ActionPlan)
            plan_id = result["plan_id"]
            assert isinstance(plan_id, str)
            digest = request.snapshot.digest
            expires_at = result["expires_at"]
            assert isinstance(expires_at, str)
            model_identity = result["model_identity"]
            assert isinstance(model_identity, str)
            return ValidatedPlanResponseV1(
                request_id=request.request_id,
                session_id=request.session_id,
                received_at=received_at,
                validated_at=self._timestamp_source(),
                action_plan=plan,
                validation=ValidationReportV1(
                    status="passed",
                    snapshot_digest=digest,
                    # Orchestration rule 9 (SPECIFICATION.md:539): never
                    # upgrade or re-derive the request's own fidelity
                    # outcome -- this lifecycle has no live session to
                    # compare against, only what the client already
                    # reported.
                    applicable=request.fidelity.status == FIDELITY_EXACT,
                    warnings=(),
                ),
                plan_id=plan_id,
                snapshot_digest=digest,
                expires_at=expires_at,
                model_identity=model_identity,
            )
        return self._to_terminal_response(
            request.request_id, request.session_id, result
        )

    def _to_terminal_response(
        self, request_id: str, session_id: str, result: dict[str, object]
    ) -> FailedPlanResponseV1:
        """Build a typed failure response from a non-parking terminal.

        Args:
            request_id: The originating request's own identifier.
            session_id: The session the graph ran under.
            result: The graph's own result mapping, whose `status` names
                one of the terminals this graph can produce.

        Returns:
            A failure response. `failed`'s own already-typed
            `FailureEnvelopeV1` is forwarded unchanged, including whatever
            `retryable` verdict the failure category that produced it
            already carries; `ask`'s bounded question becomes the
            envelope's message; every other terminal gets a fixed message
            naming itself, with `retryable` from `_RETRYABLE_TERMINALS`.
        """
        status = result["status"]
        assert isinstance(status, str)
        if status == TERMINAL_FAILED:
            failure = result["failure"]
            assert isinstance(failure, FailureEnvelopeV1)
            return FailedPlanResponseV1(
                request_id=request_id, session_id=session_id, failure=failure
            )
        if status == TERMINAL_ASK:
            question = result["question"]
            assert isinstance(question, str)
            return FailedPlanResponseV1(
                request_id=request_id,
                session_id=session_id,
                failure=FailureEnvelopeV1(
                    category=TERMINAL_ASK, message=question, retryable=False
                ),
            )
        return FailedPlanResponseV1(
            request_id=request_id,
            session_id=session_id,
            failure=FailureEnvelopeV1(
                category=status,
                message=f"request ended: {status}",
                retryable=status in _RETRYABLE_TERMINALS,
            ),
        )

    @staticmethod
    def _no_pending_plan(
        request_id: str, session_id: str
    ) -> FailedPlanResponseV1:
        """Build the fixed failure response for a refused reject or cancel.

        Args:
            request_id: The originating request's own identifier.
            session_id: The session named by the request.

        Returns:
            A non-retryable `FAILURE_NO_PENDING_PLAN` failure response.
        """
        return FailedPlanResponseV1(
            request_id=request_id,
            session_id=session_id,
            failure=FailureEnvelopeV1(
                category=FAILURE_NO_PENDING_PLAN,
                message=(
                    "no plan matching the request is pending for this session"
                ),
                retryable=False,
            ),
        )
