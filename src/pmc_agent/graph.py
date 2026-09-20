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

from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.prompt import PROMPT_BUILDER
from pmc_agent.prompt import PromptInputs
from pmc_agent.prompt import build_default_prompt
from pmc_core.errors import ExecutionErrorV1
from pmc_core.errors import normalize_message
from pmc_core.plan import ActionPlan
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.snapshot import from_json

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

#: `preparing`'s own accepted contract manifest. Every field is the
#: literal "1" because none of plan.py, policy.py, or snapshot.py defines
#: its own version constant yet -- this mirrors exactly what the fixture
#: lifecycle it replaces already asserted
#: (`pmc_server.lifecycle.FIXTURE_MANIFEST`), just no longer paired with a
#: fixture plan or a fixture snapshot identity. A future major version in
#: any of those three modules must update this constant, in this module,
#: alongside it -- there is nowhere else that decides what this server
#: accepts.
ACCEPTED_CONTRACT_MANIFEST = ContractManifestV1(
    plan_version="1", policy_version="1", snapshot_version="1"
)

#: `generating`'s own defaults for a bounded completion. Independent of
#: every other deadline in this repository (`pmc_core.executor`'s,
#: `pmc_server.transport`'s): this one bounds the model, not a process.
DEFAULT_MAX_COMPLETION_TOKENS = 1024
DEFAULT_GENERATION_DEADLINE_SECONDS = 30.0

#: `generating`'s own clarification-request contract: a completion whose
#: entire text is one line starting with this prefix is a clarification
#: question, not a plan to parse. This module owns the contract because no
#: real prompt builder exists yet (docs/master_plan.md item 13); item 13
#: inherits it or replaces it, but the graph does not change either way,
#: since classification happens here, not in the prompt.
ASK_MARKER_PREFIX = "ask:"

#: The fixed question `generating` reports when a completion is empty or
#: whitespace only -- itself a form of "the model asked for nothing more
#: to go on", handled identically to an explicit `ask:` line.
EMPTY_COMPLETION_QUESTION = (
    "the model produced no output; please rephrase your intent"
)

#: Stable failure categories `preparing` and `generating` can produce.
#: Distinct from `pmc_core.errors.CATEGORIES` (that module's categories
#: are for a PyMOL execution failure `validating` normalizes; these are
#: for a request that never reached execution at all).
FAILURE_CONTRACT_MISMATCH = "contract_mismatch"
FAILURE_MALFORMED_SNAPSHOT = "malformed_snapshot"
FAILURE_NO_TARGET_OBJECT = "no_target_object"


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


def _failed(
    state: RequestState, *, category: str, message: str, retryable: bool
) -> dict[str, object]:
    """Build the partial update common to every `failed`-ending node.

    Every node that can fail closed before a plan exists builds its
    `FailureEnvelopeV1` at the point it decided to fail, with its own
    category and its own judgment of `retryable` -- there is no single
    fixed mapping from "this node failed" to one envelope, because *why*
    a request failed is exactly the information `state["failure"]` exists
    to carry to `pmc_server.lifecycle`'s eventual wire response.

    Args:
        state: The request state at the point of failure.
        category: A stable, machine-readable failure category.
        message: A bounded, human-readable explanation.
        retryable: Whether resubmitting a new request could plausibly
            succeed where this one did not.

    Returns:
        A partial update ending the request at `TERMINAL_FAILED`.
    """
    return {
        "status": TERMINAL_FAILED,
        "history": (*state["history"], TERMINAL_FAILED),
        "failure": FailureEnvelopeV1(
            category=category, message=message, retryable=retryable
        ),
    }


def _preparing(state: RequestState) -> dict[str, object]:
    """Resolve the request's target object; verify its contract manifest.

    Orchestration rule 3 ("preparation resolves one target object") is
    already done by the time a request reaches this graph: item 7's client
    resolves exactly one molecular object, deterministically, and fails
    closed with no request sent at all if it cannot
    (`pmc_client.session.resolve_target_object`). This node's own job is
    narrower -- read what the client already resolved, and refuse to
    proceed on a request this server's own contracts cannot honor -- not
    to resolve anything itself.

    Args:
        state: The request state entering `preparing`.

    Returns:
        A partial update advancing to `generating`, or ending the request
        at `TERMINAL_FAILED` with a typed, non-repairable failure.
    """
    if state["contract_manifest"] != ACCEPTED_CONTRACT_MANIFEST:
        return _failed(
            state,
            category=FAILURE_CONTRACT_MISMATCH,
            message="request declared contract versions this server does "
            "not accept",
            retryable=False,
        )
    try:
        from_json(state["snapshot_json"])
    except Exception:
        # from_json's own failure modes are exception-typed by
        # pmc_core.snapshot, not this module's concern; any of them means
        # the same thing here: the snapshot cannot be used, so it fails
        # the same way regardless of which one it was.
        return _failed(
            state,
            category=FAILURE_MALFORMED_SNAPSHOT,
            message="request snapshot could not be decoded",
            retryable=False,
        )
    target_object = state["snapshot_identity"].object_name
    if not target_object:
        return _failed(
            state,
            category=FAILURE_NO_TARGET_OBJECT,
            message="request carried no resolved target object",
            retryable=False,
        )
    return {
        "status": STATE_GENERATING,
        "history": (*state["history"], STATE_GENERATING),
        "target_object": target_object,
    }


def _classify_completion(
    state: RequestState, *, completion: str, model_identity: str, attempt: int
) -> dict[str, object]:
    """Classify a completion as a clarification, or accept it for parsing.

    Orchestration rule 6: "LangGraph calls local inference and classifies
    clarification or no-op output before plan parsing." Whether the model
    asked a question is the model's own contribution
    (SPECIFICATION.md:551-552 permits this -- it is not retry count,
    target, policy, or approval); the classification rule itself, and the
    bounding of whatever question text results, are this module's.

    Args:
        state: The request state entering `generating`.
        completion: The engine's raw completion text.
        model_identity: The engine's reported model identity.
        attempt: This request's attempt count, already incremented.

    Returns:
        A partial update to `TERMINAL_ASK` with a bounded question, or
        advancing to `STATE_VALIDATING` with the completion recorded for
        `validating` to parse.
    """
    stripped = completion.strip()
    question: str | None = None
    if not stripped:
        question = EMPTY_COMPLETION_QUESTION
    elif "\n" not in stripped and stripped.lower().startswith(
        ASK_MARKER_PREFIX
    ):
        question = stripped[len(ASK_MARKER_PREFIX) :].strip()

    if question is not None:
        return {
            "status": TERMINAL_ASK,
            "history": (*state["history"], TERMINAL_ASK),
            "attempt": attempt,
            "completion": completion,
            "model_identity": model_identity,
            "question": normalize_message(question),
        }
    return {
        "status": STATE_VALIDATING,
        "history": (*state["history"], STATE_VALIDATING),
        "attempt": attempt,
        "completion": completion,
        "model_identity": model_identity,
    }


def _build_generating(
    *,
    engine: InferenceEngine,
    prompt_builder: PROMPT_BUILDER,
    max_tokens: int,
    deadline_seconds: float,
) -> Callable[[RequestState], dict[str, object]]:
    """Close a `generating` node body over its injected engine and prompt.

    A closure, not a bound method on some class, because a LangGraph node
    is exactly this: `Callable[[RequestState], dict[str, object]]`, and
    `build_request_graph` is where every other node's injectable
    dependencies (`pmc_agent.session.RequestGraphSession`'s eventual
    `executor`, `plan_id_source`, `clock`) get the same treatment.

    Args:
        engine: The inference engine to call. A fake in every test in this
            item; item 9's Lemonade adapter satisfies the same
            `InferenceEngine` Protocol in production.
        prompt_builder: Builds the prompt from this request's own inputs.
        max_tokens: The token budget given to every completion.
        deadline_seconds: The wall-clock budget given to every completion.

    Returns:
        The `generating` node body.
    """

    def _generating(state: RequestState) -> dict[str, object]:
        """Call the inference engine once and classify its completion.

        Args:
            state: The request state entering `generating`.

        Returns:
            A partial update: to `TERMINAL_FAILED` on an engine failure,
            to `TERMINAL_ASK` on a clarification or empty completion, or
            advancing to `STATE_VALIDATING` otherwise.
        """
        prompt = prompt_builder(
            PromptInputs(
                intent=state["intent"],
                snapshot=from_json(state["snapshot_json"]),
                contract_manifest=state["contract_manifest"],
            )
        )
        outcome = engine.complete(
            CompletionRequest(
                prompt=prompt,
                grammar=None,
                max_tokens=max_tokens,
                deadline_seconds=deadline_seconds,
            ),
            cancel=CancelToken(),
        )
        attempt = state["attempt"] + 1
        if isinstance(outcome, EngineFailure):
            failed = _failed(
                state,
                category=outcome.category,
                message=outcome.message,
                # An engine failure says nothing about this request's own
                # intent or plan; a fresh request could plausibly succeed
                # where this one hit an unavailable or timed-out engine.
                retryable=True,
            )
            failed["attempt"] = attempt
            return failed
        return _classify_completion(
            state,
            completion=outcome.text,
            model_identity=outcome.model_identity,
            attempt=attempt,
        )

    return _generating


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


def build_request_graph(
    *,
    engine: InferenceEngine,
    prompt_builder: PROMPT_BUILDER = build_default_prompt,
    max_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
    deadline_seconds: float = DEFAULT_GENERATION_DEADLINE_SECONDS,
) -> StateGraph[RequestState]:  # pyrefly: ignore[bad-specialization]
    """Build the uncompiled request graph, wired but not yet compiled.

    Left uncompiled here because compilation is where a checkpointer is
    attached, and this item's checkpointer is owned by
    `pmc_agent.session.RequestGraphSession`, one per server process, not by
    this builder -- matching how every other injectable seam in this
    repository (`PlanRequestLifecycle`, `PlanValidationService`) keeps
    construction and its runtime dependencies separate.

    Args:
        engine: The inference engine `generating` calls. Required, with no
            default: unlike every other parameter here, there is no
            production-safe default engine to fall back to.
        prompt_builder: Builds the prompt `generating` sends to `engine`.
            Defaults to this module's own placeholder
            (`pmc_agent.prompt.build_default_prompt`) until
            docs/master_plan.md item 13 supplies the real one.
        max_tokens: The token budget given to every completion.
        deadline_seconds: The wall-clock budget given to every completion.

    Returns:
        The graph, with every node and edge from `preparing` onward wired,
        ready for a caller to `.compile(checkpointer=...)`.
    """
    graph = StateGraph(RequestState)  # pyrefly: ignore[bad-specialization]
    generating = _build_generating(
        engine=engine,
        prompt_builder=prompt_builder,
        max_tokens=max_tokens,
        deadline_seconds=deadline_seconds,
    )
    graph.add_node(STATE_PREPARING, _preparing)
    graph.add_node(STATE_GENERATING, generating)  # pyrefly: ignore[bad-argument-type]
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
