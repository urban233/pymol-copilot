# Runtime Application and PyMOL Integration Design

**Status:** Draft
**Owner:** Hannah Kullik (`kullik01`)
**Reviewers:** Martin Urban (`urban233`); model-execution security reviewer to be named
**Brief:** [`SPECIFICATION.md`](../../../../SPECIFICATION.md)
**Last reviewed:** 2026-08-22

## Summary

The V1 runtime is a local companion application, not a monolithic PyMOL
plugin. A thin bridge loaded into Open-Source PyMOL exposes the command
interface and is the only component allowed to read or mutate the live
session. A separately managed companion process owns LangGraph, request
state, shared-core clients, local inference orchestration, sidecar
validation, and diagnostics.

The runtime covers three independently reviewable areas, each with its own
design document:

1. [Process architecture](process-architecture.md) -- the bridge, the
   companion lifecycle, the authenticated loopback transport between them,
   and the session and request registry. Needs cross-platform startup and
   isolation evidence.
2. [Request pipeline](request-pipeline.md) -- the LangGraph graph, local
   inference through Lemonade, and fresh-sidecar validation of every
   attempt. Needs real-engine conformance evidence.
3. [Approval and recovery](approval-and-recovery.md) -- pending actions,
   controlled PDB (Protein Data Bank) fetch, apply, automatic restore, and
   manual rollback. Needs the model-execution security reviewer.

This parent design owns what binds the three together: the process and trust
boundary, the no-live-mutation invariant, local diagnostics, and the
platform-qualification and rollout sequence.

The single safety invariant behind all three is that no model output reaches
the live session before parser, policy, sidecar, session-freshness, and
user-approval checks all pass. The bridge is the sole live-session mutation
boundary, and it rechecks that invariant independently of the companion.

This design consumes the contracts in
[`Shared Core and Contracts Design`](../shared-core/design.md) and does not
redefine them. The accepted specification remains authoritative for product
scope and safety invariants.

## Goals and non-goals

These are the cross-cutting goals and non-goals that constrain more than one
child design. Each child design linked in the Summary states the goals and
non-goals specific to its own area.

### Goals

- Ensure no model output reaches the live session before parser, policy,
  sidecar, session-freshness, and user-approval checks all pass.
- Produce actionable local diagnostics without remote telemetry or raw
  session data retention.

### Non-goals

- A V1 panel, editable plan, open-ended conversation, or token streaming.
- Supporting Incentive PyMOL.
- Multiple simultaneous requests, pending plans, or rollback points per
  PyMOL session.
- Deciding whether a plan matches the user's scientific intent.
- Defining shared plan, policy, card, grammar, error, or execution semantics.
- Cloud fallback or remote diagnostics.

## Current system and evidence

No runtime product code or test environment currently exists in the
repository. The accepted specification fixes these runtime decisions:

- a separate companion process with a thin PyMOL bridge;
- LangGraph from V1;
- Lemonade as the first inference adapter;
- Open-Source PyMOL only;
- command-only V1 interaction through `cmd.extend()`;
- explicit plan-ID approval rather than blocking stdin;
- controlled pre-fetch rather than model-generated fetch;
- exact sidecar fidelity or fail-closed apply;
- automatic restore and one-level manual rollback; and
- CPU and iGPU (integrated GPU) first runtime on evidence-qualified candidate
  platforms.

Each child design cites the subset of these decisions it must satisfy.

Unverified repository assumptions remain around Lemonade grammar behavior,
PyMOL command-thread responsiveness, cross-platform process management,
live-state export, and `.pse` (PyMOL session file) restore fidelity. They are
design acceptance evidence, not implementation details to assume away.

## Proposed design

Each child design records its own components, flow, contracts, and
alternatives -- see the linked document for that detail. This section covers
the one cross-cutting component, the trust boundary between the three areas,
and how a request crosses them.

### Components and ownership

Hannah owns every runtime component, and every one of them is new. Only the
apply and recovery controller in
[Approval and recovery](approval-and-recovery.md) additionally requires
security review.

The cross-cutting component below belongs to no single child:

| Component | Responsibility |
|---|---|
| Local diagnostics | Record versions, stage timings, bounded reason codes, and redacted support evidence |

The child designs contribute the remaining twelve components:

| Design | Components |
|---|---|
| [Process architecture](process-architecture.md) | PyMOL bridge, companion lifecycle manager, loopback protocol, session and request registry |
| [Request pipeline](request-pipeline.md) | LangGraph request graph, inference abstraction, Lemonade adapter, snapshot exporter, sidecar manager |
| [Approval and recovery](approval-and-recovery.md) | Pending-action renderer, controlled fetch controller, apply and recovery controller |

### Process and trust boundaries

The diagram shows which processes exist and which of them may touch the live
session. The detailed flow inside each area is in the linked child design.

```mermaid
flowchart LR
    U[User] -->|PyMOL commands| B[Thin bridge in Open-Source PyMOL]
    B <-->|HTTP JSON + ephemeral credential on loopback| C[Companion]
    C --> G[LangGraph request graph]
    G --> K[Shared core]
    G --> I[Inference abstraction]
    I --> L[Lemonade process]
    B -->|relevant-state snapshot| C
    C -->|snapshot + typed plan| S[Fresh PyMOL sidecar]
    S -->|validation report| C
    C -->|immutable pending action| B
    B -->|approved typed plan| P[(Live PyMOL session)]
    B -->|save/restore| R[(Private local PSE recovery point)]
    B -->|approved accession only| F[PDB source]
```

The bridge trusts only version-compatible, authenticated companion responses
and shared-core typed artifacts. The companion treats user intent, model
output, engine output, snapshots, and sidecar output as untrusted until their
respective schemas and contracts pass. Lemonade never receives authority to
call tools or the bridge.

The bridge is the sole live-session mutation boundary. The companion can
request that a typed approved operation be performed, but the bridge
independently rechecks session, plan, policy, manifest, and approval state.

### Data and control flow

One request crosses all three areas in a fixed order. Each child design
carries the numbered steps for its own part.

```mermaid
flowchart TD
    ST["Startup and readiness (Process architecture)"] --> RQ["Generation and validation (Request pipeline)"]
    RQ --> PN["Pending action (Approval and recovery)"]
    PN --> AP["Apply, restore, rollback (Approval and recovery)"]
    AP -->|result transitions| RQ
```

Apply and rollback are bridge-owned consequential operations outside the
model loop; their results are recorded back into companion request state.

### APIs and contracts

The runtime defines ten contracts, all owned by Hannah, and each is
documented in the child design that owns it:

- [Process architecture](process-architecture.md#apis-and-contracts) --
  PyMOL command surface, bridge-companion protocol, session registration.
- [Request pipeline](request-pipeline.md#apis-and-contracts) -- Copilot
  request, inference abstraction, sidecar invocation.
- [Approval and recovery](approval-and-recovery.md#apis-and-contracts) --
  pending action, controlled fetch action, apply result, recovery point.

## Alternatives and trade-offs

Each child design records the alternatives specific to its own area: see
[Process architecture](process-architecture.md#alternatives-and-trade-offs),
[Request pipeline](request-pipeline.md#alternatives-and-trade-offs), and
[Approval and recovery](approval-and-recovery.md#alternatives-and-trade-offs).

## Quality and risk

- **Security/privacy:** Diagnostics do not log raw intents or structure
  context by default. Each child design covers the controls for its own
  area; see
  [Process architecture](process-architecture.md#quality-and-risk),
  [Request pipeline](request-pipeline.md#quality-and-risk), and
  [Approval and recovery](approval-and-recovery.md#quality-and-risk).
- **Reliability/concurrency:** Every child process the runtime owns has
  finite readiness and request deadlines, explicit cancellation, and
  unconditional teardown.
- **Observability/capacity/cost:** Local structured events record
  correlation and contract/model versions, stage timings, state transitions,
  typed failures, and resource use without sensitive payloads. CPU, iGPU,
  memory, model, sidecar, and `.pse` costs are measured on named laboratory
  hardware before support claims.
- **Accessibility/internationalization:** V1 uses the PyMOL command console
  and therefore inherits its accessibility limits. Output must remain plain
  text, keyboard-operable, ordered, copyable, and free of color-only
  meaning. Commands and numeric syntax are locale-independent; user-facing
  explanation may retain Unicode. The V2 panel must consume the same
  contracts rather than replacing safety behavior.

## Test strategy

These suites span all three child areas. Each child design also has its own
area-specific test list.

- No-live-mutation property tests across parse, policy, model, sidecar,
  fetch rejection, cancellation, expiry, user rejection, and companion
  failure paths.
- Sabotage tests proving the no-mutation suite detects live writes.
- Per-stage p50 and p95 (median and 95th-percentile) latency and peak memory
  on every supported platform entry.

## Migration, rollout, rollback, and cleanup

No installed V1 runtime exists to migrate. The first thin vertical slice
ends at plan rendering without apply. Controlled fetch, apply, and rollback
remain unreachable until shared-core, sidecar-fidelity, and `.pse` recovery
evidence is accepted.

Runtime qualification proceeds per exact combination of operating system,
Open-Source PyMOL, Python, Lemonade, and model. Failure on one candidate does
not weaken another and may remove that platform from V1. The companion and
model artifact are promoted as a compatible pair with their shared-core
manifest.

Application rollback restores the prior compatible bridge, companion, shared
core, Lemonade configuration, and model set. Request rollback restores only
the one retained `.pse` recovery point. Companion exit removes ephemeral
credentials, pending actions, sidecars, and scratch snapshots. Recovery files
are deleted when consumed, replaced, explicitly discarded, or the owning
PyMOL session ends.

No release step enables apply by configuration alone; apply availability is a
result of passing compatibility, security, sidecar, and recovery readiness
checks.

## Open questions

Each question below blocks more than one child design; a question specific to
one area is recorded in that child design instead.

| Question | Owner | Evidence needed | Blocking? |
|---|---|---|---|
| What finite request, inference, sidecar, fetch, pending-action, and shutdown deadlines fit the measured laboratory-hardware envelope? | Hannah | Per-stage latency distribution and failure tests | No; values freeze before runtime release |
| Who is the independent model-execution security reviewer? | Martin | Named reviewer and recorded availability | Yes, before [Approval and recovery](approval-and-recovery.md) is `Accepted` |

## Acceptance

- [ ] Material cross-cutting decisions resolved.
- [ ] [Process architecture](process-architecture.md) is `Accepted`.
- [ ] [Request pipeline](request-pipeline.md) is `Accepted`.
- [ ] [Approval and recovery](approval-and-recovery.md) is `Accepted`.
- [ ] Accountable human accepts planning against this design.
