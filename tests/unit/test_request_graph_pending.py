# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for `pending_approval`, expiry, supersession, cancellation.

Runs `pmc_agent.session.RequestGraphSession`, not the bare compiled graph
directly -- this is the layer docs/master_plan.md item 8 introduces to
enforce "at most one active request and one pending plan per session" as a
real invariant under `ThreadingHTTPServer`'s concurrency, not merely a
single-threaded property of the graph itself.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import threading
import time
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import TypedDict
from typing import cast

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_agent.graph import ACCEPTED_CONTRACT_MANIFEST
from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.graph import STATE_APPLYING
from pmc_agent.graph import TERMINAL_APPLIED
from pmc_agent.graph import TERMINAL_APPLY_FAILED_RESTORED
from pmc_agent.graph import TERMINAL_ROLLED_BACK
from pmc_agent.graph import TERMINAL_CANCELLED
from pmc_agent.graph import TERMINAL_EXPIRED
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import TERMINAL_REJECTED
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.session import RequestGraphSession
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json

_OBJECT_NAME = "fx"
_SESSION_ID = "22222222-2222-4222-8222-222222222222"
_VALID_COMPLETION = "orient chain A\n"


class _FakeClock:
    """A settable clock, so a test controls `expires_at` and its own TTL."""

    def __init__(self, moment: datetime) -> None:
        """Create a clock fixed at `moment` until advanced.

        Args:
            moment: The moment this clock starts at.
        """
        self.moment = moment

    def __call__(self) -> datetime:
        """Return the clock's current moment.

        Returns:
            Whatever `self.moment` currently holds.
        """
        return self.moment


class _SlowEngine:
    """A stateless `InferenceEngine` that sleeps before succeeding.

    Used only by the concurrency test below, to widen the window in which
    two racing `submit()` calls could actually overlap -- without a
    deliberate delay, two real threads on a fast, idle machine could
    serialize by pure luck and never genuinely exercise the per-session
    lock `RequestGraphSession` depends on.
    """

    def __init__(self, *, delay_seconds: float) -> None:
        """Create an engine that sleeps `delay_seconds` before replying.

        Args:
            delay_seconds: How long each `complete()` call sleeps.
        """
        self._delay_seconds = delay_seconds

    @property
    def model_identity(self) -> str:
        """Return this engine's fixed model identity.

        Returns:
            A constant model identity string.
        """
        return "slow-fake-v1"

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Sleep, then return a fixed, always-valid completion.

        Args:
            request: Ignored; this fake never inspects the prompt.
            cancel: Ignored; this fake never checks for cancellation.

        Returns:
            A `CompletionResult` for a simple, always-valid `.pml` line.
        """
        del request, cancel
        time.sleep(self._delay_seconds)
        return CompletionResult(
            _VALID_COMPLETION, self.model_identity, STOP_END
        )


class _CancellableEngine:
    """An engine that proves it received a live cancellation token."""

    def __init__(self) -> None:
        """Create an engine that runs until its caller cancels it."""
        self.started = threading.Event()
        self.observed_cancellation = threading.Event()

    @property
    def model_identity(self) -> str:
        """Return the fixed identity for this test-only engine."""
        return "cancellable-fake-v1"

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Wait for cancellation, then report a completion race.

        The normal-looking result makes the graph's post-call token check
        load-bearing: it must still terminate as cancelled rather than parse
        or approve this text.

        Args:
            request: Ignored by this deterministic fake.
            cancel: The signal the graph must supply from `/v1/cancel`.

        Returns:
            A valid-looking completion after recording cancellation.
        """
        del request
        self.started.set()
        while not cancel.is_cancelled():
            time.sleep(0.001)
        self.observed_cancellation.set()
        return CompletionResult(
            _VALID_COMPLETION, self.model_identity, STOP_END
        )


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


class _SubmitKwargs(TypedDict):
    """The exact keyword shape `RequestGraphSession.submit` accepts.

    Exists so `session.submit(**_submit_kwargs(...))` below type-checks
    precisely against `submit`'s own parameter types -- a plain
    `dict[str, object]` return would widen every field to `object` and
    make every call site a pyrefly error.
    """

    request_id: str
    session_id: str
    created_at: str
    intent: str
    contract_manifest: ContractManifestV1
    snapshot_identity: StructureSnapshotV1
    snapshot_json: str
    fidelity: FidelityOutcomeV1


def _submit_kwargs(
    *, request_id: str, session_id: str = _SESSION_ID
) -> _SubmitKwargs:
    """Build a well-formed set of keyword arguments for `submit()`.

    Args:
        request_id: The request's own wire identifier.
        session_id: The session this request is made under.

    Returns:
        Keyword arguments `RequestGraphSession.submit` accepts as a
        request `preparing` and `validating` both accept without error.
    """
    return cast(
        _SubmitKwargs,
        {
            "request_id": request_id,
            "session_id": session_id,
            "created_at": "2026-09-21T00:00:00.000Z",
            "intent": "orient chain A",
            "contract_manifest": ACCEPTED_CONTRACT_MANIFEST,
            "snapshot_identity": StructureSnapshotV1(
                schema_version="1",
                digest="sha256:test-digest",
                object_name=_OBJECT_NAME,
                atom_count=0,
                state_count=0,
            ),
            "snapshot_json": to_json(_snapshot()),
            "fidelity": FidelityOutcomeV1(
                status=FIDELITY_EXACT,
                reason=REASON_OK,
                mismatch_count=0,
                mismatches=(),
            ),
        },
    )


def _submit_in_thread(
    session: RequestGraphSession, *, request_id: str, session_id: str
) -> None:
    """Call `session.submit` with a minimal well-formed request.

    A module-level function, not a closure, so the concurrency test below
    can hand it straight to `threading.Thread` without capturing a loop
    variable.

    Args:
        session: The session to submit against.
        request_id: The request's own identifier.
        session_id: The session id both racing requests share.
    """
    session.submit(
        **_submit_kwargs(request_id=request_id, session_id=session_id)
    )


def _one_shot_session(
    *, clock: _FakeClock | None = None, ttl_seconds: float = 60.0
) -> RequestGraphSession:
    """Build a session whose one scripted completion always validates.

    Args:
        clock: The clock to inject, defaulting to a fresh, real-looking
            fixed moment when not given.
        ttl_seconds: How long a minted plan stays approvable.

    Returns:
        A `RequestGraphSession` ready for exactly one `submit()` call
        before its engine's script is exhausted.
    """
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    return RequestGraphSession(
        engine=engine,
        executor=_always_ok_executor,
        clock=clock
        if clock is not None
        else _FakeClock(datetime(2026, 9, 21, tzinfo=UTC)),
        ttl_seconds=ttl_seconds,
    )


def test_a_validated_request_parks_with_a_plan_id_and_expires_at() -> None:
    """A well-formed request parks at `pending_approval`, fully minted."""
    session = _one_shot_session()

    result = session.submit(**_submit_kwargs(request_id="r-1"))

    assert "__interrupt__" in result
    assert result["status"] == STATE_PENDING_APPROVAL
    assert result["plan_id"] is not None
    assert result["expires_at"] is not None


def test_reject_reaches_rejected() -> None:
    """Rejecting the pending plan by its own id reaches `rejected`."""
    session = _one_shot_session()
    pending = session.submit(**_submit_kwargs(request_id="r-1"))

    result = session.reject(
        session_id=_SESSION_ID, plan_id=cast(str, pending["plan_id"])
    )

    assert result is not None
    assert result["status"] == TERMINAL_REJECTED


def test_approve_parks_for_one_outcome_and_preserves_plan_facts() -> None:
    """A lost approval response can be replayed without advancing twice."""
    session = _one_shot_session()
    pending = session.submit(**_submit_kwargs(request_id="r-1"))

    applying = session.approve(
        session_id=_SESSION_ID, plan_id=cast(str, pending["plan_id"])
    )

    assert applying is not None
    assert applying["status"] == STATE_APPLYING
    assert applying["plan"] == pending["plan"]
    assert applying["expires_at"] == pending["expires_at"]
    assert applying["model_identity"] == pending["model_identity"]
    replay = session.approve(
        session_id=_SESSION_ID, plan_id=cast(str, pending["plan_id"])
    )
    assert replay is not None
    assert replay["status"] == STATE_APPLYING
    assert replay["plan"] == applying["plan"]
    assert session.approve(session_id=_SESSION_ID, plan_id="wrong") is None


def test_non_applicable_preview_cannot_be_approved() -> None:
    """Non-exact fidelity stays inspectable but never reaches applying."""
    session = _one_shot_session()
    request = _submit_kwargs(request_id="r-1")
    request["fidelity"] = FidelityOutcomeV1(
        status=FIDELITY_NOT_EXACT,
        reason="fidelity_mismatch",
        mismatch_count=1,
        mismatches=("test",),
    )
    pending = session.submit(**request)
    plan_id = cast(str, pending["plan_id"])

    refused = session.approve(session_id=_SESSION_ID, plan_id=plan_id)

    assert refused is not None
    assert refused["status"] == TERMINAL_FAILED
    failure = refused["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == "not_applicable"
    assert not failure.retryable
    assert session._graph.get_state(
        {"configurable": {"thread_id": _SESSION_ID}}
    ).next == (STATE_PENDING_APPROVAL,)


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("applied", TERMINAL_APPLIED),
        ("restored", TERMINAL_APPLY_FAILED_RESTORED),
        ("rolled_back", TERMINAL_ROLLED_BACK),
    ],
)
def test_apply_outcome_reaches_its_matching_terminal(
    outcome: str, expected: str
) -> None:
    """The three typed outcomes are the only terminal apply transitions."""
    session = _one_shot_session()
    pending = session.submit(**_submit_kwargs(request_id="r-1"))
    plan_id = cast(str, pending["plan_id"])
    assert session.approve(session_id=_SESSION_ID, plan_id=plan_id) is not None

    result = session.report_apply_outcome(
        session_id=_SESSION_ID, plan_id=plan_id, outcome=outcome
    )

    assert result is not None
    assert result["status"] == expected


def test_new_submit_cannot_replace_an_unreported_approved_plan() -> None:
    """A lost apply reply or outcome must not erase the applying thread."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    session = RequestGraphSession(engine=engine, executor=_always_ok_executor)
    first = session.submit(**_submit_kwargs(request_id="r-1"))
    first_id = cast(str, first["plan_id"])
    assert session.approve(session_id=_SESSION_ID, plan_id=first_id) is not None

    blocked = session.submit(**_submit_kwargs(request_id="r-2"))

    assert blocked["status"] == TERMINAL_FAILED
    failure = blocked["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == "apply_outcome_required"
    assert failure.retryable
    assert session._graph.get_state(
        {"configurable": {"thread_id": _SESSION_ID}}
    ).next == (STATE_APPLYING,)
    assert session._pending_details[_SESSION_ID]["plan_id"] == first_id
    assert session.approve(session_id=_SESSION_ID, plan_id=first_id) is not None

    recorded = session.report_apply_outcome(
        session_id=_SESSION_ID, plan_id=first_id, outcome="restored"
    )
    assert recorded is not None
    assert recorded["status"] == TERMINAL_APPLY_FAILED_RESTORED
    second = session.submit(**_submit_kwargs(request_id="r-2"))
    assert second["status"] == STATE_PENDING_APPROVAL


def test_applied_plan_can_be_rolled_back_and_replayed() -> None:
    """A lost rollback response replays its terminal without running again."""
    session = _one_shot_session()
    pending = session.submit(**_submit_kwargs(request_id="r-1"))
    plan_id = cast(str, pending["plan_id"])
    assert session.approve(session_id=_SESSION_ID, plan_id=plan_id) is not None
    assert (
        session.report_apply_outcome(
            session_id=_SESSION_ID, plan_id=plan_id, outcome="applied"
        )
        is not None
    )

    rolled_back = session.report_apply_outcome(
        session_id=_SESSION_ID, plan_id=plan_id, outcome="rolled_back"
    )

    assert rolled_back is not None
    assert rolled_back["status"] == TERMINAL_ROLLED_BACK
    assert (
        session.report_apply_outcome(
            session_id=_SESSION_ID, plan_id=plan_id, outcome="rolled_back"
        )
        == rolled_back
    )
    assert (
        session.report_apply_outcome(
            session_id=_SESSION_ID, plan_id=plan_id, outcome="applied"
        )
        is not None
    )


def test_restored_outcome_replays_after_graph_thread_is_reused() -> None:
    """A successful terminal response can be retried after a new preview."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    session = RequestGraphSession(engine=engine, executor=_always_ok_executor)
    first = session.submit(**_submit_kwargs(request_id="r-1"))
    first_id = cast(str, first["plan_id"])
    assert session.approve(session_id=_SESSION_ID, plan_id=first_id) is not None
    terminal = session.report_apply_outcome(
        session_id=_SESSION_ID, plan_id=first_id, outcome="restored"
    )
    assert terminal is not None
    assert terminal["status"] == TERMINAL_APPLY_FAILED_RESTORED
    second = session.submit(**_submit_kwargs(request_id="r-2"))
    assert second["status"] == STATE_PENDING_APPROVAL

    assert (
        session.report_apply_outcome(
            session_id=_SESSION_ID, plan_id=first_id, outcome="restored"
        )
        == terminal
    )
    assert session._graph.get_state(
        {"configurable": {"thread_id": _SESSION_ID}}
    ).next == (STATE_PENDING_APPROVAL,)


def test_restored_and_rollback_receipts_replay_independently() -> None:
    """B's lost restore reply survives a later rollback of applied plan A."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    session = RequestGraphSession(engine=engine, executor=_always_ok_executor)
    first = session.submit(**_submit_kwargs(request_id="r-1"))
    first_id = cast(str, first["plan_id"])
    assert session.approve(session_id=_SESSION_ID, plan_id=first_id) is not None
    assert (
        session.report_apply_outcome(
            session_id=_SESSION_ID, plan_id=first_id, outcome="applied"
        )
        is not None
    )
    second = session.submit(**_submit_kwargs(request_id="r-2"))
    second_id = cast(str, second["plan_id"])
    assert (
        session.approve(session_id=_SESSION_ID, plan_id=second_id) is not None
    )
    restored = session.report_apply_outcome(
        session_id=_SESSION_ID, plan_id=second_id, outcome="restored"
    )
    assert restored is not None
    rolled_back = session.report_apply_outcome(
        session_id=_SESSION_ID, plan_id=first_id, outcome="rolled_back"
    )
    assert rolled_back is not None

    assert (
        session.report_apply_outcome(
            session_id=_SESSION_ID, plan_id=second_id, outcome="restored"
        )
        == restored
    )
    assert (
        session.report_apply_outcome(
            session_id=_SESSION_ID, plan_id=first_id, outcome="rolled_back"
        )
        == rolled_back
    )


def test_applied_plan_can_be_rolled_back_after_a_new_preview() -> None:
    """A new pending graph request does not erase the prior rollback receipt."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    session = RequestGraphSession(engine=engine, executor=_always_ok_executor)
    first = session.submit(**_submit_kwargs(request_id="r-1"))
    first_id = cast(str, first["plan_id"])
    assert session.approve(session_id=_SESSION_ID, plan_id=first_id) is not None
    assert (
        session.report_apply_outcome(
            session_id=_SESSION_ID, plan_id=first_id, outcome="applied"
        )
        is not None
    )
    second = session.submit(**_submit_kwargs(request_id="r-2"))
    assert second["status"] == STATE_PENDING_APPROVAL

    rolled_back = session.report_apply_outcome(
        session_id=_SESSION_ID, plan_id=first_id, outcome="rolled_back"
    )

    assert rolled_back is not None
    assert rolled_back["status"] == TERMINAL_ROLLED_BACK
    history = rolled_back["history"]
    assert isinstance(history, tuple)
    assert history[-1] == TERMINAL_ROLLED_BACK
    assert session._graph.get_state(
        {"configurable": {"thread_id": _SESSION_ID}}
    ).next == (STATE_PENDING_APPROVAL,)
    assert (
        session.approve(
            session_id=_SESSION_ID, plan_id=cast(str, second["plan_id"])
        )
        is not None
    )


def test_cancel_reaches_cancelled() -> None:
    """Cancelling the pending plan reaches `cancelled`."""
    session = _one_shot_session()
    session.submit(**_submit_kwargs(request_id="r-1"))

    result = session.cancel(session_id=_SESSION_ID)

    assert result is not None
    assert result["status"] == TERMINAL_CANCELLED


def test_cancel_interrupts_an_inflight_generation_and_prunes_its_thread() -> (
    None
):
    """`cancel()` signals a live generation without waiting for its lock.

    The graph is deliberately still inside `engine.complete()` when cancel
    starts. A fresh token inside the graph, or acquiring the session lock
    before signalling it, would deadlock this test until the generation's
    deadline rather than completing promptly.
    """
    engine = _CancellableEngine()
    session = RequestGraphSession(engine=engine, executor=_always_ok_executor)
    submitted: list[dict[str, object]] = []
    worker = threading.Thread(
        target=lambda: submitted.append(
            session.submit(**_submit_kwargs(request_id="r-1"))
        )
    )

    worker.start()
    assert engine.started.wait(timeout=1.0)
    cancelled = session.cancel(session_id=_SESSION_ID)
    worker.join(timeout=1.0)

    assert not worker.is_alive()
    assert engine.observed_cancellation.is_set()
    assert cancelled is not None
    assert cancelled["status"] == TERMINAL_CANCELLED
    assert submitted[0]["status"] == TERMINAL_CANCELLED
    assert session._sessions == {}
    assert (
        session._graph.get_state(
            {"configurable": {"thread_id": _SESSION_ID}}
        ).values
        == {}
    )


def test_a_second_submit_reaches_superseded_and_leaves_one_pending_plan() -> (
    None
):
    """A second submit supersedes the first, leaving exactly one pending."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    session = RequestGraphSession(engine=engine, executor=_always_ok_executor)
    session.submit(**_submit_kwargs(request_id="r-1"))

    second = session.submit(**_submit_kwargs(request_id="r-2"))

    assert "__interrupt__" in second
    assert second["status"] == STATE_PENDING_APPROVAL
    assert second["request_id"] == "r-2"

    config = {"configurable": {"thread_id": _SESSION_ID}}
    snapshot = session._graph.get_state(config)
    assert snapshot.next == (STATE_PENDING_APPROVAL,)
    assert snapshot.values["request_id"] == "r-2"
    # Supersession reached a terminal state before the second initial state
    # was invoked, so it must not retain the first request's full snapshot.
    assert all(
        entry.values.get("request_id") != "r-1"
        for entry in session._graph.get_state_history(config)
    )


def test_a_reject_one_tick_past_the_ttl_reaches_expired_not_rejected() -> None:
    """A reject arriving after `expires_at` reports `expired`."""
    clock = _FakeClock(datetime(2026, 9, 21, tzinfo=UTC))
    session = _one_shot_session(clock=clock, ttl_seconds=60.0)
    pending = session.submit(**_submit_kwargs(request_id="r-1"))
    clock.moment += timedelta(seconds=61)

    result = session.reject(
        session_id=_SESSION_ID, plan_id=cast(str, pending["plan_id"])
    )

    assert result is not None
    assert result["status"] == TERMINAL_EXPIRED


def test_an_approve_one_tick_past_the_ttl_reaches_expired_not_applying() -> (
    None
):
    """An expired approval never exposes the pending plan as applicable."""
    clock = _FakeClock(datetime(2026, 9, 21, tzinfo=UTC))
    session = _one_shot_session(clock=clock, ttl_seconds=60.0)
    pending = session.submit(**_submit_kwargs(request_id="r-1"))
    clock.moment += timedelta(seconds=61)

    result = session.approve(
        session_id=_SESSION_ID, plan_id=cast(str, pending["plan_id"])
    )

    assert result is not None
    assert result["status"] == TERMINAL_EXPIRED
    assert session._pending_details == {}
    assert (
        session._graph.get_state(
            {"configurable": {"thread_id": _SESSION_ID}}
        ).values
        == {}
    )


def test_a_reject_with_a_wrong_plan_id_changes_nothing() -> None:
    """A reject naming the wrong plan id is refused, thread untouched."""
    session = _one_shot_session()
    pending = session.submit(**_submit_kwargs(request_id="r-1"))

    result = session.reject(
        session_id=_SESSION_ID, plan_id="not-the-real-plan-id"
    )

    assert result is None
    config = {"configurable": {"thread_id": _SESSION_ID}}
    snapshot = session._graph.get_state(config)
    assert snapshot.next == (STATE_PENDING_APPROVAL,)
    assert snapshot.values["plan_id"] == pending["plan_id"]


def test_two_concurrent_submits_produce_one_superseded_and_one_pending() -> (
    None
):
    """Two racing submits for one session never both park.

    `RequestGraphSession`'s per-session lock is what stands between this
    and two concurrent `invoke()` calls racing to both observe an unparked
    thread, both skip the supersede step, and both try to park -- repeated
    several times because a lock bug is exactly the kind of thing that
    passes by luck on any single run.
    """
    for iteration in range(20):
        session_id = f"concurrent-session-{iteration}"
        session = RequestGraphSession(
            engine=_SlowEngine(delay_seconds=0.01), executor=_always_ok_executor
        )
        first = threading.Thread(
            target=_submit_in_thread,
            args=(session,),
            kwargs={"request_id": "r-1", "session_id": session_id},
        )
        second = threading.Thread(
            target=_submit_in_thread,
            args=(session,),
            kwargs={"request_id": "r-2", "session_id": session_id},
        )
        first.start()
        second.start()
        first.join()
        second.join()

        config = {"configurable": {"thread_id": session_id}}
        snapshot = session._graph.get_state(config)
        assert snapshot.next == (STATE_PENDING_APPROVAL,)
        winner = snapshot.values["request_id"]
        assert winner in ("r-1", "r-2")
        assert all(
            entry.values.get("request_id") in (None, winner)
            for entry in session._graph.get_state_history(config)
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
