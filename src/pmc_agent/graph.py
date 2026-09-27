# Copyright 2026 PyMOL Copilot contributors.
"""The LangGraph request graph: states, the request's own typed shape.

docs/master_plan.md item 8 replaces the hardcoded fixture that used to sit
in `src/pmc_server/lifecycle.py` with this graph. The state space is
SPECIFICATION.md:417-426's own domain model, restated here as the graph's
node names:

```text
received -> preparing -> generating -> validating -> pending_approval
pending_approval -> applying | rejected | expired | superseded
applying -> applied | apply_failed_restored | rolled_back
any pre-apply state -> ask | failed | cancelled
```

`restoring` remains a client-side transient: recovery must not depend on a
network round trip. The server records the three terminal apply outcomes.

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

import uuid
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import TypedDict

from langgraph.graph import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.prompt import PROMPT_BUILDER
from pmc_agent.prompt import AttemptFailure
from pmc_agent.prompt import PromptInputs
from pmc_agent.prompt import build_default_prompt
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import STATUS_OK
from pmc_core.executor import DEFAULT_DEADLINE_SECONDS
from pmc_core.executor import DEFAULT_MAX_SNAPSHOT_BYTES
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import SelectionCount
from pmc_core.executor import bounded_failure
from pmc_core.executor import execute
from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.screen import SCREEN_HOSTILE
from pmc_core.screen import screen_completion
from pmc_core.snapshot import from_json

#: Non-terminal request states -- each one is also this graph's own node
#: name, so a status value and a node name are always the same string.
STATE_RECEIVED = "received"
STATE_PREPARING = "preparing"
STATE_GENERATING = "generating"
STATE_VALIDATING = "validating"
STATE_PENDING_APPROVAL = "pending_approval"
STATE_APPLYING = "applying"

#: Terminal states. Once a request carries one of these, the graph run
#: that produced it has ended -- see `route_by_status` below.
TERMINAL_REJECTED = "rejected"
TERMINAL_EXPIRED = "expired"
TERMINAL_SUPERSEDED = "superseded"
TERMINAL_FAILED = "failed"
TERMINAL_CANCELLED = "cancelled"
TERMINAL_ASK = "ask"
TERMINAL_APPLIED = "applied"
TERMINAL_APPLY_FAILED_RESTORED = "apply_failed_restored"
TERMINAL_ROLLED_BACK = "rolled_back"

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
        TERMINAL_APPLIED,
        TERMINAL_APPLY_FAILED_RESTORED,
        TERMINAL_ROLLED_BACK,
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
        STATE_APPLYING,
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

#: `preparing`'s own accepted contract manifest --
#: `pmc_core.protocol.CURRENT_CONTRACT_MANIFEST`, the one shared constant
#: `pmc_client.command.CONTRACT_MANIFEST` also declares on every request,
#: rather than a second, independently-typed literal that could silently
#: drift from it. See that constant's own docstring for why every field is
#: still the literal "1".
ACCEPTED_CONTRACT_MANIFEST = CURRENT_CONTRACT_MANIFEST

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

#: `generating`'s own failure category for a completion that stopped
#: before finishing -- `outcome.stop_reason` was something other than
#: `STOP_END` (a `max_tokens` truncation or a deadline cutoff, per
#: `pmc_agent.inference.base`'s own STOP_* constants). A completion that
#: stops early can still parse cleanly if the cut landed on a line
#: boundary, so this check has to run before the completion is ever
#: classified or handed to the parser -- accepting a truncated plan as
#: complete would mean validating and approving less than the model
#: actually intended.
FAILURE_ENGINE_INCOMPLETE = "engine_incomplete"

#: The owner of a compiled graph supplies a stable cancellation token for
#: each active session. Keeping the token out of `RequestState` matters:
#: state is checkpointed, whereas this is live, process-local coordination
#: that must disappear with the invocation rather than be serialized into
#: every checkpoint.
type CANCEL_TOKEN_SOURCE = Callable[[str], CancelToken]

#: `validating`'s own failure categories, for the infrastructure-level
#: executor outcomes that never enter the repair loop (see
#: `_build_validating`'s own docstring for why): every `execute()` reason
#: other than `pmc_core.executor.REASON_COMMAND_FAILURE`, prefixed so it
#: never collides with `pmc_core.errors.CATEGORIES` or the three names
#: above.
FAILURE_EXECUTION_PREFIX = "execution_"

#: `validating`'s own failure category once the repair budget is spent.
FAILURE_REPAIR_EXHAUSTED = "repair_exhausted"

#: `validating`'s own failure category for a completion the hostile screen
#: rejected before it was ever parsed. docs/master_plan.md item 11: a
#: hostile rejection and an ordinary user `copilot_reject` must be
#: distinguishable to the user, even though both leave `status` at
#: `TERMINAL_REJECTED` -- this category is carried in `state["failure"]`
#: alongside that terminal so `pmc_server.lifecycle` can tell the two
#: apart and report each honestly, instead of the one generic "request
#: ended: rejected" text every other `rejected` carries.
FAILURE_HOSTILE_OUTPUT = "hostile_output"


def _new_plan_id() -> str:
    """Return a new UUIDv4 plan identifier.

    Returns:
        A string containing a UUIDv4 identifier.
    """
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    """Return the current moment in UTC.

    Returns:
        A timezone-aware `datetime` in UTC.
    """
    return datetime.now(UTC)


def _format_timestamp(moment: datetime) -> str:
    """Format a moment in the protocol's own RFC3339 UTC wire form.

    The same format `pmc_server.lifecycle._server_timestamp` produces,
    reused here so `expires_at` and `created_at` are always directly
    comparable strings.

    Args:
        moment: The moment to format.

    Returns:
        The moment as `YYYY-MM-DDTHH:MM:SS.sssZ`.
    """
    return (
        moment.astimezone(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


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
        errors: Every failed attempt's evidence so far, oldest first, in
            `pmc_agent.prompt.AttemptFailure`'s uniform shape -- a parse
            rejection, a policy denial, and a real PyMOL command failure
            each have their own incompatible category vocabulary, and
            only a real command failure has a verb at all, which is what
            that type exists to paper over. What a repair prompt is built
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
        selection_counts: The sidecar's own per-selection atom counts from
            the attempt that validated
            (`pmc_core.executor.ExecutionReport.selection_counts`), empty
            before one has. docs/master_plan.md item 11: this is raw
            evidence, carried unchanged -- deriving a rendered warning from
            it is `pmc_agent.warnings.derive_warnings`'s job, done once the
            plan is actually reported, not here.
        sidecar_warnings: Bounded diagnostic text the executor itself
            already captured for the attempt that validated
            (`ExecutionReport.warnings`, such as non-fatal captured child
            stderr), empty before one has.
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
    errors: tuple[AttemptFailure, ...]
    plan: ActionPlan | None
    plan_id: str | None
    expires_at: str | None
    model_identity: str | None
    failure: FailureEnvelopeV1 | None
    question: str | None
    selection_counts: tuple[SelectionCount, ...]
    sidecar_warnings: tuple[str, ...]

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
        "failure": bounded_failure(category, message, retryable),
    }


def _cancelled(state: RequestState, *, attempt: int) -> dict[str, object]:
    """Build the terminal update for a request cancelled before approval.

    Args:
        state: The request state at the point cancellation was observed.
        attempt: The number of completion calls that have begun so far.

    Returns:
        A partial update ending the request at `TERMINAL_CANCELLED`.
    """
    return {
        "status": TERMINAL_CANCELLED,
        "history": (*state["history"], TERMINAL_CANCELLED),
        "attempt": attempt,
    }


def _new_cancel_token(_session_id: str) -> CancelToken:
    """Return an unshared cancellation token for a bare graph invocation.

    `RequestGraphSession` replaces this default with its own per-active-run
    lookup. The standalone graph tests intentionally need no such registry.

    Args:
        _session_id: Ignored; present to match `CANCEL_TOKEN_SOURCE`.

    Returns:
        A new, unset cancellation token.
    """
    return CancelToken()


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


def _sanitize_question(text: str, *, maximum: int = 200) -> str:
    """Bound a model's clarification question for safe display.

    Deliberately not `pmc_core.errors.normalize_message`: that pipeline
    lowercases its input and replaces every quoted span with a fixed
    redaction marker, both exactly right for a raw PyMOL exception message
    and exactly wrong for a clarifying question, which routinely quotes the
    very chain or residue names the user needs to read back
    (`Did you mean chain "A" or "B"?` must not become
    `did you mean chain "<redacted>" or "<redacted>"?`). This guarantees
    only the two properties `question` actually needs downstream: one
    printable-ASCII line, bounded in length.

    Args:
        text: The model's raw `ask:` question text.
        maximum: The greatest number of characters to keep.

    Returns:
        A single-line, printable-ASCII, length-bounded question.
    """
    collapsed = " ".join(text.split())
    printable = "".join(
        character if 0x20 <= ord(character) < 0x7F else "?"
        for character in collapsed
    )
    return _bounded(printable, maximum=maximum)


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
            "question": _sanitize_question(question),
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
    cancel_token_source: CANCEL_TOKEN_SOURCE,
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
        cancel_token_source: Finds the live cancellation token for this
            session's active graph invocation.

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
        cancel_token = cancel_token_source(state["session_id"])
        if cancel_token.is_cancelled():
            return _cancelled(state, attempt=state["attempt"])
        prompt = prompt_builder(
            PromptInputs(
                intent=state["intent"],
                snapshot=from_json(state["snapshot_json"]),
                contract_manifest=state["contract_manifest"],
                errors=state["errors"],
            )
        )
        outcome = engine.complete(
            CompletionRequest(
                prompt=prompt,
                grammar=None,
                max_tokens=max_tokens,
                deadline_seconds=deadline_seconds,
            ),
            cancel=cancel_token,
        )
        attempt = state["attempt"] + 1
        # Check the token even when the engine did not return
        # `STOP_CANCELLED`: adapters are cooperative and a cancellation can
        # race a normally completed response. Once the user cancelled, the
        # response must never continue to parsing, validation, or approval.
        if cancel_token.is_cancelled():
            return _cancelled(state, attempt=attempt)
        if isinstance(outcome, EngineFailure):
            failed = _failed(
                state,
                category=outcome.category,
                message=_bounded(outcome.message),
                # An engine failure says nothing about this request's own
                # intent or plan; a fresh request could plausibly succeed
                # where this one hit an unavailable or timed-out engine.
                retryable=True,
            )
            failed["attempt"] = attempt
            return failed
        if outcome.stop_reason != STOP_END:
            # A completion that stopped early can still parse as a
            # complete, valid plan if the cut landed on a line boundary --
            # this has to be checked before classification or parsing, or
            # a truncated plan would be silently validated and approved as
            # though it were whatever the model actually intended.
            failed = _failed(
                state,
                category=FAILURE_ENGINE_INCOMPLETE,
                message=_bounded(
                    "the engine stopped before finishing "
                    f"(stop_reason={outcome.stop_reason})"
                ),
                retryable=True,
            )
            failed["attempt"] = attempt
            return failed
        return _classify_completion(
            state,
            completion=outcome.text,
            # The engine's own stable identity, never the per-call
            # result's own claim: SPECIFICATION.md:541 requires this be
            # re-verified at approval, which only means something if this
            # graph never trusts a result to assert its own provenance in
            # the first place.
            model_identity=engine.model_identity,
            attempt=attempt,
        )

    return _generating


def _bounded(text: str, *, maximum: int = 200) -> str:
    """Bound a diagnostic string to a maximum character count.

    A cheap character-count bound, not `pmc_core.errors.normalize_message`
    -- what this function bounds is already a stable, short, machine-
    generated reason string from `pmc_core.parser` or `pmc_core.policy`,
    never raw PyMOL text, so none of that module's redaction machinery
    applies here.

    Args:
        text: The text to bound.
        maximum: The greatest number of characters to keep.

    Returns:
        `text` unchanged if within the bound, else truncated with a
        marker.
    """
    if len(text) <= maximum:
        return text
    return text[: maximum - len("...")] + "..."


def _build_validating(
    *,
    executor: Callable[[ExecutionRequest], ExecutionReport],
    policy_validator: Callable[[ActionPlan], PlanDecision],
    plan_id_source: Callable[[], str],
    clock: Callable[[], datetime],
    max_snapshot_bytes: int,
    deadline_seconds: float,
    ttl_seconds: float,
    max_repair_attempts: int,
    cancel_token_source: CANCEL_TOKEN_SOURCE,
) -> Callable[[RequestState], dict[str, object]]:
    """Close a `validating` node body over its injected executor and clock.

    Args:
        executor: Runs one `ExecutionRequest` in a fresh sidecar. A fake
            in every test in this item; `pmc_core.executor.execute` in
            production -- always a *fresh* one per call, per orchestration
            rule 8; this closure calls it at most once per attempt and
            never pools or reuses anything across calls.
        policy_validator: Independently re-checks a parsed plan. Defaults
            to `pmc_core.policy.evaluate_plan` in production, matching
            `pmc_server.lifecycle.PlanRequestLifecycle`'s own
            `policy_validator` seam exactly. Injectable for the same
            reason that one is: a plan the parser itself accepts can never
            reach a real policy denial (the two enforce the same
            allowlist, independently, over the same grammar), so the only
            way to prove this graph's own denial-handling path -- as
            opposed to the policy's, which `tests/contract/test_policy.py`
            already owns -- is to inject a validator that denies on
            purpose.
        plan_id_source: Mints a plan identifier on a successful attempt.
        clock: Reports the current moment, for `expires_at`. Both this and
            `plan_id_source` are called at most once per successful
            attempt, inside this node, never inside `pending_approval`
            (see the module docstring's finding about `interrupt`).
        max_snapshot_bytes: The snapshot size ceiling given to `executor`.
        deadline_seconds: The wall-clock deadline given to `executor`.
        ttl_seconds: How long a minted plan stays approvable.
        max_repair_attempts: SPECIFICATION.md:640's repair budget --
            `MAX_REPAIR_ATTEMPTS` by default, injectable only so a test can
            prove the bound is actually enforced by lowering or raising it.
        cancel_token_source: Finds the live cancellation token for this
            session's active graph invocation.

    Returns:
        The `validating` node body.
    """

    def _attempt_failed(
        state: RequestState,
        *,
        source: str,
        category: str,
        command_index: int | None,
        message: str,
    ) -> dict[str, object]:
        """Record one failed attempt and decide whether to repair or fail.

        Args:
            state: The request state entering this decision.
            source: "parse", "policy", or "execution".
            category: The stable category from that source's vocabulary.
            command_index: The command index the failure names, if any.
            message: A bounded, human-readable explanation.

        Returns:
            A partial update: back to `STATE_GENERATING` with the failure
            appended to `errors`, when the repair budget is not yet
            spent; otherwise `TERMINAL_FAILED`.
        """
        error = AttemptFailure(
            source=source,
            category=category,
            command_index=command_index,
            message=_bounded(message),
        )
        errors = (*state["errors"], error)
        if state["attempt"] <= max_repair_attempts:
            return {
                "status": STATE_GENERATING,
                "history": (*state["history"], STATE_GENERATING),
                "errors": errors,
            }
        failed = _failed(
            state,
            category=FAILURE_REPAIR_EXHAUSTED,
            message="the repair budget was spent with no validated plan",
            # The user's intent may still be achievable; a fresh request
            # with a clearer intent is not ruled out by this outcome.
            retryable=True,
        )
        failed["errors"] = errors
        return failed

    def _validating(state: RequestState) -> dict[str, object]:
        """Parse, screen, police, and execute one attempt.

        Orchestration rules 7 and 8, in the fixed order both require:
        parse, screen the raw text for a hostile marker regardless of
        parse outcome, re-check policy independently of the parser, then
        execute in a fresh sidecar -- never reordered, and never skipped
        because an earlier step looked like it already covered the same
        ground.

        Args:
            state: The request state entering `validating`. `completion`
                and `attempt` are always set by the time this runs --
                `generating` is `validating`'s only predecessor and always
                writes both before advancing here.

        Returns:
            A partial update: to `TERMINAL_REJECTED` immediately on a
            hostile completion, with zero repairs; back to
            `STATE_GENERATING` on an ordinary, repairable failure within
            budget; to `TERMINAL_FAILED` once the budget is spent or on an
            infrastructure-level executor failure no repair could fix; or
            to `STATE_PENDING_APPROVAL` with `plan`, `plan_id`, and
            `expires_at` all committed, on success.
        """
        cancel_token = cancel_token_source(state["session_id"])
        if cancel_token.is_cancelled():
            return _cancelled(state, attempt=state["attempt"])

        completion = state["completion"]
        assert completion is not None, (
            "validating always follows generating, which always sets "
            "completion before advancing here"
        )

        if screen_completion(completion) == SCREEN_HOSTILE:
            return {
                "status": TERMINAL_REJECTED,
                "history": (*state["history"], TERMINAL_REJECTED),
                "failure": bounded_failure(
                    FAILURE_HOSTILE_OUTPUT,
                    "the model produced a forbidden command form; "
                    "nothing was run",
                    False,
                ),
            }

        parsed = parse_pml(completion)
        if isinstance(parsed, ParseRejection):
            return _attempt_failed(
                state,
                source="parse",
                category=parsed.category,
                command_index=parsed.command_index,
                message=parsed.message,
            )
        plan = parsed

        decision = policy_validator(plan)
        if not decision.allowed:
            # pmc_core.policy.PlanDecision's own docstring: `allowed` is
            # False either when some per-operation decision denies, or
            # when the plan shape itself is outside the accepted form --
            # the latter can leave `decisions` with no denied entry at
            # all (or even empty), so this must not assume one exists.
            denied = next(
                (d for d in decision.decisions if not d.allowed), None
            )
            return _attempt_failed(
                state,
                source="policy",
                category="policy_denied",
                command_index=(
                    denied.operation_index if denied is not None else None
                ),
                message=(
                    denied.reason
                    if denied is not None
                    else "plan was denied by server policy"
                ),
            )

        report = executor(
            ExecutionRequest(
                executor_version=EXECUTOR_VERSION,
                plan=plan,
                snapshot_json=state["snapshot_json"],
                expected_snapshot_digest=state["snapshot_identity"].digest,
                max_snapshot_bytes=max_snapshot_bytes,
                deadline_seconds=deadline_seconds,
            )
        )
        # Validation itself is safe and side-effect free, but it may take
        # long enough that a user cancels while the fresh sidecar runs. Do
        # not mint or park a plan after that cancellation.
        if cancel_token.is_cancelled():
            return _cancelled(state, attempt=state["attempt"])
        if report.status == STATUS_OK:
            now = clock()
            return {
                "status": STATE_PENDING_APPROVAL,
                "history": (*state["history"], STATE_PENDING_APPROVAL),
                "plan": plan,
                "plan_id": plan_id_source(),
                "expires_at": _format_timestamp(
                    now + timedelta(seconds=ttl_seconds)
                ),
                # docs/master_plan.md item 11: raw evidence only, carried
                # unchanged from the sidecar that actually ran the parsed
                # plan -- never from `completion` itself. See
                # `pmc_agent.warnings.derive_warnings`'s own docstring for
                # why that purity matters.
                "selection_counts": report.selection_counts,
                "sidecar_warnings": report.warnings,
            }
        if report.reason == REASON_COMMAND_FAILURE:
            failing = next(
                (
                    outcome
                    for outcome in report.command_outcomes
                    if outcome.status == OUTCOME_ERROR
                ),
                None,
            )
            envelope = failing.error_envelope if failing else None
            if envelope is not None:
                category = envelope.category
                command_index = envelope.command_index
                message = envelope.message
            else:
                # A defect in this graph's own dispatch, never a real
                # PyMOL failure -- see pmc_sidecar.child's own
                # "__unsupported__" sentinel, the one command_failure case
                # ExecutionErrorV1 refuses to normalize.
                category = "unknown"
                command_index = failing.index if failing else None
                message = (
                    failing.error
                    if failing and failing.error
                    else "command failed with no further detail"
                )
            return _attempt_failed(
                state,
                source="execution",
                category=category,
                command_index=command_index,
                message=message,
            )
        # Every other executor reason -- oversized input, a malformed or
        # mismatched snapshot, a spawn failure, a timeout, a child crash,
        # or a fidelity mismatch -- is an infrastructure-level problem a
        # repaired completion cannot fix: SPECIFICATION.md's own failure-
        # mode table calls exactly this out for a sidecar timeout ("repairs
        # stop"), and the same reasoning applies to every reason in this
        # branch. None of them consumes a repair attempt.
        return _failed(
            state,
            category=f"{FAILURE_EXECUTION_PREFIX}{report.reason}",
            message=f"sidecar execution failed: {report.reason}",
            retryable=True,
        )

    return _validating


#: `pending_approval`'s resume contract: `pmc_agent.session.
#: RequestGraphSession` resumes the parked thread with exactly
#: `{"action": <one of these values>}`, and this node maps that value to
#: the terminal status it ends the request at. Kept as plain string
#: constants, not something richer shared between the two modules, because
#: `pmc_agent.session` imports this module and not the reverse -- these
#: three strings are the whole of that contract.
RESUME_ACTION_REJECT = "reject"
RESUME_ACTION_CANCEL = "cancel"
RESUME_ACTION_SUPERSEDE = "supersede"
RESUME_ACTION_APPROVE = "approve"

_RESUME_ACTION_TERMINALS: dict[str, str] = {
    RESUME_ACTION_REJECT: TERMINAL_REJECTED,
    RESUME_ACTION_CANCEL: TERMINAL_CANCELLED,
    RESUME_ACTION_SUPERSEDE: TERMINAL_SUPERSEDED,
}

_APPLY_OUTCOME_TERMINALS: dict[str, str] = {
    "applied": TERMINAL_APPLIED,
    "restored": TERMINAL_APPLY_FAILED_RESTORED,
    "rolled_back": TERMINAL_ROLLED_BACK,
}


def _parse_timestamp(text: str) -> datetime:
    """Parse the protocol's own RFC3339 UTC wire form.

    The exact inverse of `_format_timestamp`.

    Args:
        text: A timestamp in `YYYY-MM-DDTHH:MM:SS.sssZ` form.

    Returns:
        The parsed, timezone-aware `datetime`.
    """
    return datetime.fromisoformat(text[:-1] + "+00:00")


def _build_pending_approval(
    *, clock: Callable[[], datetime]
) -> Callable[[RequestState], dict[str, object]]:
    """Close a `pending_approval` node body over its injected clock.

    Args:
        clock: Reports the current moment, checked fresh on every resume
            against `state["expires_at"]`. Unlike `plan_id` and
            `expires_at` themselves, checking the *current* moment against
            an already-fixed expiry on every re-entry is exactly what
            expiry requires, and carries none of the module docstring's
            re-minting hazard: nothing this call reads from `clock()` is
            ever written into a value the model or a user saw before this
            call.

    Returns:
        The `pending_approval` node body.
    """

    def _pending_approval(state: RequestState) -> dict[str, object]:
        """Park for approval; resolve whatever resumes it.

        Expiry is checked before the resume value is honored
        (SPECIFICATION.md:432-435): a reject, cancel, or supersede
        arriving after `expires_at` has passed reports `expired`, not the
        action that was actually requested -- the plan was already
        invalid by the time it arrived, regardless of which action asked.

        Args:
            state: The request state entering `pending_approval`.
                `plan_id` and `expires_at` were already committed by
                `validating`'s own success path (see the module
                docstring); this call mints nothing.

        Returns:
            A partial update to `TERMINAL_EXPIRED`, `TERMINAL_REJECTED`,
            `TERMINAL_CANCELLED`, or `TERMINAL_SUPERSEDED`, once resumed
            with a recognized action; to `TERMINAL_FAILED` if resumed with
            anything else, since an unrecognized resume value is this
            graph's own defect to surface, never a state to guess past.
        """
        resume_value = interrupt(
            {"plan_id": state["plan_id"], "expires_at": state["expires_at"]}
        )
        expires_at = state["expires_at"]
        if expires_at is not None and clock() >= _parse_timestamp(expires_at):
            return {
                "status": TERMINAL_EXPIRED,
                "history": (*state["history"], TERMINAL_EXPIRED),
            }
        action = (
            resume_value.get("action")
            if isinstance(resume_value, dict)
            else None
        )
        terminal = (
            _RESUME_ACTION_TERMINALS.get(action)
            if isinstance(action, str)
            else None
        )
        if terminal is None:
            if action == RESUME_ACTION_APPROVE:
                return {
                    "status": STATE_APPLYING,
                    "history": (*state["history"], STATE_APPLYING),
                    # Carry every approval fact explicitly across the second
                    # interrupt. LangGraph otherwise serializes this node's
                    # partial update without the immutable pending payload.
                    "plan": state["plan"],
                    "plan_id": state["plan_id"],
                    "expires_at": state["expires_at"],
                    "model_identity": state["model_identity"],
                }
            return _failed(
                state,
                category="unrecognized_resume",
                message="pending_approval was resumed with an "
                "unrecognized action",
                retryable=True,
            )
        return {
            "status": terminal,
            "history": (*state["history"], terminal),
        }

    return _pending_approval


def _applying(state: RequestState) -> dict[str, object]:
    """Park until the client reports the sole terminal apply outcome."""
    resume_value = interrupt({"plan_id": state["plan_id"]})
    outcome = (
        resume_value.get("outcome") if isinstance(resume_value, dict) else None
    )
    terminal = (
        _APPLY_OUTCOME_TERMINALS.get(outcome)
        if isinstance(outcome, str)
        else None
    )
    if terminal is None:
        return _failed(
            state,
            category="unrecognized_apply_outcome",
            message="applying was resumed with an unrecognized outcome",
            retryable=True,
        )
    return {"status": terminal, "history": (*state["history"], terminal)}


def build_request_graph(
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
    cancel_token_source: CANCEL_TOKEN_SOURCE = _new_cancel_token,
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
        executor: Runs one `ExecutionRequest` in a fresh sidecar. Defaults
            to `pmc_core.executor.execute`; every test in this item injects
            a fake so no real PyMOL process is ever spawned by a graph
            test.
        policy_validator: Independently re-checks a parsed plan. Defaults
            to `pmc_core.policy.evaluate_plan`; see `_build_validating`'s
            own docstring for why this seam exists at all.
        plan_id_source: Mints a plan identifier on a successful attempt.
            Defaults to a real UUIDv4 source.
        clock: Reports the current moment for computing `expires_at`.
            Defaults to the real wall clock, in UTC.
        max_snapshot_bytes: The snapshot size ceiling given to `executor`.
        validation_deadline_seconds: The wall-clock deadline given to
            `executor`. Independent of `deadline_seconds`, which bounds
            the engine, not a spawned process.
        ttl_seconds: How long a minted plan stays approvable.
        max_repair_attempts: SPECIFICATION.md:640's repair budget.
        cancel_token_source: Finds the live cancellation token for one
            session. Defaults to independent unset tokens for callers that
            use a bare graph; `RequestGraphSession` supplies tokens that a
            concurrent `/v1/cancel` can signal.

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
        cancel_token_source=cancel_token_source,
    )
    validating = _build_validating(
        executor=executor,
        policy_validator=policy_validator,
        plan_id_source=plan_id_source,
        clock=clock,
        max_snapshot_bytes=max_snapshot_bytes,
        deadline_seconds=validation_deadline_seconds,
        ttl_seconds=ttl_seconds,
        max_repair_attempts=max_repair_attempts,
        cancel_token_source=cancel_token_source,
    )
    pending_approval = _build_pending_approval(clock=clock)
    graph.add_node(STATE_PREPARING, _preparing)
    graph.add_node(STATE_GENERATING, generating)  # pyrefly: ignore[bad-argument-type]
    graph.add_node(STATE_VALIDATING, validating)  # pyrefly: ignore[bad-argument-type]
    graph.add_node(STATE_PENDING_APPROVAL, pending_approval)  # pyrefly: ignore[bad-argument-type]
    graph.add_node(STATE_APPLYING, _applying)

    graph.set_entry_point(STATE_PREPARING)
    for name in (
        STATE_PREPARING,
        STATE_GENERATING,
        STATE_VALIDATING,
        STATE_PENDING_APPROVAL,
        STATE_APPLYING,
    ):
        graph.add_conditional_edges(name, route_by_status)

    return graph
