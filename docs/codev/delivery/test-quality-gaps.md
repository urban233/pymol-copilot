# Initial test-quality follow-up plan

**Status:** Draft
**Owner:** Martin Urban (`urban233`)
**Brief:** [`SPECIFICATION.md`](../../../SPECIFICATION.md)
**Design:** [plan and execution](../design/shared-core/plan-and-execution.md) and [process architecture](../design/runtime-application/process-architecture.md)
**Project tracker:** [T-01](https://github.com/urban233/pymol-copilot/issues/4) and [T-02](https://github.com/urban233/pymol-copilot/issues/3)
**Supersedes:** Not applicable
**Last reviewed:** 2026-08-27

## Changes since last review

- New focused plan created from the testing-craft audit of T-01 tests.
- Q-01 implemented with boundary-claim corrections, sabotage evidence, and a
  three-run uncached baseline.

## Current milestone

**Outcome:** The initial core and client-server tests provide trustworthy
evidence for the non-mutating `select`/`color` slice.

**Evidence:** The core suite detects a deliberate default-deny regression, its
boundary claim matches what it actually verifies, and a real local
client-server test catches a schema or no-mutation integration failure.

**Target:** Not committed.

## Current work

The work contains one narrow/small core test task and one medium-sized,
medium-scope client-server contract task. The latter earns its cost by testing
the real client-server boundary that narrow parser and policy tests cannot
exercise.

| ID | Task | Issue | Status | Blocked by |
|---|---|---|---|---|
| Q-01 | Strengthen core default-deny test evidence | [#4](https://github.com/urban233/pymol-copilot/issues/4) | Done | None |
| Q-02 | Add client-server contract and no-mutation test | [#3](https://github.com/urban233/pymol-copilot/issues/3) | Blocked | T-02 implementation boundary |

### Q-01: Strengthen core default-deny test evidence

- **Owner and reviewer:** Martin Urban (`urban233`); Hannah Kullik
  (`kullik01`) reviews independently.
- **Outcome and acceptance:** Add a bounded mutation or sabotage check that
  proves the focused suite fails when default-deny policy is changed to allow
  an unsupported operation. Rename or replace the current no-dispatcher test
  so it claims only the boundary it proves: the shared core does not import or
  invoke PyMOL. Record a repeated, uncached run of the focused tests as an
  initial flake baseline.
- **Validation:** Run the focused suite with the intentional mutation and
  confirm failure; restore the implementation and confirm a clean run. Run the
  same focused targets repeatedly without cached results and record the pass
  count and any failure. Evidence: `policy_sabotage` passed its intentional
  mutation check, and the four focused targets passed in three consecutive
  uncached runs (`12/12` target executions).
- **Non-goals:** Add production behavior, a PyMOL integration test, coverage
  targets, or a permanent large-test tier.

### Q-02: Add client-server contract and no-mutation test

- **Owner and reviewer:** Hannah Kullik (`kullik01`); Martin Urban
  (`urban233`) reviews independently.
- **Outcome and acceptance:** Exercise the real local client and server
  processes against the accepted `PlanRequestV1` and `ValidatedPlanResponseV1`
  fixtures. Confirm request/session correlation, schema rejection, canonical
  rendering from typed commands, and zero live-session mutation.
- **Validation:** Run the test through the public client command path against
  a disposable PyMOL fixture. Include one malformed message or version-mismatch
  case that returns a typed failure without a partial action plan.
- **Non-goals:** Test model quality, apply, rollback, fetch, or qualification
  on every candidate platform.

## Integration checkpoint

After Q-01 and Q-02 pass, Martin and Hannah review the evidence together. They
confirm that the narrow core checks and the local contract test cover distinct
failure modes, then decide whether the non-mutating slice has enough evidence
to move from development-only to its next planned task.

## Risks and discovery

| Risk or unknown | Impact | Evidence-producing action | Owner | Decision point |
|---|---|---|---|---|
| A mutation check alters source or test state unsafely. | The check could create false evidence or leave the workspace dirty. | Isolate the mutation in a disposable copy or controlled test harness and verify the resulting diff is clean. | Martin | Q-01 review |
| The client-server test needs a real PyMOL environment unavailable in ordinary presubmit. | A slow or non-hermetic test could erode fast-tier trust. | Keep the test local and disposable; classify it separately if it cannot remain fast and hermetic. | Hannah | Before Q-02 lands |

## Later milestones

- **Repeatable health signal:** Use the first flake baseline and the T-02
  runtime evidence to decide whether CI needs a distinct slow test tier.

## Team agreements

- Default WIP: one item per developer.
- Owners do not approve their own changes.
- Coverage percentage is diagnostic only; each acceptance claim needs a named
  test that would fail if the claim became false.
