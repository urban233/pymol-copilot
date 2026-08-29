# Process Architecture Design

**Status:** Draft
**Owner:** Hannah Kullik (`kullik01`)
**Reviewers:** Martin Urban (`urban233`)
**Brief:** [`SPECIFICATION.md`](../../../../SPECIFICATION.md)
**Parent design:** [Runtime Application and PyMOL Integration Design](design.md)
**Last reviewed:** 2026-08-22

## Summary

This design defines the two processes the runtime runs and the channel
between them. A thin client inside Open-Source PyMOL registers the Copilot
commands through `cmd.extend()`; a separately managed server process holds
everything else.

The recommended V1 process boundary is authenticated HTTP/JSON over an
ephemeral loopback port. It is portable across Windows, macOS, and Linux,
keeps machine-learning and orchestration dependencies out of PyMOL's Python
process, and permits contract testing from both sides. The client starts one
server per PyMOL process and uses an unguessable per-session credential
delivered through the inherited startup channel rather than a command-line
argument or a persistent file.

The registry in this design enforces the session-level limits the rest of the
runtime assumes: one active request, one immutable pending action, and one
recovery point per PyMOL session.

This design defines the transport and the command surface. What travels over
that transport is covered by [Request pipeline](request-pipeline.md) and
[Approval and recovery](approval-and-recovery.md).

## Goals and non-goals

See the parent design's [Goals and non-goals](design.md#goals-and-non-goals)
for the goals and non-goals that constrain more than one child. This design
adds:

### Goals

- Keep LangGraph, inference, and most application dependencies outside the
  Open-Source PyMOL process.
- Provide a minimal cross-platform `cmd.extend()` client with an explicit,
  testable, two-command approval protocol.

### Non-goals

- Running LangGraph or Lemonade inside PyMOL's Python process.

## Current system and evidence

The repository has no active client, server, or transport implementation.
See the parent design's
[Current system and evidence](design.md#current-system-and-evidence) for the
accepted specification decisions this design must satisfy -- most directly, a
separate server process with a thin PyMOL client, command-only V1
interaction through `cmd.extend()`, and explicit plan-ID approval rather than
blocking stdin.

Cross-platform process management and PyMOL command-thread responsiveness
remain unverified assumptions and appear as blocking open questions in this
design.

## Proposed design

This section covers the four components that make up the two processes and
their channel, the startup sequence that brings them to readiness, and the
three contracts other designs depend on.

### Components and ownership

Hannah owns every component below, and every one of them is new.

| Component | Responsibility |
|---|---|
| PyMOL client | Register commands, extract live state, render results, approve actions, execute typed plans, and save and restore sessions |
| Server lifecycle manager | Start, authenticate, health-check, and stop one server for the owning PyMOL process |
| Loopback protocol | Carry versioned local requests, results, cancellation, and apply outcomes between client and server |
| Session and request registry | Enforce one active request, one pending action, expiry, supersession, and contract identity |

The client is a high-trust component because it is the only one permitted to
mutate the live session. Everything that can live in the server does.

### Data and control flow

The client brings the server to readiness before any request can run:

1. On the first Copilot command, the client ensures that one server exists
   for the current PyMOL process.
2. The client and server establish an ephemeral credential through the
   inherited startup channel. The server binds only to an ephemeral
   loopback address and reports its port through that channel.
3. The server starts or connects only to its managed Lemonade child,
   verifies exact engine and model identity, and runs a grammar capability
   probe. [Request pipeline](request-pipeline.md) owns what that probe
   requires.
4. The client and server exchange protocol and shared-contract manifests.
   Incompatibility leaves Copilot unavailable but does not affect PyMOL.

Once readiness holds, `copilot <intent>` enters the flow described in
[Request pipeline](request-pipeline.md#data-and-control-flow).

### Session and request registry

The registry binds one client identity to one server per PyMOL process.
It holds the single active request, the single pending action, their
expiries, and the contract identity in force when each was created.

Server restart, protocol change, model change, session change, or expiry
invalidates outstanding pending actions. A new `copilot` request cancels or
supersedes prior pre-apply work and consumes the prior pending action.

### APIs and contracts

Hannah owns every contract below. The protocol's exact HTTP paths are private
implementation details; the message schemas, guarantees, identity rules, and
fixtures are the architectural contracts.

| Contract | Consumers | Compatibility policy |
|---|---|---|
| PyMOL command surface | User | Additive command changes within V1; a behavior change requires design review |
| Client-server protocol | Client, server | Same-major only after bidirectional fixtures; otherwise refuse readiness |
| Session registration | Client, server | Session protocol versioned with the client-server protocol |

**PyMOL command surface**
- Guarantees: `copilot` is non-mutating; apply, reject, and rollback require
  exact opaque identifiers.
- Errors: unknown, stale, expired, or mismatched identifiers fail without
  mutation.
- Test/fixture: headless command fixtures and GUI-console smoke tests.

**Client-server protocol**
- Guarantees: authenticated loopback-only JSON with request and session
  correlation and bounded payloads.
- Errors: typed schema, authentication, readiness, cancellation, and deadline
  failures.
- Test/fixture: both-side contract suite plus wrong-token and
  version-mismatch probes.

### Initial client-server fixture

The initial protocol fixture defines the request and validated response for the
non-mutating `select`/`color` slice. HTTP paths remain private. The ephemeral
loopback credential is an HTTP header, not a JSON field.

The schemas use JSON Schema 2020-12. The V1 schemas reject unrecognized
fields. A protocol change publishes a new schema version and its bidirectional
fixture. `requestId`, `sessionId`, and `planId` are UUIDv4 identifiers for
correlation, not authorization. The client's `createdAt` is diagnostic; the
server's `receivedAt` and `validatedAt` record authoritative server times.
All timestamps use RFC 3339 UTC format.

**`PlanRequestV1` — client to server**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:pymol-copilot:protocol:PlanRequestV1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "protocolVersion",
    "requestId",
    "sessionId",
    "createdAt",
    "contractManifest",
    "intent",
    "snapshot"
  ],
  "properties": {
    "protocolVersion": {"const": "1"},
    "requestId": {"type": "string", "format": "uuid"},
    "sessionId": {"type": "string", "format": "uuid"},
    "createdAt": {"type": "string", "format": "date-time"},
    "contractManifest": {"$ref": "ContractManifestV1.schema.json"},
    "intent": {"type": "string", "minLength": 1, "maxLength": 4096},
    "snapshot": {"$ref": "StructureSnapshotV1.schema.json"}
  }
}
```

The contract fixture supplies this request. Its `snapshot` value is a local
test instance of `StructureSnapshotV1`; production messages carry the complete
canonical snapshot rather than a fixture identifier.

```json
{
  "protocolVersion": "1",
  "requestId": "11111111-1111-4111-8111-111111111111",
  "sessionId": "22222222-2222-4222-8222-222222222222",
  "createdAt": "2026-08-26T14:22:03.123Z",
  "contractManifest": {
    "planVersion": "1",
    "policyVersion": "1",
    "snapshotVersion": "1"
  },
  "intent": "Select chain A and color it red.",
  "snapshot": {
    "schemaVersion": "1",
    "digest": "sha256:example-chain-a-digest",
    "fixtureId": "one-object-chain-a-v1"
  }
}
```

**`ValidatedPlanResponseV1` — server to client**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:pymol-copilot:protocol:ValidatedPlanResponseV1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "protocolVersion",
    "requestId",
    "sessionId",
    "receivedAt",
    "validatedAt",
    "status",
    "actionPlan",
    "validation"
  ],
  "properties": {
    "protocolVersion": {"const": "1"},
    "requestId": {"type": "string", "format": "uuid"},
    "sessionId": {"type": "string", "format": "uuid"},
    "receivedAt": {"type": "string", "format": "date-time"},
    "validatedAt": {"type": "string", "format": "date-time"},
    "status": {"const": "validated"},
    "actionPlan": {"$ref": "ActionPlanV1.schema.json"},
    "validation": {"$ref": "ValidationReportV1.schema.json"}
  }
}
```

The contract fixture expects this response. `actionPlan.commands` is the only
plan representation on the wire; the client renders canonical `.pml` through
the shared-core serializer.

```json
{
  "protocolVersion": "1",
  "requestId": "11111111-1111-4111-8111-111111111111",
  "sessionId": "22222222-2222-4222-8222-222222222222",
  "receivedAt": "2026-08-26T14:22:03.124Z",
  "validatedAt": "2026-08-26T14:22:03.220Z",
  "status": "validated",
  "actionPlan": {
    "planId": "33333333-3333-4333-8333-333333333333",
    "planVersion": "1",
    "snapshotDigest": "sha256:example-chain-a-digest",
    "commands": [
      {
        "verb": "select",
        "name": "copilot_selection",
        "expression": "chain A"
      },
      {
        "verb": "color",
        "color": "red",
        "target": "copilot_selection"
      }
    ]
  },
  "validation": {
    "status": "passed",
    "snapshotDigest": "sha256:example-chain-a-digest",
    "warnings": []
  }
}
```

The server returns a separate typed failure response for invalid input or an
unsuccessful validation. It returns neither a partial action plan nor raw
model `.pml` text.

**Session registration**
- Guarantees: one client identity and one server per PyMOL process.
- Errors: a duplicate or stale session is rejected; there is no automatic
  cross-session reuse.
- Test/fixture: restart, duplicate, stale, and credential-rotation tests.

## Alternatives and trade-offs

| Option | Benefits | Costs/risks | Decision |
|---|---|---|---|
| Run all runtime code inside PyMOL | Simplest communication and packaging | Dependency conflicts and failures share the user's PyMOL process | Rejected by specification; separate server |
| Unix domain sockets | Filesystem permissions and no TCP listener | Inconsistent Windows behavior and cleanup | Rejected for V1 cross-platform baseline |
| Stdio for all client-server traffic | No local listening socket | Harder persistent request correlation, cancellation, and recovery after stream corruption | Rejected; retain startup channel only |
| HTTP/JSON on loopback | Cross-platform libraries, inspectable fixtures, simple versioning | Requires authentication and strict bind checks | Recommended for V1 |
| Synchronous blocking `copilot` | Simple command semantics | May freeze the PyMOL user interface during CPU inference | Provisional V1 default pending reference-environment responsiveness evidence |
| Asynchronous request plus status command | Responsive user interface and cancellation | Expands the command protocol and PyMOL thread-safety surface | Fallback if the synchronous command violates usability or platform behavior |

## Quality and risk

- **Security/privacy:** The client is a high-trust component and must remain
  minimal. It accepts only authenticated, version-compatible typed artifacts
  and independently rechecks policy. The server binds only to loopback and
  uses an ephemeral credential.
- **Reliability/concurrency:** One active request and one pending action
  prevent ordering ambiguity.

## Test strategy

- Unit tests for session and request state identity, expiry, and
  supersession.
- Bidirectional client-server schema and compatibility fixtures.
- Wrong-token, non-loopback-bind, oversized-payload, replay, stale-session,
  and version-mismatch security tests.
- Headless Open-Source PyMOL command tests for `copilot`, apply, reject, and
  rollback behavior.
- GUI-console smoke tests on each candidate platform, including command
  responsiveness during representative inference.

## Migration, rollout, rollback, and cleanup

Covered by the parent design's
[Migration, rollout, rollback, and cleanup](design.md#migration-rollout-rollback-and-cleanup),
since the client and server are qualified and rolled back as one
compatible pair with the rest of the runtime.

## Open questions

Each question below is specific to this design. Hannah owns both.

| Question | Evidence needed | Blocking? |
|---|---|---|
| Is authenticated loopback HTTP available and sufficiently isolated in every candidate Open-Source PyMOL environment? | Cross-platform startup, bind, credential, firewall, and teardown probes | Yes, before protocol acceptance |
| Can `copilot` wait synchronously without unacceptable GUI freezing or unsafe PyMOL threading behavior? | GUI-console responsiveness tests with representative model latency | Yes, before command-flow acceptance; the asynchronous status flow is the fallback |

## Acceptance

- [ ] Material decisions resolved.
- [ ] Cross-platform startup, bind, and teardown evidence accepted.
- [ ] Accountable human accepts planning against this design.
