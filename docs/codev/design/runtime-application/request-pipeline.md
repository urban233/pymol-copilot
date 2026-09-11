# Request Pipeline Design

**Status:** Draft
**Owner:** Hannah Kullik (`kullik01`)
**Reviewers:** Martin Urban (`urban233`)
**Brief:** [`SPECIFICATION.md`](../../../../SPECIFICATION.md)
**Parent design:** [Runtime Application and PyMOL Integration Design](design.md)
**Last reviewed:** 2026-09-09

**2026-09-09 reconciliation:** The merged client/server preview proves a
non-mutating fixed request path, but it does not implement LangGraph,
inference, snapshot export, reconstruction, or sidecar execution. The next
wave selected a full-V1 state contract. This design returns to `Draft` until
shared-core discovery establishes the sidecar invocation boundary it consumes.

## Summary

This design turns one user intent into one validated plan, or into a typed
failure. It covers the LangGraph graph that routes the request, the inference
abstraction and its first Lemonade adapter, the snapshot exporter, and the
sidecar manager that validates every attempt in a fresh disposable
Open-Source PyMOL process.

The recommended shape keeps LangGraph small: the graph contains only
decisions that branch, terminate, or retry, and every pure function stays
outside it. The graph permits one initial model call and at most two repair
calls, and a hostile failure class receives none.

Validation is the gate that makes the rest of the runtime safe. Generation
runs against one exact live-state snapshot, and only exact snapshot fidelity
plus a passing sidecar report can produce a pending plan.

This design ends at that pending plan. Rendering it, approving it, and
applying it are covered by
[Approval and recovery](approval-and-recovery.md). The transport that carries
the request is covered by [Process architecture](process-architecture.md).

## Goals and non-goals

See the parent design's [Goals and non-goals](design.md#goals-and-non-goals)
for the goals and non-goals that constrain more than one child; they apply
here unchanged. This design adds:

### Goals

- Manage Lemonade lifecycle and capability checks locally without remote or
  unconstrained fallback.
- Generate against one exact live-state snapshot and validate each attempt in
  a fresh disposable Open-Source PyMOL sidecar.

## Current system and evidence

The repository has a fixed authenticated loopback preview in `pmc_client` and
`pmc_server`. It has no active graph, inference, snapshot exporter, or sidecar
implementation. See
the parent design's
[Current system and evidence](design.md#current-system-and-evidence) for the
accepted specification decisions this design must satisfy -- most directly,
LangGraph from V1, Lemonade as the first inference adapter, and exact sidecar
fidelity or fail-closed apply.

Lemonade grammar behavior and live-state export fidelity remain unverified
assumptions and appear as blocking open questions in this design.

## Proposed design

This section covers the five components between an accepted intent and a
validated plan, the numbered flow through them, the graph's state model, and
the three contracts other designs depend on.

### Components and ownership

Hannah owns every component below, and every one of them is new.

| Component | Responsibility |
|---|---|
| LangGraph request graph | Coordinate deterministic preparation, bounded inference, parsing and policy, validation, repair, and terminal routing |
| Inference abstraction | Expose capability discovery, bounded completion, cancellation, and typed local-engine errors |
| Lemonade adapter | Manage the first local inference process and translate the engine protocol into the abstraction |
| Snapshot exporter | Export relevant live state through the shared snapshot contract without model involvement |
| Sidecar manager | Start a fresh Open-Source PyMOL process per attempt, load the snapshot, execute through the shared protocol, and terminate |

### Data and control flow

A loaded-object request proceeds through these steps. Startup and readiness
happen first, in
[Process architecture](process-architecture.md#data-and-control-flow).

1. `copilot <intent>` resolves one target object deterministically. Ambiguity
   returns a non-mutating clarification. If no suitable object is loaded, the
   request instead enters the controlled fetch flow in
   [Approval and recovery](approval-and-recovery.md#controlled-fetch-request).
2. The client exports the shared relevant-state snapshot and digest on the
   live PyMOL thread.
3. The server creates immutable request state. LangGraph computes the card
   and grammar exactly once.
4. Inference produces restricted native plan text. Clarification and no-op
   forms are classified before parsing.
5. The shared parser and command policy produce an immutable allowed plan or
   a typed failure. Ordinary correctable failures may enter the bounded
   repair loop; hostile classes terminate immediately.
6. The sidecar manager starts a fresh PyMOL process, reconstructs the
   snapshot, checks fidelity, executes the typed plan, and returns validation
   evidence.
7. Only exact fidelity and a passing report can produce a pending plan, which
   [Approval and recovery](approval-and-recovery.md) then owns.

The live session remains unchanged throughout every step in this sequence.

#### Initial implementation fixture

The first non-mutating runtime slice consumes and renders only the shared
core's `select` and `color` `.pml` fixture:

```pml
select copilot_selection, chain A
color red, copilot_selection
```

It may use a deterministic local completion fixture while model integration
remains unplanned. The client does not apply the resulting plan to the live
session.

### LangGraph state model

LangGraph contains only decisions that branch, terminate, or retry. Pure
parsing, policy, normalization, and rendering helpers remain ordinary
shared-core or runtime functions.

```text
received
  -> resolve_target
      -> fetch_pending | ask | snapshot
  -> prepare_context
  -> generate
      -> ask | noop | parse_and_policy
  -> validate_sidecar
      -> pending_plan
      -> repair -> generate
      -> failed
```

The graph permits one initial model call and at most two repair calls. An
ordinary denied command receives at most one repair; a hostile security
class, a path or network escape, an invalid manifest, or a fidelity failure
receives none.

Apply and rollback happen outside this graph, and their result transitions
are recorded back into server request state.

### APIs and contracts

Hannah owns every contract below.

| Contract | Consumers | Compatibility policy |
|---|---|---|
| Copilot request | Client, LangGraph | Additive optional fields only, with deterministic defaults |
| Inference abstraction | LangGraph, Lemonade adapter | Engine adapters may vary behind one semantic contract |
| Sidecar invocation | LangGraph, sidecar manager | The shared snapshot and execution manifest must match |

**Copilot request**
- Guarantees: immutable intent, target hints, snapshot, contract manifest,
  and limits.
- Errors: an invalid snapshot, manifest, or size fails before inference.
- Test/fixture: golden loaded-object, ambiguity, no-object, and oversized
  requests. The first client-server message shapes are defined in
  [Initial client-server fixture](process-architecture.md#initial-client-server-fixture).

**Inference abstraction**
- Guarantees: local bounded completion, grammar capability, cancellation, and
  engine and model identity.
- Errors: typed unavailable, timeout, cancelled, grammar-ignored, and
  malformed-response failures.
- Test/fixture: fake engine plus a pinned Lemonade conformance suite.

**Sidecar invocation**
- Guarantees: fresh process, exact snapshot reconstruction, shared execution
  protocol, and unconditional termination.
- Errors: spawn, load, fidelity, timeout, resource, and execution failures,
  with no internal retry.
- Test/fixture: process leak, state leak, fidelity, timeout, and
  forced-crash tests.

H-02's fresh-process execution-boundary prototype
(`tests/discovery/h02/execution_boundary.py`) demonstrated this boundary's
request and report shape: a fresh process per attempt, reconstruction from
the snapshot alone (never the original source), command-indexed outcomes,
unconditional termination with the child reaped on every exit path --
including the exception path between spawn and completion -- scratch-data
cleanup on every exit path, and typed, fail-closed reasons with no internal
retry, demonstrated by an attempt-counter probe distinguishing "attempted
once" from "attempted, then silently retried" (see the
[H-02 evidence](../../wave/evidence/H-02.md)). The report itself now carries
the spawned child's own process identity and its observed termination,
rather than that guarantee being observable only through a test-only hook.

Only two of the finite-resource limits above were actually prototyped:
maximum input size in bytes, and a wall-clock deadline. No memory bound was
prototyped; a passing report from this prototype is evidence for those two
limits only, not for the full finite-resources guarantee. Exactly which
request, report, limit, and teardown contract this evidence feeds into one
shared full-V1 executor is
[plan and execution](plan-and-execution.md#open-questions)'s own open
question, owned by Martin; this prototype supplies evidence toward it and
does not decide it.

## Alternatives and trade-offs

| Option | Benefits | Costs/risks | Decision |
|---|---|---|---|
| User-managed model server | Less process-management code | Poor installation experience and uncontrolled endpoint and security properties | Rejected; the server manages Lemonade |
| Validate by reloading the original file | Low serialization cost | Wrong for modified live objects | Rejected; exact live-state snapshot |
| Produce a pending plan after static or degraded validation | Higher availability | Can act against untested state | Rejected; fail closed |

## Quality and risk

- **Security/privacy:** The server never exposes a remote model fallback.
  Lemonade output is untrusted until the shared parser and policy accept it.
- **Reliability/concurrency:** Retries are bounded in LangGraph and never
  cross apply.

## Test strategy

- Unit tests for LangGraph routing, retry caps, and cancellation.
- Fake-engine tests for every inference error, and real Lemonade tests for
  model identity, grammar enforcement, timeout, cancellation, and malformed
  responses.
- Fresh-sidecar lifecycle, process-leak, state-leak, snapshot-fidelity,
  timeout, crash, and resource-bound tests.

## Migration, rollout, rollback, and cleanup

Covered by the parent design's
[Migration, rollout, rollback, and cleanup](design.md#migration-rollout-rollback-and-cleanup),
since the server and model artifact are qualified and rolled back as one
compatible pair with the rest of the runtime.

## Open questions

Each question below is specific to this design. Hannah owns both.

| Question | Evidence needed | Blocking? |
|---|---|---|
| Does Lemonade expose enforceable per-request grammar, cancellation, model identity, and CPU and iGPU (integrated GPU) behavior on the reference environment? | Pinned real-engine conformance report | Yes, before Lemonade adapter acceptance |
| Which live-state serialization and reconstruction path passes exact fidelity on modified, multi-state, and altloc-bearing objects (atoms modeled in more than one position)? | Shared-core snapshot differential evidence -- produced, see the [H-02 evidence](../../wave/evidence/H-02.md) | Yes, before sidecar design acceptance |

## Acceptance

- [ ] Material decisions resolved.
- [ ] Real-engine conformance and snapshot-fidelity evidence accepted.
- [ ] Accountable human accepts planning against this revised design.
