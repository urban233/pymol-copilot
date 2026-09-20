# LangGraph request graph

## Context

This is item 8 of
[docs/master_plan.md:376-391](docs/master_plan.md#L376-L391), Hannah's, sized
at ~4 days. It is the item that turns the server from a fixture responder
into the thing the specification actually describes: a bounded state machine
that owns a request from arrival to approval, and refuses to let model output
touch anything that decides authority.

Today [src/pmc_server/lifecycle.py](src/pmc_server/lifecycle.py) is 208 lines
with no states in it at all. `PlanRequestLifecycle.__call__`
([lifecycle.py:114-164](src/pmc_server/lifecycle.py#L114-L164)) pattern-matches
one exact request shape and answers with one module-level constant:

```python
FIXTURE_INTENT = "Select chain A and color it red."
FIXTURE_PLAN = ActionPlan(operations=(SelectOperation(...), ColorOperation(...)))
```

It never calls a model, never spawns a sidecar, holds no per-session state,
and its own comments say twice that item 8 deletes it
([lifecycle.py:32-36](src/pmc_server/lifecycle.py#L32-L36),
[:48-57](src/pmc_server/lifecycle.py#L48-L57)). The only graph in the
repository is [src/pmc_agent/runtime.py](src/pmc_agent/runtime.py) — a
one-node pass-through compiled purely to prove the LangGraph dependency
links.

The prerequisites this item was blocked on have all landed on `main`:

- **Item 4**, [`pmc_core.executor`](src/pmc_core/executor.py) — the
  fresh-process boundary. `execute()` with finite input size, finite
  deadline, SIGTERM→SIGKILL escalation, reap, scratch cleanup, twelve typed
  `REASON_*` outcomes and an explicit *no internal retry* guarantee.
- **Item 6**, [`pmc_core.errors`](src/pmc_core/errors.py) — `ExecutionErrorV1`
  ([:424](src/pmc_core/errors.py#L424)) and the total `normalize()`
  ([:559](src/pmc_core/errors.py#L559)), proven byte-equal against a captured
  real-PyMOL corpus. Its docstring names this item explicitly: *"There is no
  decoder: putting an envelope on the wire is item 8's contract, not this
  module's."*
- **Item 7**, [`pmc_client.fidelity`](src/pmc_client/fidelity.py) and
  [`pmc_client.session`](src/pmc_client/session.py) — real per-session
  snapshots, a real digest, and the fidelity gate feeding
  `ValidationReportV1.applicable`.
- **Item 5**, [`pmc_core.card`](src/pmc_core/card.py) with `CARD_VERSION`.

What is missing is every state between them.

### What the specification requires

[SPECIFICATION.md:417-426](SPECIFICATION.md#L417-L426) — the state space this
item owns (everything from `applying` rightward is item 10's):

> ```text
> received -> preparing -> generating -> validating -> pending_approval
> pending_approval -> rejected | expired | superseded
> any pre-apply state -> ask | failed | cancelled
> ```

[SPECIFICATION.md:409-411](SPECIFICATION.md#L409-L411), the pending plan:

> A validated plan tied to a plan identifier, session identity,
> relevant-state digest, contract versions, and expiration. **At most one
> exists per session.**

[SPECIFICATION.md:432-435](SPECIFICATION.md#L432-L435):

> A pending plan becomes invalid when the session digest changes, its
> contracts or model identity no longer match, the server restarts, its
> expiry is reached, or another request supersedes it.

[SPECIFICATION.md:524-538](SPECIFICATION.md#L524-L538), orchestration rules
2, 3, 5, 6, 7 and 8 — one active request per session; preparation resolves
one target object; the card and grammar are computed once and stay immutable
for the request; clarification and no-op output are classified *before* plan
parsing; parsing and policy run before every execution attempt; denied
commands get at most one repair and hostile classes none; **validation uses a
fresh sidecar per attempt**, one initial generation plus at most two repairs.

[SPECIFICATION.md:551-552](SPECIFICATION.md#L551-L552) is the invariant the
whole item is built to make provable:

> No model output determines authority, retries, target object, network
> destination, policy, approval, or rollback behavior.

[SPECIFICATION.md:710](SPECIFICATION.md#L710) names the evidence owed: *"unit
tests for state transitions, identifiers, expiry, normalization, policy, and
configuration invariants"*.

**Outcome:** a request arrives, the graph resolves one target object, builds
a prompt, calls a bounded local engine, classifies the output, parses it,
screens it, policy-checks it, validates it in a fresh sidecar, and either
parks it at `pending_approval` with an expiry or lands it in one of six
terminal states. A second request on the same session supersedes the first.
`copilot_reject` reaches `rejected`. Nothing the model emits changes the
attempt count, the target object, the policy verdict or the approval flag.

### Decisions taken (from the clarifying questions)

- **The snapshot's bytes now ride `/v1/plan`.** Plan 06 deliberately kept
  `/v1/plan` at `MAX_MESSAGE_BYTES` (64 KiB) and sent identity only, noting
  the full canonical JSON would travel *"over `/v1/validate` when item 8
  wires server-side plan validation"*. It does not: the graph lives in the
  server, so the bytes must arrive with the request that triggers it.
  `PlanRequestV1` gains `snapshotJson`, and `PLAN_PATH`'s body cap rises to
  `MAX_EXECUTION_REQUEST_BYTES`
  ([src/pmc_server/transport.py:38](src/pmc_server/transport.py#L38)), which
  already exists for `/v1/validate` and is sized at
  `2 * DEFAULT_MAX_SNAPSHOT_BYTES + MAX_MESSAGE_BYTES`. The bytes cross one
  socket, once. `/v1/validate` and `PlanValidationService` stay as they are
  and keep their tests — they are no longer on the production path, and that
  is recorded rather than deleted, because item 12 drives them directly.

- **Item 8 adds `/v1/reject`, `/v1/cancel` *and* the `copilot_reject`
  client command.** master_plan lists `copilot_reject` under item 10, but a
  terminal state nothing can reach is a terminal state nothing tests, and
  `rejected` and `cancelled` are both in this item's brief. Item 10 keeps
  `copilot_apply`'s real body and `copilot_rollback` entirely; it inherits a
  working rejection path rather than building one.

- **The error envelope is built in the sidecar child, at the catch site.**
  [src/pmc_sidecar/child.py:166](src/pmc_sidecar/child.py#L166) currently
  does `bounded_diagnostic(str(error), maximum_bytes=128)` and throws the
  exception away. That is the only place in the system holding a live PyMOL
  exception, and [SPECIFICATION.md:489](SPECIFICATION.md#L489) requires
  *"same normalization and placement in development and runtime"*.
  `normalize()` is called there, and `CommandOutcome` / `CommandOutcomeV1`
  gain the envelope. Re-normalizing the flattened string in the graph was
  rejected: the exception type is gone by then, `CLASSIFICATION_RULES`
  ([errors.py:167](src/pmc_core/errors.py#L167)) supports type-keyed rules,
  and the 128-byte truncation would happen before normalization rather than
  after.

- **State lives in a LangGraph checkpointer, `session_id` as `thread_id`.**
  `InMemorySaver` from `langgraph.checkpoint.memory`, `interrupt()` at
  `pending_approval`, resumed with `Command(resume=...)`. One thread per
  session *is* the "at most one active request and one pending plan per
  session" invariant — it is structural, not a rule enforced by a separate
  registry that could drift from the graph. Server restart clears everything,
  which [SPECIFICATION.md:433](SPECIFICATION.md#L433) already names as a
  pending-plan invalidation condition.

- **A hostile screen is added to `pmc_core`.** Orchestration rule 7 gives
  ordinary denials one repair and hostile classes none, and the parser cannot
  currently tell them apart:
  [tests/adversarial/test_denied_forms.py:104-131](tests/adversarial/test_denied_forms.py#L104-L131)
  shows `__import__(os)`, `eval(1+1)`, `$(id)`, `../../etc/passwd`,
  `http://example.com/x.pdb` and `chain A; rm -rf /` **all** rejected as
  `invalid_selection_expression` — the same category as an ordinary grammar
  typo. Filing that one category either way is wrong half the time, so
  repair eligibility gets its own default-deny screen with the existing
  adversarial corpus as its fixture.

- **`src/pmc_agent/inference/` is created in this item**, with the typed
  engine Protocol and the fake adapter. Item 9 adds `lemonade.py` and startup
  capability probing only. The interface is designed against a real consumer
  rather than in the abstract.

### Decisions I took, stated so you can overrule them

- **The engine returns text, and the graph writes exactly one key from it.**
  This is how "no model output may influence retry count, target object,
  policy or approval" becomes structural rather than aspirational. The
  `generating` node's return value is `{"completion": <str>}` and nothing
  else; `attempt`, `target_object`, `plan_id`, `expires_at`, the policy
  decision and `applicable` are written by other nodes from inputs the engine
  never touches. Step 11 is a suite that proves it with a *hostile* fake
  adapter — one that emits state-shaped JSON, extra `.pml` lines, and text
  claiming a higher retry budget — and asserts those fields are unchanged.

- **The prompt builder is a seam, not an implementation.** Item 13
  ([docs/master_plan.md:465-475](docs/master_plan.md#L465-L475)) is Martin's
  and owns the real prompt and the emitted grammar. This item defines
  `PROMPT_BUILDER = Callable[[PromptInputs], str]` with a minimal default
  that stamps `CARD_VERSION`, `POLICY_VERSION` and the intent, and a comment
  naming item 13 as its replacement. The graph passes `grammar=None` to the
  engine until item 13 emits one. Designing Martin's prompt for him here
  would be work he deletes.

- **`ask` is classified by deterministic code from a declared marker.** The
  prompt contract says a clarification is a single line `ask: <question>`
  and a no-op is empty output. The classifier is ours; only *whether* the
  model emitted the marker is the model's, which rule 6 explicitly allows
  (it is not retry count, target, policy or approval). The question text is
  bounded and redacted through `errors.normalize_message()` before it
  reaches a user.

- **Expiry is lazy, not a timer.** `PLAN_TTL_SECONDS = 300.0`, checked
  whenever the thread is touched — a reject, a cancel, a supersede, or item
  10's approve. A single-user loopback server with one thread per session
  does not need a reaper, and a background thread mutating checkpointed
  state is a concurrency hazard for no gain. The clock is injected, as every
  other source in this repository is.

- **One `threading.Lock` per session.** `LoopbackPlanServer` is a
  `ThreadingHTTPServer`, so two requests for one session can genuinely race
  into the same thread. The lock is held for the whole graph invocation, so
  "at most one active request" is true rather than nearly true. Requests for
  *different* sessions stay concurrent.

- **The graph calls `pmc_core.executor.execute()` directly, through an
  injectable seam**, exactly as
  [PlanValidationService](src/pmc_server/validation.py#L77) does — not over
  HTTP to `/v1/validate`. `//src/pmc_agent:pmc_agent` keeps
  `//src/pmc_sidecar:pmc_sidecar` in its forbidden set
  ([tools/bazel/check_dependency_boundaries.py:36](tools/bazel/check_dependency_boundaries.py#L36));
  the sidecar reaches the runfiles through `//src/pmc_server`'s existing
  dependency, and the graph only ever names a runner module.

- **Terminal states are recorded, not just reached.** The graph state carries
  a bounded `history: tuple[str, ...]` of every state entered. Without it,
  `superseded` is unobservable — the thread has already moved on to the new
  request by the time a test can look. This is also what
  [SPECIFICATION.md:688](SPECIFICATION.md#L688) wants for diagnostics.

- **No pyproject change is needed.** `src/pmc_agent` is already in pyrefly's
  `project-includes` ([pyproject.toml:112](pyproject.toml#L112)), so
  everything added here is strict-checked from the first commit. The
  `# pyrefly: ignore[bad-specialization]` already on
  [runtime.py](src/pmc_agent/runtime.py) is the known friction with
  langgraph's structural `StateT` bound and will be needed again.

---

## Delivery: one branch, one PR

`origin/main` is at `80b4e7c` and already contains items 4, 5, 6 and 7 —
the master plan's status table
([docs/master_plan.md:87-108](docs/master_plan.md#L87-L108)) is stale and
still shows 4 and 6 as `ready` and 7 as `blocked`. Branch from an updated
`main`:

```text
git checkout main && git pull --ff-only
git checkout -b feat/langgraph-request-graph
```

Steps 1–12 ship together; they are not independently mergeable. Step 3
changes a wire type item 4 shipped, step 9 deletes the handler steps 5–8
replace, and step 10 rewrites client output step 11 asserts. One commit per
step, in order. Link the PR to an issue per
[CONTRIBUTING.md](CONTRIBUTING.md).

Note [.github/CODEOWNERS](.github/CODEOWNERS): every `**/BUILD.bazel` is
`@urban233`, so steps 1 and 2 pull Martin in as a required reviewer. Step 3
touches `src/pmc_core/errors.py`'s consumers and step 5 adds a `pmc_core`
module — tell Martin before step 3 lands, since item 6 is his and item 11
reads the envelope he defined.

---

## Step 1 — Wire the gates before writing any graph code

**Files**

- `plans/07-langgraph-request-graph.md` (new) — this document, verbatim.
- [src/pmc_server/BUILD.bazel](src/pmc_server/BUILD.bazel) — add
  `"//src/pmc_agent:pmc_agent"` to `deps`, with a comment: the server owns
  the request graph's lifetime, the graph owns the states.
- [src/pmc_agent/BUILD.bazel](src/pmc_agent/BUILD.bazel) — add
  `"@pypi//langgraph_checkpoint"` to `deps` (it is a transitive dependency of
  `@pypi//langgraph` today; the checkpointer becomes a direct import, so the
  edge should be direct), and widen `visibility` to `//src:subsystems`.
- [tools/bazel/check_dependency_boundaries.py:34-59](tools/bazel/check_dependency_boundaries.py#L34-L59)
  — no new root, but confirm `//src/pmc_client:pmc_client`'s forbidden set
  still excludes `//src/pmc_agent:pmc_agent` and its names still include
  `"langgraph"`. The client runs inside PyMOL's interpreter; this step is
  where that is re-proven, before `pmc_server` acquires langgraph.

Do this first and alone. `pmc_server` gaining langgraph is the one edge in
this item that could quietly reach somewhere it must not.

**Test that proves it**

```text
bazel build //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel query 'deps(//src/pmc_client:pmc_client)' | grep -E 'langgraph|pmc_agent'   # expect no output
bazel query 'deps(//src/pmc_core:pmc_core)'   | grep -E 'langgraph|pmc_agent'     # expect no output
bazel query 'deps(//src/pmc_server:pmc_server)' | grep langgraph                  # expect a hit
```

The two empty greps are the load-bearing assertions; the third confirms the
edge was actually added rather than silently dropped.

---

## Step 2 — `src/pmc_agent/inference/`: the engine seam and the fake

**Files**

- `src/pmc_agent/inference/__init__.py` (new).
- `src/pmc_agent/inference/base.py` (new) — the Protocol and its typed
  values.
- `src/pmc_agent/inference/fake.py` (new) — the test adapter.
- `src/pmc_agent/inference/BUILD.bazel` (new).
- `tests/unit/test_inference_fake.py` (new), `tests/unit/BUILD.bazel`.

The interface is the one
[docs/master_plan.md:397-400](docs/master_plan.md#L397-L400) describes —
bounded completion taking prompt, optional grammar, token limit, time limit,
cancellation and model identity — and it is **total**, in this repository's
house style: a typed failure value, never an exception.

```text
@dataclass(frozen=True)
class CompletionRequest:
    prompt: str
    grammar: str | None
    max_tokens: int
    deadline_seconds: float

@dataclass(frozen=True)
class CompletionResult:
    text: str
    model_identity: str
    stop_reason: str        # STOP_END | STOP_LENGTH | STOP_DEADLINE | STOP_CANCELLED

@dataclass(frozen=True)
class EngineFailure:
    category: str           # ENGINE_UNAVAILABLE | ENGINE_TIMEOUT | ENGINE_REFUSED_GRAMMAR | ENGINE_UNKNOWN
    message: str            # bounded through errors.normalize_message()

class InferenceEngine(Protocol):
    @property
    def model_identity(self) -> str: ...
    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure: ...
```

`ENGINE_REFUSED_GRAMMAR` exists now, unused, because item 9's brief requires
treating silently-ignored grammar as a hard engine failure and the graph
needs somewhere to route it. `CancelToken` is a minimal
`threading.Event`-backed object; the Lemonade spike found cancellation is
only partial
([tests/discovery/lemonade/FINDINGS.md](tests/discovery/lemonade/FINDINGS.md)),
so the token is advisory and the deadline is the real bound.

`FakeEngine` takes a scripted sequence of `CompletionResult | EngineFailure`,
returns them in order, raises `AssertionError` if called more times than
scripted, and exposes `calls: tuple[CompletionRequest, ...]` so a test can
assert *exactly* how many engine calls a path made and what each prompt
contained.

**Test that proves it**

```text
bazel test //tests/unit:inference_fake --lockfile_mode=error
```

Asserts: the fake returns its script in order; it records every request; a
call past the end of the script fails loudly rather than returning a
plausible default; and `EngineFailure.message` is bounded and printable for
a deliberately over-long, control-character-laden input.

---

## Step 3 — The error envelope crosses the process boundary

**Files**

- [src/pmc_sidecar/child.py:160-181](src/pmc_sidecar/child.py#L160-L181) —
  call `errors.normalize()` at the catch site.
- [src/pmc_core/executor.py:165-181](src/pmc_core/executor.py#L165-L181) —
  `CommandOutcome` gains `error_envelope: ExecutionErrorV1 | None`.
- [src/pmc_core/protocol.py:1022](src/pmc_core/protocol.py#L1022) —
  `CommandOutcomeV1` gains the same field, plus its encoder and the
  envelope's first decoder.
- [src/pmc_server/validation.py:63-71](src/pmc_server/validation.py#L63-L71)
  — carry the new field through `_to_wire_report`.
- [tests/contract/test_executor.py](tests/contract/test_executor.py),
  [tests/contract/test_protocol.py](tests/contract/test_protocol.py),
  [tests/integration/test_sidecar_child.py](tests/integration/test_sidecar_child.py)
  — extend.

`ExecutionErrorV1` is written to be decoded here for the first time:
`errors.py` provides `to_dict()` and says so explicitly. The decoder belongs
in `protocol.py` beside every other `from_dict`, and must reuse
`_strict_object` so an envelope with an unexpected field is rejected exactly
as every other wire type is.

Two details that will bite:

1. **`verb` may be `"__unsupported__"`.**
   [child.py:167](src/pmc_sidecar/child.py#L167) uses that sentinel when
   `_dispatch` cannot recognize an operation type, and
   `ExecutionErrorV1.__post_init__` rejects any verb outside
   `COMMAND_ALLOWLIST` — `normalize()` would raise, inside an except block,
   losing the original failure. The envelope is therefore `None` for that
   case and the existing bounded string stays. That path is a defect in our
   own dispatch, not a PyMOL error, and it must not be repairable.
2. **Two different bounds.** `MAX_COMMAND_ERROR_BYTES` is 128
   ([executor.py:104](src/pmc_core/executor.py#L104));
   `errors.MAX_MESSAGE_BYTES` is 256
   ([errors.py:65](src/pmc_core/errors.py#L65)). Keep both: the string field
   keeps its own bound for backward compatibility and the envelope keeps its
   own. Do **not** normalize the already-truncated string — normalize the
   exception, independently.

`error_envelope` is optional on both types, so the existing round-trip
fixtures stay valid and this is an additive wire change within protocol
version 1.

**Test that proves it**

```text
bazel test //tests/contract:executor //tests/contract:protocol --lockfile_mode=error
bazel test //tests/integration:sidecar_child --lockfile_mode=error
```

Asserts: a real PyMOL `color bogus_color, x` failure in the child produces
`CommandOutcome.error_envelope` with `category == "unknown_color"`, the right
`command_index` and `verb`, matching the checked-in corpus in
[tests/contract/testdata/pymol_errors/color.json](tests/contract/testdata/pymol_errors/color.json)
byte for byte; the envelope survives `to_dict`/`from_dict` unchanged; a
decode with an extra or missing field is rejected; an outcome with no
envelope still decodes; and the `"__unsupported__"` path yields
`error_envelope is None` with the bounded string intact.

---

## Step 4 — The hostile screen

**Files**

- `src/pmc_core/screen.py` (new).
- [src/pmc_core/BUILD.bazel](src/pmc_core/BUILD.bazel) — add the module.
- `tests/adversarial/test_hostile_screen.py` (new),
  [tests/adversarial/BUILD.bazel](tests/adversarial/BUILD.bazel).

One pure function, no PyMOL import, no I/O:

```text
SCREEN_ORDINARY = "ordinary"
SCREEN_HOSTILE  = "hostile"

def screen_completion(text: str) -> str:
```

Default-deny in spirit but narrow in effect: it does not decide whether text
is *acceptable* — the parser and policy already do that, totally — it decides
only whether a **rejected** completion may be repaired. It returns
`SCREEN_HOSTILE` when the raw text contains a path or URL form, a shell
metacharacter, a Python call or attribute form, or a null byte, and
`SCREEN_ORDINARY` otherwise.

The corpus is already written.
[tests/adversarial/test_denied_forms.py:72-165](tests/adversarial/test_denied_forms.py#L72-L165)
holds three tables — `UNKNOWN_VERB_FORMS`, `DENIED_EXPRESSION_FORMS` and
`LEXICALLY_DENIED_FORMS` — and this step imports them rather than retyping
them, so the two suites cannot drift.

The screen is deliberately allowed false positives and no false negatives:
misfiling an ordinary typo as hostile costs one repair attempt, misfiling
`$(id)` as ordinary hands the model another turn to try again. State that in
the module docstring, because it is the reason the function is not
symmetric.

**Test that proves it**

```text
bazel test //tests/adversarial:hostile_screen --lockfile_mode=error
```

Asserts: every entry in `DENIED_EXPRESSION_FORMS` and
`LEXICALLY_DENIED_FORMS` screens `SCREEN_HOSTILE`; every valid `.pml` round-
trip case from [tests/contract/test_parser.py](tests/contract/test_parser.py)
screens `SCREEN_ORDINARY`; and a representative set of *ordinary* mistakes
(`color reddd, chain A`, `select copilot_a, chain`, `orient chain`) screens
`SCREEN_ORDINARY`, since those are precisely what repair exists for. The
third group is the one that can silently regress to "everything is hostile"
and quietly disable repair altogether.

---

## Step 5 — The graph's state, its transitions, and nothing else

**Files**

- `src/pmc_agent/graph.py` (new) — state, constants, edges, compile.
- [src/pmc_agent/BUILD.bazel](src/pmc_agent/BUILD.bazel) — add the module.
- `tests/unit/test_request_graph_transitions.py` (new).

Build the whole shape with trivial node bodies first, and test every edge
before any node does real work. The transition table is the deliverable of
this item; the node bodies are how it gets exercised.

```text
STATE_RECEIVED         = "received"
STATE_PREPARING        = "preparing"
STATE_GENERATING       = "generating"
STATE_VALIDATING       = "validating"
STATE_PENDING_APPROVAL = "pending_approval"

TERMINAL_REJECTED   = "rejected"
TERMINAL_EXPIRED    = "expired"
TERMINAL_SUPERSEDED = "superseded"
TERMINAL_FAILED     = "failed"
TERMINAL_CANCELLED  = "cancelled"
TERMINAL_ASK        = "ask"

TERMINAL_STATES: frozenset[str] = frozenset({...})
REQUEST_STATES:  frozenset[str] = frozenset({...})

MAX_REPAIR_ATTEMPTS = 2        # SPECIFICATION.md:640
PLAN_TTL_SECONDS    = 300.0

class RequestState(TypedDict):
    # set once at received, never rewritten
    request_id: str
    session_id: str
    created_at: str
    intent: str
    contract_manifest: ContractManifestV1
    snapshot_identity: StructureSnapshotV1
    snapshot_json: str
    fidelity: FidelityOutcomeV1
    # owned by deterministic code only
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
    # the model's entire contribution
    completion: str | None
```

Every node returns a partial dict and appends to `history`. `interrupt()`
from `langgraph.types` parks the run at `pending_approval`;
`InMemorySaver` from `langgraph.checkpoint.memory` is the checkpointer;
`thread_id` is the session id. Conditional edges route on `status` alone, so
the routing function is a pure `str -> str` that can be tested without
running the graph at all.

Keep every clock, id source and engine injectable on the builder —
`build_request_graph(*, engine, executor, prompt_builder, plan_id_source,
clock, ttl_seconds)` — matching
[PlanRequestLifecycle](src/pmc_server/lifecycle.py#L96-L102) and
[PlanValidationService](src/pmc_server/validation.py#L80-L86).

**Test that proves it**

```text
bazel test //tests/unit:request_graph_transitions --lockfile_mode=error
```

Asserts, with stub node bodies that simply set `status`: every edge in
[SPECIFICATION.md:420-425](SPECIFICATION.md#L420-L425) that this item owns is
reachable and lands where the specification says; every terminal state ends
the run; `history` records the full path; `REQUEST_STATES` equals exactly the
eleven names in the brief, no more and no fewer — a set-equality assertion,
so adding a twelfth state without a decision fails the suite; and the routing
function rejects an unknown status rather than defaulting to a live state.

---

## Step 6 — `preparing` and `generating`

**Files**

- `src/pmc_agent/graph.py` — the two node bodies.
- `src/pmc_agent/prompt.py` (new) — the `PROMPT_BUILDER` seam.
- `tests/unit/test_request_graph_generation.py` (new).

`preparing` resolves the target object from the request's own
`snapshot_identity.object_name` — which item 7's client already resolved
deterministically and failed closed on
([session.py:127-160](src/pmc_client/session.py#L127)) — and writes it once.
It is never rewritten, and step 11 proves no completion can change it. The
contract manifest is checked here; a mismatch is `failed` with a typed
`FailureEnvelopeV1`, not a repairable error. Rule 5's *"computed once and
remain immutable for the request"* is why the card is built here and carried,
not rebuilt per attempt.

`generating` calls `engine.complete()` once with a deadline, and writes
exactly `{"completion": result.text, "model_identity": ..., "status": ...}`.
An `EngineFailure` routes to `failed`. Then, **before parsing** (rule 6), the
completion is classified:

| Completion | Next |
|---|---|
| empty or whitespace only | `ask` — a no-op, with a fixed question |
| single line `ask: <question>` | `ask`, question bounded and redacted |
| anything else | `validating` |

`model_identity` is recorded from the engine, not from the text, because
[SPECIFICATION.md:541](SPECIFICATION.md#L541) makes item 10 re-verify it at
approval.

**Test that proves it**

```text
bazel test //tests/unit:request_graph_generation --lockfile_mode=error
```

Asserts: exactly one engine call for a first-pass success
(`FakeEngine.calls` has length 1); a contract-manifest mismatch never calls
the engine at all; both `ask` forms reach `TERMINAL_ASK` with a bounded,
printable question and **no plan**; an `EngineFailure` of each category
reaches `TERMINAL_FAILED` with a typed envelope and no traceback; and
`target_object` after `preparing` equals the request's resolved object for
every completion the fake is scripted to return, including ones naming a
different object.

---

## Step 7 — `validating`, and the bounded repair loop

**Files**

- `src/pmc_agent/graph.py` — the `validating` node and the repair edge.
- `tests/unit/test_request_graph_repair.py` (new).

Per attempt, in this order, and the order is the point:

1. `parse_pml(completion)` — [parser.py:126](src/pmc_core/parser.py#L126).
   A `ParseRejection` is a failed attempt.
2. `screen_completion(completion)` on the raw text, whether or not parsing
   succeeded. `SCREEN_HOSTILE` ends the request at `rejected` immediately,
   with **zero** repairs (rule 7).
3. `evaluate_plan(plan)` — [policy.py:415](src/pmc_core/policy.py#L415). A
   denial is a failed attempt.
4. `execute()` in a **fresh sidecar** (rule 8, and
   [SPECIFICATION.md:636-638](SPECIFICATION.md#L636-L638) forbids pooling).
   A non-`STATUS_OK` report is a failed attempt.

A failed attempt with `attempt < MAX_REPAIR_ATTEMPTS` appends its
`ExecutionErrorV1` (or a synthesized envelope for a parse or policy failure,
carrying `command_index` and the real category), increments `attempt`, and
routes back to `generating`. The repair prompt is the original prompt plus
every envelope so far — the model sees what went wrong, never how many turns
it has left. At `attempt == MAX_REPAIR_ATTEMPTS` the request is `failed`.

`attempt` is incremented by this node and read by the router. No other code
writes it, and nothing derived from `completion` is ever compared against it.
Total engine calls are therefore at most 3, always, and step 11 proves it.

**Test that proves it**

```text
bazel test //tests/unit:request_graph_repair --lockfile_mode=error
```

Asserts, with a scripted `FakeEngine` and a fake executor: first-pass success
makes exactly one engine call and one executor call; fail-fail-succeed makes
three of each and reaches `pending_approval`; fail-fail-fail makes exactly
three of each and reaches `TERMINAL_FAILED` — never four; each repair prompt
contains the previous attempt's envelope category and message and contains no
attempt counter; a hostile completion reaches `TERMINAL_REJECTED` after
exactly one engine call and **zero** executor calls; an ordinary policy
denial does get its repair; and each executor call receives a distinct
`ExecutionRequest`, proving no attempt reuses a sidecar.

---

## Step 8 — `pending_approval`, expiry, supersession, cancellation

**Files**

- `src/pmc_agent/graph.py` — the interrupt, the TTL, the resume commands.
- `src/pmc_agent/session.py` (new) — the per-session lock table and the
  graph's public entry points.
- `tests/unit/test_request_graph_pending.py` (new).

`pending_approval` mints `plan_id`, computes `expires_at` from the injected
clock and `PLAN_TTL_SECONDS`, and calls `interrupt()`. The thread stays
parked until something resumes it:

| Trigger | Resume value | Outcome |
|---|---|---|
| `/v1/reject` with the matching plan id | `RESUME_REJECT` | `rejected` |
| `/v1/cancel` | `RESUME_CANCEL` | `cancelled` |
| a new `/v1/plan` for the same session | `RESUME_SUPERSEDE` | `superseded`, then the new request starts on a fresh checkpoint |
| any of the above, past `expires_at` | — | `expired` wins, checked first |

Expiry is evaluated before the resume value is honoured, so a reject arriving
after the TTL reports `expired` rather than `rejected` — the plan was already
invalid ([SPECIFICATION.md:433](SPECIFICATION.md#L433)). A reject naming a
different plan id is refused without touching the thread.

`session.py` owns `RequestGraphSession`: the compiled graph, the
`InMemorySaver`, and a `dict[str, threading.Lock]`. Its `submit()`,
`reject()` and `cancel()` each take the session lock for the whole
invocation, so `ThreadingHTTPServer` cannot interleave two requests into one
thread.

**Test that proves it**

```text
bazel test //tests/unit:request_graph_pending --lockfile_mode=error
```

Asserts: a validated request parks at `pending_approval` with a plan id and a
computed `expires_at`; reject reaches `rejected`; cancel reaches `cancelled`;
a second submit reaches `superseded` in the first request's `history` and
leaves exactly one pending plan; a reject one tick past the TTL reaches
`expired`, not `rejected`; a reject with a wrong plan id changes nothing;
and — the one that needs real threads — two concurrent submits for one
session produce one `superseded` and one `pending_approval`, never two
pending plans, run under `pytest` repeatedly enough to be meaningful.

---

## Step 9 — Replace the fixture lifecycle

**Files**

- [src/pmc_server/lifecycle.py](src/pmc_server/lifecycle.py) — rewritten.
  `FIXTURE_INTENT`, `FIXTURE_PLAN`, `FIXTURE_SNAPSHOT_SCHEMA_VERSION`,
  `FIXTURE_MANIFEST` and `PlanRequestLifecycle` all **deleted**.
- [src/pmc_server/transport.py:26-38](src/pmc_server/transport.py#L26)
  — `REJECT_PATH`, `CANCEL_PATH`, and `PLAN_PATH`'s body cap raised to
  `MAX_EXECUTION_REQUEST_BYTES`.
- [tests/unit/test_server_lifecycle.py](tests/unit/test_server_lifecycle.py)
  — rewritten against the graph.
- [tests/integration/test_loopback_transport.py](tests/integration/test_loopback_transport.py),
  [tests/integration/test_client_server_command.py](tests/integration/test_client_server_command.py),
  [tests/integration/test_real_pymol_command.py](tests/integration/test_real_pymol_command.py)
  — all four import `FIXTURE_PLAN` or `PlanRequestLifecycle` and must move to
  the graph.

What replaces it is thin, because the states live in the graph:

```text
class RequestGraphLifecycle:
    def __init__(self, *, session: RequestGraphSession) -> None: ...
    def __call__(self, request: PlanRequestV1) -> PLAN_RESPONSE: ...
    def reject(self, request: RejectRequestV1) -> REJECT_RESPONSE: ...
    def cancel(self, request: CancelRequestV1) -> CANCEL_RESPONSE: ...
```

`__call__` keeps the existing
`Callable[[PlanRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1]`
signature, so `PLAN_HANDLER`
([transport.py:43-44](src/pmc_server/transport.py#L43)) and every transport
test survive unchanged. `ValidationReportV1.applicable` keeps the rule it got
in item 7 — `request.fidelity.status == FIDELITY_EXACT`, never upgraded,
never re-derived — and gains nothing, because the server still has no live
session to compare against.

A terminal state that is not `pending_approval` becomes a
`FailedPlanResponseV1` whose `FailureEnvelopeV1.category` is the terminal
state's own name, and `retryable` is finally meaningful: `true` for
`expired`, `superseded` and `cancelled`, `false` for `rejected`, `failed`
and `ask`. Today it is hardcoded `false` at its one producer
([lifecycle.py:206](src/pmc_server/lifecycle.py#L206)).

**Test that proves it**

```text
bazel test //tests/unit:server_lifecycle //tests/integration:loopback_transport --lockfile_mode=error
bazel test //tests/integration:client_server_command --lockfile_mode=error
grep -rn "FIXTURE_PLAN\|FIXTURE_INTENT\|PlanRequestLifecycle" src/ tests/    # expect no output
```

Asserts: a request carrying `snapshotJson` above the old 64 KiB cap is
accepted over the real loopback socket and one above
`MAX_EXECUTION_REQUEST_BYTES` is refused; each terminal state maps to its
category and the right `retryable`; `applicable` still tracks the request's
own fidelity status through all three values; and the credential and
correlation checks
([client/transport.py:106-124](src/pmc_client/transport.py#L106)) still hold
against the widened request.

---

## Step 10 — The client: real intents, snapshot bytes, `copilot_reject`

**Files**

- [src/pmc_client/command.py:47-48](src/pmc_client/command.py#L47) — delete
  `FIXTURE_INTENT` and `FIXTURE_MANIFEST`'s fixture role; send the user's
  actual text.
- [src/pmc_client/command.py:306-404](src/pmc_client/command.py#L306) —
  attach `snapshot_json`, register `copilot_reject`.
- [src/pmc_client/transport.py:21](src/pmc_client/transport.py#L21) — the
  request cap rises to match the server; the *response* cap stays at 64 KiB,
  because no response carries a snapshot.
- [tests/integration/test_command.py](tests/integration/test_command.py) —
  extend.

`copilot <intent>` stops being a fixture echo. The client already clears its
pending plan unconditionally at the top of every call
([command.py:315-321](src/pmc_client/command.py#L315)) — that stays, and now
means the same thing on both sides.

`copilot_reject <plan-id>` mirrors `copilot_apply`'s refusal table exactly:

| Condition | Output |
|---|---|
| no pending plan | `copilot_reject: no pending plan for this session` |
| id does not match | `copilot_reject: plan <id> is not the pending plan` |
| matches | `copilot_reject: plan <id> rejected. Nothing was applied.` |

The client's own `PendingPlan.applicable` AND
([command.py:445](src/pmc_client/command.py#L445)) is untouched. Neither side
trusts the other's verdict, and that does not change because the server grew
a state machine.

**Test that proves it**

```text
bazel test //tests/integration:command --lockfile_mode=error
bazel test //tests/integration:real_pymol_command --lockfile_mode=error
```

Asserts: the submitted `PlanRequestV1` carries the user's literal intent and
the full canonical `snapshotJson` whose digest matches
`snapshot_identity.digest`; each `copilot_reject` row verbatim; a reject
clears the local pending plan so a following `copilot_apply` refuses; and,
against real PyMOL, `assert_session_unchanged` holds across
`copilot` → `copilot_reject` and across every terminal state the fake engine
can drive.

---

## Step 11 — The no-model-authority suite

**Files**

- `tests/adversarial/test_model_authority.py` (new),
  [tests/adversarial/BUILD.bazel](tests/adversarial/BUILD.bazel).

This is the step that proves
[SPECIFICATION.md:551-552](SPECIFICATION.md#L551-L552), and it is a separate
step because it must be written against the finished graph, adversarially,
rather than alongside the code it is checking.

A `HostileFakeEngine` returns completions engineered to subvert each
protected field:

| Attack | Field it targets | Must remain |
|---|---|---|
| `{"attempt": 0, "status": "pending_approval"}` as the completion | retry count, status | exactly 3 engine calls, `failed` |
| a valid plan naming a different object | `target_object` | the request's resolved object |
| `# policy: allowed` / `applicable: true` appended to a valid plan | policy, `applicable` | `evaluate_plan`'s verdict, the request's fidelity |
| a completion embedding a well-formed `plan_id` | `plan_id` | the server's own `plan_id_source` value |
| `expires_at` far in the future | expiry | the injected clock plus TTL |
| 128 valid commands (`MAX_COMMANDS`) plus one | plan shape | rejected, not truncated |

The assertion is uniform: run the graph, then compare the protected fields
against what deterministic code would have produced from the same request
with a *benign* engine. They must be identical.

**Test that proves it**

```text
bazel test //tests/adversarial:model_authority --lockfile_mode=error
```

Then prove the suite can fail, which matters more than its passing: make
`generating` write `target_object` from the completion when the completion
names one, re-run, and confirm exactly the target-object case goes red and
nothing else. Restore. Repeat for the attempt counter by letting the
completion set `attempt`. A suite of this shape is worthless if it is
vacuous, and vacuity here is invisible.

---

## Step 12 — READMEs and the master plan

**Files**

- `src/pmc_agent/README.md` (new) — the package finally owns something; state
  what the graph is, which states it owns, and that
  `applying`/`applied`/`restoring` are item 10's.
- [tests/unit/README.md](tests/unit/README.md),
  [tests/adversarial/README.md](tests/adversarial/README.md) — add the
  transition, repair, pending and model-authority evidence.
- [src/pmc_server/BUILD.bazel](src/pmc_server/BUILD.bazel) — extend the
  package comment: the server owns the graph's lifetime, not its states.
- [docs/master_plan.md:87-108](docs/master_plan.md#L87-L108) — the status
  table is stale by four items. Mark 4, 5, 6 and 7 `done` with their PR
  numbers and recompute what that unblocks. Leave every item's intent text
  alone; it is the brief, not a status board.
- [docs/master_plan.md:396-407](docs/master_plan.md#L396-L407) — add one note
  to item 9's brief: the engine interface and fake landed in item 8, so item
  9 is `lemonade.py` and capability probing only.

**Test that proves it**

```text
bazel test //... --lockfile_mode=error
grep -rn "FIXTURE_" src/ --include=*.py            # expect no output
grep -rn "fixture lifecycle" src/ --include=*.py   # expect no output
```

---

## Verification (end to end)

From a clean checkout of the branch, the full gate sequence from
[docs/development_setup.md](docs/development_setup.md), which is also what CI
runs on ubuntu-24.04, macos-15 and windows-2025:

```text
bazel version
bazel mod graph --lockfile_mode=error
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Then, specifically for this item:

1. **Every state is reachable and every state is tested.** A test asserts
   `REQUEST_STATES` has exactly eleven members, and the transition suite
   covers each. Add a twelfth constant temporarily and confirm the
   set-equality assertion fails — a state nobody decided on must not be able
   to appear quietly.
2. **The engine is called at most three times, ever.** Across the whole
   suite, `FakeEngine.calls` never exceeds 3 for one request. Raise
   `MAX_REPAIR_ATTEMPTS` to 3, re-run, and confirm the repair tests fail.
   Restore.
3. **Every validation attempt got its own process.** In the real-PyMOL repair
   test, the executor's `child_pid` differs across all three attempts.
4. **No model output reaches a protected field** — step 11, including the two
   deliberate sabotages that must go red.
5. `bazel query 'deps(//src/pmc_client:pmc_client)'` contains neither
   `langgraph` nor `//src/pmc_agent`; `bazel query
   'deps(//src/pmc_core:pmc_core)'` contains neither, and still contains no
   `//src/pmc_sidecar`.
6. **Zero live mutation on every new path.** Run the real-PyMOL suite with
   `assert_session_unchanged` across `rejected`, `expired`, `superseded`,
   `cancelled`, `failed` and `ask`; then sabotage it with
   `cmd.color("blue", "chain A")` inside the reject handler and confirm those
   tests go red. Restore.
7. `ls $TMPDIR | grep pmc-executor-` is empty after the whole suite, and on
   POSIX the `pymol` process count is unchanged before and after the
   integration tests — three sidecars per repaired request is three chances
   to leak one.
8. CI green on all three operating systems before the PR is marked ready.
   Windows is where process spawning and `exclusive` tags have historically
   broken, and this item triples the spawns per request.

Finally, by hand, the thing no test asserts: run `copilot` in a real
interactive PyMOL with a deliberately broken fake engine wired in, watch a
request go through two repairs and fail, and read the output cold. If a user
could not tell how many attempts were made, what went wrong each time, or
that nothing was applied, the wording is wrong regardless of what is green.
Then leave a plan pending for six minutes and `copilot_apply` it — the
refusal must say `expired`, and it must say it without a traceback.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| `interrupt()`/`Command(resume=...)` does not behave as assumed under `InMemorySaver`, and `pending_approval` cannot actually be parked and resumed | Step 8, after steps 5–7 are already built on it | Verified present in the pinned wheel (`langgraph.types.interrupt`, `langgraph.checkpoint.memory.InMemorySaver`, langgraph 1.2.11) but not yet exercised. Spike it in the first hour of step 5, not step 8: a throwaway two-node graph that interrupts and resumes. If it does not work, the fallback is a graph that runs to `pending_approval` and terminal transitions driven as fresh single-node invocations against the same thread — more code, same states — and that is a plan change to raise, not to improvise |
| pyrefly's strict preset rejects the `RequestState` TypedDict against langgraph's structural `StateT` bound, as it already does in `runtime.py` | Step 5, immediately | The existing `# pyrefly: ignore[bad-specialization]` is the precedent and is acceptable on the same two sites. A wider spray of ignores is not — if it needs more than the builder and the return annotation, stop and report rather than silencing the checker across the module |
| The hostile screen is so broad that repair never happens, and the repair tests pass only because they inject completions the screen was never shown | Never, on its own — that is the danger | Step 4's third assertion group is ordinary typos screening `SCREEN_ORDINARY`, and step 7 asserts an ordinary policy denial *does* get its repair. Both are written before the screen is tuned |
| Raising `/v1/plan`'s body cap to ~8 MiB opens a local resource-exhaustion path | Step 9 | The cap is finite, it is the same one `/v1/validate` has carried since item 4, and the endpoint is loopback-only behind an ephemeral per-session credential ([SPECIFICATION.md:446-447](SPECIFICATION.md#L446-L447)). The response cap deliberately stays at 64 KiB |
| Adding `error_envelope` to `CommandOutcomeV1` breaks item 4's shipped round-trip fixtures, or item 14's dataset writer later | Step 3, or silently in Martin's work | The field is optional and the change is additive within protocol version 1, so existing fixtures stay valid — that is asserted explicitly. Tell Martin before step 3 lands; the envelope is his module and item 14 reads this type |
| Three PyMOL spawns per repaired request makes a failing request take 15+ seconds and the demo feel broken | First real interactive use, or step 10's real-PyMOL tests | Measure it in step 10 and record the number, as plan 06 did for the fidelity probe. The bound is the executor's own deadline, so it cannot wedge. No sidecar pool — [SPECIFICATION.md:636-638](SPECIFICATION.md#L636-L638) forbids it until state-reset equivalence is proven, and a repair loop is the *worst* place to start reusing state |
| The per-session lock deadlocks, or is held across a 30-second executor deadline and blocks a cancel | Step 8, intermittently, worst case only on Windows CI | One lock, one level, never nested, acquired only in `RequestGraphSession`'s three entry points. A cancel that has to wait for an in-flight generation is correct behaviour, not a bug — but say so in the docstring, because it looks like one |
| `superseded` is recorded in `history` and nowhere a user can see, so the client silently loses a plan | Step 9 | The superseded request's own response is a `FailedPlanResponseV1` with category `superseded` and `retryable=true`; item 11 owns making that readable. Verified by the cold read in verification |
| Item 13 lands a prompt builder whose shape the `PROMPT_BUILDER` seam cannot express | Later, as Martin's work merges | The seam is one callable taking a frozen inputs dataclass and returning a string, which is the narrowest thing that can work. It also returns the grammar in item 13's version — leave `grammar: str \| None` threaded through the engine call from day one so adding it is a one-line change, not a signature change |
