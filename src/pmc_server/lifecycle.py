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
from pmc_agent.graph import TERMINAL_REJECTED
from pmc_agent.graph import TERMINAL_SUPERSEDED
from pmc_agent.session import RequestGraphSession
from pmc_agent.warnings import derive_warnings
from pmc_core.executor import SelectionCount
from pmc_core.executor import bounded_failure
from pmc_core.plan import ActionPlan
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import CancelRequestV1
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import EngineHealthV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import HealthRequestV1
from pmc_core.protocol import HealthResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import SelectionCountV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.versions import APPLICATION_VERSION
from pmc_core.versions import contract_versions

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


def _selection_counts_v1(
    counts: tuple[SelectionCount, ...],
) -> tuple[SelectionCountV1, ...]:
    """Convert the graph's own selection counts to their V1 wire shape.

    Args:
        counts: Selection counts from `pmc_core.executor.ExecutionReport`,
            carried unchanged through `RequestState["selection_counts"]`.

    Returns:
        The same counts, in the same order, as `SelectionCountV1`.
    """
    return tuple(
        SelectionCountV1(count.name, count.atom_count) for count in counts
    )


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
        target_object = result["target_object"]
        selection_counts = result["selection_counts"]
        sidecar_warnings = result["sidecar_warnings"]
        attempt = result["attempt"]
        snapshot_identity = result["snapshot_identity"]
        assert isinstance(expires_at, str) and isinstance(model_identity, str)
        assert isinstance(snapshot_digest, str) and isinstance(applicable, bool)
        assert isinstance(target_object, str) and isinstance(attempt, int)
        assert isinstance(selection_counts, tuple) and isinstance(
            sidecar_warnings, tuple
        )
        assert isinstance(snapshot_identity, StructureSnapshotV1)
        repair_attempts = max(0, attempt - 1)
        # /v1/apply re-sends the exact facts /v1/plan previewed, computed
        # the same way, so the plan applied is never a different report
        # from the plan shown -- pmc_client.command already refuses if the
        # two ever disagree.
        return ValidatedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            received_at=self._timestamp_source(),
            validated_at=self._timestamp_source(),
            action_plan=plan,
            validation=ValidationReportV1(
                status="passed",
                snapshot_digest=snapshot_digest,
                applicable=applicable,
                warnings=derive_warnings(
                    selection_counts=selection_counts,
                    target_atom_count=snapshot_identity.atom_count,
                    repair_attempts=repair_attempts,
                    sidecar_warnings=sidecar_warnings,
                ),
                selection_counts=_selection_counts_v1(selection_counts),
                repair_attempts=repair_attempts,
            ),
            plan_id=request.plan_id,
            snapshot_digest=snapshot_digest,
            expires_at=expires_at,
            model_identity=model_identity,
            target_object=target_object,
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

    def health(self, request: HealthRequestV1) -> HealthResponseV1:
        """Report this server's own application, contract, and engine facts.

        docs/master_plan.md item 11's own `copilot_health` command. Never
        touches the request graph: health is a property of the engine and
        this build, not of any one request.

        Args:
            request: Decoded health request to answer.

        Returns:
            The server's application version, every contract version this
            build agrees to, and the engine's own current health.
        """
        engine_health = self._session.engine_health()
        failure = engine_health.failure
        return HealthResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            application_version=APPLICATION_VERSION,
            contract_versions=dict(contract_versions()),
            engine=EngineHealthV1(
                state=engine_health.state,
                engine=engine_health.engine,
                engine_version=engine_health.engine_version,
                device=engine_health.device,
                failure_category=failure.category
                if failure is not None
                else None,
                failure_message=failure.message
                if failure is not None
                else None,
            ),
            model_identity=engine_health.model_identity,
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
            target_object = result["target_object"]
            assert isinstance(target_object, str)
            selection_counts = result["selection_counts"]
            sidecar_warnings = result["sidecar_warnings"]
            attempt = result["attempt"]
            assert isinstance(selection_counts, tuple) and isinstance(
                sidecar_warnings, tuple
            )
            assert isinstance(attempt, int)
            repair_attempts = max(0, attempt - 1)
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
                    warnings=derive_warnings(
                        selection_counts=selection_counts,
                        target_atom_count=request.snapshot.atom_count,
                        repair_attempts=repair_attempts,
                        sidecar_warnings=sidecar_warnings,
                    ),
                    selection_counts=_selection_counts_v1(selection_counts),
                    repair_attempts=repair_attempts,
                ),
                plan_id=plan_id,
                snapshot_digest=digest,
                expires_at=expires_at,
                model_identity=model_identity,
                # The graph's own independent resolution
                # (`pmc_agent.graph`'s `preparing` node), not the client's
                # own declared object -- `pmc_client.command` cross-checks
                # the two and refuses to park a plan if they disagree.
                target_object=target_object,
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
            envelope's message; a hostile-screen `rejected` forwards its
            own recorded `hostile_output` envelope so it reads differently
            from an ordinary user reject, even though both leave `status`
            at `rejected`; every other terminal gets a fixed message
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
                failure=bounded_failure(TERMINAL_ASK, question, False),
            )
        if status == TERMINAL_REJECTED:
            hostile_failure = result.get("failure")
            if isinstance(hostile_failure, FailureEnvelopeV1):
                return FailedPlanResponseV1(
                    request_id=request_id,
                    session_id=session_id,
                    failure=hostile_failure,
                )
        return FailedPlanResponseV1(
            request_id=request_id,
            session_id=session_id,
            failure=bounded_failure(
                status,
                f"request ended: {status}",
                status in _RETRYABLE_TERMINALS,
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
            failure=bounded_failure(
                FAILURE_NO_PENDING_PLAN,
                "no plan matching the request is pending for this session",
                False,
            ),
        )
