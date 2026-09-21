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
minting the very plan it names. One `threading.Lock` per session id, held
for the whole graph invocation, makes "at most one active request per
session" true rather than nearly true, while sessions with different ids
stay fully concurrent. The lock table itself is guarded by a second lock,
held only long enough to find or create one session's lock -- never for the
graph invocation itself.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import threading
import uuid
from collections.abc import Callable
from datetime import UTC
from datetime import datetime

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from pmc_agent.graph import MAX_REPAIR_ATTEMPTS
from pmc_agent.graph import PLAN_TTL_SECONDS
from pmc_agent.graph import RESUME_ACTION_CANCEL
from pmc_agent.graph import RESUME_ACTION_REJECT
from pmc_agent.graph import RESUME_ACTION_SUPERSEDE
from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.graph import STATE_RECEIVED
from pmc_agent.graph import RequestState
from pmc_agent.graph import build_request_graph
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
from pmc_core.protocol import StructureSnapshotV1

DEFAULT_MAX_COMPLETION_TOKENS = 1024
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
        self._clock = clock
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
        ).compile(checkpointer=InMemorySaver())
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def _lock_for(self, session_id: str) -> threading.Lock:
        """Find or create the one lock guarding `session_id`'s thread.

        Args:
            session_id: The session to look up.

        Returns:
            That session's lock, created on first use and reused after.
        """
        with self._locks_guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[session_id] = lock
            return lock

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
        with self._lock_for(session_id):
            if self._is_pending(session_id):
                self._graph.invoke(
                    Command(resume={"action": RESUME_ACTION_SUPERSEDE}),
                    config,
                )
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
            return self._graph.invoke(initial_state, config)

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
        with self._lock_for(session_id):
            if not self._is_pending(session_id):
                return None
            snapshot = self._graph.get_state(config)
            if snapshot.values.get("plan_id") != plan_id:
                return None
            return self._graph.invoke(
                Command(resume={"action": RESUME_ACTION_REJECT}), config
            )

    def cancel(self, *, session_id: str) -> dict[str, object] | None:
        """Resume `session_id`'s pending plan as cancelled.

        Args:
            session_id: The session whose pending plan is being cancelled.

        Returns:
            The resumed request's own result mapping (its terminal status
            is `cancelled` unless expiry won first), or None when there is
            no pending plan to cancel.
        """
        config = _thread_config(session_id)
        with self._lock_for(session_id):
            if not self._is_pending(session_id):
                return None
            return self._graph.invoke(
                Command(resume={"action": RESUME_ACTION_CANCEL}), config
            )
