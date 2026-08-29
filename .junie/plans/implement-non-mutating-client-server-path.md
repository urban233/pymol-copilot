# Non-mutating PyMOL Client-Server Path Implementation Plan

**Status:** Draft
**Owner:** Hannah Kullik (`kullik01`)
**Reviewer:** Martin Urban (`urban233`)
**Risk:** High
**Base commit:** `0c8f9706ce4a41837ea5fbb1fdd3e996a3837b29`
**Issue/work item:** [#3](https://github.com/urban233/pymol-copilot/issues/3)
**Brief/design/API:** [`SPECIFICATION.md`](../../SPECIFICATION.md),
[runtime application design](../../docs/codev/design/runtime-application/design.md),
[process architecture](../../docs/codev/design/runtime-application/process-architecture.md#initial-client-server-fixture),
and [plan and execution](../../docs/codev/design/shared-core/plan-and-execution.md)

## Focus card

- **Change:** Add the first authenticated, non-mutating local PyMOL client to
  server path for one `select`/`color` intent.
- **Success:** The client sends the accepted request fixture over authenticated
  loopback HTTP/JSON, the server returns a correlated typed plan and passing
  validation report, and the client renders canonical `.pml` without mutating
  the live PyMOL session.
- **Non-goals:** Apply, rollback, controlled fetch, model lifecycle, broader
  command coverage, platform qualification, and raw model `.pml` responses.
- **Allowed scope:** New `src/pmc_client/` and `src/pmc_server/` packages,
  their Bazel targets, contract and integration tests, and product/design
  documents that rename runtime roles from bridge/companion to client/server.
- **Validation:** Bazel build and tests, dependency-boundary check, Ruff,
  formatter, Pyrefly, schema/codec contract tests, and a headless no-mutation
  client-server test.
- **Stop if:** The transport requires a new dependency, PyMOL cannot expose a
  safe non-mutating command adapter, or the accepted schemas need a new field
  or a wire-compatibility change.
- **Work style:** Bounded delegate; the accepted fixtures and one-intent scope
  make the work isolated, testable, and independently reviewable.

## Repository evidence

- `src/pmc_core/plan.py`: `ActionPlan` is immutable and
  `render_pml()` produces canonical `select` then `color` text for the sole
  accepted fixture.
- `src/pmc_core/policy.py`: the shared core evaluates the initial plan with a
  default-deny policy.
- `src/pmc_core/BUILD.bazel`: `pmc_core` is the reusable Bazel library; it
  must remain free of PyMOL runtime imports.
- `tests/contract/` and `tests/adversarial/`: existing Bazel test packages
  cover shared-core contracts and rejection behavior.
- `docs/codev/design/runtime-application/process-architecture.md`: the
  authoritative V1 request and validated-response schemas define UUIDv4
  correlation identifiers, RFC 3339 timestamps, strict fields, and an
  ephemeral HTTP-header credential.
- Issue #3: the server returns typed plans and validation only; the client,
  not the server, renders canonical `.pml`.

## Proposed change

1. Add client and server package boundaries with explicit Bazel dependencies.
   Keep `pmc_core` independent of PyMOL and transport concerns. Give the
   client the sole PyMOL command/session adapter and give the server the
   request lifecycle, deterministic completion fixture, and response assembly.
2. Implement strict codecs for `PlanRequestV1`, `ValidatedPlanResponseV1`,
   the referenced manifest and snapshot fixture values, and a typed failure
   envelope. Enforce `additionalProperties: false`, protocol version `1`,
   UUID and timestamp formats, bounded intent length, request/session
   correlation, and no partial `actionPlan` in failures.
3. Implement the authenticated loopback boundary. The server binds only to a
   loopback address and validates the ephemeral credential from the HTTP
   header before parsing a request. The client sends the credential outside the
   JSON payload, applies finite request and response limits, and rejects any
   unauthenticated, unsupported, malformed, or inconsistent response.
4. Implement the non-mutating command path. The client creates request and
   session UUIDs, builds the accepted snapshot fixture, submits the request,
   validates the correlated response, and renders its typed `ActionPlan` with
   `ActionPlan.render_pml()`. It reports the canonical text and validation
   result but never calls a PyMOL mutation API or executes rendered text.
5. Implement the deterministic server fixture. For the accepted request, the
   server returns the accepted `select copilot_selection, chain A` and
   `color red, copilot_selection` typed action plan with a passed validation
   report. For every invalid request or failed validation, it returns a typed
   failure with no raw model text and no partial plan.
6. Add narrow/small codec tests for accepted fixtures, unknown fields,
   malformed UUIDs and timestamps, unsupported versions, correlation mismatch,
   malformed responses, and absent partial plans. Add narrow/small credential
   and loopback-bind tests. Add one medium-sized, medium-scope headless test
   through the public client command path and a disposable PyMOL adapter. It
   must prove canonical rendering, request/session correlation, and zero live
   session mutations. This larger test earns its cost by detecting a real
   client-server contract mismatch that unit tests cannot detect.
7. Update product/design prose, component names, fixture labels, package
   names, test names, and schema filenames or IDs that describe these runtime
   roles from `bridge`/`companion` to `client`/`server`. Preserve unrelated
   uses of “bridge,” such as delivery-workflow transitions and the Bridge
   design pattern. The existing source tree has no runtime role identifiers to
   migrate; new implementation identifiers must use the new terms.

## Validation

- `bazel build //...` -> all targets build.
- `bazel test //tests/contract/... //tests/adversarial/...` -> existing shared
  core behavior remains valid.
- `bazel test <new client and server unit targets>` -> codecs, authentication,
  strict schema rejection, and typed failures pass.
- `bazel test <new client-server integration target>` -> the real local
  request/response path renders the canonical plan and records zero live
  session mutations.
- `bazel test //tests/integration/...` -> package-boundary imports remain
  valid.
- `bazel run //tools/bazel:check_dependency_boundaries` -> runtime packages do
  not reverse the core dependency boundary.
- `bazel run //tools/quality:ruff -- check src tests` and
  `bazel run //tools/quality:ruff -- format --check src tests` -> lint and
  formatting pass.
- `bazel run //tools/quality:pyrefly` -> strict type checks pass.

## Risks and rollout

- **Local protocol exposure:** Bind only to loopback, require the ephemeral
  header credential, enforce payload limits, and test wrong-token rejection.
- **Accidental mutation:** Keep rendering separate from dispatch, use a
  disposable adapter in the end-to-end test, and add a mutation-observing
  assertion that fails on every client path.
- **Schema drift:** Treat the accepted fixtures as the contract; reject unknown
  or version-mismatched input instead of accepting best-effort values.
- **PyMOL availability:** Keep the normal test path headless and adapter-based.
  Stop for a design decision if real PyMOL integration cannot be exercised
  safely in the repository environment.
- **Rollback:** No release or live mutation is introduced. Revert the new
  runtime packages and fixtures as one change if the path fails its safety
  evidence.

## Decisions needed

- None. The client/server naming, HTTP/JSON loopback transport, authentication
  placement, strict V1 schemas, and non-mutation boundary are accepted by
  issue #3 and the cited designs.

## Completion evidence

- **Delivered:** Pending implementation.
- **Changed:** Pending implementation.
- **Head commit/snapshot:** Pending implementation.
- **Validation actually run:** Planning-only artifact; no product validation
  has run.
- **Acceptance evidence:** Pending implementation.
- **Scope deviations:** None.
- **Known limitations:** The real PyMOL adapter and transport implementation do
  not yet exist in the repository.
- **Review state:** Not reviewed.
