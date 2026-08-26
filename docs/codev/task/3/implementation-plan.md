# Issue #3 non-mutating PyMOL client-companion path implementation plan

**Status:** Draft — blocked before build by the contracts listed in
[Decisions needed](#decisions-needed)
**Owner:** Hannah Kullik (`kullik01`)
**Reviewer:** Martin Urban (`urban233`)
**Risk:** High
**Base commit:** `80682b25f387d7c234bb9ec69b031a685ae5d126`
**Issue/work item:** [GitHub issue #3](https://github.com/urban233/pymol-copilot/issues/3)
**Brief/design/API:** [`SPECIFICATION.md`](../../../../SPECIFICATION.md),
[initial runtime delivery plan](../../delivery/design-readiness.md),
[process architecture](../../design/runtime-application/process-architecture.md),
[request pipeline](../../design/runtime-application/request-pipeline.md), and
[plan language and execution](../../design/shared-core/plan-and-execution.md)

The mandatory wire fixtures are:

- [PlanRequestV1 schema and request example](https://github.com/urban233/pymol-copilot/issues/3#issuecomment-5430725893)
- [ValidatedPlanResponseV1 schema and response example](https://github.com/urban233/pymol-copilot/issues/3#issuecomment-5430732918)

## Focus card

- **Change:** Add the first authenticated, non-mutating bridge-to-companion
  path for the accepted `select`/`color` plan fixture.
- **Success:** A `copilot` command submits the accepted request to a local
  companion, receives a correlated validated typed plan, renders the canonical
  `.pml` sequence through the shared-core serializer, and does not alter the
  active PyMOL session.
- **Non-goals:** Applying or rolling back a plan, controlled fetch, labels or
  wider command coverage, companion lifecycle management, model lifecycle,
  canonical live-state serialization, and platform qualification.
- **Allowed scope:** `src/pmc_agent/`, its Bazel targets, contract and
  integration tests under `tests/`, and fixture files required by those tests.
- **Validation:** Contract fixtures, a headless non-mutation end-to-end test,
  and the existing Bazel build, test, dependency-boundary, Ruff, format, and
  Pyrefly checks.
- **Stop if:** The work needs an unrecorded wire schema, authentication
  bootstrap, shared-core type, live snapshot representation, PyMOL mutation,
  new external dependency, or a change to the accepted command fixture.
- **Work style:** Pair.

## Repository evidence

- The issue requires a PyMOL client to send one authenticated loopback
  HTTP/JSON request, a companion outside PyMOL to return a typed validated
  plan, canonical client rendering, and zero live-session mutation. It also
  requires typed failures for malformed messages, unsupported protocol
  versions, and invalid responses.
- The mandatory issue comments define the V1 request and success-response
  schemas. Their required fields, UUIDv4 examples, RFC 3339 UTC timestamps,
  contract manifest, snapshot fixture, typed `select`/`color` action plan, and
  passed validation report are the source fixtures for this plan. The build
  must not rename, omit, or add fields to those successful wire messages.
- The delivery plan assigns T-02 to Hannah, Martin as the independent
  reviewer, and permits integration with T-01 only through recorded typed-plan
  and serializer fixtures. T-01 is tracked by [issue #4](https://github.com/urban233/pymol-copilot/issues/4).
- `src/pmc_agent/` currently contains only a package marker and a Bazel target
  that may depend on `//src/pmc_core:pmc_core`. No bridge, companion, transport,
  PyMOL adapter, shared-core plan type, or serializer implementation exists.
- The repository locks only pytest, Ruff, and Pyrefly. The fixture must use the
  Python standard library for local HTTP and process control unless a human
  approves a dependency change.
- `process-architecture.md` requires authenticated HTTP/JSON over loopback,
  an ephemeral credential in an HTTP header, strict V1 request and successful
  response schemas, UUIDv4 correlation, RFC 3339 UTC timestamps, and no raw
  `.pml` text on the wire.
- The accepted positive plan is exactly:

  ```pml
  select copilot_selection, chain A
  color red, copilot_selection
  ```

- The current shared-core and runtime designs remain `Draft`. The runtime
  design explicitly leaves the typed failure response and the concrete
  bootstrap interface unspecified. The shared-core snapshot design leaves the
  canonical `StructureSnapshotV1` representation unresolved.

## Mandatory V1 wire schema

The implementation and contract fixtures must preserve the two issue-comment
schemas exactly. Both schemas are JSON Schema 2020-12 objects that reject
unrecognized properties.

`PlanRequestV1` requires the following fields:

- `protocolVersion` is exactly `"1"`.
- `requestId` and `sessionId` are UUIDs.
- `createdAt` is a date-time.
- `contractManifest` references `ContractManifestV1`.
- `intent` is a 1–4096-character string.
- `snapshot` references `StructureSnapshotV1`.

`ValidatedPlanResponseV1` requires the following fields:

- `protocolVersion` is exactly `"1"`.
- `requestId` and `sessionId` correlate to the request.
- `receivedAt` and `validatedAt` are date-times.
- `status` is exactly `"validated"`.
- `actionPlan` references `ActionPlanV1`.
- `validation` references `ValidationReportV1`.

The mandatory success fixture fixes the action plan to one `select` command
with `name: "copilot_selection"` and `expression: "chain A"`, followed by one
`color` command with `color: "red"` and `target: "copilot_selection"`. Its
`planVersion` is `"1"`, its `snapshotDigest` is
`"sha256:example-chain-a-digest"`, and the validation report has
`status: "passed"`, the same snapshot digest, and no warnings. The client must
not accept a raw `.pml` alternative for this typed response.

## Decisions needed

This plan deliberately does not invent the following stable interfaces. Record
them in the runtime design before build starts, then update this plan's status
to `Ready`.

1. Define the typed failure message, including required fields, failure codes,
   HTTP status mapping, correlation behavior for malformed requests, and the
   rule that no failure can carry a partial `actionPlan`.
2. Define how the bridge receives the ephemeral loopback endpoint and
   per-session credential without using a command-line argument or persistent
   file, including the exact authentication-header name and loopback-address
   validation rule.
3. Define the typed `StructureSnapshotV1` source that the bridge captures for
   this fixture, or explicitly limit this issue to forwarding the recorded
   fixture from a supplied test seam. T-02 must not create a competing snapshot
   schema in `pmc_agent`.
4. Confirm the public shared-core symbols and serialization entry point that
   T-01 provides. T-02 must import them rather than duplicate action-plan,
   validation, parser, policy, or canonical-rendering behavior.

## Proposed change after the build gate

The implementation stays within the accepted fixture and fails closed at every
boundary.

### 1. Preserve the shared-core boundary

1. Consume the typed action plan, validation report, and canonical serializer
   from `pmc_core` using the symbols accepted by T-01.
2. Keep the bridge responsible only for command registration, request
   construction, transport invocation, response correlation, and display.
3. Keep the companion responsible for request validation and deterministic
   production of the accepted typed plan and passed validation report.
4. Do not add a parser, policy, raw `.pml` generator, `cmd.do()` call, apply
   operation, or mutation fallback to `pmc_agent`.

### 2. Implement the bridge and local companion boundary

1. Register `copilot` through the PyMOL extension seam. The command accepts one
   nonempty intent and reads the current snapshot only through the accepted
   snapshot contract.
2. Create a V1 JSON request that matches the accepted fixture exactly: protocol
   version, UUIDv4 request and session identifiers, RFC 3339 UTC creation time,
   contract manifest, intent, and snapshot.
3. Send the request only to the accepted authenticated loopback endpoint. Apply
   finite payload and request-time limits once their contract values are
   recorded; do not retry or redirect.
4. Validate the server response before rendering. Require V1, matching request
   and session identifiers, a passed validation report for the same snapshot
   digest, and a typed action plan accepted by shared core.
5. Render only the returned typed commands with the shared-core serializer and
   display that canonical text. Never execute the output or call a PyMOL
   mutation method on this path.
6. Make the deterministic companion return the fixture's typed `select` then
   `color` plan and passed validation report. It must validate authentication,
   JSON shape, protocol version, and correlation input before it creates any
   plan.

### 3. Make failure fail closed

1. Decode the recorded typed failure response for malformed requests,
   unsupported versions, failed validation, and authentication rejection.
2. Treat malformed JSON, unknown fields, wrong credentials, non-loopback
   configuration, an unexpected HTTP status, response-schema failure,
   correlation mismatch, digest mismatch, and a response containing raw `.pml`
   as terminal typed client failures.
3. On every failure, render an actionable diagnostic only. Do not retain or
   display a partial plan, and do not mutate the live session.

### 4. Add focused Bazel test targets and fixtures

1. Store the accepted request and successful response as JSON contract fixtures
   under `tests/contract/`. Keep UUIDs, timestamps, snapshot digest, and the
   two typed commands byte-for-byte aligned with the runtime-design fixture.
2. Add narrow, small contract tests for request construction, required
   authentication, strict request and response decoding, correlation, digest
   matching, canonical serializer use, and every typed failure class.
3. Add adversarial tests for unknown fields, malformed JSON, unsupported
   protocol versions, wrong credentials, invalid UUIDs/timestamps, a partial
   action plan, raw `.pml` in a response, and mismatched request, session, or
   snapshot identities.
4. Add one medium, broad headless test that exercises a real local loopback
   server and bridge command seam. Its PyMOL test double records attempted
   mutations and fails if the request path invokes one. The test asserts the
   canonical two-line rendering, request/session correlation, and zero
   mutations. A real Open-Source PyMOL execution test remains a later
   platform-qualification task.
5. Add the new sources and tests to `src/pmc_agent/BUILD.bazel` and relevant
   `tests/*/BUILD.bazel` targets. Preserve the existing dependency direction:
   agent may depend on core, but core must not depend on agent.

## Expected file map

- **Add:** Focused bridge, companion, and protocol modules under
  `src/pmc_agent/`, with no live-apply code.
- **Update:** `src/pmc_agent/BUILD.bazel` for the runtime sources and their
  accepted shared-core dependency.
- **Add:** V1 request, successful-response, and typed-failure JSON fixtures
  under `tests/contract/`.
- **Add:** Contract and adversarial tests under `tests/contract/`, plus one
  headless non-mutating integration test under `tests/integration/`.
- **Update:** The corresponding Bazel test targets only.

The precise module and fixture filenames follow the accepted public
shared-core symbols and failure schema. Do not create placeholder contracts or
duplicate core types merely to start this issue.

## Validation

Run from the repository root after the decision gate is closed:

```text
bazel test //tests/contract/... --lockfile_mode=error
bazel test //tests/integration/... --lockfile_mode=error
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
git diff --check
git status --short
```

Expected evidence:

- Contract tests prove that the client sends the accepted V1 request and that
  the companion returns the accepted correlated typed plan and validation.
- The end-to-end test proves canonical rendering of the two accepted commands
  and zero calls to the PyMOL mutation seam.
- Negative tests prove that every malformed, unauthorized, unsupported, or
  invalid response produces a typed failure with no rendered action plan.
- Build, test, dependency-boundary, lint, format, and type checks pass without
  changing lockfiles or introducing a training dependency into the runtime
  closure.

## Risks and handoff

- **Unresolved protocol contracts:** The current authority does not define the
  failure envelope, bootstrap interface, or fixture snapshot type. Resolve
  these before build; do not infer them from test convenience.
- **Concurrent T-01 work:** The runtime must use, not reproduce, shared-core
  types and canonical serialization. If its accepted symbols or behavior differ
  from this plan, revise the plan and integrate at the delivery-plan checkpoint.
- **PyMOL test fidelity:** A headless test double proves that this path does not
  call its mutation seam, not that Open-Source PyMOL is qualified. Retain real
  PyMOL and platform testing as later evidence.
- **Security boundary:** Any listener outside loopback, persistent or
  command-line credential, redirect, retry, raw-plan response, or mutation
  request exceeds this task and returns control to the design owner.

**Next action:** Record the four decision-gate contracts in the runtime design,
then review this plan against them before a separate Build session starts.
