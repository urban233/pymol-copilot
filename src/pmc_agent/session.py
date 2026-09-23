# Copyright 2026 PyMOL Copilot contributors.
"""The request graph's only public entry points: submit, reject, cancel.

`pmc_agent.graph.build_request_graph` returns an uncompiled graph; nothing
in that module owns a checkpointer, a lock, or a session's identity across
calls. `RequestGraphSession` is the one long-lived object docs/master_plan.md
item 8 wants instead: one compiled graph, one `InMemorySaver`, for one server
process, and the three operations `src/pmc_server/lifecycle.py` (item 9) and
`/v1/reject`, `/v1/cancel` call against it.

Locking exists because `LoopbackPlanServer` is a `ThreadingHTTPServer`: two
requests for the same session can arrive on two threads at once, and without
a lock they could both observe an unparked thread and both invoke the graph
concurrently, or a reject could interleave with a submit that is still
minting the very plan it names. One live lock per session id, held for the
whole graph invocation, makes "at most one active request per session" true
rather than nearly true, while sessions with different ids stay fully
concurrent. The registry reference-counts waiting operations, so a lock is
removed only after its final user leaves; retaining neither locks nor
checkpointed snapshots after a terminal request bounds a long-lived server's
memory to its currently pending plans, in-flight requests, and one small
rollback receipt per session with a still-applied plan.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC
from datetime import datetime

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from pmc_agent.graph import MAX_REPAIR_ATTEMPTS
from pmc_agent.graph import PLAN_TTL_SECONDS
from pmc_agent.graph import RESUME_ACTION_CANCEL
from pmc_agent.graph import RESUME_ACTION_APPROVE
from pmc_agent.graph import RESUME_ACTION_REJECT
from pmc_agent.graph import RESUME_ACTION_SUPERSEDE
from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.graph import STATE_APPLYING
from pmc_agent.graph import TERMINAL_APPLIED
from pmc_agent.graph import TERMINAL_APPLY_FAILED_RESTORED
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import TERMINAL_ROLLED_BACK
from pmc_agent.graph import TERMINAL_CANCELLED
from pmc_agent.graph import STATE_RECEIVED
from pmc_agent.graph import RequestState
from pmc_agent.graph import build_request_graph
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.prompt import PROMPT_BUILDER
from pmc_agent.prompt import build_default_prompt
from pmc_core.executor import DEFAULT_DEADLINE_SECONDS
from pmc_core.executor import DEFAULT_MAX_SNAPSHOT_BYTES
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import execute
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import StructureSnapshotV1

DEFAULT_MAX_COMPLETION_TOKENS = 1024
MAX_OUTCOME_RECEIPTS = 512
DEFAULT_GENERATION_DEADLINE_SECONDS = 30.0


def _new_plan_id() -> str:
    """Return a new UUIDv4 plan identifier.

    Mirrors `pmc_agent.graph._new_plan_id` and
    `pmc_server.lifecycle._new_plan_id` exactly; kept local rather than
    imported so this module's own default construction does not reach into
    another module's private names.

    Returns:
        A string containing a UUIDv4 identifier.
    """
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    """Return the current moment in UTC.

    Mirrors `pmc_agent.graph._utc_now`; kept local for the same reason as
    `_new_plan_id` above.

    Returns:
        A timezone-aware `datetime` in UTC.
    """
    return datetime.now(UTC)


def _thread_config(session_id: str):
    """Build the checkpointer config naming `session_id` as the thread.

    Deliberately left without a `RunnableConfig` return annotation:
    `RunnableConfig` lives in `langchain_core.runnables.config`, a package
    this module reaches only transitively through `@pypi//langgraph`, and
    every call site below passes this function's result straight into a
    `Pregel` method that declares that exact parameter type, so pyrefly
    checks the returned dict literal structurally against it either way.
    An explicit `dict[str, object]` annotation here would only widen the
    checked type and break that structural match.

    Args:
        session_id: The session whose thread this config addresses.

    Returns:
        A LangGraph `RunnableConfig`-shaped mapping.
    """
    return {"configurable": {"thread_id": session_id}}


class _SessionSlot:
    """One session lock and the number of operations using or waiting on it."""

    def __init__(self) -> None:
        """Create an unlocked, unreferenced session slot."""
        self.lock = threading.Lock()
        self.operations = 0


class RequestGraphSession:
    """One compiled request graph, one checkpointer, per-session locking."""

    def __init__(
        self,
        *,
        engine: InferenceEngine,
        prompt_builder: PROMPT_BUILDER = build_default_prompt,
        max_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
        deadline_seconds: float = DEFAULT_GENERATION_DEADLINE_SECONDS,
        executor: Callable[[ExecutionRequest], ExecutionReport] = execute,
        policy_validator: Callable[[ActionPlan], PlanDecision] = evaluate_plan,
        plan_id_source: Callable[[], str] = _new_plan_id,
        clock: Callable[[], datetime] = _utc_now,
        max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
        validation_deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
        ttl_seconds: float = PLAN_TTL_SECONDS,
        max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
    ) -> None:
        """Compile the request graph and prepare an empty lock table.

        Every argument beyond `engine` matches `build_request_graph`'s own
        parameter, forwarded unchanged; see that function's docstring for
        what each one means.

        Args:
            engine: The inference engine `generating` calls.
            prompt_builder: Builds the prompt `generating` sends to
                `engine`.
            max_tokens: The token budget given to every completion.
            deadline_seconds: The wall-clock budget given to every
                completion.
            executor: Runs one `ExecutionRequest` in a fresh sidecar.
            policy_validator: Independently re-checks a parsed plan.
            plan_id_source: Mints a plan identifier on a successful
                attempt.
            clock: Reports the current moment for computing `expires_at`
                and for judging whether one already has.
            max_snapshot_bytes: The snapshot size ceiling given to
                `executor`.
            validation_deadline_seconds: The wall-clock deadline given to
                `executor`.
            ttl_seconds: How long a minted plan stays approvable.
            max_repair_attempts: SPECIFICATION.md:640's repair budget.
        """
        self._sessions_guard = threading.Lock()
        self._sessions: dict[str, _SessionSlot] = {}
        self._active_cancellations: dict[str, CancelToken] = {}
        self._pending_details: dict[str, dict[str, object]] = {}
        # Only the latest successfully applied plan can still be rolled back.
        # Keep its tiny receipt apart from the graph thread: a later preview
        # must be free to use that same session thread without losing it.
        self._applied_details: dict[str, tuple[str, tuple[str, ...]]] = {}
        # A response can be lost after a terminal was recorded. Keep a
        # bounded replay window independent of the graph thread, which a
        # later preview is free to reuse.
        self._outcome_receipts: OrderedDict[
            tuple[str, str, str], dict[str, object]
        ] = OrderedDict()
        self._checkpointer = InMemorySaver()
        self._graph = build_request_graph(
            engine=engine,
            prompt_builder=prompt_builder,
            max_tokens=max_tokens,
            deadline_seconds=deadline_seconds,
            executor=executor,
            policy_validator=policy_validator,
            plan_id_source=plan_id_source,
            clock=clock,
            max_snapshot_bytes=max_snapshot_bytes,
            validation_deadline_seconds=validation_deadline_seconds,
            ttl_seconds=ttl_seconds,
            max_repair_attempts=max_repair_attempts,
            cancel_token_source=self._active_cancel_token,
        ).compile(checkpointer=self._checkpointer)

    def _active_cancel_token(self, session_id: str) -> CancelToken:
        """Return `session_id`'s active token, or an unreachable fallback.

        The fallback keeps a direct misuse of a compiled session graph from
        turning into a graph exception. Normal `submit()` always installs the
        token before invoking, so it cannot be reached by a real request.

        Args:
            session_id: The session currently being generated or validated.

        Returns:
            The session's active cancellation token.
        """
        with self._sessions_guard:
            token = self._active_cancellations.get(session_id)
        return token if token is not None else CancelToken()

    def _acquire_session(self, session_id: str) -> _SessionSlot:
        """Reserve and acquire the serialized-operation slot for a session.

        Args:
            session_id: The session whose graph operation is starting.

        Returns:
            The acquired session slot. The caller must pass it to
            `_release_session` in a `finally` block.
        """
        with self._sessions_guard:
            slot = self._sessions.get(session_id)
            if slot is None:
                slot = _SessionSlot()
                self._sessions[session_id] = slot
            slot.operations += 1
        slot.lock.acquire()
        return slot

    def _release_session(self, session_id: str, slot: _SessionSlot) -> None:
        """Release one operation and remove its idle lock-table entry.

        A waiter increments `operations` before it waits for `slot.lock`, so
        deleting the registry entry after release cannot create a second lock
        for the same session while another caller is queued on this one.

        Args:
            session_id: The session whose operation has completed.
            slot: The acquired slot returned by `_acquire_session`.
        """
        slot.lock.release()
        with self._sessions_guard:
            slot.operations -= 1
            if slot.operations == 0 and self._sessions.get(session_id) is slot:
                del self._sessions[session_id]

    def _delete_thread(self, session_id: str) -> None:
        """Remove every checkpoint for a terminal request's session.

        Args:
            session_id: The LangGraph thread id to prune.
        """
        self._checkpointer.delete_thread(session_id)

    def _is_pending(self, session_id: str) -> bool:
        """Return whether `session_id`'s thread is parked at approval.

        A thread that has never been used and a thread that has already
        reached a terminal status both report `next == ()` -- neither has
        anything to supersede, reject, or cancel, and the caller treats
        them identically.

        Args:
            session_id: The session to inspect.

        Returns:
            True when the thread is currently interrupted at
            `pending_approval`.
        """
        snapshot = self._graph.get_state(_thread_config(session_id))
        return snapshot.next == (STATE_PENDING_APPROVAL,)

    def _is_applying(self, session_id: str) -> bool:
        """Return whether a session is waiting for its apply outcome."""
        return self._graph.get_state(_thread_config(session_id)).next == (
            STATE_APPLYING,
        )

    def submit(
        self,
        *,
        request_id: str,
        session_id: str,
        created_at: str,
        intent: str,
        contract_manifest: ContractManifestV1,
        snapshot_identity: StructureSnapshotV1,
        snapshot_json: str,
        fidelity: FidelityOutcomeV1,
    ) -> dict[str, object]:
        """Start a new request on `session_id`'s thread, superseding any.

        SPECIFICATION.md:409-411 allows at most one pending plan per
        session; `session_id` being this graph's own `thread_id` (see
        `pmc_agent.graph`'s module docstring) makes that structural, but
        starting a second run on an already-parked thread still requires
        resolving the first one, not merely overwriting it -- otherwise
        `superseded` would never appear in the first request's own
        `history`.

        Args:
            request_id: The new request's own wire identifier.
            session_id: The session this request was made under.
            created_at: When the request was received, in the protocol's
                RFC3339 UTC wire form.
            intent: The user's literal, immutable request text.
            contract_manifest: The contract versions the request declared.
            snapshot_identity: The client's own computed snapshot identity.
            snapshot_json: The full canonical snapshot JSON.
            fidelity: The client's own local fidelity outcome.

        Returns:
            The new request's own result mapping: either a terminal
            status, or a parked one carrying `"__interrupt__"`.
        """
        config = _thread_config(session_id)
        slot = self._acquire_session(session_id)
        try:
            if self._is_applying(session_id):
                # An approved client may already have mutated the live
                # session even if its outcome report was lost. Never replace
                # this thread until the client supplies that outcome.
                return {
                    "status": TERMINAL_FAILED,
                    "failure": FailureEnvelopeV1(
                        category="apply_outcome_required",
                        message=(
                            "the previous approved plan still awaits its "
                            "client apply outcome"
                        ),
                        retryable=True,
                    ),
                }
            if self._is_pending(session_id):
                self._graph.invoke(
                    Command(resume={"action": RESUME_ACTION_SUPERSEDE}),
                    config,
                )
                self._delete_thread(session_id)
                self._pending_details.pop(session_id, None)
            elif (
                self._graph.get_state(config).values.get("status")
                == TERMINAL_APPLIED
            ):
                self._delete_thread(session_id)
                self._pending_details.pop(session_id, None)
            initial_state: RequestState = {
                "request_id": request_id,
                "session_id": session_id,
                "created_at": created_at,
                "intent": intent,
                "contract_manifest": contract_manifest,
                "snapshot_identity": snapshot_identity,
                "snapshot_json": snapshot_json,
                "fidelity": fidelity,
                "status": STATE_RECEIVED,
                "target_object": None,
                "attempt": 0,
                "history": (STATE_RECEIVED,),
                "errors": (),
                "plan": None,
                "plan_id": None,
                "expires_at": None,
                "model_identity": None,
                "failure": None,
                "question": None,
                "completion": None,
            }
            cancel_token = CancelToken()
            with self._sessions_guard:
                self._active_cancellations[session_id] = cancel_token
            try:
                result = self._graph.invoke(initial_state, config)
            except BaseException:
                self._delete_thread(session_id)
                raise
            finally:
                with self._sessions_guard:
                    if (
                        self._active_cancellations.get(session_id)
                        is cancel_token
                    ):
                        del self._active_cancellations[session_id]
            if result.get("status") != STATE_PENDING_APPROVAL:
                self._delete_thread(session_id)
                self._pending_details.pop(session_id, None)
            else:
                # LangGraph's interrupted checkpoint retains its control
                # fields but not every opaque domain value. Keep the exact
                # response facts server-side for the later approval reply.
                result["snapshot_digest"] = snapshot_identity.digest
                result["validation_applicable"] = fidelity.status == "exact"
                self._pending_details[session_id] = dict(result)
            return result
        finally:
            self._release_session(session_id, slot)

    def reject(
        self, *, session_id: str, plan_id: str
    ) -> dict[str, object] | None:
        """Resume `session_id`'s pending plan as rejected, if it matches.

        Args:
            session_id: The session whose pending plan is being rejected.
            plan_id: The plan identifier the caller believes is pending.
                Refused, with the thread untouched, when it does not match
                the plan actually pending -- SPECIFICATION.md:432-435's
                invalidation is about the plan itself changing underneath a
                caller, not about honoring a stale or mistaken identifier.

        Returns:
            The resumed request's own result mapping (its terminal status
            is `rejected` unless expiry won first), or None when there is
            no pending plan or `plan_id` does not match it -- nothing was
            touched.
        """
        config = _thread_config(session_id)
        slot = self._acquire_session(session_id)
        try:
            if not self._is_pending(session_id):
                return None
            snapshot = self._graph.get_state(config)
            if snapshot.values.get("plan_id") != plan_id:
                return None
            result = self._graph.invoke(
                Command(resume={"action": RESUME_ACTION_REJECT}), config
            )
            self._delete_thread(session_id)
            self._pending_details.pop(session_id, None)
            return result
        finally:
            self._release_session(session_id, slot)

    def approve(
        self, *, session_id: str, plan_id: str
    ) -> dict[str, object] | None:
        """Approve once, or replay the same handshake while awaiting outcome."""
        config = _thread_config(session_id)
        slot = self._acquire_session(session_id)
        try:
            snapshot = self._graph.get_state(config)
            if snapshot.next not in {
                (STATE_PENDING_APPROVAL,),
                (STATE_APPLYING,),
            }:
                return None
            if snapshot.values.get("plan_id") != plan_id:
                return None
            approved_values = self._pending_details.get(session_id)
            if approved_values is None:
                return None
            if approved_values.get("validation_applicable") is not True:
                return {
                    "status": TERMINAL_FAILED,
                    "failure": FailureEnvelopeV1(
                        category="not_applicable",
                        message="a non-exact fidelity preview cannot be approved",
                        retryable=False,
                    ),
                }
            if snapshot.next == (STATE_PENDING_APPROVAL,):
                result = self._graph.invoke(
                    Command(resume={"action": RESUME_ACTION_APPROVE}), config
                )
                # Approval can race the graph's own TTL check. Only an actual
                # ``applying`` interrupt may receive the committed preview.
                if result.get("status") != STATE_APPLYING:
                    self._delete_thread(session_id)
                    self._pending_details.pop(session_id, None)
                    return result
            # LangGraph's interrupt return contains only the resumed node's
            # partial update. Read the checkpoint for both first approval
            # and a retry after its response was lost.
            applying = dict(self._graph.get_state(config).values)
            for name in (
                "plan",
                "plan_id",
                "expires_at",
                "model_identity",
                "snapshot_digest",
                "validation_applicable",
            ):
                applying[name] = approved_values[name]
            return applying
        finally:
            self._release_session(session_id, slot)

    def report_apply_outcome(
        self, *, session_id: str, plan_id: str, outcome: str
    ) -> dict[str, object] | None:
        """Resume an approved plan with its client-observed terminal outcome."""
        config = _thread_config(session_id)
        slot = self._acquire_session(session_id)
        try:
            receipt_key = (session_id, plan_id, outcome)
            receipt = self._outcome_receipts.get(receipt_key)
            if receipt is not None:
                self._outcome_receipts.move_to_end(receipt_key)
                return dict(receipt)
            snapshot = self._graph.get_state(config)
            applied = self._applied_details.get(session_id)
            if (
                applied is not None
                and outcome == "rolled_back"
                and applied[0] == plan_id
            ):
                # A later preview may have reused this graph thread. Its
                # current pending plan must remain untouched by the rollback
                # of an earlier successfully applied plan.
                result: dict[str, object] = {
                    "status": TERMINAL_ROLLED_BACK,
                    "history": (*applied[1], TERMINAL_ROLLED_BACK),
                }
                del self._applied_details[session_id]
                if (
                    snapshot.values.get("status") == TERMINAL_APPLIED
                    and snapshot.values.get("plan_id") == plan_id
                ):
                    self._delete_thread(session_id)
                    self._pending_details.pop(session_id, None)
                self._remember_outcome(receipt_key, result)
                return result
            if not self._is_applying(session_id):
                return None
            if snapshot.values.get("plan_id") != plan_id:
                return None
            result = self._graph.invoke(
                Command(resume={"outcome": outcome}), config
            )
            if result.get("status") == TERMINAL_APPLIED:
                history = result.get("history")
                assert isinstance(history, tuple)
                self._applied_details[session_id] = (plan_id, history)
            if result.get("status") in {
                TERMINAL_APPLY_FAILED_RESTORED,
                TERMINAL_ROLLED_BACK,
            }:
                self._delete_thread(session_id)
                self._pending_details.pop(session_id, None)
            self._remember_outcome(receipt_key, result)
            return result
        finally:
            self._release_session(session_id, slot)

    def _remember_outcome(
        self, key: tuple[str, str, str], result: dict[str, object]
    ) -> None:
        """Retain a bounded exact-terminal receipt for a lost HTTP reply."""
        self._outcome_receipts[key] = dict(result)
        self._outcome_receipts.move_to_end(key)
        if len(self._outcome_receipts) > MAX_OUTCOME_RECEIPTS:
            self._outcome_receipts.popitem(last=False)

    def cancel(self, *, session_id: str) -> dict[str, object] | None:
        """Resume `session_id`'s pending plan as cancelled.

        Args:
            session_id: The session whose pending plan is being cancelled.

        Returns:
            The resumed request's own result mapping (its terminal status
            is `cancelled` unless expiry won first), or None when there is
            no pending plan to cancel.
        """
        # Do not acquire the session lock before signalling: `submit()` holds
        # it while `engine.complete()` is in flight. The live token makes the
        # signal reachable immediately, while acquiring afterwards waits only
        # to serialize the graph transition or collect its terminal result.
        with self._sessions_guard:
            active_token = self._active_cancellations.get(session_id)
        if active_token is not None:
            active_token.cancel()
            slot = self._acquire_session(session_id)
            try:
                # A cancellation that raced the last few instructions of
                # validation may have parked just before it was observed.
                # Resolve that parked plan too; otherwise the generating or
                # validating node has already ended it as cancelled.
                if self._is_pending(session_id):
                    result = self._graph.invoke(
                        Command(resume={"action": RESUME_ACTION_CANCEL}),
                        _thread_config(session_id),
                    )
                    self._delete_thread(session_id)
                    self._pending_details.pop(session_id, None)
                    return result
                return {"status": TERMINAL_CANCELLED}
            finally:
                self._release_session(session_id, slot)

        config = _thread_config(session_id)
        slot = self._acquire_session(session_id)
        try:
            if not self._is_pending(session_id):
                return None
            result = self._graph.invoke(
                Command(resume={"action": RESUME_ACTION_CANCEL}), config
            )
            self._delete_thread(session_id)
            self._pending_details.pop(session_id, None)
            return result
        finally:
            self._release_session(session_id, slot)
