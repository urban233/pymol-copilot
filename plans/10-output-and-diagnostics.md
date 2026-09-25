# Output and diagnostics

## Context

This is item 11 of
[docs/master_plan.md:461-472](docs/master_plan.md#L461-L472). It is Hannah's,
sized at ~2 days, and `ready` now that PR #51 (item 10) has merged. Item 12,
the end-to-end suite, is blocked only on this item.

The brief:

> Make copilot print what the specification promises: plan id and expiry,
> resolved object, numbered canonical commands, selection counts, validation
> warnings, fidelity status, an explicit statement of what was and wasn't
> checked, and the exact approval and rejection commands to type. Add a health
> command reporting server, engine, model and contract versions. Every failure
> path must produce a bounded, actionable message — no tracebacks, no plan
> text leaking through an error.

### What the specification requires

[SPECIFICATION.md:503-511](SPECIFICATION.md#L503-L511):

> `copilot <intent>` never applies commands. It prints:
> plan identifier and expiry; resolved object or proposed fetch accession;
> numbered canonical commands; selection counts and validation warnings where
> available; sidecar fidelity status; a concise statement of what was checked
> and what was not; the exact approval or rejection command.

- [SPECIFICATION.md:482](SPECIFICATION.md#L482): the command surface
  guarantees *"actionable terminal output"*. *"Invalid, stale, unknown, or
  mismatched identifiers fail without mutation."*
- [SPECIFICATION.md:690](SPECIFICATION.md#L690): *"The command surface
  exposes concise health and version diagnostics."*
- [SPECIFICATION.md:608-609](SPECIFICATION.md#L608-L609): when the server is
  unavailable, the client readiness check detects it. When Lemonade is
  unavailable, *"Server remains available for diagnostics; no unconstrained
  fallback."*
- [SPECIFICATION.md:685-686](SPECIFICATION.md#L685-L686): diagnostics carry
  identifiers *"without raw structure data or intent text by default."*
- [SPECIFICATION.md:840](SPECIFICATION.md#L840): the mitigation for
  *"Approval becomes a reflex"* is *"specific plan rendering, warnings, 'not
  checked' statement"*. This item is that mitigation.

The fetch half of *"resolved object or proposed fetch accession"* is out of
scope. There is no controlled fetch flow yet, and master_plan's *Honest
sizing* cut it.

### What exists today (surveyed 2026-09-24 on `main` @ `b064e5e`)

**The preview.** `copilot` prints four separate `_output` calls from
[src/pmc_client/command.py:975-1034](src/pmc_client/command.py#L975-L1034):
`_fidelity_block`, `_plan_block`, `_checked_block` (lines 239-328), then the
apply line.

- **Not printed:** the expiry, the reject command, selection counts, warnings,
  and the object (except inside the exact-fidelity line).
- **Selection counts are computed and dropped.** The sidecar computes them
  ([src/pmc_sidecar/child.py:289-298](src/pmc_sidecar/child.py#L289)) and
  `ExecutionReport.selection_counts` carries them
  ([src/pmc_core/executor.py:305](src/pmc_core/executor.py#L305)). The graph's
  `_validating` keeps only `report.status` on success
  ([src/pmc_agent/graph.py:905-914](src/pmc_agent/graph.py#L905-L914)).
- **Warnings are always empty.** The executor's only warnings are captured
  sidecar stderr (`_stderr_warning`,
  [executor.py:575](src/pmc_core/executor.py#L575)). The lifecycle hard-codes
  `warnings=()` in both places it builds a report
  ([src/pmc_server/lifecycle.py:190](src/pmc_server/lifecycle.py#L190),
  [:256](src/pmc_server/lifecycle.py#L256)).
- **The resolved object never reaches the client.** `RequestState.target_object`
  is set in `preparing` but never goes on the wire.
- **The "checked" statement is wrong for non-exact fidelity.** It says *"the
  plan was never executed anywhere"*
  ([command.py:300-328](src/pmc_client/command.py#L300)). The graph runs the
  sidecar executor regardless of fidelity: `_validating` never reads
  `state["fidelity"]`. So the plan *was* executed, against a reconstruction
  that does not match the live session. The statement has to be derived from
  what actually ran, not from the fidelity status alone.

**Health.** There is no health, ping or readiness endpoint, and nothing
combines versions. `RequestGraphSession` does not keep a reference to its
engine ([src/pmc_agent/session.py:134-209](src/pmc_agent/session.py#L134)).
`LemonadeEngine.capabilities` exists but is not on the `InferenceEngine`
Protocol. Nothing in `src/` starts a server; only tests wire
`LoopbackPlanServer` + `RequestGraphLifecycle` + an engine.

**Failure paths.** Four kinds of problem, with their sites:

- **Raw exception text is printed.** `str(error)` from arbitrary PyMOL or
  other exceptions:
  - `command.py:559` (`copilot failed: {error}`)
  - `:651`, `:841`
  - `apply.py:86`, printed through `:809`
- **Server text is printed unbounded.** `failure.message` at
  `command.py:694, 957, 972`. `FailureEnvelopeV1.from_dict` bounds nothing;
  the only limit is the 64 KiB response cap.
- **User input is echoed unbounded:** `plan_id` at `:832, :918` and throughout
  `approval.py`.
- **Tracebacks reach PyMOL:**
  1. **`to_json(snapshot)` at [command.py:588](src/pmc_client/command.py#L588)
     is unguarded.** It raises `ValueError` on a NaN or infinite view, the exact
     case `check_fidelity` already handles at
     [fidelity.py:118-125](src/pmc_client/fidelity.py#L118). This is a real bug.
  2. **`cmd.extend` registers with `[function, 0, 0, ',', parsing.STRICT]`** (the
     pinned wheel's `pymol/commanding.py`). An intent containing a comma
     arrives as two positional arguments and raises `TypeError`. `x=y` becomes
     a keyword argument, `;` splits the line into two commands, and a bare
     `copilot` with no argument raises `TypeError` too. PyMOL's
     `parsing.LITERAL` (20) mode passes the rest of the line through as one
     string and disables `;` splitting (`pymol/parser.py:277-282`).
  3. The transport converts only `HTTPException`/`OSError`/`TimeoutError`/
     `ProtocolDecodeError`/`UnicodeDecodeError`
     ([transport.py:252-265](src/pmc_client/transport.py#L252)). Anything else
     escapes.
  4. Any exception other than `ProtocolDecodeError`/`ValueError` in a server
     handler escapes to `socketserver`. That prints a traceback to server
     stderr and drops the connection, and the client can only say `loopback
     request failed`.
- **Two terminals are indistinguishable or invisible.** A hostile-screen
  rejection and a user rejection both produce `rejected` / `"request ended:
  rejected"` ([lifecycle.py:305-312](src/pmc_server/lifecycle.py#L305)), so a
  user who just typed `copilot …` is told their plan was "rejected". A
  superseded plan's terminal is never reported.

**Tests that pin today's layout.** Every client test captures output through
`output: list[str]` (no `capsys`). Three kinds of assertion depend on the
current shape:

- **Index-based:** `tests/integration/test_command.py:598-623` indexes
  `output[0..3]`, and `test_real_pymol_command.py:695-708` asserts
  `len(output) == 7`.
- **Id parsing:** `test_command.py:997` and `test_real_pymol_command.py:677`
  parse the plan id with `removeprefix("copilot plan: ")`.
- **Loopback preview:** `test_client_server_command.py:383-387` checks the same
  four-line shape over the real loopback server.

### Decisions you answered

- **Health is a seam, not a server.** This item adds:
  - `/v1/health` and `HealthRequestV1`/`HealthResponseV1` in
    `pmc_core.protocol`;
  - an engine health value the server can read;
  - an `UnavailableEngine` that holds a failed startup probe;
  - the `copilot_health` command.

  Tests wire it the way they wire everything today. A production entrypoint
  (process launch, and how PyMOL learns the port and credential) stays out,
  and step 12 names it in item 12's brief so it is not lost.
- **Warnings are derived plus stderr.** The server computes fixed, bounded
  warnings from the validation evidence: a selection that matched 0 atoms, a
  selection covering every atom of the target object, and a plan that needed
  repairs. It appends the executor's bounded stderr warning, normalized.
- **The preview is one block.** A single `_output` call with a fixed section
  order. Tests assert on the whole block, or on named sections through one
  helper, never on list indices.

### Decisions I took, stated so you can overrule them

- **`PROTOCOL_VERSION` stays `"1"`; the new fields are required.** This is
  plan 09's precedent: a peer missing them fails closed. Neither process has
  shipped, so no compatibility reader is needed.
- **The command is named `copilot_health`.** It matches the `copilot_*`
  prefix, and [SPECIFICATION.md:482](SPECIFICATION.md#L482) permits
  *"additive commands within V1"*. It is read-only, works while Copilot is
  halted, and works when the server is down (it then reports that, with the
  action).
- **Engine health is live, not only the startup record.** `health()` joins the
  `InferenceEngine` Protocol:
  - `LemonadeEngine.health()` returns its probed capabilities plus one bounded
    `GET /api/v1/health` (2 s). An engine that died after startup is then
    visible without re-running the expensive load and grammar canary.
  - `FakeEngine` returns a configurable value.
  - `UnavailableEngine` returns the recorded probe failure, and its
    `complete()` returns that same `EngineFailure`.
- **Contract versions are aggregated in one place.** A new
  `pmc_core/versions.py` owns `APPLICATION_VERSION` and
  `contract_versions()`. It covers protocol, plan manifest, policy,
  snapshot, card, prompt, grammar, error envelope and executor.
  `copilot_health` compares the client's own values with the server's
  field by field and names each mismatch.
- **Failure categories become a closed set.** `FAILURE_CATEGORIES` in
  `pmc_core.protocol` lists every category the server may emit, with
  `execution_<reason>` derived from the executor's `REASON_*` set. The client
  keeps a category → action table. Tests enforce both sides: the server emits
  nothing outside the set, and the client has an action for everything in it.
  This is what makes "actionable" checkable rather than aspirational.
- **Arbitrary exceptions are reported by type name, never `str(error)`.** A
  PyMOL exception message can carry selection text, which is plan text. Our
  own typed errors (`TargetResolutionError`, `RecoveryPointError`,
  `TransportError`) keep their fixed messages, bounded.
- **The server returns a bounded envelope instead of dropping the
  connection.** On an unexpected exception it answers with a `FailedPlanResponseV1`
  (category `server_internal_error`, fixed message, retryable) and logs one
  fixed-format line to its stderr: path, exception type and request id, with
  no traceback, intent or plan.
- **A last-resort guard wraps every registered command.**
  - For `copilot`, `copilot_reject` and `copilot_health`, which never mutate,
    it prints a bounded *"internal error (TypeName). Nothing was applied."*
    plus an action.
  - For `copilot_apply` and `copilot_rollback`, it cannot know whether the
    session changed. If a recovery point is retained, it therefore **latches
    Copilot halted and preserves the point**, exactly as a failed restore
    does. [SPECIFICATION.md:692-694](SPECIFICATION.md#L692-L694): dangerous
    failures *"halt Copilot operations and preserve local evidence"*.
- **A hostile-screen rejection gets its own envelope,** category
  `hostile_output`: *"the model produced a forbidden command form; nothing
  was run"*. The graph's terminal state stays `rejected`; only the envelope
  changes.
- **The client cross-checks the server's `targetObject` against its own
  resolved object.** On a difference it refuses to park the plan
  (`server resolved a different object`). Neither side trusts the other alone,
  as with `applicable`.
- **The `ask` text stays the model's own question.** It is already collapsed
  to one printable line of 200 characters server-side
  ([graph.py:506-531](src/pmc_agent/graph.py#L506)); the client re-bounds it.
  It is a clarification, not an error, so the plan-text rule does not apply
  to it.

---

## Delivery: one branch, one PR

```text
git checkout main && git pull --ff-only
git checkout -b feat/output-and-diagnostics
```

One commit per step, in order. Open a GitHub issue for item 11 first and link
the PR to it ([CONTRIBUTING.md](CONTRIBUTING.md) §1).

Steps 2-4 change wire types in `pmc_core.protocol`. The shared core is *"Joint;
Martin accountable"* ([SPECIFICATION.md:382](SPECIFICATION.md#L382)), and
every `**/BUILD.bazel` is `@urban233` in
[.github/CODEOWNERS](.github/CODEOWNERS), so tell Martin before step 2 lands.
Item 14 does not read `ValidationReportV1`, so his data half is unaffected.

**Sizing, honestly:** the brief says ~2 days. The failure-path table, the wire
change and the health seam make this closer to 4. The lever, if needed, is
step 11: `copilot_health` could ship reporting only client, server and
contract versions, with engine health following. That is a plan change to
raise, not to take silently.

Every step's gate is the repository's closing check:

```text
bazel test //... && bazel run //tools/quality:ruff -- check . && bazel run //tools/quality:pyrefly -- check
```

The test listed under each step is the one that proves *that* step. It runs
in addition to the gate, not instead of it. Do not pass `BUILD.bazel` files
to `ruff format`.

---

## Step 1 — One source of truth for versions

**Files**

- `plans/10-output-and-diagnostics.md` (new): this document, verbatim.
- `src/pmc_core/versions.py` (new):
  - `APPLICATION_VERSION = "0.0.0"`;
  - `contract_versions() -> Mapping[str, str]`, returning a frozen mapping
    `{"protocol", "plan", "policy", "snapshot", "card", "prompt", "grammar",
    "errorEnvelope", "executor"}` → string, built from the existing module
    constants. The manifest's three string literals come from
    `CURRENT_CONTRACT_MANIFEST` so they cannot drift.
- [src/pmc_core/BUILD.bazel](src/pmc_core/BUILD.bazel): add the source.
- `tests/contract/test_versions.py` (new),
  [tests/contract/BUILD.bazel](tests/contract/BUILD.bazel): new target
  `versions`, with `//:pyproject.toml` as `data`. Export it from the root
  `BUILD.bazel` if it is not exported already.

**Test that proves it**

```text
bazel test //tests/contract:versions
```

It asserts two things:

1. `APPLICATION_VERSION` equals `pyproject.toml`'s `[project].version`.
2. `contract_versions()` covers **every** module-level `*_VERSION` constant in
   `src/pmc_core/*.py`, found with `ast`, not a hand list. Each value equals
   its constant.

Sabotage: add `FOO_VERSION = 1` to `pmc_core/card.py`, and the test must go red
naming it. Restore. A version nobody aggregates is exactly how health would
silently under-report.

---

## Step 2 — Widen the wire: validation facts, bounded failures, health

**Files**

- [src/pmc_core/protocol.py](src/pmc_core/protocol.py):
  - **`ValidationReportV1`** (line 989) gains two required fields:
    - `selectionCounts`: a list of `{name, atomCount}`, at most `MAX_COMMANDS`
      entries, reusing `SelectionCountV1` (line 1404);
    - `repairAttempts`: an int from 0 to 2.

    `warnings` becomes bounded: at most `MAX_VALIDATION_WARNINGS = 8`, each at
    most `MAX_VALIDATION_WARNING_BYTES = 200` and printable ASCII. The bound is
    enforced in `__post_init__` (construction) *and* `from_dict` (decode).
  - **`ValidatedPlanResponseV1`** (line 1066) gains a required `targetObject`.
  - **`FailureEnvelopeV1`** (line 1187): `message` must be at most
    `MAX_FAILURE_MESSAGE_BYTES = 256` and printable ASCII, enforced both ways.
    Add `bounded_failure(category, message, retryable)`, which truncates with
    `executor.bounded_diagnostic` before constructing, so no server site can
    raise by passing an overlong message.
  - **`FAILURE_CATEGORIES: frozenset[str]`** lists every category in the
    current server table, plus `hostile_output`, `server_internal_error`, and
    `execution_<r>` for each executor `REASON_*`.
  - **`HealthRequestV1`** (`protocolVersion, requestId, sessionId`) and
    **`HealthResponseV1`**:
    - `status: "health"`;
    - `server {applicationVersion}`;
    - `contracts`: the step 1 mapping, exact key set;
    - `engine {state: "ready" | "unavailable", engine, engineVersion, device,
      failureCategory, failureMessage}`, with nullable fields strict per state;
    - `model {identity}` or null.

    Every string is bounded, and the response has its own
    `decode_health_response_json`.
- [tests/contract/test_protocol.py](tests/contract/test_protocol.py): extend.

**Test that proves it**

```text
bazel test //tests/contract:protocol
```

It asserts:

- the new types round-trip;
- a report or response **missing** any new field fails to decode, which is
  the fail-closed claim;
- 9 warnings, a 201-byte warning, a 257-byte failure message, a non-ASCII
  message, `repairAttempts=3`, and a health response with an extra or missing
  contract key are each rejected, on both encode and decode;
- `bounded_failure` never raises for any input in a hypothesis-style sweep of
  lengths 0-10 000.

---

## Step 3 — The graph keeps what validation proved

**Files**

- [src/pmc_agent/graph.py](src/pmc_agent/graph.py):
  - `RequestState` (line 335) gains `selection_counts:
    tuple[SelectionCount, ...]` and `sidecar_warnings: tuple[str, ...]`.
  - `_validating`'s `STATUS_OK` branch (line 905) writes both from the report.
  - The hostile-screen branch (line 848) records a `hostile_output` failure
    alongside its `rejected` terminal.
  - Every `FailureEnvelopeV1(...)` becomes `bounded_failure(...)`.
- `src/pmc_agent/warnings.py` (new): a pure `derive_warnings(*, selection_counts,
  target_atom_count, repair_attempts, sidecar_warnings) -> tuple[str, ...]`.
  - It emits fixed templates in fixed order:
    - `selection <name> matched 0 atoms`
    - `selection <name> matches every atom of the target object`
    - `this plan needed <n> repair attempt(s) before it validated`
    - `sidecar: <normalize_message(stderr)>`
  - Output is bounded to step 2's limits.
  - Selection names are grammar-constrained identifiers, but they are
    re-bounded anyway.
- [src/pmc_agent/session.py:405-410](src/pmc_agent/session.py#L405-L410): the
  checkpoint drops opaque values, so `_pending_details` also keeps
  `selection_counts`, `sidecar_warnings`, `target_object` and `attempt`.
- [src/pmc_agent/BUILD.bazel](src/pmc_agent/BUILD.bazel).
- `tests/unit/test_validation_warnings.py` (new, target
  `validation_warnings`), and
  [tests/unit/test_request_graph_pending.py](tests/unit/test_request_graph_pending.py),
  [test_request_graph_transitions.py](tests/unit/test_request_graph_transitions.py):
  extend.
- [tests/adversarial/test_model_authority.py](tests/adversarial/test_model_authority.py):
  one new row.

**Test that proves it**

```text
bazel test //tests/unit:validation_warnings //tests/unit:request_graph_pending \
  //tests/unit:request_graph_transitions //tests/adversarial:model_authority
```

It asserts:

- each warning template fires on exactly its condition, in order, and within
  bounds;
- a pending thread's details carry the executor's counts unchanged, in the
  executor's order;
- a hostile completion ends `rejected` with envelope category
  `hostile_output`, and a user reject still yields `rejected`;
- **model authority:** a completion that appends `# warnings: none` or
  `# selection copilot_selection: 999 atoms` to a valid plan leaves counts and
  warnings identical to the benign run.

Sabotage: let `derive_warnings` read the completion. The model-authority row
must go red.

---

## Step 4 — The server sends it, and never drops a connection

**Files**

- [src/pmc_server/lifecycle.py](src/pmc_server/lifecycle.py):
  - Both report builders (lines 164-196, 240-265) fill `selectionCounts`,
    `repairAttempts`, `targetObject` and `derive_warnings(...)` from the
    pending details. `/v1/apply` re-sends the same facts it previewed.
  - `_to_terminal_response` (line 267) forwards a recorded `hostile_output`
    envelope for `rejected`.
  - Every envelope goes through `bounded_failure`.
- [src/pmc_server/transport.py](src/pmc_server/transport.py): each handler
  gains a final `except Exception` that answers 200 with a
  `bounded_failure("server_internal_error", "the server hit an internal error;
  nothing was applied", True)` and logs one fixed-format line. There is no
  traceback, because `log_message` is already fixed-text (lines 492-499).
- [tests/unit/test_server_lifecycle.py](tests/unit/test_server_lifecycle.py),
  [tests/integration/test_loopback_transport.py](tests/integration/test_loopback_transport.py):
  extend.

**Test that proves it**

```text
bazel test //tests/unit:server_lifecycle //tests/integration:loopback_transport
```

It asserts:

- the `/v1/plan` and `/v1/apply` reports for the same plan carry identical
  counts, warnings and target;
- **every** failure the lifecycle can produce has a category in
  `FAILURE_CATEGORIES`, driven through each terminal and each `failed`
  source;
- a lifecycle handler that raises `AssertionError`, `RuntimeError` or
  `KeyError` produces a decodable `server_internal_error` response over real
  loopback, not a dropped socket;
- captured server stderr contains neither `Traceback` nor the request's
  intent string.

---

## Step 5 — Engines can say how they are

**Files**

- [src/pmc_agent/inference/base.py](src/pmc_agent/inference/base.py):
  - `EngineHealth` (frozen): `state`, `engine`, `engine_version`, `device`,
    `model_identity`, `failure: EngineFailure | None`;
  - `health() -> EngineHealth` on the `InferenceEngine` Protocol. It is total
    and never raises.
- [fake.py](src/pmc_agent/inference/fake.py): a configurable `health` value,
  defaulting to ready / `fake` / `fake-engine-v1`.
- [lemonade.py](src/pmc_agent/inference/lemonade.py): `health()` combines the
  probed `capabilities` (lines 326-339) with one `GET /api/v1/health` under a
  2 s deadline. Any failure maps to `state="unavailable"` with a normalized
  `EngineFailure`. It never re-loads and never re-runs the canary.
- `src/pmc_agent/inference/unavailable.py` (new): `UnavailableEngine(failure,
  *, engine="lemonade")`. `complete()` returns `failure`, and `health()`
  reports it. This is what a future entrypoint builds when `connect_lemonade`
  returns an `EngineFailure`, so the server stays up for diagnostics.
- [src/pmc_agent/session.py](src/pmc_agent/session.py): `RequestGraphSession`
  keeps its engine and exposes `engine_health()`.
- [src/pmc_agent/inference/BUILD.bazel](src/pmc_agent/inference/BUILD.bazel).
- Tests: `tests/unit/test_inference_unavailable.py` (new, target
  `inference_unavailable`), plus
  [test_inference_fake.py](tests/unit/test_inference_fake.py) and
  [test_inference_lemonade.py](tests/unit/test_inference_lemonade.py)
  extended, and [tests/integration/test_lemonade_real.py](tests/integration/test_lemonade_real.py)
  (tag `external`) with one health assertion.

**Test that proves it**

```text
bazel test //tests/unit:inference_unavailable //tests/unit:inference_fake //tests/unit:inference_lemonade
```

It asserts:

- the Lemonade adapter's `health()` against its existing stub server reports
  version and device when `/api/v1/health` is ok;
- it reports `unavailable` + `engine_unavailable` when the stub is stopped,
  returns non-200, or hangs past 2 s;
- `health()` issued zero `/api/v1/load` calls and zero completions;
- `UnavailableEngine.complete()` returns the recorded failure unchanged and
  never blocks.

The real-Lemonade check runs by hand:

```text
bazel test //tests/integration:lemonade_real --test_tag_filters=external
```

---

## Step 6 — `/v1/health`

**Files**

- [src/pmc_server/transport.py](src/pmc_server/transport.py): `HEALTH_PATH =
  "/v1/health"` and an optional `health_handler`, returning 404 when absent
  like the others. It is authenticated like every path, with a 64 KiB body cap.
- [src/pmc_server/lifecycle.py](src/pmc_server/lifecycle.py): `health(request)
  -> HealthResponseV1` from `APPLICATION_VERSION`, `contract_versions()` and
  `session.engine_health()`.
- [src/pmc_client/transport.py](src/pmc_client/transport.py): a duplicated
  `HEALTH_PATH` (the client may not import `pmc_server`), and
  `LoopbackPlanClient.health() -> HealthResponseV1` with correlation checks.
- [tests/unit/test_server_lifecycle.py](tests/unit/test_server_lifecycle.py),
  [tests/integration/test_loopback_transport.py](tests/integration/test_loopback_transport.py).

**Test that proves it**

```text
bazel test //tests/unit:server_lifecycle //tests/integration:loopback_transport
```

It asserts:

- a real loopback round-trip with `FakeEngine` returns ready and exact
  versions;
- with `UnavailableEngine` it returns `unavailable` while `/v1/plan` still
  answers a bounded `engine_unavailable` failure, so the server stays up for
  diagnostics;
- a wrong credential yields 401;
- `bazel run //tools/bazel:check_dependency_boundaries` still passes, with
  `pmc_client` importing nothing from `pmc_server` or `pmc_agent`.

---

## Step 7 — One place the client turns failures into sentences

**Files**

- `src/pmc_client/messages.py` (new), with these parts:
  - **`bounded(text, *, max_bytes=256)`:** printable ASCII only, via
    `executor.bounded_diagnostic`.
  - **`ACTIONS: Mapping[str, str]`:** category → next step. For example:
    - `engine_unavailable` → *"Start Lemonade, check `copilot_health`, then
      run copilot again."*
    - `repair_exhausted` → *"Rephrase the intent more specifically and run
      copilot again."*
    - `contract_mismatch` → *"Client and server versions differ; run
      `copilot_health`."*
    - `expired` → *"Run copilot again for a fresh plan."*
    - `hostile_output` → *"Rephrase the intent; nothing was run."*
    - `server_internal_error` → *"Retry; if it repeats, restart the server
      and run `copilot_health`."*
  - **A fallback** for any category not in the table.
  - **`HTTP_ACTIONS`** for the transport's status codes: 401 is a credential
    mismatch (*restart the server and this PyMOL session*), 413 means the
    session is too large to validate, 404 an endpoint missing from an older
    server.
  - **`describe_failure(command, envelope)`,
    `describe_transport(command, error)` and
    `describe_unexpected(command, error, *, mutated_possible)`:** each returns
    one line of at most 400 bytes, in the form `<command>: <what happened>.
    <whether anything was applied>. <next step>.`
- [src/pmc_client/BUILD.bazel](src/pmc_client/BUILD.bazel).
- `tests/unit/test_client_messages.py` (new, target `client_messages`),
  [tests/unit/BUILD.bazel](tests/unit/BUILD.bazel).

**Test that proves it**

```text
bazel test //tests/unit:client_messages
```

It asserts:

- `ACTIONS.keys() >= FAILURE_CATEGORIES`; with step 4's server-side assertion
  this closes the loop in both directions;
- every described line is at most 400 bytes and printable, whatever the input
  (a 1 MiB message, control characters, non-ASCII);
- `describe_unexpected` never contains `str(error)`: the exception is raised
  with the sentinel `LEAK select chain A` and the output must lack it.

Sabotage: delete one `ACTIONS` entry, and the first assertion must go red
naming it.

---

## Step 8 — The preview block

**Files**

- [src/pmc_client/command.py](src/pmc_client/command.py):
  - Replace `_fidelity_block`, `_plan_block` and `_checked_block` (lines
    239-328) with one `_preview_block(...)`. `_report_validated` (line 975)
    emits it in one `_output` call.
  - Refuse to park the plan if `response.target_object != object_name`.
  - Cap fidelity mismatches at `MAX_FIDELITY_MISMATCHES`, with `… and N more`.
- `tests/integration/preview_support.py` (new, a small `py_library`):
  `plan_id_from(output)` and `section(output, name)`, so no test indexes
  lines again.
- [tests/integration/test_command.py](tests/integration/test_command.py),
  [test_client_server_command.py](tests/integration/test_client_server_command.py),
  [test_real_pymol_command.py](tests/integration/test_real_pymol_command.py):
  migrate every index and `removeprefix` assertion to the helpers, and add the
  golden blocks.
- [tests/integration/BUILD.bazel](tests/integration/BUILD.bazel).

The layout, exact fidelity:

```text
copilot plan p-<id> (expires 2026-09-24T12:05:00Z, in 5 min)
  object:    1abc (2,041 atoms, 1 state)
  commands:
    1 | select copilot_selection, chain A   -> 1,020 atoms
    2 | color red, copilot_selection
  warnings:  none
  fidelity:  exact on the declared state scope
  checked:   parses; allowed by policy; passed the hostile-form screen;
             ran in a fresh PyMOL sidecar rebuilt from this session exactly
  NOT checked: whether this is scientifically what you meant
  apply:     copilot_apply p-<id>
  reject:    copilot_reject p-<id>
```

Non-exact fidelity keeps the same sections, and the three that change are:

- `fidelity:` becomes `NOT EXACT (<n> mismatches)` with the bounded list;
- `checked:` says the plan *ran in a fresh sidecar rebuilt from a
  reconstruction that differs from this session, so the counts above describe
  that reconstruction, not this session*;
- `apply:` becomes `unavailable (inspectable only)`.

`reject:` is always present; the server parks non-applicable plans too.
Unavailable fidelity names its reason the same way. The relative expiry comes
from the existing `now_factory` (line 345). Counts align to a `select` line
by the selection name; other verbs carry none.

**Test that proves it**

```text
bazel test //tests/integration:command //tests/integration:client_server_command
bazel test //tests/integration:real_pymol_command
```

It asserts:

- **golden blocks, byte-exact,** for exact / not-exact / unavailable /
  server-not-applicable, and a 0-atom warning;
- a target-object mismatch prints a refusal and a following `copilot_apply`
  refuses with `no pending plan`;
- 25 mismatches print 10 plus `… and 15 more`;
- against real PyMOL, the printed count for `chain A` equals
  `cmd.count_atoms("chain A")` in the live session;
- a cold-read regression: no block for a non-exact plan contains the phrase
  `never executed`.

---

## Step 9 — Every failure path, bounded and actionable

**Files**

- [src/pmc_client/command.py](src/pmc_client/command.py): route every
  `_output` of a failure through `messages`.
  - Replace the `str(error)` sites (lines 559, 651, 841) and
    `_report_failure`/refusal sites (lines 694, 957, 972).
  - Bound the echoed `plan_id`s (lines 832, 918).
  - Wrap `to_json(snapshot)` at line 588 and report `the session cannot be
    serialized (non-finite view)`.
  - Add `_guarded(command, handler)` at registration, with the semantics
    decided above: *nothing applied* for read-only commands; for apply and
    rollback, halt and preserve when a recovery point is retained.
- [src/pmc_client/apply.py:86](src/pmc_client/apply.py#L86): a fixed message
  plus the exception type name.
- [src/pmc_client/approval.py](src/pmc_client/approval.py): bound the echoed
  entered id. When one exists, name the actual pending id: `plan p-X is not
  the pending plan (pending: p-Y); apply that, or run copilot again`.
- [src/pmc_client/transport.py:252-265](src/pmc_client/transport.py#L252): a
  final `except Exception` → `TransportError`. `TransportError` carries the
  HTTP status as a field, so `HTTP_ACTIONS` can map it.
- `tests/integration/test_failure_messages.py` (new, target
  `failure_messages`), [tests/integration/BUILD.bazel](tests/integration/BUILD.bazel).
- [tests/recovery/test_no_mutation_sabotage.py](tests/recovery/test_no_mutation_sabotage.py):
  extend.

**Test that proves it**

```text
bazel test //tests/integration:failure_messages //tests/recovery:no_mutation_sabotage
```

`failure_messages` is one parametrized table with **one row per failure
path**. The rows cover:

- **every server category** in `FAILURE_CATEGORIES` through a fake transport;
- **transport errors:** each HTTP status, a refused connection, a timeout, a
  malformed reply, and an uncategorized exception;
- **target resolution:** no object, and several objects;
- **a NaN view;**
- **every approval refusal;**
- **the recovery-store errors;**
- **rollback's inspection failure;**
- **an exception injected into each handler body.**

Each row asserts the same five things:

1. no captured output line contains `Traceback`;
2. every line is at most 400 bytes and printable;
3. the line contains that category's action text;
4. **no line contains any line of the canonical plan's `render_pml()`.** Each
   injected exception and server message embeds that plan text plus the
   sentinel `LEAK`, and neither may appear;
5. `assert_session_unchanged` holds for every non-apply row.

The recovery row asserts that an exception injected after the recovery point
is saved halts Copilot and preserves the `.pse`.

Sabotage: restore `f"copilot failed: {error}"` at line 559, and exactly the
target-resolution and NaN rows must go red. Restore.

---

## Step 10 — PyMOL hands the intent over literally

**Files**

- [src/pmc_client/command.py:406-410](src/pmc_client/command.py#L406-L410):
  - After `cmd.extend("copilot", …)`, set its keyword entry's mode to
    `parsing.LITERAL`, extending the `CmdExtension` Protocol with a
    `keyword` mapping.
  - The handlers take a defaulted `str = ""`. An empty intent or plan id
    prints a usage line, `copilot: usage: copilot <what you want to do>`.
  - An intent over 4 096 characters (the protocol limit, `protocol.py:552`)
    is refused before encoding, with its length.
  - The three id commands stay `STRICT`, since ids contain no commas, but
    gain the empty-argument usage line.
- [tests/integration/test_command.py](tests/integration/test_command.py) (the
  fake `cmd` gains `keyword`),
  [test_real_pymol_command.py](tests/integration/test_real_pymol_command.py).

**Test that proves it**

```text
bazel test //tests/integration:command //tests/integration:real_pymol_command
```

Against real PyMOL, driven through `cmd.do(...)` with PyMOL's stdout captured
by `capfd`:

- `copilot color chain A red, then show sticks; orient` reaches the handler
  as exactly that one string;
- `copilot`, `copilot_apply` and `copilot_reject` with no argument each print
  their usage line;
- a 5 000-character intent prints the refusal;
- none of these produces `Traceback` in the captured output.

Also: `orient` was **not** executed as a second PyMOL command, because the
view matrix is unchanged.

---

## Step 11 — `copilot_health`

**Files**

- [src/pmc_client/command.py](src/pmc_client/command.py): register
  `copilot_health` (guarded, read-only, allowed while halted).
- [tests/integration/test_command.py](tests/integration/test_command.py),
  [test_client_server_command.py](tests/integration/test_client_server_command.py).

The output:

```text
copilot health
  client:    application 0.0.0, protocol 1
  server:    reachable, application 0.0.0
  engine:    ready -- lemonade 11.9.0 on cpu
  model:     Llama-3.2-1B-Instruct-GGUF@unsloth/…Q4_K_XL.gguf
  contracts: plan 1, policy 1, snapshot 1, card 1, prompt 1, grammar 1,
             errorEnvelope 1, executor 1 -- all match this client
  copilot:   ready
```

A mismatch prints `snapshot server 2 / client 1 -- MISMATCH` and the action.
The other states print as follows:

- **Server down:** `server: unavailable (<described>)` plus the action, with
  the rest shown as `unknown`.
- **Engine down:** its bounded failure and action.
- **Halted:** `copilot: HALTED -- recovery point preserved at <path>`.

**Test that proves it**

```text
bazel test //tests/integration:command //tests/integration:client_server_command
```

It asserts:

- golden blocks for ready / engine unavailable / contract mismatch / server
  unreachable / 401 / halted;
- over real loopback, `FakeEngine` and `UnavailableEngine` produce the ready
  and unavailable blocks;
- `copilot_health` sends no `/v1/plan` and changes no client state: a pending
  plan is still pending afterwards;
- `assert_session_unchanged` holds.

---

## Step 12 — Documentation and the master plan

**Files**

- [src/pmc_client/README.md](src/pmc_client/README.md): the preview block, what
  "checked" does and does not mean, `copilot_health`, and the failure →
  action table.
- `src/pmc_agent/README.md`: derived warnings, and `health()` on the engine
  Protocol.
- [docs/master_plan.md](docs/master_plan.md):
  - Item 11 becomes `in review`, with its dependents recomputed.
  - Item 12's brief gets a note: a production server entrypoint (launch, the
    Lemonade probe falling back to `UnavailableEngine`, port and credential
    hand-off to PyMOL) is not built yet, and the "server unavailable"
    scenario needs it.
  - Leave the intent text alone.

**Test that proves it**

```text
bazel test //...
grep -rnE '\{error\}|str\(error\)' src/pmc_client/            # expect no output
grep -rn 'never executed' src/pmc_client/                     # expect no output
grep -rn 'FailureEnvelopeV1(' src/pmc_agent src/pmc_server    # expect no output (all bounded_failure)
```

---

## Verification (end to end)

The full gate from [docs/development_setup.md](docs/development_setup.md):

```text
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Then, specifically for this item:

1. **Every failure category has an action, and the server emits nothing
   else.** Two assertions close the set in both directions: step 4's
   server-side check and step 7's client-side one. Both sabotages go red.
2. **No plan text leaks through an error.** In step 9's table the `LEAK`
   sentinel and canonical-plan lines never appear, and the reverted line-559
   sabotage goes red.
3. **No tracebacks.** Neither PyMOL's stdout (steps 9 and 10) nor the
   server's stderr (step 4) contains `Traceback` on any tested path.
4. **Zero live mutation on every new path.** `assert_session_unchanged` holds
   across the preview, `copilot_health`, and every read-only failure row.
5. **The preview tells the truth.** The real-PyMOL count equals the live
   `count_atoms`, and a non-exact block never claims the plan did not run.
6. CI is green on ubuntu-24.04, macos-15 and windows-2025. Windows is where
   the `capfd` capture in step 10 is most likely to differ.

Finally, by hand: in an interactive PyMOL with the test-wired server, run:

- `copilot` on a comma-containing intent;
- `copilot_health` with the fake engine, then with `UnavailableEngine`;
- `copilot_apply` on a plan left for six minutes;
- `copilot_apply p-garbage`.

Read each output cold. For every line, a user must be able to say what
happened, whether anything changed, and what to type next. If one cannot, the
wording is wrong regardless of what is green.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| Setting `cmd.keyword[name][4] = parsing.LITERAL` after `extend` is not honored by the pinned wheel, or behaves differently in GUI PyMOL | Step 10 | The read path is verified in the wheel's `parser.py:277-282`. Prove it first in step 10's real-PyMOL test, before the handler changes. If it fails, `*args` joining is a weaker fallback (it loses `;` and `=`), which is a plan change to raise, not to improvise |
| Required new wire fields break every existing protocol fixture at once | Step 2 | Expected and intended: plan 09's precedent. Update the fixtures in the same commit. Item 14 does not consume these types; tell Martin anyway |
| The halting guard fires on a benign bug in `copilot_apply`'s reporting *after* a clean apply, and latches Copilot needlessly | Step 9 | Conservative by design ([SPECIFICATION.md:692-694](SPECIFICATION.md#L692-L694)). The latch preserves evidence and costs one PyMOL restart. Step 9's table includes the "clean apply, then the reporter raises" row so the behaviour is decided, not discovered |
| Lemonade's `/api/v1/health` shape differs from what the probe saw, so live health reports a working engine as unavailable | Step 5, real-Lemonade run | Reuse the probe's own step-1 parser rather than a second one. The `external` real test covers it |
| Golden-block tests make every wording change touch many tests | Step 8 onward | That is the point for a spec-mandated surface. The section helper keeps non-golden tests off the wording |
| The item grows past its ~2-day size | Whole item | Stated up front. Step 11's engine half is the cut if needed, and that is Hannah's call |
