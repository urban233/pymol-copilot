# Initial runtime delivery plan

**Status:** Draft
**Owner:** Martin Urban (`urban233`)
**Brief:** [`SPECIFICATION.md`](../../../SPECIFICATION.md)
**Design:** [shared core](../design/shared-core/design.md) and [runtime application](../design/runtime-application/design.md)
**Project tracker:** Not used
**Supersedes:** Not applicable
**Last reviewed:** 2026-08-24

## Changes since last review

- Replaced the discovery lanes with a direct two-task start. Existing
  cross-project runtime evidence is accepted as applicable to this project.

## Current milestone

**Outcome:** A structural biologist can submit an intent in PyMOL and inspect a
locally produced, validated plan without changing the live session.

**Evidence:** A headless end-to-end fixture proves that the command bridge,
companion, typed-plan boundary, and plan rendering complete without a live
session mutation.

**Target:** Not committed.

## Before implementation

The first fixture uses native PyMOL `.pml` command syntax and permits only
`select` followed by `color`:

```pml
select copilot_selection, chain A
color red, copilot_selection
```

Labels and every other command are out of scope. The typed-plan and
bridge-companion request/response shapes are accepted in the runtime
[Initial bridge-companion fixture](../design/runtime-application/process-architecture.md#initial-bridge-companion-fixture).
The prior project evidence is sufficient for loopback startup, command
responsiveness, sidecar fidelity, and recovery feasibility; no separate probe
or evidence-adoption task is required.

## Current work

Both tasks are high risk because they establish the safety boundary. Hannah and
Martin each have one work-in-progress slot and independently review the other
developer's work.

| ID | Task | Issue | Status | Blocked by |
|---|---|---|---|---|
| T-01 | Restricted-plan core | [#4](https://github.com/urban233/pymol-copilot/issues/4) | Ready | None |
| T-02 | Non-mutating runtime path | [#3](https://github.com/urban233/pymol-copilot/issues/3) | Ready | None |

### T-01: Restricted-plan core

- **Owner and reviewer:** Martin Urban (`urban233`); Hannah Kullik
  (`kullik01`) reviews independently.
- **Outcome and acceptance:** Implement the agreed typed-plan representation,
  canonical rendering, and default-deny parser and policy for native `.pml`
  `select` and `color` commands only. Unknown input is rejected and never
  reaches a PyMOL dispatcher.
- **Integrates with:** T-02 only through the recorded typed-plan and
  bridge-companion fixtures.
- **Validation:** Positive and adversarial corpus tests, including grammar-free
  rejection tests.
- **Non-goals:** Broader command coverage, grammar generation, model training,
  labels, and live execution.

### T-02: Non-mutating runtime path

- **Owner and reviewer:** Hannah Kullik (`kullik01`); Martin Urban
  (`urban233`) reviews independently.
- **Outcome and acceptance:** Implement the agreed command bridge and local
  companion path for one intent. It produces and renders a typed native `.pml`
  `select`/`color` plan and validation result without applying commands to the
  live PyMOL session.
- **Integrates with:** T-01 through the recorded fixtures. It may use a local
  deterministic completion fixture until a model adapter is planned.
- **Validation:** A headless end-to-end fixture verifies command input, local
  request handling, plan rendering, and zero live-session mutation.
- **Non-goals:** Apply, rollback, controlled fetch, model lifecycle, and
  platform qualification.

## Integration checkpoint

After both tasks pass their local validation, Martin and Hannah run the
headless end-to-end fixture together. They confirm that the rendered plan uses
the same canonical typed-plan representation and that no live-session mutation
occurred. Any contract disagreement returns to the two design documents before
the next build task is planned.

## Risks and discovery

| Risk or unknown | Impact | Evidence-producing action | Owner | Decision point |
|---|---|---|---|---|
| The first contract discussion leaves a command or protocol detail unresolved. | Parallel work could diverge. | Record the smallest explicit fixture before either task begins. | Martin and Hannah | Before T-01 and T-02 |
| Existing external evidence does not match the intended environment. | A runtime assumption could be invalid for this project. | Stop the affected task and document the mismatch before changing the design. | Hannah | During T-02 |

## Later milestones

- **Safe apply:** Plan approval, sidecar validation, recovery, and controlled
  fetch only after the non-mutating vertical slice provides integration evidence.

## Team agreements

- Default WIP: one item per developer.
- Owners do not approve their own changes.
- Hannah owns T-02 and independently reviews T-01. Martin owns T-01 and
  independently reviews T-02.
