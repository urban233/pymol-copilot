# PyMOL-Copilot Wave Plan

**Status:** Draft
**Owner:** Martin Urban (`urban233`)
**Brief:** [`SPECIFICATION.md`](../../../SPECIFICATION.md)
**Designs:** [Shared core](../design/shared-core/design.md), [plan and execution](../design/shared-core/plan-and-execution.md), [runtime application](../design/runtime-application/design.md), [runtime process architecture](../design/runtime-application/process-architecture.md), [approval and recovery](../design/runtime-application/approval-and-recovery.md), [model development](../design/model-development/design.md), and [dataset and oracle](../design/model-development/dataset-and-oracle.md)
**Project tracker:** [GitHub issues](https://github.com/urban233/pymol-copilot/issues)
**Supersedes:** [`design-readiness.md`](../delivery/design-readiness.md) and [`test-quality-gaps.md`](../delivery/test-quality-gaps.md) in full. Both stay as the historical record of completed work; their still-open items (T-02, Q-02) carry forward unchanged in substance as W-01 below.
**Last reviewed:** 2026-09-01

## Changes since last review

- Rewritten against `SPECIFICATION.md`'s 2026-09-01 course-scope revision:
  this is a five-week, two-developer master's-course deliverable (a Jupyter
  Notebook plus a 40-minute PowerPoint, 20 minutes per developer), not a
  commercial release. Gates are lighter; the safety mechanics are not.
- Replaced the previous draft's W-01 (disposable-sidecar lifecycle proof,
  proven in isolation) and W-02 (first oracle case), which were gated behind
  issue #3 landing first. Issue #3 (T-02, non-mutating runtime path) was
  never started under that plan, so this revision makes it the current
  wave's own work instead of a precondition for it.
- Confirmed against the actual repository, not assumed: issue #4/T-01
  (restricted-plan core: typed plan, canonical rendering, default-deny
  parser and policy for `select`/`color` in `pmc_core`) is merged to `main`
  via PR #5. Its test hardening, Q-01, is also done. Issue #3/T-02 is not
  started — `pmc_agent` is still an empty package.
- Folded sidecar-lifecycle validation into Wave 2's safe-apply-and-recovery
  work instead of proving it standalone first: the five-week window doesn't
  afford a separate foundation-only wave, and the underlying safety
  mechanic is unchanged either way.
- Sized waves against the real course deadline (five weeks from
  2026-09-01) instead of leaving `Target` uncommitted throughout, since an
  external date now genuinely constrains sequencing.

## Current wave

**Outcome:** A structural biologist can submit an intent in PyMOL and
inspect a locally produced, validated `select`/`color` plan, with the
bridge and companion communicating over loopback and making no live-session
change. In parallel, the first independently asserted gold/oracle case
shows that a dataset label can be graded correctly without trusting model
output to grade itself, and initial program-first data generation begins
for the same small taxonomy.

**Evidence:** A headless end-to-end fixture proves the command bridge,
companion, and typed-plan boundary complete for one intent without a
live-session mutation. One gold case, whose expected atom set and color are
derived from the structure independently of any plan output, passes its
assertions and fails under a deliberate semantic mutation (wrong chain or
color). Both lanes record the same typed-plan, policy, and contract
versions from T-01.

**Target:** End of week 1.5 of 5 (of the five weeks from 2026-09-01 to the
presentation).

### Current uncertainty

- **Requirements-shaped:** None. The accepted runtime-application and
  shared-core designs already fix the bridge-companion protocol, the
  typed-plan boundary, and the `select`/`color` fixture.
- **Architecture-shaped:** None within this wave's scope. Both tasks
  implement already-accepted designs; neither requires a new
  cross-component decision.
- **Risk tracks:** The bridge-companion loopback protocol has only been
  designed on paper, not run; W-01 is its first real integration. Oracle
  correctness is unproved beyond the design's reasoning; W-02 is the first
  case that could reveal it is circular or wrong.

## Current work

| ID | Task and acceptance | Owner | Reviewer | Risk | Status | Blocked by | Integrates with |
|---|---|---|---|---|---|---|---|
| W-01 | Non-mutating runtime path (= T-02) — bridge + companion produce and render a typed `select`/`color` plan and validation result without touching the live PyMOL session | Hannah | Martin | High | Ready — issue [#3](https://github.com/urban233/pymol-copilot/issues/3) (open) | — | W-02, via the shared typed-plan and contract fixtures from T-01 |
| W-02 | First gold/oracle case + initial program-first generation for the accepted fixture | Martin | Hannah | High | Ready — issue not yet created | — | W-01, via the shared typed-plan and contract fixtures from T-01 |

### W-01 — Non-mutating runtime path

**Acceptance** (carried forward from `design-readiness.md`'s T-02, unchanged in substance):

- Implements the agreed command bridge and local companion path for one
  intent. It produces and renders a typed native `.pml` `select`/`color`
  plan and validation result without applying commands to the live PyMOL
  session.
- A headless end-to-end fixture verifies command input, local request
  handling, plan rendering, and zero live-session mutation.
- Includes the client-server contract and no-mutation test from
  `test-quality-gaps.md`'s Q-02: exercises the real local client and
  companion processes against the accepted `PlanRequestV1` and
  `ValidatedPlanResponseV1` fixtures, confirms request/session correlation,
  schema rejection, canonical rendering, and zero live-session mutation, and
  includes one malformed-message or version-mismatch case that returns a
  typed failure without a partial action plan.

**Authority:** [Runtime application design](../design/runtime-application/design.md),
[process architecture](../design/runtime-application/process-architecture.md),
and [plan language, policy, and execution design](../design/shared-core/plan-and-execution.md).

**Dependencies:** None — T-01's typed-plan and policy contracts are already
on `main`. Integrates with W-02 only through those shared fixtures.

**Validation:** The headless end-to-end fixture above; positive and
adversarial corpus tests already in place from T-01/Q-01; complete
repository checks. Martin reviews independently; no external reviewer is
required for this deliverable.

**Containment:** Non-goals carried forward from T-02: apply, rollback,
controlled fetch, model lifecycle, and platform qualification. This task
may use a local deterministic completion fixture until a model adapter is
planned.

### W-02 — First gold/oracle case and initial data generation

**Acceptance** (carried forward from the prior draft's W-02, with the
research-rigor bar relaxed to match `SPECIFICATION.md`):

- One gold case records stable identity, structure source and checksum,
  contract and PyMOL versions, intent, category, difficulty, canonical
  typed plan, assertions, and complete fixture provenance.
- The oracle derives the expected chain-A atom set from the controlled
  structure independently of model output. The assertion evaluator checks
  that set, the requested red color state, and the absence of unintended
  changes.
- `TaskSuccess` is true only when every required assertion passes. Missing
  provenance, unsupported assertions, or evaluator errors invalidate the
  case rather than receiving defaults.
- A semantic mutation or sabotage case, such as changing the expected chain
  or color, causes the relevant test to fail.
- Program-first generation starts for the same small taxonomy beyond the
  single gold case, at whatever scale is realistic before Wave 2's
  fine-tuning run needs data — no fixed sample count is committed here.

**Authority:** [Dataset and oracle design](../design/model-development/dataset-and-oracle.md)
and [model-development design](../design/model-development/design.md).

**Dependencies:** None — can start immediately from T-01's accepted plan
and policy fixture. Integrates with W-01 at the integration checkpoint
below.

**Validation:** Gold-case schema round-trip and missing-provenance
rejection; exact, wrong-chain, wrong-color, and unintended-change assertion
cases; one semantic mutation or sabotage test; shared parser and policy
fixtures; complete repository checks. Hannah reviews independently; no
external reviewer is required for this deliverable.

**Containment:** This task does not run a teacher at scale, freeze the full
dataset schema or taxonomy, train a model, or publish data. Full
decontamination, a blind label audit, and multi-seed evaluation are Next,
not required here — see `SPECIFICATION.md`'s V1 scope.

## Integration checkpoints

| Checkpoint | Participating work | Owner | Entry evidence | Completion evidence |
|---|---|---|---|---|
| Controlled fixture agreement | W-01, W-02 | Martin | T-01's typed plan and policy are on `main` | Both lanes record the same artifact checksum, typed plan, and contract versions |
| Wave 1 → Wave 2 handoff | W-01, W-02 | Joint | W-01's headless end-to-end fixture passes; W-02's gold case passes and fails its sabotage test | Martin and Hannah agree Wave 2 (sidecar validation, safe apply, recovery, first fine-tuning run) can start |

## Risks and discovery

| Risk or unknown | Impact | Evidence-producing action | Owner | Decision point |
|---|---|---|---|---|
| W-01's branch drifts from the accepted runtime-application design | Wave 1 could build against a contract that conflicts with accepted authority | Reconcile the branch before merge; accepted designs win by default | Hannah | Before W-01 merges |
| The first oracle is circular or semantically wrong | Incorrect labels could pass because they repeat plan output instead of independent structure evidence | Derive the atom set independently; run wrong-chain, wrong-color, and semantic-mutation tests | Martin | Block W-02 completion on unexplained disagreement |
| Five weeks isn't enough to land a working harness demo and a meaningful fine-tuning comparison | The presentation could be thin on one developer's half | Check progress against the week-1.5 / week-3 / week-5 targets in this and later waves; cut Later-possibilities scope first, never the safety mechanics or the honest-reporting requirement | Joint | End of each wave |

## Later waves

- **Safe apply and recovery demo:** Sidecar validation, plan approval,
  fail-closed apply, and automatic `.pse` restore for the accepted
  `select`/`color` fixture, plus the first supervised fine-tuning run
  compared honestly against Martin's base-model baseline. Target: end of
  week 3 of 5. Refine into ready tasks once Wave 1's evidence and
  integration checkpoint are in.
- **Integration and presentation readiness:** Expand the demo taxonomy if
  time allows, dry-run the full intent-to-apply-to-failure-to-recovery
  script together, finalize the Notebook's honest evaluation write-up
  (whatever ablations, seeds, or decontamination were actually reached),
  and prepare the 40-minute PowerPoint. Target: week 5. Refine once Wave 2
  lands.
- **Past the course, if the project continues:** Controlled fetch, a
  multi-platform qualification matrix, external/specialist review, the
  full ablation suite, multi-seed variance, RL, and the V2 panel — all
  currently Later possibilities or Non-goals in `SPECIFICATION.md`.

## Team agreements

- Default implementation work in progress is one item per developer.
- Martin owns dataset, oracle, training, and evaluation. Hannah owns the
  bridge, companion, and runtime path. Each reviews the other's
  integration with shared contracts; neither approves their own work.
- No external reviewers for this deliverable; Martin/Hannah cross-review is
  the complete review process (see `SPECIFICATION.md`'s Non-goals).
- Create GitHub issues only for current-wave items once this plan is
  accepted. W-01 already has issue [#3](https://github.com/urban233/pymol-copilot/issues/3);
  record W-02's issue URL here once created.
- Track routine status and availability in this plan or the linked tracker,
  not in the design documents.
