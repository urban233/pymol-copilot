# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for `RequestGraphLifecycle`.

Runs `pmc_agent.session.RequestGraphSession` against a `FakeEngine`, never a
real one -- this module's own scope is the wire translation
`RequestGraphLifecycle` does between the graph's result mapping and this
protocol's typed responses; every state and transition is
`pmc_agent.graph`'s own, already covered by `tests/unit/test_request_graph_*`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import itertools
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_agent.graph import MAX_REPAIR_ATTEMPTS
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.session import RequestGraphSession
from pmc_core.executor import REASON_CHILD_CRASH
from pmc_core.executor import REASON_FIDELITY_MISMATCH
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_core.policy import PolicyDecision
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import FIDELITY_UNAVAILABLE
from pmc_core.protocol import CancelRequestV1
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_server.lifecycle import FAILURE_NO_PENDING_PLAN
from pmc_server.lifecycle import RequestGraphLifecycle
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json

REQUEST_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
_OBJECT_NAME = "one-object-chain-a-v1"
_VALID_COMPLETION = "orient chain A\n"


def _always_ok_executor(_request: ExecutionRequest) -> ExecutionReport:
    """Report success for any request, without ever spawning anything.

    Args:
        _request: Ignored.

    Returns:
        A minimal `STATUS_OK` report.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:test",
        resulting_fingerprint="sha256:" + "0" * 64,
        selection_counts=(),
        command_outcomes=(),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=0.01,
    )


def _snapshot() -> ObjectSnapshot:
    """Build the smallest well-formed snapshot, named `_OBJECT_NAME`.

    Returns:
        An empty-state ObjectSnapshot.
    """
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name=_OBJECT_NAME,
        enabled=True,
        states=(),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )


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
        intent="orient chain A",
        snapshot=StructureSnapshotV1(
            schema_version="1",
            digest="sha256:example-chain-a-digest",
            object_name=_OBJECT_NAME,
            atom_count=2,
            state_count=1,
        ),
        snapshot_json=to_json(_snapshot()),
        fidelity=FidelityOutcomeV1(
            status=FIDELITY_EXACT,
            reason=REASON_OK,
            mismatch_count=0,
            mismatches=(),
        ),
    )


def _lifecycle(
    engine: FakeEngine,
    *,
    policy_validator: Callable[[ActionPlan], PlanDecision] = evaluate_plan,
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> RequestGraphLifecycle:
    """Build a lifecycle over a fresh session, fixed timestamps, a fake.

    Args:
        engine: The fake engine `generating` will call.
        policy_validator: Forwarded to `RequestGraphSession`. Defaults to
            the graph's own real `evaluate_plan`.
        max_repair_attempts: Forwarded to `RequestGraphSession`. Defaults
            to the graph's own real repair budget.

    Returns:
        A lifecycle whose `received_at`/`validated_at` are fixed, in that
        order, and whose graph never spawns a real sidecar.
    """
    session = RequestGraphSession(
        engine=engine,
        executor=_always_ok_executor,
        policy_validator=policy_validator,
        max_repair_attempts=max_repair_attempts,
    )
    timestamps = itertools.cycle(
        ("2026-08-26T14:22:03.124Z", "2026-08-26T14:22:03.220Z")
    )
    return RequestGraphLifecycle(
        session=session, timestamp_source=timestamps.__next__
    )


def test_a_well_formed_intent_returns_a_correlated_validated_plan() -> None:
    """A validated request produces a passing typed plan response."""
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    lifecycle = _lifecycle(engine)

    response = lifecycle(request())

    assert isinstance(response, ValidatedPlanResponseV1)
    assert response.request_id == REQUEST_ID
    assert response.session_id == SESSION_ID
    assert response.received_at == "2026-08-26T14:22:03.124Z"
    assert response.validated_at == "2026-08-26T14:22:03.220Z"
    assert response.snapshot_digest == "sha256:example-chain-a-digest"
    assert response.validation.status == "passed"
    assert (
        response.validation.snapshot_digest == "sha256:example-chain-a-digest"
    )
    assert response.validation.applicable is True
    assert response.validation.warnings == ()


@pytest.mark.parametrize(
    ("status", "reason", "expected_applicable"),
    [
        (FIDELITY_EXACT, REASON_OK, True),
        (FIDELITY_NOT_EXACT, REASON_FIDELITY_MISMATCH, False),
        (FIDELITY_UNAVAILABLE, REASON_CHILD_CRASH, False),
    ],
)
def test_applicable_is_derived_from_the_requests_own_fidelity_status(
    status: str, reason: str, expected_applicable: bool
) -> None:
    """`applicable` is set from request.fidelity.status alone.

    The server's whole share of orchestration rule 9
    (SPECIFICATION.md:539): it never upgrades or re-derives an outcome,
    since it has no live session of its own to check fidelity against.

    Args:
        status: The request's own fidelity status under test.
        reason: The request's own fidelity reason under test.
        expected_applicable: The applicable value this status must
            produce.
    """
    fidelity_gated_request = dataclasses.replace(
        request(),
        fidelity=FidelityOutcomeV1(
            status=status, reason=reason, mismatch_count=0, mismatches=()
        ),
    )
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    lifecycle = _lifecycle(engine)

    response = lifecycle(fidelity_gated_request)

    assert isinstance(response, ValidatedPlanResponseV1)
    assert response.validation.applicable is expected_applicable


def test_a_contract_manifest_mismatch_returns_typed_failure_without_plan() -> (
    None
):
    """A request outside the server's accepted contracts returns no plan."""
    mismatched = dataclasses.replace(
        request(), contract_manifest=ContractManifestV1("2", "1", "1")
    )
    lifecycle = _lifecycle(FakeEngine([]))

    response = lifecycle(mismatched)

    assert isinstance(response, FailedPlanResponseV1)
    assert response.request_id == REQUEST_ID
    assert response.session_id == SESSION_ID
    assert response.failure.category == "contract_mismatch"
    assert response.failure.retryable is False
    assert "actionPlan" not in response.to_dict()


def test_a_policy_denial_returns_typed_failure_without_plan() -> None:
    """A policy denial returns no plan or executable text."""
    denied = PlanDecision(
        decisions=(PolicyDecision(0, False, "denied_for_test"),),
        allowed=False,
    )
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    lifecycle = _lifecycle(
        engine, policy_validator=lambda _plan: denied, max_repair_attempts=0
    )

    response = lifecycle(request())

    assert isinstance(response, FailedPlanResponseV1)
    assert response.failure.category == "repair_exhausted"
    assert "actionPlan" not in response.to_dict()


def test_an_ask_completion_returns_its_question_as_the_failure_message() -> (
    None
):
    """A clarification reaches the caller as a non-retryable `ask` failure."""
    engine = FakeEngine(
        [CompletionResult("ask: which chain do you mean?", "m-1", STOP_END)]
    )
    lifecycle = _lifecycle(engine)

    response = lifecycle(request())

    assert isinstance(response, FailedPlanResponseV1)
    assert response.failure.category == "ask"
    assert response.failure.message == "which chain do you mean?"
    assert response.failure.retryable is False


def test_reject_reaches_rejected() -> None:
    """Rejecting the pending plan by its own id reaches `rejected`."""
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    lifecycle = _lifecycle(engine)
    pending = lifecycle(request())
    assert isinstance(pending, ValidatedPlanResponseV1)

    response = lifecycle.reject(
        RejectRequestV1(
            request_id=REQUEST_ID,
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
        )
    )

    assert response.failure.category == "rejected"
    assert response.failure.retryable is False


def test_cancel_reaches_cancelled() -> None:
    """Cancelling the pending plan reaches `cancelled`."""
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    lifecycle = _lifecycle(engine)
    pending = lifecycle(request())
    assert isinstance(pending, ValidatedPlanResponseV1)

    response = lifecycle.cancel(
        CancelRequestV1(request_id=REQUEST_ID, session_id=SESSION_ID)
    )

    assert response.failure.category == "cancelled"
    assert response.failure.retryable is True


def test_reject_with_no_pending_plan_is_refused() -> None:
    """Rejecting with nothing pending is refused, not a graph terminal."""
    lifecycle = _lifecycle(FakeEngine([]))

    response = lifecycle.reject(
        RejectRequestV1(
            request_id=REQUEST_ID,
            session_id=SESSION_ID,
            plan_id="33333333-3333-4333-8333-333333333333",
        )
    )

    assert response.failure.category == FAILURE_NO_PENDING_PLAN
    assert response.failure.retryable is False


def test_cancel_with_no_pending_plan_is_refused() -> None:
    """Cancelling with nothing pending is refused, not a graph terminal."""
    lifecycle = _lifecycle(FakeEngine([]))

    response = lifecycle.cancel(
        CancelRequestV1(request_id=REQUEST_ID, session_id=SESSION_ID)
    )

    assert response.failure.category == FAILURE_NO_PENDING_PLAN
    assert response.failure.retryable is False


def test_apply_returns_the_canonical_approved_plan_then_records_outcome() -> (
    None
):
    """The approval endpoint advances once and exposes no client-supplied plan."""
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    lifecycle = _lifecycle(engine)
    pending = lifecycle(request())
    assert isinstance(pending, ValidatedPlanResponseV1)

    approved = lifecycle.apply(
        ApplyRequestV1(
            request_id="33333333-3333-4333-8333-333333333333",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
        )
    )

    assert isinstance(approved, ValidatedPlanResponseV1)
    assert approved.plan_id == pending.plan_id
    assert approved.action_plan.render_pml() == pending.action_plan.render_pml()
    assert approved.model_identity == pending.model_identity

    terminal = lifecycle.report_apply_outcome(
        ApplyOutcomeRequestV1(
            request_id="44444444-4444-4444-8444-444444444444",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
            outcome="applied",
        )
    )

    assert terminal.failure.category == "applied"
    repeated = lifecycle.report_apply_outcome(
        ApplyOutcomeRequestV1(
            request_id="55555555-5555-4555-8555-555555555555",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
            outcome="applied",
        )
    )
    assert repeated.failure.category == "applied"


def test_apply_refuses_a_non_applicable_preview_without_advancing() -> None:
    """The server never approves a plan built from non-exact fidelity."""
    non_exact = dataclasses.replace(
        request(),
        fidelity=FidelityOutcomeV1(
            status=FIDELITY_NOT_EXACT,
            reason=REASON_FIDELITY_MISMATCH,
            mismatch_count=1,
            mismatches=("test",),
        ),
    )
    lifecycle = _lifecycle(
        FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    )
    pending = lifecycle(non_exact)
    assert isinstance(pending, ValidatedPlanResponseV1)
    assert not pending.validation.applicable

    refused = lifecycle.apply(
        ApplyRequestV1(
            request_id="33333333-3333-4333-8333-333333333333",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
        )
    )

    assert isinstance(refused, FailedPlanResponseV1)
    assert refused.failure.category == "not_applicable"
    assert not refused.failure.retryable
    rejected = lifecycle.reject(
        RejectRequestV1(
            request_id="44444444-4444-4444-8444-444444444444",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
        )
    )
    assert rejected.failure.category == "rejected"


def test_submit_while_apply_outcome_is_missing_returns_typed_retryable_failure() -> (
    None
):
    """The wire API preserves an applying plan until its outcome arrives."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    lifecycle = _lifecycle(engine)
    pending = lifecycle(request())
    assert isinstance(pending, ValidatedPlanResponseV1)
    approved = lifecycle.apply(
        ApplyRequestV1(
            request_id="33333333-3333-4333-8333-333333333333",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
        )
    )
    assert isinstance(approved, ValidatedPlanResponseV1)

    next_request = dataclasses.replace(
        request(), request_id="66666666-6666-4666-8666-666666666666"
    )
    blocked = lifecycle(next_request)

    assert isinstance(blocked, FailedPlanResponseV1)
    assert blocked.failure.category == "apply_outcome_required"
    assert blocked.failure.retryable
    replay = lifecycle.apply(
        ApplyRequestV1(
            request_id="44444444-4444-4444-8444-444444444444",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
        )
    )
    assert isinstance(replay, ValidatedPlanResponseV1)
    assert replay.plan_id == approved.plan_id
    assert replay.action_plan == approved.action_plan

    terminal = lifecycle.report_apply_outcome(
        ApplyOutcomeRequestV1(
            request_id="55555555-5555-4555-8555-555555555555",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
            outcome="restored",
        )
    )
    assert terminal.failure.category == "apply_failed_restored"
    next_preview = lifecycle(next_request)
    assert isinstance(next_preview, ValidatedPlanResponseV1)


def test_apply_after_expiry_returns_a_typed_terminal_not_a_plan() -> None:
    """The lifecycle must not turn an expired approval into executable text."""
    moment = [datetime(2026, 9, 21, tzinfo=UTC)]
    session = RequestGraphSession(
        engine=FakeEngine(
            [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)]
        ),
        executor=_always_ok_executor,
        clock=lambda: moment[0],
        ttl_seconds=60.0,
    )
    lifecycle = RequestGraphLifecycle(
        session=session, timestamp_source=lambda: "2026-09-21T00:00:00Z"
    )
    pending = lifecycle(request())
    assert isinstance(pending, ValidatedPlanResponseV1)
    moment[0] += timedelta(seconds=61)

    response = lifecycle.apply(
        ApplyRequestV1(
            request_id="33333333-3333-4333-8333-333333333333",
            session_id=SESSION_ID,
            plan_id=pending.plan_id,
        )
    )

    assert isinstance(response, FailedPlanResponseV1)
    assert response.failure.category == "expired"
    assert response.failure.retryable is True


def test_apply_without_a_matching_pending_plan_is_refused() -> None:
    """A stale approval cannot make the lifecycle return executable text."""
    lifecycle = _lifecycle(FakeEngine([]))

    response = lifecycle.apply(
        ApplyRequestV1(
            request_id="33333333-3333-4333-8333-333333333333",
            session_id=SESSION_ID,
            plan_id="44444444-4444-4444-8444-444444444444",
        )
    )

    assert isinstance(response, FailedPlanResponseV1)
    assert response.failure.category == FAILURE_NO_PENDING_PLAN


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
