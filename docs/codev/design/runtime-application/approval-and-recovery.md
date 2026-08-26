# Approval and Recovery Design

**Status:** Draft
**Owner:** Hannah Kullik (`kullik01`)
**Reviewers:** Martin Urban (`urban233`)
**Brief:** [`SPECIFICATION.md`](../../../../SPECIFICATION.md)
**Parent design:** [Runtime Application and PyMOL Integration Design](design.md)
**Last reviewed:** 2026-08-22

## Summary

This design covers every point at which the runtime asks the user for
authority and every point at which it changes the live PyMOL session. It owns
pending actions, controlled PDB (Protein Data Bank) fetch, apply, automatic
restore, and manual rollback.

Two commands carry the whole approval protocol. `copilot` never mutates the
session. `copilot_apply <id>` approves either a controlled fetch action or an
already validated plan. A fetch approval loads the requested accession and
resumes the original request, which still requires a second approval for its
generated plan.

Apply is fail-closed and self-restoring. It creates a recovery point as a
`.pse` (PyMOL session file), stops on the first command failure, and
automatically restores the snapshot. One explicit manual rollback remains
available after success, and a failed restore halts Copilot entirely rather
than continuing against uncertain state.

This design consumes the validated plan produced by
[Request pipeline](request-pipeline.md) and the command surface defined by
[Process architecture](process-architecture.md#apis-and-contracts).

## Goals and non-goals

See the parent design's [Goals and non-goals](design.md#goals-and-non-goals)
for the goals and non-goals that constrain more than one child. This design
adds:

### Goals

- Support controlled PDB fetching without allowing model-directed network
  destinations.
- Automatically restore the complete pre-apply `.pse` snapshot on partial
  apply failure, and retain one manual rollback point after success.

### Non-goals

- Model-generated fetch, load, save, export, delete, extract, file paths, or
  molecular-data mutation.

## Current system and evidence

The repository has no active approval, fetch, apply, or recovery
implementation. See the parent design's
[Current system and evidence](design.md#current-system-and-evidence) for the
accepted specification decisions this design must satisfy -- most directly,
explicit plan-ID approval rather than blocking stdin, controlled pre-fetch
rather than model-generated fetch, and automatic restore with one-level
manual rollback.

`.pse` restore fidelity remains an unverified assumption and appears as a
blocking open question in this design.

## Proposed design

This section covers the three components that hold user authority, the three
flows they implement, and the four contracts other designs depend on.

### Components and ownership

Hannah owns every component below, and every one of them is new. The apply
and recovery controller requires accepted safety evidence because it is the
only component that writes to the live session.

| Component | Responsibility |
|---|---|
| Pending-action renderer | Present exact fetch or plan actions, validation evidence, warnings, expiry, and approval commands |
| Controlled fetch controller | Validate and apply an explicitly approved PDB accession before plan generation |
| Apply and recovery controller | Recheck pending plan identity, save `.pse`, dispatch exact commands, auto-restore failure, and perform manual rollback |

### Pending actions

A pending action is immutable and is bound to an opaque identifier, the
session digest, the model and contract identities, its creation time, and a
finite expiry. The renderer shows the canonical commands, selection counts,
warnings, and -- explicitly -- what was not checked.

Only exact snapshot fidelity and a passing sidecar report can produce a
pending plan; see
[Request pipeline](request-pipeline.md#data-and-control-flow) for how that
report is produced.

### Controlled fetch request

Fetch is the only ordinary external network operation the runtime performs,
and the model never chooses its destination.

1. If no suitable object is loaded and the intent includes one syntactically
   valid PDB accession, preparation returns a pending fetch action containing
   only the accession and the configured source identity.
2. `copilot_apply <fetch-id>` rechecks the pending action and displays that a
   network operation will occur. The bridge performs the fetch through the
   reviewed PyMOL API.
3. Fetch failure is terminal and produces no plan. Fetch success resumes the
   original request from target resolution with the loaded object.
4. The resulting generated plan receives a new plan identifier and requires a
   separate `copilot_apply` command.

### Approval and apply

Apply is the only path that mutates the live session, and it rechecks
everything before it writes.

1. `copilot_apply <plan-id>` looks up exactly one immutable pending plan.
2. The bridge recomputes the relevant live digest and verifies session
   identity, expiry, model identity, contract manifest, and command policy.
   Any mismatch invalidates the plan without mutation.
3. The bridge writes a private, plan-associated `.pse` snapshot and verifies
   that the file exists and is readable before mutation begins.
4. The exact canonical typed plan is executed through the same shared
   dispatcher semantics used by the sidecar. No regeneration occurs.
5. On the first command failure, the bridge halts apply and restores the
   `.pse`. Copilot remains halted if restore or differential verification
   fails.
6. On success, the snapshot becomes the one manual recovery point. A
   subsequent successful apply replaces it.

### Rejection, supersession, and rollback

- `copilot_reject <id>` consumes a matching pending action without mutation.
- A new `copilot` request cancels or supersedes prior pre-apply work and
  consumes the prior pending action.
- Companion restart, protocol change, model change, session change, or expiry
  invalidates pending actions.
- `copilot_rollback <plan-id>` is accepted only for the retained recovery
  point. It warns that the whole current session will be replaced, then
  restores and verifies the snapshot. Successful rollback consumes that
  recovery point.

### APIs and contracts

Hannah owns every contract below.

| Contract | Consumers | Compatibility policy |
|---|---|---|
| Pending action | Companion, bridge | A major change invalidates all outstanding actions |
| Controlled fetch action | Companion, bridge | Source-policy changes require an explicit privacy and security decision |
| Apply result | Bridge, companion | Must match the pending-plan and execution contract versions |
| Recovery point | Bridge, user | PyMOL, version, and platform-specific qualification required |

**Pending action**
- Guarantees: the opaque identifier binds the exact action, session digest,
  model and contracts, creation time, and expiry.
- Errors: a lookup mismatch is terminal and consumes nothing else.
- Test/fixture: stale session, restart, expiry, supersession, and tamper
  fixtures.

**Controlled fetch action**
- Guarantees: only a validated accession and the configured PDB source, with
  separate approval.
- Errors: rejection, timeout, not-found, and checksum or load failure are
  terminal.
- Test/fixture: known accession, malformed accession, wrong source, offline,
  and rejection tests.

**Apply result**
- Guarantees: exact command-index outcomes, no command after the first
  failure, and recorded restore status.
- Errors: apply failure triggers restore; restore failure halts Copilot.
- Test/fixture: successful apply, partial failure, restore success and
  failure, and duplicate result tests.

**Recovery point**
- Guarantees: one private `.pse` bound to the plan and session, with
  automatic and manual restore semantics.
- Errors: save, read, restore, and digest errors are explicit, with no silent
  continuation.
- Test/fixture: save, mutate, and restore differentials on every supported
  matrix entry.

## Alternatives and trade-offs

| Option | Benefits | Costs/risks | Decision |
|---|---|---|---|
| Let the model emit `fetch` | Natural-looking single plan | The model chooses a network action before structure context exists | Rejected; deterministic separately approved fetch |
| No recovery snapshot | Less disk input and output | Partial apply can leave uncertain state | Rejected; `.pse` save and restore required |

## Quality and risk

- **Security/privacy:** Fetch is the only ordinary external runtime network
  operation and requires separate approval.
- **Reliability/concurrency:** Restore failure halts all further Copilot
  actions.

## Test strategy

- Unit tests for pending-action expiry and restoration halt behavior.
- End-to-end controlled fetch with an approved accession and no generation
  before successful load.
- Deliberate partial apply followed by automatic `.pse` restore and complete
  session differential verification.
- Manual rollback after successful apply, including warning and
  later-session-change behavior.
- Sabotage tests proving the recovery suite detects incomplete restore.

## Migration, rollout, rollback, and cleanup

Covered by the parent design's
[Migration, rollout, rollback, and cleanup](design.md#migration-rollout-rollback-and-cleanup),
since apply availability is gated by the same readiness checks that govern
the rest of the runtime.

## Open questions

Hannah owns the question below.

| Question | Evidence needed | Blocking? |
|---|---|---|
| Does `.pse` restore produce complete session equality after deliberate partial application on each candidate platform? | Recovery differential and sabotage report | Yes, before apply and recovery design acceptance |

## Acceptance

- [ ] Material decisions resolved.
- [ ] Apply and recovery safety evidence accepted.
- [ ] Accountable human accepts planning against this design.
