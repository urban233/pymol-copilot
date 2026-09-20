# Copyright 2026 PyMOL Copilot contributors.
"""The LangGraph request graph: states, the request's own typed shape.

docs/master_plan.md item 8 replaces the hardcoded fixture lifecycle in
`src/pmc_server/lifecycle.py` with this graph. The state space is
SPECIFICATION.md:417-426's own domain model, restated here as the graph's
node names:

```text
received -> preparing -> generating -> validating -> pending_approval
pending_approval -> rejected | expired | superseded
any pre-apply state -> ask | failed | cancelled
```

`applying`, `applied`, `restoring`, `apply_failed_restored`, and
`rolled_back` are item 10's own states, deliberately absent here.

`received` is not a graph node: it is the status a request carries before
the graph is ever invoked, recorded by the caller
(`pmc_agent.session.RequestGraphSession.submit`) as `history`'s first
entry. `preparing` is this graph's entry point.

A finding worth recording once here rather than rediscovering at the next
node that needs it: a LangGraph node that calls `langgraph.types.interrupt`
re-runs its own body **from the top** every time the parked thread is
resumed, including whatever code ran before that call. A value minted
there -- a plan id from `uuid.uuid4()`, a computed expiry -- would differ
between what a user is shown while parked and what the thread holds after
resume. Every value `pending_approval` must report and that must survive
resumption unchanged (`plan_id`, `expires_at`, `model_identity`) is
therefore always minted by `validating`'s own success path, committed to
state *before* the graph transitions to `pending_approval`, whose body
after this item does nothing but call `interrupt` and interpret whatever
resumes it. Verified empirically against langgraph 1.2.11 before this
module was written; not asserted by any test here because it is a property
of the dependency, not of this code, but it is why `pending_approval`'s own
body is as thin as it is.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from typing import TypedDict

from langgraph.graph import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from pmc_core.errors import ExecutionErrorV1
from pmc_core.plan import ActionPlan
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import StructureSnapshotV1

#: Non-terminal request states -- each one is also this graph's own node
#: name, so a status value and a node name are always the same string.
STATE_RECEIVED = "received"
STATE_PREPARING = "preparing"
STATE_GENERATING = "generating"
STATE_VALIDATING = "validating"
STATE_PENDING_APPROVAL = "pending_approval"

#: Terminal states. Once a request carries one of these, the graph run
#: that produced it has ended -- see `route_by_status` below.
TERMINAL_REJECTED = "rejected"
TERMINAL_EXPIRED = "expired"
TERMINAL_SUPERSEDED = "superseded"
TERMINAL_FAILED = "failed"
TERMINAL_CANCELLED = "cancelled"
TERMINAL_ASK = "ask"

#: Every terminal status this graph can produce, for `route_by_status` and
#: for a test to assert against by identity rather than by re-listing them.
TERMINAL_STATES: frozenset[str] = frozenset(
    {
        TERMINAL_REJECTED,
        TERMINAL_EXPIRED,
        TERMINAL_SUPERSEDED,
        TERMINAL_FAILED,
        TERMINAL_CANCELLED,
        TERMINAL_ASK,
    }
)

#: Every non-terminal status, including `received`, which has no node of
#: its own (see the module docstring).
NON_TERMINAL_STATES: frozenset[str] = frozenset(
    {
        STATE_RECEIVED,
        STATE_PREPARING,
        STATE_GENERATING,
        STATE_VALIDATING,
        STATE_PENDING_APPROVAL,
    }
)

#: Every status this graph's domain model defines -- the eleven names
#: docs/master_plan.md item 8 names exactly, no more and no fewer.
REQUEST_STATES: frozenset[str] = NON_TERMINAL_STATES | TERMINAL_STATES

#: SPECIFICATION.md:640: "at most one initial attempt and two repair
#: attempts." `attempt` counts from 1 at the first generation, so a request
#: may reach `attempt == MAX_REPAIR_ATTEMPTS + 1` before failing closed.
MAX_REPAIR_ATTEMPTS = 2

#: How long a validated plan may sit at `pending_approval` before an
#: approval, rejection, or cancellation against it is refused as expired.
#: Chosen for a single-user, local, interactive tool -- long enough that a
#: user reading the printed plan is never rushed, short enough that a
#: forgotten session does not leave an approvable plan lying around
#: indefinitely. The clock that measures it is always injected (see
#: `build_request_graph` and `pmc_agent.session`), never read from the
#: wall clock directly, so a test controls it exactly.
PLAN_TTL_SECONDS = 300.0


class RequestState(TypedDict):
    """The one piece of state a request's graph run threads through.

    Fields are grouped by who may ever write them. The first group is
    fixed at `received`, before the graph is invoked, and no node below
    ever rewrites a field in it. The second group is written only by this
    module's own deterministic node bodies. The third group -- exactly one
    field -- is the model's entire contribution to this state:
    `generating` is the only node that writes it, and no other field is
    ever derived from its *content*, only from whether it is present, in
    the same spirit as SPECIFICATION.md:551-552's "no model output
    determines authority, retries, target object, network destination,
    policy, approval, or rollback behavior."

    Attributes:
        request_id: The request's own wire identifier, echoed on every
            response.
        session_id: The session this request was made under. Used as this
            graph's own `thread_id`
            (`pmc_agent.session.RequestGraphSession`), which is what makes
            "at most one active request per session" structural rather
            than a separately enforced rule.
        created_at: When the request was received, in the protocol's own
            RFC3339 UTC wire form.
        intent: The user's literal, immutable request text.
        contract_manifest: The contract versions the request declared.
        snapshot_identity: The requesting client's own computed snapshot
            identity -- digest, object name, and counts, never bytes.
        snapshot_json: The full canonical snapshot JSON `validating` needs
            to run a fresh sidecar. Computed once by the client and never
            rewritten here.
        fidelity: The client's own local fidelity outcome for this
            snapshot, carried unchanged; this graph never upgrades or
            re-derives it (orchestration rule 9).
        status: The request's current state. Always one of
            `REQUEST_STATES`.
        target_object: The one molecular object `preparing` resolved, or
            None before `preparing` has run. Written once, by `preparing`
            alone; nothing after it may change it, model output least of
            all.
        attempt: How many times `generating` has been asked for a
            completion for this request, starting at 0 before the first
            call. Never read from, or influenced by, `completion`.
        history: Every status this request has carried, in order,
            starting with `received`. Exists because a terminal status
            such as `superseded` is otherwise unobservable -- the thread
            has already moved on to a new request's checkpoint by the time
            anything could ask it.
        errors: The normalized `ExecutionErrorV1` from every failed
            attempt so far, oldest first -- what a repair prompt is built
            from.
        plan: The typed plan `validating` most recently parsed, or None
            before any attempt has produced one.
        plan_id: The server-issued identifier for the plan now pending
            approval, or None before one exists. Minted exactly once, by
            `validating`'s own success path, never re-minted on a later
            resume of `pending_approval` (see the module docstring).
        expires_at: When `plan_id` stops being approvable, in the same
            wire timestamp form as `created_at`. Minted alongside
            `plan_id`, from the same injected clock plus `PLAN_TTL_SECONDS`.
        model_identity: The identity the inference engine reported for the
            completion that produced `plan`, re-verifiable at approval
            (item 10's territory; this graph only carries it forward).
        failure: The typed failure this request ended with, when `status`
            is `failed`; None otherwise.
        question: The bounded, redacted clarification question, when
            `status` is `ask`; None otherwise.
        completion: The most recent raw text `generating` received from
            the engine, or None before it has run once. The one field the
            model writes.
    """

    request_id: str
    session_id: str
    created_at: str
    intent: str
    contract_manifest: ContractManifestV1
    snapshot_identity: StructureSnapshotV1
    snapshot_json: str
    fidelity: FidelityOutcomeV1

    status: str
    target_object: str | None
    attempt: int
    history: tuple[str, ...]
    errors: tuple[ExecutionErrorV1, ...]
    plan: ActionPlan | None
    plan_id: str | None
    expires_at: str | None
    model_identity: str | None
    failure: FailureEnvelopeV1 | None
    question: str | None

    completion: str | None


def route_by_status(state: RequestState) -> str:
    """Route to the node named by `state["status"]`, or end the run.

    A pure function of `status` alone, deliberately: every edge this graph
    can take is decided by this one mapping, and a test exercises it
    directly, without compiling or running the graph at all.

    Args:
        state: The request state to route from.

    Returns:
        `state["status"]` itself, when it names a non-terminal state --
        every such name is also this graph's own node name -- or
        `langgraph.graph.END` when it names a terminal one.

    Raises:
        ValueError: If `status` is not a member of `REQUEST_STATES`. A
            status this graph did not itself produce is a defect to raise
            on, not a state to route past.
    """
    status = state["status"]
    if status in TERMINAL_STATES:
        return END
    if status in NON_TERMINAL_STATES:
        return status
    raise ValueError(f"unrecognized request status: {status!r}")


def _preparing(state: RequestState) -> dict[str, object]:
    """Resolve the request's target object. Stub: see `pmc_agent.prompt`.

    docs/master_plan.md item 8, step 6 replaces this body with real target
    resolution and contract-manifest verification. Step 5's own stub exists
    so the graph compiles and its pass-through shape is provable before any
    node does real work.

    Args:
        state: The request state entering `preparing`.

    Returns:
        A partial update advancing to `generating`.
    """
    return {
        "status": STATE_GENERATING,
        "history": (*state["history"], STATE_GENERATING),
    }


def _generating(state: RequestState) -> dict[str, object]:
    """Call the inference engine. Stub: see step 6.

    Args:
        state: The request state entering `generating`.

    Returns:
        A partial update advancing to `validating`.
    """
    return {
        "status": STATE_VALIDATING,
        "history": (*state["history"], STATE_VALIDATING),
    }


def _validating(state: RequestState) -> dict[str, object]:
    """Parse, screen, police, and execute one attempt. Stub: see step 7.

    Args:
        state: The request state entering `validating`.

    Returns:
        A partial update advancing to `pending_approval`.
    """
    return {
        "status": STATE_PENDING_APPROVAL,
        "history": (*state["history"], STATE_PENDING_APPROVAL),
    }


def _pending_approval(state: RequestState) -> dict[str, object]:
    """Park for approval, for real; the resume path is still a stub.

    docs/master_plan.md item 8, step 8 replaces the return below with real
    reject/cancel/supersede/expire handling driven by whatever resumes this
    call. This stub's own job -- proving the graph genuinely parks rather
    than merely setting a status -- is not deferred, per the module
    docstring's finding about `interrupt`.

    Args:
        state: The request state entering `pending_approval`. Every field
            `interrupt` reports here (`plan_id`, `expires_at`) was already
            committed by `validating`'s own success path, never minted in
            this call.

    Returns:
        A partial update to a terminal status once resumed.
    """
    interrupt(
        {"plan_id": state.get("plan_id"), "expires_at": state.get("expires_at")}
    )
    return {
        "status": TERMINAL_ASK,
        "history": (*state["history"], TERMINAL_ASK),
    }


def build_request_graph() -> StateGraph[RequestState]:  # pyrefly: ignore[bad-specialization]
    """Build the uncompiled request graph, wired but not yet compiled.

    Left uncompiled here because compilation is where a checkpointer is
    attached, and this item's checkpointer is owned by
    `pmc_agent.session.RequestGraphSession`, one per server process, not by
    this builder -- matching how every other injectable seam in this
    repository (`PlanRequestLifecycle`, `PlanValidationService`) keeps
    construction and its runtime dependencies separate.

    Returns:
        The graph, with every node and edge from `preparing` onward wired,
        ready for a caller to `.compile(checkpointer=...)`.
    """
    graph = StateGraph(RequestState)  # pyrefly: ignore[bad-specialization]
    graph.add_node(STATE_PREPARING, _preparing)
    graph.add_node(STATE_GENERATING, _generating)
    graph.add_node(STATE_VALIDATING, _validating)
    graph.add_node(STATE_PENDING_APPROVAL, _pending_approval)

    graph.set_entry_point(STATE_PREPARING)
    for name in (
        STATE_PREPARING,
        STATE_GENERATING,
        STATE_VALIDATING,
        STATE_PENDING_APPROVAL,
    ):
        graph.add_conditional_edges(name, route_by_status)

    return graph
