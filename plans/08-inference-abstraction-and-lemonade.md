# Inference abstraction and Lemonade

## Context

This is item 9 of
[docs/master_plan.md:393-406](docs/master_plan.md#L393-L406), Hannah's, sized
at ~4 days, and blocked on item 8
([docs/master_plan.md:98](docs/master_plan.md#L98)). It is the item that
replaces the last fake in the request path: after item 8 the graph calls an
engine, but the only engine that exists is a scripted test double.

**Half of item 9's brief already landed.** Item 8's step 2 shipped
`src/pmc_agent/inference/` — [base.py](src/pmc_agent/inference/base.py) (the
`InferenceEngine` Protocol, `CompletionRequest`, `CompletionResult`,
`EngineFailure`, `CancelToken`, the four `STOP_*` reasons and the four
`ENGINE_*` categories) and [fake.py](src/pmc_agent/inference/fake.py)
(`FakeEngine`). [base.py:4-11](src/pmc_agent/inference/base.py#L4-L11) says so
in its own docstring:

> item 9 adds the one production implementation (`lemonade.py`), against a
> local Lemonade server, plus startup capability probing.

So what is actually outstanding is: the Lemonade adapter, the startup
capability probe, the wiring that makes the server use it, and the honest
record of what the engine can and cannot do. `ENGINE_REFUSED_GRAMMAR`
([base.py:64-68](src/pmc_agent/inference/base.py#L64-L68)) was defined by item
8 and is unreachable today; this item is what makes it reachable.

The other thing that exists is a stub:
[runtime.py:56-66](src/pmc_agent/runtime.py#L56-L66)'s
`build_engine_client(base_url, timeout)` returns a configured `httpx.Client`
and its own docstring ends *"No request is sent."* It was a dependency-linking
placeholder from item 0 and this item supersedes it.

### What the spike already answered

[tests/discovery/lemonade/FINDINGS.md](tests/discovery/lemonade/FINDINGS.md)
is item 1, merged as PR #25. It answers four questions against Lemonade
11.9.0 on the `llamacpp` recipe, and three of its answers dictate this item's
design rather than merely informing it.

**Grammar is enforced — but undocumented.**
[FINDINGS.md:30](tests/discovery/lemonade/FINDINGS.md#L30) records `YES`, and
[FINDINGS.md:47-55](tests/discovery/lemonade/FINDINGS.md#L47-L55) proves it
per request, deterministically, down to a single forced token. The caveat is
the part that matters:

> Lemonade forwards unrecognized request-body fields to llama-server rather
> than deliberately implementing `grammar` support — which is exactly why it
> works today and exactly why it is the kind of thing that regresses silently
> in a later release without anyone treating it as a breaking change.

and the consequence it draws
([FINDINGS.md:109-118](tests/discovery/lemonade/FINDINGS.md#L109-L118)):

> item 9 should still probe it at startup with a canary shaped exactly like
> R1 (a grammar that forbids the model's otherwise-deterministic answer) and
> treat anything other than the constrained output as a hard failure

**So the brief's fallback clause does not fire.** master_plan item 9 says *"If
the spike showed grammar can't be enforced, implement syntax-only and record
that limitation in the code and the readme rather than pretending."* The spike
showed the opposite, so this item implements real grammar support. What gets
recorded in the code and the readme instead is the *other* two limitations
below, which are just as real and were not anticipated by the brief.

**Cancellation is streaming-only.**
[FINDINGS.md:139-170](tests/discovery/lemonade/FINDINGS.md#L139-L170):

> Disconnecting a non-streaming request does not stop compute — it runs to
> completion regardless. […] **The adapter should always call the streaming
> endpoint internally, even for a conceptually "single-shot" completion, and
> cancel by ceasing to read the stream.**

Item 8 already encoded this at
[base.py:22-27](src/pmc_agent/inference/base.py#L22-L27): the `CancelToken` is
advisory and `deadline_seconds` is the real bound.

**Identity is a checkpoint, not a model name.**
[FINDINGS.md:206-212](tests/discovery/lemonade/FINDINGS.md#L206-L212):

> pin a `checkpoint` string, not just a friendly model name, and treat a
> `model_not_found` at startup as the capability probe's first, cheapest
> check.

And [FINDINGS.md:259-261](tests/discovery/lemonade/FINDINGS.md#L259-L261), on
never trusting the absence of an error:

> assert `/api/v1/health`'s `device` field explicitly — Lemonade auto-selects
> Vulkan first and silently falls back to CPU if unavailable, so an absence
> of an error is not proof of GPU use.

### What the specification requires

[SPECIFICATION.md:490](SPECIFICATION.md#L490) — the contract row this item
owns end to end:

> | Inference interface | Hannah | LangGraph and engine adapters | Bounded
> local completion with prompt, grammar, token/time limits, cancellation,
> model identity | **No remote fallback; deterministic shipping
> configuration** | Capability discovery, finite timeout, cancellation, typed
> engine errors | Adapters may vary; semantic contract remains stable | Fake
> adapter plus real Lemonade capability suite |

[SPECIFICATION.md:488](SPECIFICATION.md#L488), the grammar row, states the
rule the brief restates: *"Capability probe at engine startup; ignored
grammar is a hard engine failure."*

[SPECIFICATION.md:609](SPECIFICATION.md#L609) — and this is the one that
decides what a failed probe *does*:

> | Lemonade unavailable or incompatible | Generation cannot start | Engine
> health and capability probe | **Server remains available for diagnostics;
> no unconstrained fallback** | Restart engine, install compatible version,
> or reject platform | Hannah |

[SPECIFICATION.md:191-193](SPECIFICATION.md#L191-L193):

> When Lemonade or the model is unavailable, the application fails locally
> with actionable diagnostics. It does not fall back to a remote or
> unconstrained model.

[SPECIFICATION.md:675-678](SPECIFICATION.md#L675-L678): *"The server owns
inference-process startup, readiness, shutdown, and version checks. It never
silently connects to an arbitrary server."*

[SPECIFICATION.md:287](SPECIFICATION.md#L287): *"The server process and
inference process bind only to the local machine."*

[SPECIFICATION.md:716](SPECIFICATION.md#L716) names the evidence owed: *"real
Lemonade integration tests, including ignored grammar and cancellation"*.

**Outcome:** the server starts, probes a local Lemonade server, proves that
server will honour a grammar it is given, pins the exact checkpoint it is
talking to, and hands the request graph a real engine. If any of that fails
the server stays up, answers diagnostics, and refuses to generate — it never
generates unconstrained and it never reaches off the machine.

### Decisions taken (from the clarifying questions)

- **Item 8 is assumed fully merged to `main`.** This plan references
  `pmc_agent.session.RequestGraphSession`, the replaced
  [src/pmc_server/lifecycle.py](src/pmc_server/lifecycle.py), and
  `src/pmc_agent/README.md` as things that exist. None of them exists on
  `feat/langgraph-request-graph` today (that branch is at item 8's step 6 of
  12). Every step below that touches an item-8 artifact says so explicitly,
  so an execution session that finds one missing or differently shaped stops
  and reports a plan error rather than improvising around it.

- **The engine is connected, probed and loaded — not supervised.** This item
  assumes a Lemonade server is already running locally. It reads
  `/api/v1/health`, asserts the pinned checkpoint through `/api/v1/models`,
  issues `/api/v1/load` to pin the backend and context size, and runs the
  grammar canary. It does not spawn, terminate, port-allocate or reap the
  Lemonade process; that part of
  [SPECIFICATION.md:675](SPECIFICATION.md#L675) belongs to item 19's
  packaging work, and this plan records it there rather than silently
  dropping it.

- **CI proves everything it can against a fake transport; the real server is
  opt-in.** No runner has Lemonade on it, and the spike's image is
  `linux/amd64` only
  ([FINDINGS.md:277](tests/discovery/lemonade/FINDINGS.md#L277)). Every
  hermetic assertion runs against `httpx.MockTransport` in `tests/unit/`, so
  `bazel test //...` stays green on all three operating systems. The real
  suite lives in `tests/integration/`, skips itself when
  `PMC_LEMONADE_BASE_URL` is unset, and is run by hand against the spike's
  own `compose.yaml`.

- **No configuration schema.** [configs/runtime/README.md](configs/runtime/README.md)
  still says no configuration schema or behavior is defined, and this item
  does not define one. The base URL, model id, checkpoint, backend, context
  size, timeouts and token budget are named module constants in
  `lemonade.py`, passed explicitly as constructor arguments by whoever builds
  the engine. A config file is a later item's decision, not a side effect of
  this one.

### Decisions I took, stated so you can overrule them

- **The adapter has no non-streaming code path at all.** Not "prefers
  streaming" — there is no branch that can emit `"stream": false`, and a test
  asserts every outgoing request body carries `"stream": true`. This is the
  only way
  [FINDINGS.md:139-153](tests/discovery/lemonade/FINDINGS.md#L139-L153)'s
  finding stays true against a future contributor: a non-streaming call
  cannot be cancelled and was measured running ~158 seconds past a client
  disconnect, which would blow through `deadline_seconds` silently.

- **A deadline discards partial text.** Hitting `deadline_seconds` mid-stream
  closes the response and returns `EngineFailure(ENGINE_TIMEOUT, ...)`, per
  [base.py:125-127](src/pmc_agent/inference/base.py#L125-L127). The bytes
  received so far are dropped: a truncated `.pml` that parses is worse than
  no `.pml`, because it would reach the policy and sidecar stages looking
  like a real plan. `STOP_DEADLINE` therefore never appears from this
  adapter; it stays in `STOP_REASONS` for `FakeEngine` and for an engine that
  can return a *meaningful* partial, and `lemonade.py` says so where it would
  otherwise look like an oversight.

- **Cancellation returns a result, not a failure, and the graph must read
  `stop_reason`.** A set `CancelToken` closes the stream and returns
  `CompletionResult(text=<bytes received>, stop_reason=STOP_CANCELLED)`.
  That is what `STOP_CANCELLED` is for — but
  [graph.py:557-574](src/pmc_agent/graph.py#L557-L574) today classifies any
  non-failure completion without looking at `stop_reason`, so a cancelled
  empty completion would be classified as a *no-op*. Step 6 closes that; it
  is a real defect that only becomes reachable once a real engine exists, and
  it is fixed here rather than tracked.

- **`ENGINE_REFUSED_GRAMMAR` is not retryable.**
  [graph.py:565](src/pmc_agent/graph.py#L565) marks every `EngineFailure`
  `retryable=True`, with the reasoning that *"a fresh request could plausibly
  succeed where this one hit an unavailable or timed-out engine."* That
  reasoning is correct for `ENGINE_UNAVAILABLE` and `ENGINE_TIMEOUT` and
  false for a refused grammar: an engine that ignores grammars will ignore
  the next one too, and telling a user to retry is telling them to retry
  forever. Also step 6.

- **The startup canary is a nonsense sentinel, not the spike's
  Berlin/Madrid/Rome.** FINDINGS asks for an R1-shaped canary — a grammar
  forbidding the model's otherwise-deterministic answer — which needs an
  unconstrained control run to mean anything, because a model *could* say
  "Rome". Instead the canary constrains generation to one string no model
  would ever emit unprompted (`root ::= "pmc-grammar-probe-ok"`) for a prompt
  that invites a different answer entirely. An engine ignoring the grammar
  cannot produce it by accident, so no control run is needed and startup
  costs one model call instead of two. Same guarantee, half the latency —
  but it is a departure from the spike's own wording, so it is stated here
  rather than buried.

- **`model_identity` is `f"{model_name}@{checkpoint}"`**, minted once by the
  probe from `/api/v1/health`'s loaded-model block and constant for the
  engine's lifetime, as
  [base.py:182-191](src/pmc_agent/inference/base.py#L182-L191) requires. Each
  completion response's own `model` field is compared against `model_name`
  and a mismatch is an `ENGINE_UNKNOWN` failure — the server having swapped
  models underneath us is exactly what
  [SPECIFICATION.md:541](SPECIFICATION.md#L541)'s approval-time
  re-verification exists to catch, and catching it earlier is cheaper.

- **A failed probe does not abort server startup.**
  [SPECIFICATION.md:609](SPECIFICATION.md#L609) says the server remains
  available for diagnostics. The server holds an `EngineFailure` instead of
  an engine and returns it, typed, on every plan request.

- **`lemonade.py` stays one module file, never a subpackage.**
  [tools/bazel/check_dependency_boundaries.py:104-109](tools/bazel/check_dependency_boundaries.py#L104-L109)
  matches forbidden *names* against each label's package identity —
  everything before the first `:`. A source file at
  `src/pmc_agent/inference/lemonade.py` has identity
  `//src/pmc_agent/inference` and is invisible to that check; a *directory*
  `src/pmc_agent/inference/lemonade/` would put the literal string
  `lemonade` into a package identity and trip `RUNTIME_NAMES`
  ([:48](tools/bazel/check_dependency_boundaries.py#L48)) for any root that
  ever reached it. Worth a comment in the file, because it looks arbitrary.

- **Nothing is reused from the spike.**
  [tests/discovery/lemonade/README.md:9-11](tests/discovery/lemonade/README.md#L9-L11)
  is explicit: *"`src/pmc_agent/inference/` (a later item) is designed from
  this directory's findings, not from anything reused out of it."*
  `probe.py` is 924 lines of disposable prototype. The adapter is written
  fresh against `httpx`, which is already pinned
  ([requirements_lock.txt:217](requirements_lock.txt#L217)) and already a
  dependency of `//src/pmc_agent`.

---

## Delivery: one branch, one PR

Branch from a `main` that already contains item 8:

```text
git checkout main && git pull --ff-only
git checkout -b feat/inference-lemonade
```

Steps 1–8 ship together. One commit per step, in order. Link the PR to an
issue per [CONTRIBUTING.md:21-33](CONTRIBUTING.md#L21-L33).

[.github/CODEOWNERS](.github/CODEOWNERS) makes every `**/BUILD.bazel`
`@urban233`, so steps 1, 2 and 7 pull Martin in as a required reviewer. Tell
him before step 2: item 13 emits the grammar this adapter enforces
([docs/master_plan.md:205-207](docs/master_plan.md#L205-L207)) and item 16
runs its untuned baseline through this same interface
([:208-209](docs/master_plan.md#L208-L209)), so the request body shape
decided in step 2 is a shape he inherits.

---

## Step 1 — The gates, before any adapter code

**Files**

- `plans/08-inference-abstraction-and-lemonade.md` (new) — this document.
- [src/pmc_agent/inference/BUILD.bazel](src/pmc_agent/inference/BUILD.bazel)
  — add `deps = ["@pypi//httpx", "//src/pmc_core:pmc_core"]`. The package has
  no `deps` at all today; it is about to acquire both an HTTP client and
  `pmc_core.errors.normalize_message`
  ([src/pmc_core/errors.py:391](src/pmc_core/errors.py#L391)), which
  [base.py:163-167](src/pmc_agent/inference/base.py#L163-L167) already names
  as how `EngineFailure.message` is bounded.
- [tools/bazel/check_dependency_boundaries.py](tools/bazel/check_dependency_boundaries.py)
  — no new root and no new entry. Extend the comment on `RUNTIME_NAMES`
  ([:48](tools/bazel/check_dependency_boundaries.py#L48)) to record that
  `lemonade` is matched as a *package identity*, which is why the adapter is
  a module and not a directory.

Do this first and alone. The in-PyMOL client must never acquire an HTTP
engine client, and this is the step where that is re-proven before the
adapter exists to make it possible.

**Test that proves it**

```text
bazel build //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel query 'deps(//src/pmc_client:pmc_client)' | grep -E 'httpx|pmc_agent'   # expect no output
bazel query 'deps(//src/pmc_core:pmc_core)'   | grep -E 'httpx|pmc_agent'     # expect no output
bazel query 'deps(//src/pmc_agent/inference:inference)' | grep httpx          # expect a hit
```

The two empty greps are the load-bearing assertions; the third confirms the
edge landed rather than being silently dropped.

---

## Step 2 — `lemonade.py`: one bounded streaming completion

**Files**

- `src/pmc_agent/inference/lemonade.py` (new) — `LemonadeEngine`, the
  constants, the request builder and the stream reader.
- [src/pmc_agent/inference/BUILD.bazel](src/pmc_agent/inference/BUILD.bazel) —
  add `lemonade.py` to `srcs`.
- `tests/unit/test_inference_lemonade.py` (new),
  [tests/unit/BUILD.bazel](tests/unit/BUILD.bazel) — a new `py_test` named
  `inference_lemonade`, `size = "small"`, deps `@pypi//pytest`,
  `@pypi//httpx`, `//src/pmc_agent/inference:inference`,
  `//src/pmc_core:pmc_core`.

The module's named constants, all overridable per construction:

```text
DEFAULT_BASE_URL          = "http://localhost:13305"
DEFAULT_MODEL_NAME        = "Llama-3.2-1B-Instruct-GGUF"
DEFAULT_CHECKPOINT        = "unsloth/Llama-3.2-1B-Instruct-GGUF:Llama-3.2-1B-Instruct-UD-Q4_K_XL.gguf"
DEFAULT_BACKEND           = "cpu"
DEFAULT_CONTEXT_SIZE      = 4096
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_READ_TIMEOUT_SECONDS    = 30.0
```

Every value is the spike's own
([FINDINGS.md:273-283](tests/discovery/lemonade/FINDINGS.md#L273-L283),
[evidence/03-identity.json](tests/discovery/lemonade/evidence/03-identity.json)),
with a comment naming item 17 as what replaces the model and checkpoint once
a fine-tuned artifact exists.

`complete()` posts to `/api/v1/chat/completions` with, always:

```text
{"model": ..., "messages": [{"role": "user", "content": request.prompt}],
 "max_tokens": request.max_tokens, "temperature": 0, "stream": true,
 "grammar": request.grammar}          # key omitted entirely when None
```

It reads the SSE stream with `httpx.Client.stream()`, accumulating
`choices[0].delta.content`, and checks two things between chunks: a
`time.monotonic()` budget against `request.deadline_seconds`, and
`cancel.is_cancelled()`. `temperature: 0` is not a quality choice — it is
what makes the shipping configuration deterministic, as
[SPECIFICATION.md:490](SPECIFICATION.md#L490) requires.

Outcomes, all typed, none raised — the total boundary
[base.py:13-20](src/pmc_agent/inference/base.py#L13-L20) demands:

| Condition | Returns |
|---|---|
| Stream completes, `finish_reason: "stop"` | `CompletionResult(..., STOP_END)` |
| Stream completes, `finish_reason: "length"` | `CompletionResult(..., STOP_LENGTH)` |
| Deadline passes mid-stream | `EngineFailure(ENGINE_TIMEOUT, ...)`, text discarded |
| `cancel` set mid-stream | `CompletionResult(..., STOP_CANCELLED)` |
| Connect error, refused, DNS, non-2xx 5xx | `EngineFailure(ENGINE_UNAVAILABLE, ...)` |
| 4xx naming `grammar` when a grammar was sent | `EngineFailure(ENGINE_REFUSED_GRAMMAR, ...)` |
| Response `model` != configured `model_name` | `EngineFailure(ENGINE_UNKNOWN, ...)` |
| Malformed SSE, unparseable JSON, any other exception | `EngineFailure(ENGINE_UNKNOWN, ...)` |

Every `message` goes through
[`normalize_message`](src/pmc_core/errors.py#L391), so a server error string
is bounded to 256 bytes, single-line and printable-ASCII before it can reach
a request's history.

**Test that proves it**

```text
bazel test //tests/unit:inference_lemonade --lockfile_mode=error
```

Against an `httpx.MockTransport`, so no server and no network. Asserts: a
scripted SSE stream accumulates to the expected text with `STOP_END`;
`finish_reason: "length"` gives `STOP_LENGTH`; **every** request body the
transport sees carries `"stream": true` and `"temperature": 0`; `grammar` is
present verbatim when supplied and the key is absent entirely when `None`; a
transport raising `httpx.ConnectError` gives `ENGINE_UNAVAILABLE` and does
not propagate; a slow stream past `deadline_seconds` gives `ENGINE_TIMEOUT`
and the partial text does not appear anywhere in the returned value; a token
set mid-stream gives `STOP_CANCELLED`; a 400 whose body names `grammar` gives
`ENGINE_REFUSED_GRAMMAR`; a response echoing a different `model` gives
`ENGINE_UNKNOWN`; and a 900-character control-character-laden server error
comes back through `normalize_message` bounded and printable.

The `"stream": true` assertion is the load-bearing one. Flip the module's
literal to `False` and it must go red — that is the test standing in for a
finding no unit test can otherwise reach.

---

## Step 3 — The capability probe, and `connect_lemonade()`

**Files**

- `src/pmc_agent/inference/lemonade.py` — `EngineCapabilities` (frozen),
  `probe_capabilities()`, and `connect_lemonade() -> LemonadeEngine |
  EngineFailure`.
- `tests/unit/test_inference_lemonade_probe.py` (new),
  [tests/unit/BUILD.bazel](tests/unit/BUILD.bazel) — `inference_lemonade_probe`.

Four checks, cheapest first, exactly the order
[FINDINGS.md:174-212](tests/discovery/lemonade/FINDINGS.md#L174-L212)
recommends. Each returns an `EngineFailure` and stops; none raises.

1. **`GET /api/v1/health`** — reachable, `status == "ok"`. Record `version`.
   Unreachable is `ENGINE_UNAVAILABLE`, and this is the only check that can
   distinguish "no server" from "wrong server".
2. **`GET /api/v1/models/{model_name}`** — 200, and `checkpoint` equal to the
   configured checkpoint **byte for byte**. A 404 `model_not_found` is the
   cheapest possible mismatch signal and the spike confirmed identity is
   validated case-sensitively
   ([FINDINGS.md:186-194](tests/discovery/lemonade/FINDINGS.md#L186-L194)).
   Mismatch is `ENGINE_UNKNOWN` with both checkpoints in the bounded message.
3. **`POST /api/v1/load`** with `{"model_name": ..., "llamacpp_backend":
   DEFAULT_BACKEND, "ctx_size": DEFAULT_CONTEXT_SIZE}`, then **re-read
   `/api/v1/health`** and assert the loaded-model block's `checkpoint`,
   `device` and `recipe` are what was asked for. The re-read is the whole
   point: *"Lemonade auto-selects Vulkan first and silently falls back to CPU
   if unavailable, so an absence of an error is not proof"*
   ([FINDINGS.md:259-261](tests/discovery/lemonade/FINDINGS.md#L259-L261)).
   A mismatch is `ENGINE_UNKNOWN`.
4. **The grammar canary.** One real completion through `complete()` itself —
   not a second code path — with `grammar = 'root ::= "pmc-grammar-probe-ok"'`
   and a prompt that invites a different answer. Anything other than exactly
   `pmc-grammar-probe-ok` is `ENGINE_REFUSED_GRAMMAR`, whether it arrived as
   a 4xx, as a different string, or as a perfectly ordinary-looking 200. That
   last case is the one
   [master_plan:402-403](docs/master_plan.md#L402-L403) and
   [SPECIFICATION.md:488](SPECIFICATION.md#L488) both name: *ignored grammar
   is a hard engine failure*, not a logged warning and not a degraded mode.

`EngineCapabilities` carries `lemonade_version`, `model_name`, `checkpoint`,
`device`, `recipe`, `context_length` and `grammar_enforced`, is frozen, and
is what `model_identity` is minted from. There is no `grammar_enforced=False`
state — the probe either proves it or fails. A field that can only ever be
`True` is deliberate: it makes the absence of a fallback structural, and its
docstring says so, because otherwise someone will helpfully add the other
branch.

`connect_lemonade()` runs the probe and returns the engine or the failure. It
has no fallback parameter, no retry, and no remote anything
([SPECIFICATION.md:191-193](SPECIFICATION.md#L191-L193)).

**Test that proves it**

```text
bazel test //tests/unit:inference_lemonade_probe --lockfile_mode=error
```

Against `MockTransport`, one scripted server per case. Asserts: the full
happy path yields a `LemonadeEngine` whose `capabilities` match the scripted
responses; a dead transport fails at check 1 with `ENGINE_UNAVAILABLE` and
**never issues a load or a completion** (assert the recorded request count is
1 — a probe that pushes on past an unreachable server is a probe that will
one day start a model on the wrong machine); a 404 fails at check 2; a
`checkpoint` differing by one character fails at check 2; a load that reports
back `device: "cpu"` when `"vulkan"` was asked fails at check 3; and three
separate grammar-canary failures — a 400 naming the parameter, a 200
returning the unconstrained answer (**the silently-ignored case**), and a 200
returning a near-miss string — all yield `ENGINE_REFUSED_GRAMMAR` and no
engine.

The silently-ignored case is the single most important assertion in this
item. Delete the canary from `probe_capabilities()` and that test must go
red.

---

## Step 4 — Retire `build_engine_client`

**Files**

- [src/pmc_agent/runtime.py](src/pmc_agent/runtime.py) — delete
  `build_engine_client` and its `import httpx`.
- [src/pmc_agent/BUILD.bazel](src/pmc_agent/BUILD.bazel) — drop
  `"@pypi//httpx"` from `deps`; the dependency now belongs to
  `//src/pmc_agent/inference` alone.
- [tests/unit/BUILD.bazel](tests/unit/BUILD.bazel) and
  `tests/unit/test_agent_runtime.py` — remove whatever covered the stub.

*Depends on item 8.* If item 8 already deleted `runtime.py` outright, this
step is a no-op — report that rather than reinstating the file.

**Test that proves it**

```text
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
grep -rn "build_engine_client" src/ tests/    # expect no output
bazel query 'deps(//src/pmc_agent:pmc_agent)' | grep httpx   # expect only the transitive inference edge
```

---

## Step 5 — The server builds the engine and survives a failed probe

**Files**

- [src/pmc_server/lifecycle.py](src/pmc_server/lifecycle.py) (item 8's
  rewritten version) — the request handler takes `InferenceEngine |
  EngineFailure` instead of an `InferenceEngine`, and answers a stored
  failure directly with the typed failure response item 8 already defines,
  without touching the graph.
- [src/pmc_server/BUILD.bazel](src/pmc_server/BUILD.bazel) — add
  `"//src/pmc_agent/inference:inference"` if item 8 did not already, with a
  comment: the server owns the engine's lifetime, the adapter owns its
  protocol.
- `tests/unit/test_server_engine_wiring.py` (new),
  [tests/unit/BUILD.bazel](tests/unit/BUILD.bazel).

The engine is built **once at startup**, not per request: the probe costs a
real model call and the checks are about the server's identity, not the
request's. `connect_lemonade()`'s result — engine or failure — is held for
the process lifetime.

A failed probe leaves the server listening
([SPECIFICATION.md:609](SPECIFICATION.md#L609)). Every plan request gets the
stored `EngineFailure`, typed, with `retryable` decided by category as step 6
defines. Health and version diagnostics
([SPECIFICATION.md:690](SPECIFICATION.md#L690)) keep working, and that is the
entire point of not aborting.

*Depends on item 8* for the handler's shape and its failure-response type.

**Test that proves it**

```text
bazel test //tests/unit:server_engine_wiring --lockfile_mode=error
```

Asserts: with a stored `EngineFailure`, a plan request returns that failure's
category and message unchanged and the graph is never invoked (a recording
graph seam asserts zero calls); the server still answers its diagnostic
surface in that state; and with a working engine the request reaches the
graph exactly once.

---

## Step 6 — `stop_reason` is read, and a refused grammar is not retryable

**Files**

- [src/pmc_agent/graph.py:547-574](src/pmc_agent/graph.py#L547-L574) — the
  `generating` node body.
- `tests/unit/test_request_graph_generation.py` (item 8's) — extended.

Two corrections, both of which only become reachable once a real engine
exists:

1. **Guard on `stop_reason` before classifying.** Today
   [graph.py:569-574](src/pmc_agent/graph.py#L569-L574) passes any
   non-failure completion straight to `_classify_completion`, which reads an
   empty completion as a no-op. A cancelled stream returns little or no text,
   so a user cancelling mid-generation would be told the model had nothing to
   do. `STOP_CANCELLED` now routes to the `cancelled` terminal without ever
   reaching the classifier. `STOP_LENGTH` still classifies — a truncated plan
   failing to parse is an ordinary repairable outcome — but is recorded in
   `history` so "it hit the token ceiling three times" is visible rather than
   inferred.

2. **`retryable` is decided by category.**
   [graph.py:558-566](src/pmc_agent/graph.py#L558-L566) hardcodes
   `retryable=True` with a comment justifying it for an unavailable or
   timed-out engine. That justification does not extend to
   `ENGINE_REFUSED_GRAMMAR`: an engine that ignores grammars ignores the next
   one too. `ENGINE_UNAVAILABLE` and `ENGINE_TIMEOUT` stay retryable;
   `ENGINE_REFUSED_GRAMMAR` and `ENGINE_UNKNOWN` do not.

*Depends on item 8*, heavily — this step edits its node. If item 8's merged
`generating` differs from the lines cited above, stop and report; this is a
plan error, not a detail to work around.

**Test that proves it**

```text
bazel test //tests/unit:request_graph_generation --lockfile_mode=error
```

Asserts, all against `FakeEngine`: a scripted
`CompletionResult(text="", stop_reason=STOP_CANCELLED)` reaches `cancelled`
and **not** `ask` — revert the guard and this must go red, since it is the
exact bug being fixed; a `STOP_LENGTH` completion still classifies and still
repairs; `ENGINE_REFUSED_GRAMMAR` produces `retryable=False`;
`ENGINE_UNAVAILABLE` still produces `retryable=True`; and no path adds an
attempt the engine did not cause (`FakeEngine.calls` unchanged by any of it).

---

## Step 7 — The opt-in real-Lemonade suite

**Files**

- `tests/integration/lemonade_support.py` (new) — the base-URL lookup and the
  shared skip.
- `tests/integration/test_lemonade_real.py` (new).
- [tests/integration/BUILD.bazel](tests/integration/BUILD.bazel) — a
  `py_test` named `lemonade_real` with `env_inherit =
  ["PMC_LEMONADE_BASE_URL"]` and `tags = ["external"]`.

Not `manual`: the target stays in `bazel test //...` and *skips* when the
variable is unset, so a missing server reads as a skip in the log rather than
as a target nobody remembers exists.

Bring the server up with the spike's own rig, unchanged:

```text
docker compose -f tests/discovery/lemonade/compose.yaml up -d
PMC_LEMONADE_BASE_URL=http://localhost:13305 bazel test //tests/integration:lemonade_real \
  --test_output=all --lockfile_mode=error
```

This is the suite [SPECIFICATION.md:490](SPECIFICATION.md#L490) means by
*"Fake adapter plus real Lemonade capability suite"* and
[SPECIFICATION.md:716](SPECIFICATION.md#L716) by *"real Lemonade integration
tests, including ignored grammar and cancellation"*. One honest gap, recorded
in the file rather than papered over: **the ignored-grammar path cannot be
exercised against a real server**, because no Lemonade build available today
exhibits it — that is the whole finding. Its evidence is step 3's
MockTransport case, and `test_lemonade_real.py` says so in a comment pointing
at that test by name.

**Test that proves it**

```text
bazel test //tests/integration:lemonade_real --lockfile_mode=error         # skips, exits 0
PMC_LEMONADE_BASE_URL=http://localhost:13305 bazel test //tests/integration:lemonade_real \
  --test_output=all --lockfile_mode=error                                   # runs
```

With a server, asserts: `connect_lemonade()` returns an engine and its
`capabilities.checkpoint` equals the pinned one; a grammar of
`root ::= "pmc-grammar-probe-ok"` returns exactly that string while the same
prompt with `grammar=None` does not — **the enforcement proof, taken against
a real model rather than a scripted transport**; a `max_tokens=8` request
returns `STOP_LENGTH`; a `deadline_seconds=2.0` request against a 2000-token
generation returns `ENGINE_TIMEOUT` inside ~3 seconds; and a cancelled
streaming request is followed by `/api/v1/health`'s `is_busy` flipping to
`false` within 10 seconds — the spike measured ~2.0s
([FINDINGS.md:122-137](tests/discovery/lemonade/FINDINGS.md#L122-L137)), so
10 is a generous bound that still fails loudly if cancellation stops working
altogether.

Record the wall-clock time of `connect_lemonade()` against the real server in
the PR description. It runs on every server start and nobody has measured it.

---

## Step 8 — Record what this engine cannot do

**Files**

- `src/pmc_agent/inference/lemonade.py` — a module docstring section, not a
  scattered comment, naming both limitations and pointing at the evidence.
- `src/pmc_agent/README.md` (item 8's) — the inference section: the seam, the
  fake, the adapter, the probe, and what a failed probe means for a user.
- [README.md](README.md) — the brief requires the limitation be recorded "in
  the code and the readme". Add a short **Local inference** section under
  `## Development`, in the top-level readme's own register (it is a user-
  facing document, not a design note).
- [tests/unit/README.md](tests/unit/README.md),
  [tests/integration/README.md](tests/integration/README.md) — the new
  evidence, in each file's existing voice.
- [docs/master_plan.md:98](docs/master_plan.md#L98) — item 9's status row.
  Leave the intent text at
  [:396-406](docs/master_plan.md#L396-L406) alone; it is the brief, not a
  status board.
- [docs/master_plan.md:213-225](docs/master_plan.md#L213-L225) — the
  "Risks carried out of week 1" section says items 8 and 9 *"have to design
  around"* partial cancellation. Record how this one did.

The two limitations, stated plainly, are **not** the one master_plan item 9
anticipated:

- **Grammar enforcement is undocumented and may vanish without warning.** It
  works because Lemonade forwards unknown request fields to llama-server, not
  because it is a supported feature
  ([FINDINGS.md:93-107](tests/discovery/lemonade/FINDINGS.md#L93-L107)). A
  Lemonade upgrade can remove it silently. This is why the canary runs at
  every startup and why its failure stops generation instead of warning.
- **Cancellation only works because the adapter always streams.** A
  non-streaming request cannot be cancelled and was measured running ~158
  seconds past a client disconnect
  ([FINDINGS.md:139-153](tests/discovery/lemonade/FINDINGS.md#L139-L153)).

And one piece of scope this item deliberately does not carry, recorded so it
is not lost: [SPECIFICATION.md:675](SPECIFICATION.md#L675)'s *"The server
owns inference-process startup, readiness, shutdown"* is only half satisfied
— readiness and version checks are here, process startup and shutdown are
item 19's.

**Test that proves it**

```text
bazel test //... --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
grep -rn "no remote fallback\|remote fallback" src/pmc_agent/inference/   # expect a hit
grep -c "stream" src/pmc_agent/inference/lemonade.py                      # expect a non-trivial count
```

Then read `README.md`'s new section cold, as a user who has never seen this
repository: it has to say what to install, what happens when it is not
running, and that nothing is ever sent off the machine. If it reads as an
engineering note rather than an instruction, it is wrong.

---

## Verification (end to end)

The full gate sequence from
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

1. **There is no unconstrained path.** `grep -rn "stream" src/pmc_agent/
   inference/lemonade.py` shows no literal `False`, and no code path omits
   the grammar when one was supplied. Set `"stream": False` by hand, re-run
   step 2's suite, confirm it goes red. Restore.
2. **A silently-ignored grammar stops the server generating.** Point the
   probe at a MockTransport that returns a perfectly valid 200 with the
   unconstrained answer. `connect_lemonade()` must return
   `ENGINE_REFUSED_GRAMMAR`, the server must still answer diagnostics, and
   every plan request must return that failure with `retryable=False`. This
   is the item's central claim; do it by hand once, not only in a test.
3. **Nothing reaches off the machine.** Run the whole suite with the loopback
   interface as the only route (or under `--sandbox_block_network` for the
   hermetic targets) and confirm green. Then `grep -rn "https\?://" src/
   --include=*.py` and confirm every hit is `localhost` or `127.0.0.1`.
4. **The probe is paid once.** Start the server against a real Lemonade,
   issue three plan requests, and confirm from the Lemonade container log
   that exactly one `/api/v1/load` and one canary completion were issued.
   A probe that runs per request is a 4-second tax on every request.
5. **A dead engine does not take the server down.** Start the server with
   nothing listening on 13305. It must come up, answer diagnostics, and
   refuse plan requests with `ENGINE_UNAVAILABLE` and `retryable=True` —
   [SPECIFICATION.md:609](SPECIFICATION.md#L609) verbatim.
6. **Cancellation actually stops compute.** Step 7's real-server test, run by
   hand, watching `docker stats` alongside: CPU must fall from its
   mid-generation level within a few seconds of the cancel, not at the end of
   the generation. The spike measured ~2.0s to `is_busy: false` and ~4.1s to
   quiescence.
7. CI green on all three operating systems before the PR is marked ready,
   with `//tests/integration:lemonade_real` visibly **skipped** rather than
   missing.

Finally, by hand, the thing no test asserts: run `copilot` in a real
interactive PyMOL against a real Lemonade server and a real request, then
stop Lemonade and run it again. Read both outputs cold. The second must tell
a user which engine was unreachable, at which address, and that nothing was
applied — and it must do that without a traceback and without ever
suggesting a cloud alternative, because there isn't one.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| Grammar passthrough regresses in a Lemonade upgrade and the server stops generating entirely | First startup after any Lemonade version bump | This is the designed behaviour, not a failure of it — [SPECIFICATION.md:488](SPECIFICATION.md#L488) calls ignored grammar a hard engine failure. The mitigation is that the message names the version and the canary, so the cause is obvious in one read. Pin the Lemonade version in the readme and treat a bump as a change that needs step 7 re-run |
| The startup canary costs a real model call, and nobody has measured it | Every server start; worst on a cold model load | Step 7 records the number in the PR. On the spike's emulated CPU a short completion is on the order of a second; a cold `/api/v1/load` is much worse. If it proves intolerable the answer is to make startup asynchronous with requests failing `ENGINE_UNAVAILABLE` until it finishes — a plan change to raise, not to improvise |
| `POST /api/v1/load` evicts a model a user loaded for their own purposes — `max_models.llm` is 1 ([evidence/01-health.json](tests/discovery/lemonade/evidence/01-health.json)) | First time someone shares a Lemonade server with another tool | Accepted and documented in step 8's readme section: Copilot expects to own its Lemonade server. The alternative — probing without loading — cannot assert `device` or `ctx_size` and was rejected for that reason |
| `MockTransport` does not reproduce real SSE framing, so step 2's suite passes against a stream shape Lemonade never sends | Silently, until step 7 is run against a real server | Capture one real SSE body during step 7 and use its exact bytes as step 2's fixture rather than a hand-written approximation. A hand-written stream proves the parser against itself |
| `env_inherit` does not propagate on Windows or under a particular Bazel sandbox, so `lemonade_real` fails instead of skipping in CI | CI, on the first push | The skip is decided inside the test from `os.environ.get`, so the worst case is a skip, not a failure. Verify on all three runners in the first CI run specifically |
| Step 6 edits item 8's `generating` node while item 8 is still in review, and the two conflict | At rebase, or worse, at merge | Step 6 is a single small edit to one function, kept in its own commit so it can be dropped and re-applied. If item 8's merged shape differs from the cited lines, stop and report — that is a plan error by the memory's own rule, not something to work around |
| Item 13's real grammar turns out not to be expressible as a GBNF string, or needs a `response_format` schema instead | Later, when Martin's grammar lands | The spike proved **both** routes work ([FINDINGS.md:58-60](tests/discovery/lemonade/FINDINGS.md#L58-L60)) — `grammar` and `response_format: json_schema`. `CompletionRequest.grammar` stays a `str`, and if item 13 emits a schema instead, the adapter gains one branch rather than a new signature. Tell Martin the field shape before step 2 lands |
| `temperature: 0` plus a tiny 1B model produces the same wrong plan every time, and the repair loop burns all three attempts on it | First real end-to-end use, item 12's territory | Determinism is required by [SPECIFICATION.md:490](SPECIFICATION.md#L490) and is not negotiable here; the repair loop feeds a *different* prompt each attempt (the error envelope), so the input differs even though the sampler does not. If repairs still converge, that is a model-quality finding for item 16, and the eval harness is where it belongs |
| The pinned checkpoint is the spike's 1B model and item 17 will replace it, leaving a stale constant nobody notices | When Martin ships a fine-tuned artifact | The constants carry a comment naming item 17, and `model_identity` is derived from the checkpoint rather than hardcoded, so a swap is a two-constant change. [SPECIFICATION.md:541](SPECIFICATION.md#L541)'s approval-time re-verification catches a stale pin at the only moment it could do harm |
