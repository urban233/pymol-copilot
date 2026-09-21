# Inference abstraction and Lemonade

## Scope

Implement only the inference boundary described by item 9:

- a narrow bounded-completion interface;
- a scripted fake implementation for tests;
- a production adapter for one explicitly configured local Lemonade server;
- a startup capability probe based on the Lemonade spike;
- a hard failure when grammar is rejected or silently ignored; and
- no remote fallback under any condition.

This plan does **not** add server lifecycle construction, health or version
endpoints, request-graph behavior, client commands, configuration files,
process supervision, or master-plan status changes. Those are separate items.
The startup boundary in this plan is `connect_lemonade()`: callers receive a
usable engine only after that function has completed every capability check.

The branch already contains a partial implementation from the superseded plan.
Treat that code as a draft to audit against this plan, not as evidence that a
step is complete. Preserve correct code, amend incomplete behavior, and do not
touch files outside the lists below without stopping and reporting a plan
error.

The spike established that request-level grammar is enforced by Lemonade
11.9.0 with the `llamacpp` recipe. Therefore the syntax-only fallback clause
does not apply. There is no degraded `grammar_enforced=False` mode: failure to
prove grammar enforcement prevents construction of an engine.

## Fixed decisions from the spike and brief

- `CompletionRequest` carries prompt text, optional grammar, maximum tokens,
  and a finite wall-clock deadline. `complete()` also receives a cooperative
  cancellation token.
- Every engine outcome is a `CompletionResult` or `EngineFailure`; transport,
  protocol, timeout, and malformed-response failures do not escape as
  exceptions.
- The Lemonade adapter always requests streaming. The spike found that
  abandoning a non-streaming request does not stop compute, while closing a
  streaming response does.
- Successful results carry the exact model identity proved at startup. Model
  identity is model name plus checkpoint, not the friendly name alone.
- Grammar is omitted from the JSON body only when the request's grammar is
  `None`. A supplied grammar is forwarded verbatim.
- Generation is deterministic: the adapter always sends `temperature: 0`.
- A deadline returns `ENGINE_TIMEOUT` and discards partial text. Cancellation
  returns `STOP_CANCELLED` and may carry text received before cancellation.
- The adapter accepts exactly one configured loopback origin. Valid hosts are
  `localhost`, IPv4 loopback addresses, and IPv6 loopback addresses. Reject a
  non-loopback host, non-HTTP scheme, credentials, query, fragment, or nonempty
  base path before opening a transport. There is no endpoint list, discovery
  service, retry-to-another-host behavior, cloud option, or environment-based
  fallback.
- The real Lemonade suite is opt-in. Hermetic tests use
  `httpx.MockTransport`; ordinary `bazel test //...` never needs a model,
  Lemonade installation, network route, or Docker daemon.

## Step 1 — Lock the engine contract and fake

### Files

- `src/pmc_agent/inference/base.py`
- `src/pmc_agent/inference/fake.py`
- `src/pmc_agent/inference/__init__.py`
- `src/pmc_agent/inference/BUILD.bazel`
- `tests/unit/test_inference_fake.py`
- `tests/unit/BUILD.bazel`

### Work

Audit the existing interface and retain a deliberately small public contract:

- `CompletionRequest(prompt, grammar, max_tokens, deadline_seconds)`;
- `CompletionResult(text, model_identity, stop_reason)`;
- `EngineFailure(category, message)`;
- `CancelToken.cancel()` and `CancelToken.is_cancelled()`; and
- `InferenceEngine.model_identity` plus total `complete()`.

Keep the existing stable stop reasons and engine-failure categories. Validate
constructor invariants that are necessary to make “bounded” true: token count
and deadline must be positive, result stop reasons must be known, and failure
categories must be known. Invalid locally constructed values may raise
`ValueError`; the totality requirement applies to an engine call after it has
received a valid request.

Keep `FakeEngine` as the second implementation. It replays a finite ordered
script, records every request, exposes its configured model identity, and
fails loudly if a test calls it more times than scripted. It must never invent
a default completion or inspect model output to decide control flow.

Make `inference/__init__.py` expose the supported interface deliberately,
rather than relying on callers to discover implementation internals.

### Proof

Extend `//tests/unit:inference_fake` to prove:

- valid requests/results/failures round-trip unchanged;
- zero or negative token/deadline bounds are rejected;
- unknown stop reasons and failure categories are rejected;
- scripted results and failures are returned in order;
- every request is recorded exactly once; and
- script exhaustion raises instead of returning a plausible default.

Run:

```text
bazel test //tests/unit:inference_fake --lockfile_mode=error
bazel test //... && bazel run //tools/quality:ruff -- check . && bazel run //tools/quality:pyrefly -- check
```

Do not begin step 2 until both commands pass.

## Step 2 — Finish one bounded, local-only streaming Lemonade adapter

### Files

- `src/pmc_agent/inference/lemonade.py`
- `src/pmc_agent/inference/BUILD.bazel`
- `tests/unit/test_inference_lemonade.py`
- `tests/unit/BUILD.bazel`

### Work

Finish `LemonadeEngine.complete()` against
`POST /api/v1/chat/completions`. Its request body is exactly:

```json
{
  "model": "<configured model name>",
  "messages": [{"role": "user", "content": "<prompt>"}],
  "max_tokens": "<request limit>",
  "temperature": 0,
  "stream": true,
  "grammar": "<supplied grammar only>"
}
```

Validate the configured base URL before creating or using an HTTP client. A
test-injected `MockTransport` does not bypass this rule; tests use a loopback
base URL too. Preserve one explicit local destination for the engine's
lifetime.

Read OpenAI-compatible SSE events, accumulate
`choices[0].delta.content`, require the response model to match the configured
model name, and map `finish_reason` values `stop` and `length` to `STOP_END`
and `STOP_LENGTH`. Treat malformed framing, JSON, choice data, finish reasons,
or model identity as `ENGINE_UNKNOWN`.

Enforce the request deadline in both HTTP timeout configuration and stream
processing. The HTTP connect/read/write/pool timeout used for the call must
never exceed the request's remaining deadline. Check elapsed monotonic time
before the request, between chunks, and after the stream closes. If the
deadline expires, close the response and return `ENGINE_TIMEOUT` without any
partial completion. Check cancellation before the request and between chunks;
close the response and return `STOP_CANCELLED` immediately when observed.

Map connection failures, DNS failures, refused connections, and 5xx responses
to `ENGINE_UNAVAILABLE`. When a grammar was supplied, map a 4xx response that
identifies the grammar parameter to `ENGINE_REFUSED_GRAMMAR`. Normalize every
failure message with `pmc_core.errors.normalize_message` before returning it.
No code in this module may try another address after any failure.

### Proof

Against `httpx.MockTransport`, make
`//tests/unit:inference_lemonade` prove:

- streamed chunks accumulate into the expected text;
- `stop` and `length` map correctly;
- every body has `stream: true` and `temperature: 0`;
- a supplied grammar is byte-for-byte unchanged and `grammar` is absent for
  `None`;
- a token and deadline are checked before network I/O;
- cancellation during streaming returns `STOP_CANCELLED` and closes the
  response;
- a deadline during streaming returns `ENGINE_TIMEOUT`, closes the response,
  and exposes no partial text;
- the per-call HTTP timeout is no greater than the request deadline;
- connection and 5xx failures return `ENGINE_UNAVAILABLE`;
- explicit grammar rejection returns `ENGINE_REFUSED_GRAMMAR`;
- a mismatched response model and malformed SSE return `ENGINE_UNKNOWN`;
- hostile error text is bounded, printable, and single-line;
- each accepted loopback spelling works; and
- a public or otherwise non-loopback URL is rejected before the transport
  records any request, proving there is no remote path or fallback.

Run:

```text
bazel test //tests/unit:inference_lemonade --lockfile_mode=error
bazel test //... && bazel run //tools/quality:ruff -- check . && bazel run //tools/quality:pyrefly -- check
```

Do not begin step 3 until both commands pass.

## Step 3 — Make capability probing the startup constructor

### Files

- `src/pmc_agent/inference/lemonade.py`
- `tests/unit/test_inference_lemonade_probe.py`
- `tests/unit/BUILD.bazel`

### Work

Keep `EngineCapabilities` frozen and have `connect_lemonade()` return either a
probed `LemonadeEngine` or an `EngineFailure`. A successfully returned engine
carries immutable capabilities and a model identity minted from the exact
probed checkpoint.

Run these checks in this order and stop on the first failure:

1. `GET /api/v1/health`: require HTTP 200, `status == "ok"`, and a string
   Lemonade version. An unreachable server is `ENGINE_UNAVAILABLE`.
2. `GET /api/v1/models/{model_name}`: require the configured model and exact,
   case-sensitive checkpoint. Missing or mismatched identity is
   `ENGINE_UNKNOWN`.
3. `POST /api/v1/load`: request the configured model, backend, and context
   size. Re-read `/api/v1/health` and require the loaded block to report the
   expected model, checkpoint, device, recipe, and context size. This detects
   Lemonade's documented silent fallback from an unavailable GPU backend to
   CPU.
4. Run one completion through the same streaming path as ordinary requests,
   with `root ::= "pmc-grammar-probe-ok"` and a prompt that would naturally
   invite a different answer. Require exactly `pmc-grammar-probe-ok` with
   `STOP_END`.

Anything other than the exact grammar sentinel—including an ordinary HTTP 200
with an unconstrained answer—is `ENGINE_REFUSED_GRAMMAR`. Do not return an
engine, warn-and-continue, omit future grammars, or expose a
`grammar_enforced=False` capability. The spike proved enforcement, so do not
add syntax-only operation.

`connect_lemonade()` performs no retry and accepts no fallback URL. Failed
startup leaves the caller with only the typed failure value.

### Proof

Against one recorded `MockTransport` script per case, make
`//tests/unit:inference_lemonade_probe` prove:

- the happy path returns an engine with exact immutable capabilities and
  `model_name@checkpoint` identity;
- the request sequence is health, model, load, health, canary exactly once;
- an unreachable first health request stops after one request;
- a missing model or one-character checkpoint mismatch stops before load;
- a reported device, recipe, or context-size mismatch stops before canary;
- explicit grammar rejection returns `ENGINE_REFUSED_GRAMMAR`;
- a valid 200 carrying an unconstrained answer returns
  `ENGINE_REFUSED_GRAMMAR`;
- a near-miss sentinel returns `ENGINE_REFUSED_GRAMMAR`;
- no failed case returns a usable engine; and
- no case records a request to any origin other than the configured loopback
  origin.

Run:

```text
bazel test //tests/unit:inference_lemonade_probe --lockfile_mode=error
bazel test //... && bazel run //tools/quality:ruff -- check . && bazel run //tools/quality:pyrefly -- check
```

Do not begin step 4 until both commands pass.

## Step 4 — Add the opt-in real Lemonade evidence

### Files

- `tests/integration/lemonade_support.py` (new)
- `tests/integration/test_lemonade_real.py` (new)
- `tests/integration/BUILD.bazel`
- `tests/integration/README.md`

### Work

Add one `lemonade_real` Bazel target tagged `external`. It inherits only
`PMC_LEMONADE_BASE_URL` and skips with a clear reason when that variable is
unset. Validate the environment value through the same loopback-only URL
validator as production; setting it to a remote URL is a test failure, not a
route to a remote service.

Use the spike's existing `tests/discovery/lemonade/compose.yaml` to run the
suite manually. Do not copy production code from the discovery probe.

The real suite must cover:

- successful `connect_lemonade()` with the pinned checkpoint;
- a grammar-constrained prompt producing exactly its forced sentinel;
- the same prompt without grammar not accidentally producing that sentinel;
- `max_tokens` producing `STOP_LENGTH`;
- a short deadline producing `ENGINE_TIMEOUT` within a small measured grace
  window; and
- cancelling a long streaming completion, followed by Lemonade health
  reporting `is_busy == false` within a bounded wait.

A currently working Lemonade build cannot demonstrate ignored grammar against
the real server. State in the test that this negative evidence is the hermetic
silently-ignored response case from step 3; do not pretend the real suite
exercised a server behavior that was unavailable.

### Proof

Run without a server and require an intentional skip with exit status zero:

```text
bazel test //tests/integration:lemonade_real --lockfile_mode=error --test_output=all
```

Then run the spike container and the same target with the loopback variable:

```text
docker compose -f tests/discovery/lemonade/compose.yaml up -d
PMC_LEMONADE_BASE_URL=http://localhost:13305 bazel test //tests/integration:lemonade_real --lockfile_mode=error --test_output=all
```

Record the real run's elapsed startup-probe time in the commit or PR notes; do
not encode a machine-specific latency assertion in the test.

Finally run:

```text
bazel test //... && bazel run //tools/quality:ruff -- check . && bazel run //tools/quality:pyrefly -- check
```

Do not begin step 5 until the skip path and full repository gate pass. If no
local Lemonade server is available, record the real run as an explicit manual
verification still owed; do not substitute a mock result for it.

## Step 5 — Document the boundary and verify no fallback exists

### Files

- `src/pmc_agent/inference/lemonade.py`
- `src/pmc_agent/README.md`
- `tests/unit/README.md`
- `tests/integration/README.md`

### Work

Update the inference section of `src/pmc_agent/README.md` to describe the
engine-neutral contract, `FakeEngine`, local Lemonade adapter, startup probe,
exact model identity, hard grammar failure, and loopback-only/no-fallback
rule. Remove stale language saying item 9 or `lemonade.py` is future work.

In the Lemonade module docstring, record the spike-derived operational facts
that explain the implementation: cancellation requires streaming, model
identity is the checkpoint, and grammar enforcement is proved at each startup
because it is not a safe assumption. Do not document a syntax-only mode,
because the spike did not require one and the code must not provide one.

Update the test READMEs with the hermetic adapter/probe targets and the opt-in
real suite. Keep the distinction between scripted ignored-grammar evidence and
the live server's positive enforcement evidence explicit.

### Proof

Run the required gate:

```text
bazel test //... && bazel run //tools/quality:ruff -- check . && bazel run //tools/quality:pyrefly -- check
```

Then audit the finished tree:

```text
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
rg -n 'https?://' src/pmc_agent/inference --glob '*.py'
rg -n 'fallback|grammar_enforced|stream' src/pmc_agent/inference src/pmc_agent/README.md
```

The URL audit may contain the named loopback default and test documentation;
it must contain no public endpoint. The fallback audit must show only explicit
statements that fallback does not exist, never code that selects one. Review
the final diff and confirm that no `pmc_server`, request-graph, client,
configuration, process-supervision, or master-plan file changed.

## Completion criteria

The item is complete only when:

- the fake and Lemonade adapter both satisfy the same narrow interface;
- every completion is token-bounded, time-bounded, cancellable where the
  streaming server permits, and tied to an exact model identity;
- an optional grammar is forwarded exactly when supplied;
- startup refuses explicit and silently ignored grammar failures;
- only a caller-selected loopback Lemonade origin can ever receive a request;
- no remote, alternate-origin, unconstrained, or syntax-only fallback exists;
- the hermetic full suite and all quality gates pass; and
- the real Lemonade target either passes against the spike container or is
  reported explicitly as manual verification still owed.
