# PyMOL-Copilot wave plan

**Status:** Superseded
**Owner:** Martin Urban (`urban233`)
**Brief:** [Specification and accepted planning baseline](../../../SPECIFICATION.md#current-wave-planning-authority-2026-09-05)
**Design:** [Dataset and oracle](../design/model-development/dataset-and-oracle.md), [plan and execution](../design/shared-core/plan-and-execution.md), and [runtime application](../design/runtime-application/design.md)
**Project tracker:** [GitHub issues](https://github.com/urban233/pymol-copilot/issues)
**Supersedes:** The outdated wave plan removed in commit `a7d052c`; its incomplete work is carried forward, not declared done.
**Last reviewed:** 2026-09-05

The accepted
[full-V1 contract wave](pymol-copilot-full-v1-contracts.md) carries forward
the incomplete evidence closeout and the real-PyMOL test-runner defect
discovered during M-01 review. Superseding this plan does not retroactively
declare its final validation checkpoint complete.

## Current wave

Finish the first fixture's scientific evidence and make the existing preview
path fail predictably. Martin builds the independent oracle evidence; Hannah
hardens the runtime and proves its non-mutating behavior in real Open-Source
PyMOL. Neither workstream requires the other's unfinished implementation.

This is an enabling and risk-retirement wave, not a claim that natural-language
generation, safe apply, or a useful trained model already works. It completes
missing evidence from the previous wave before expanding runtime capabilities.

- **Demonstration:** Martin shows a controlled chain-A/red case whose selection,
  color, and unintended-change assertions detect a deliberately wrong result.
  Hannah invokes the registered `copilot` command in real PyMOL and shows an
  explicitly fixture-only preview or a bounded failure, with unchanged session
  state in either case.
- **Durable result:** Reproducible fixtures, executable regression checks, and
  separate evidence receipts suitable for the final Notebook.
- **Target:** Not calendar-committed. The five-week course frame remains the
  context, but this plan does not invent a submission date or available hours.
- **Exit:** Both evidence tracks pass cross-review and the joint checkpoint.
  Missing real-PyMOL evidence leaves the relevant task incomplete.

## Changes since last review

The refined wave has exactly two implementation items: one gold-case verifier
for Martin and one hardened, real-PyMOL-tested preview for Hannah. Environment
probes and regression checks are steps within those items, not separate
assignments. Explicit handoff criteria replace the previous checkpoint list,
followed by one final validation checkpoint on a combined code snapshot.
The acceptance checklists now identify the exact evidence required for each
handoff and the combined snapshot. All boxes remain unchecked until that
evidence exists; adding a checklist does not certify implementation.

The plan is grounded in `main` at `a7d052c514f319f98a0d7a734ba2d82896e4496c`,
the live issue tracker, and the latest merged product pull requests. The
working tree was clean before this planning change. Repository tests were not
rerun during planning; recorded CI results are historical evidence only.

| Evidence | Established behavior | Remaining limit |
|---|---|---|
| [PR #5](https://github.com/urban233/pymol-copilot/pull/5), merged 2026-08-27; issue #4 closed | Typed plan, canonical rendering, restricted parser, and default-deny policy | Only the exact `chain A` / `red` / `copilot_selection` fixture is supported |
| [PR #9](https://github.com/urban233/pymol-copilot/pull/9), merged 2026-09-03; issue #3 closed | Authenticated loopback request, fixed plan response, and non-mutating command seam; Martin approved the PR | Policy-only fixture validation, not model inference or sidecar execution; public-command tests use a PyMOL double |
| [Issue #8](https://github.com/urban233/pymol-copilot/issues/8), open and assigned to Martin | Existing authority for the first gold/oracle case and initial generation | No oracle or generation implementation is present; this wave delivers the gold/conformance portion, not the entire issue |

Both product PRs report successful Linux, macOS, and Windows smoke checks.
Those checks do not qualify real PyMOL, a model, or the eventual demo machines.
The `pmc_data`, `pmc_train`, and `pmc_agent` packages remain skeletons.

The previous runtime receipt named two unresolved limitations. Current code
still accepts differing plan/report digests in the response codec, although
the HTTP client checks both against the request. Known transport exceptions
also escape the command callback. Task H-01 addresses this fallout before
Hannah advances the runtime evidence; Martin's independent oracle work does
not consume either affected boundary.

## Authority and uncertainty

The [recorded human decision](../../../SPECIFICATION.md#current-wave-planning-authority-2026-09-05)
sets the course scope and staffing baseline. Parent designs still contain
draft labels and older rigor requirements; those are not evidence that their
implementations or qualification checks have passed. This plan uses their
unchanged architectural boundaries and the accepted child fixture designs.
It does not blanket-accept the unreconciled documents.

| Classification | Current-wave treatment |
|---|---|
| Fixed | Existing restricted plan and policy; local-only runtime; no implicit execution; Martin owns data/oracle/training, Hannah owns runtime; reciprocal review |
| Requirements-shaped | Whether the first assertion report and fixture-only preview explain their limits clearly; each developer observes the other's demonstration and adjusts presentation within scope |
| Architecture-shaped, deferred | Production executor/report API, relevant-state serialization, structure-card bytes, inference/model handshake, and approval/recovery integration; no current task defines or depends on these missing contracts |
| Risk track | A pinned real-PyMOL environment and independent atom/color observations; each domain probes its own environment without waiting for the other |
| Staffing input, confirmed | One active implementation item per developer, including time for cross-review; no hourly or calendar commitment inferred |

The oracle's narrow reference harness is test evidence for the existing
fixture, not a second production executor. A need for a new shared execution
or snapshot contract stops the affected work and returns to technical design
before implementation. It does not justify an improvised API in either lane.

## Current work

The table proposes one concrete implementation item per developer for human
acceptance. Both start with a domain-local environment check, recorded as
`discovery` until the real-PyMOL environment is known. This is a readiness
condition within the assigned item, not an additional task. Hannah's existing
hermetic hardening tests do not depend on that probe or on Martin's work.

| ID | Task | Owner / independent reviewer | Risk | Status / tracker |
|---|---|---|---|---|
| M-01 | Implement a chain-A/red gold-case verifier | Martin / Hannah | high | discovery; partial delivery of [#8](https://github.com/urban233/pymol-copilot/issues/8) |
| H-01 | Implement a hardened fixture preview with real-PyMOL regression tests | Hannah / Martin | normal | discovery; one new current-wave issue needed before implementation |

### M-01: Implement the gold-case verifier

Martin implements a runnable verifier in `pmc_data` that grades the accepted
chain-A/red fixture against independent expected results. Its deliverable is
the verifier, one provenance-complete gold record, and automated positive and
negative tests. Hannah reviews oracle independence and wrong-result detection,
not merely successful execution.

- **Authority:** [Issue #8](https://github.com/urban233/pymol-copilot/issues/8),
  [oracle and assertion model](../design/model-development/dataset-and-oracle.md#oracle-and-assertion-model),
  and [initial implementation fixture](../design/shared-core/plan-and-execution.md#initial-implementation-fixture).
- **Allowed scope:** `src/pmc_data/`, new data-specific tests and fixtures,
  `configs/generation/`, and a data evidence note under `results/` or `docs/`.
  Necessary data-target build wiring is Martin's responsibility. Existing
  plan/parser/policy modules are consumed unchanged. No runtime edits.
- **First step:** Record a public or explicitly licensed controlled structure,
  checksum, and a reproducible pinned Open-Source PyMOL environment. Include
  target and non-target atoms so over-selection and unintended coloring are
  observable. Define stable atom identity for this fixture, not the future
  runtime snapshot schema. Failed environment or identity probes leave the
  implementation unready and produce a bounded diagnostic record.
- **Acceptance:** The gold record retains stable identity, source/checksum,
  intent, category, difficulty, canonical typed plan, assertions, contract and
  PyMOL versions, and fixture provenance. Missing required provenance or an
  unsupported assertion invalidates the record.
- **Acceptance:** The expected chain-A atom set is derived independently from
  controlled structure data, not from model output or the same PyMOL selection
  query being tested. A narrow disposable reference run compares actual
  selection membership and red color state against independent expectations.
  It also checks declared non-target state for unintended changes.
- **Acceptance:** Every required assertion must pass for `TaskSuccess`.
  Wrong-chain, wrong-color, and unintended-change cases fail; evaluator errors
  invalidate the result. At least one semantic sabotage check proves that a
  corrupted oracle/evaluator fails the suite. Report every conformance mismatch
  and the exact tested scope; do not generalize from one fixture.
- **Dependencies:** No dependency on H-01. Integrates with H-01 only at the
  final validation checkpoint. No cross-stream landing order.
- **Slices:** Behavior-vertical: one reviewable item containing the environment
  check, gold record, verifier, and conformance tests. Prefer one pull request;
  use a short independently tested stack only if needed for review size, with
  each slice cross-reviewed under the same implementation item.
- **Validation:** Gold-record serialization round-trip preserving provenance,
  assertions, and canonical plan identity; provenance rejection; exact and
  deliberately wrong outcomes; real-PyMOL differential evidence; semantic
  sabotage; and the repository checks listed in Validation. Record the new test
  targets and exact probe command in the task evidence; these targets do not
  exist yet. This does not freeze the full dataset schema.
- **Containment:** Test/reference execution uses only disposable development
  structures and the accepted typed plan with policy checks. No raw generated
  text, teacher access, runtime structure data, or production execution path.
- **Completion limit:** Issue #8 remains open. Initial program-first generation
  is still required, but verified generation must not silently replace the
  missing shared production executor with this reference harness. Additional
  examples can use the existing command fixture on different controlled
  structures; broader command support is not a prerequisite. This wave records
  the execution-contract dependency rather than promising a training-ready
  dataset.

### H-01: Implement the hardened PyMOL preview

Hannah delivers one hardened `copilot` preview with automated real-PyMOL
success/failure checks. Codec corrections, command diagnostics, and the
integration harness are parts of this item; passing only the test-double
suite does not complete it. Martin reviews the behavior and reproduces the
real-PyMOL evidence.

- **Authority:** [Client-server contract](../../../SPECIFICATION.md#apis-protocols-and-contracts),
  [failure behavior](../../../SPECIFICATION.md#failure-modes-and-resilience), and
  [process architecture](../design/runtime-application/process-architecture.md),
  together with the [runtime test strategy](../design/runtime-application/design.md#test-strategy).
- **Allowed scope:** `src/pmc_client/`, `src/pmc_core/protocol.py`, the existing
  protocol/client tests, new runtime-specific integration tests/fixtures, and
  their build or explicit integration-runner wiring. Include a runtime setup
  and evidence note. Server fixture warning text may change if needed; no
  lifecycle redesign or new shared snapshot/executor API.
- **First step:** Record Hannah's OS, Python, and pinned Open-Source PyMOL
  combination, with a finite-deadline disposable test invocation. Do not assume
  Bazel's CPython 3.13.13 can import the PyMOL build. If a separate integration
  environment is needed, document it and retain the existing hermetic tests;
  do not add the ML stack to the client. A failed probe prevents real-PyMOL
  implementation readiness, not independent codec/command hardening.
- **Acceptance:** `ValidatedPlanResponseV1.from_dict()` rejects inconsistent
  plan/report snapshot digests. The HTTP client retains its separate
  request-relative digest and correlation checks. Test a changed plan digest,
  a changed report digest, and matching response digests from another request.
- **Acceptance:** Unsupported operation values received through the wire codec
  follow its typed decode-error contract rather than leaking constructor
  `ValueError`. Known transport/decode failures at `copilot` produce a bounded,
  actionable diagnostic without traceback, plan text, or session mutation.
  Do not hide arbitrary programming errors with a catch-all success path.
- **Acceptance:** Successful output identifies the result as a fixed,
  policy-checked preview. It states that loaded-state fidelity, execution, and
  scientific intent were not validated and that nothing was applied. The
  placeholder digest must not be described as a computed structure checksum.
- **Acceptance:** Public-command tests cover representative success, typed
  rejection, unavailable transport, and malformed-response paths. All preserve
  the disposable adapter's original state. A deliberate mutation causes the
  no-mutation check to fail.
- **Acceptance:** Register and invoke `copilot` through real PyMOL's command
  surface against the existing authenticated loopback server. A locally owned
  controlled fixture is sufficient; Martin's fixture is not an entry gate.
- **Acceptance:** Success, returned rejection, and unavailable-server cases
  produce the bounded output behavior in real PyMOL. Compare pre/post object
  identities, coordinates, selection membership, colors, and other state
  declared in the test's comparison scope. A deliberate mutation fails the comparison.
  Do not claim whole-session recovery or snapshot fidelity from this check.
- **Acceptance:** The receipt records structure provenance/checksum, relevant
  contract versions, exact commands, comparison scope, output, deadlines, and
  process cleanup. Martin can independently repeat the documented check; an
  incompatible reviewer environment is reported, not silently skipped.
- **Dependencies:** No dependency on Martin's new code, fixture, oracle, or
  model. Integrates with M-01 only at the final validation checkpoint. The
  real-PyMOL portion needs a successful local environment probe.
- **Slices:** Behavior-vertical: one reviewable item containing failure-boundary
  fixes and their real-command regression evidence. Prefer one pull request;
  a short independently tested stack may separate hardening from integration
  tests if review size requires it. Each slice is cross-reviewed under the
  same implementation item; partial delivery does not satisfy its handoff.
- **Validation:** Existing protocol, command, loopback-transport, and public
  command targets; the recorded real-PyMOL invocation; and repository checks.
  Real-PyMOL validation stays explicitly separate if it cannot run inside Bazel.
- **Containment:** Valid existing V1 payloads remain compatible; no adapter or
  flag is required. Tests use disposable development sessions and never execute
  the displayed plan. Apply, fetch, rollback, sidecar execution, and inference
  remain absent. The harness is not a managed application launcher.

## Parallel work and ownership

The two workstreams share stable inputs already on `main`, not code that one
developer must deliver first. Martin works only on M-01 while Hannah works
only on H-01, including their respective environment checks. Cross-review and
the final validation checkpoint are part of these items, not additional
implementation assignments.

| Boundary | Martin's workstream | Hannah's workstream |
|---|---|---|
| Stable shared input | Existing `ActionPlan`, parser, policy, and canonical fixture | Same existing contracts; runtime request/response types already exist |
| New source ownership | `pmc_data` and data-local reference evidence | Client and protocol hardening; runtime-local command tests |
| Test/fixture ownership | New data-specific paths | Existing runtime tests and new runtime-specific paths |
| Cross-stream dependency | Does not consume HTTP transport, response codec, live snapshot, inference, or sidecar | Does not consume oracle implementation, generated dataset, model, or structure card |
| Final integration | Provides its controlled artifact and oracle receipt | Repeats the preview check using that artifact after both lanes have independent evidence |

Each owner uses a separate branch and checkout. The resolved Git workflow is
`trunk`; independently valid slices may merge after review. No cross-stream
`Lands after` relationship is required. Neither item must land before the other
can be implemented or reviewed.

Avoid shared-file work by placing new data and runtime tests in separate
targets. Hannah owns this wave's edits to `protocol.py`; Martin consumes the
unchanged plan/parser/policy interfaces. Martin handles root dependency/lock
changes if required, but Hannah can use an explicitly documented integration
environment without waiting for a root dependency change. Stop and coordinate
if either lane requires shared API or root build changes that affect the other.

The [CODEOWNERS file](../../../.github/CODEOWNERS) assigns core paths to Hannah
and build files to Martin; it omits client/server source rules. This plan does
not change those rules or infer review authority from them. It preserves the
specification's semantic ownership and requires the named independent reviewer
on every slice, including Hannah-authored core edits reviewed by Martin.

## Handoff criteria

Each developer hands off their complete item to the other for independent
review using the checklists in this section. The owner completes the behavior
and evidence entries before requesting handoff review; only the named reviewer
completes the independent-review entry. No checkbox is satisfied by a claim
such as "tests pass" without its linked evidence.

Record evidence in the following receipt templates as implementation occurs.
The templates exist with unchecked boxes and placeholders; filling them in is
part of the assigned item, not a separate task:

| Receipt | Writer | Independent reviewer |
|---|---|---|
| `docs/codev/wave/evidence/M-01.md` | Martin | Hannah |
| `docs/codev/wave/evidence/H-01.md` | Hannah | Martin |
| `docs/codev/wave/evidence/combined.md` | Martin coordinates | Both record their own verdict |

Each receipt maps every checklist ID to a test or inspection result and a
durable artifact path or attachment. Use the same small evidence record for
both domains; this is delivery evidence, not a new runtime schema.

| Required evidence | Exact contents |
|---|---|
| Snapshot | Full base and tested-head commit SHAs; source/test paths; issue or PR link when available; `git status --short` result showing no unrecorded source/test changes |
| Environment | OS and architecture; exact Python, Open-Source PyMOL, and relevant dependency versions; reproducible environment/install recipe; probe command and result; configured finite test deadlines |
| Fixture and contracts | Retained structure path, public/licensed source and checksum; actual SHA-256 verification output; fixture identity; exact canonical PML bytes; plan/policy versions and other contract versions actually used, with unavailable contracts marked not implemented |
| Each check | Checklist ID; test target or test name; exact command, working directory, and relevant non-secret configuration; run time and executor; exit status; test counts and skipped cases; retained stdout/stderr or test-report path |
| Observations | Expected and observed values or state comparisons needed by the checklist, not just an aggregate pass count; declared comparison scope and limitations |
| Review | Reviewer identity; reviewed commit SHA; independently executed commands and reports; verdict; findings and their resolution or explicit missing-evidence status |

Do not retain credentials or private runtime data in logs. Store only controlled
development evidence. A screenshot alone cannot replace machine-readable test
output or a reproducible command. For a negative test, the expected rejection
must occur and the test suite must pass; for a sabotage test, retain the
deliberately failing child run as well as the passing detection check.

Keep previous receipts recoverable through Git history and retain their linked
artifacts. If source, tests, fixtures, or configuration change after review,
refresh the affected evidence and review against the new snapshot. A later
evidence-only commit must name the code snapshot actually tested rather than
claiming that its own SHA was tested.

### Martin's acceptance checklist

M-01 hands off a runnable verifier, one provenance-complete gold record, and
its automated regression suite. Martin records M-A1 through M-A8 in the M-01
receipt; Hannah records M-R1 after independent reproduction.

- [ ] **M-A1: Reproducible fixture and environment.** Retain the controlled
  structure, its source/license note, verified SHA-256, and target/non-target
  atom identities. Record the pinned PyMOL environment and successful disposable
  reference invocation. Evidence identifies the actual loaded fixture, not the
  runtime's placeholder digest.
- [ ] **M-A2: Complete gold record and lossless round-trip.** Retain the record
  with stable ID, source/checksum, intent, category, difficulty, typed/canonical
  plan, assertions, contract/PyMOL versions, and provenance. A named test proves
  serialization preserves provenance, assertions, and canonical plan identity.
- [ ] **M-A3: Independent selection oracle.** Link the expected-set derivation
  code and its controlled input. Retain expected and actual stable atom-ID sets,
  their counts, and their differences from the real-PyMOL reference run. The
  expected set must not be copied from model output or the PyMOL selection query
  being tested; counts alone are insufficient evidence of equality.
- [ ] **M-A4: Correct-case assertions.** Retain per-assertion results showing
  exact chain-A membership, requested red color on target atoms, and unchanged
  declared non-target state. Include the color observations and pre/post state
  comparison. `TaskSuccess` is true only when all required assertions pass.
- [ ] **M-A5: Semantic negative cases.** Retain separate wrong-chain,
  wrong-color, and unintended-change cases with their injected changes,
  expected failed assertions, and observed results. Each case must fail its
  relevant assertion and must not receive a successful `TaskSuccess` result.
- [ ] **M-A6: Invalid cases fail closed.** Retain named missing-provenance,
  unsupported-assertion, and evaluator-error tests. Each invalidates the record
  or score instead of inserting defaults, dropping the assertion, or reporting
  scientific success. Record the observed diagnostic for each case.
- [ ] **M-A7: Sabotage detects an incorrect oracle.** Retain the deliberately
  changed oracle/evaluator behavior, the exact targeted test, and its expected
  failure output. Also retain passing baseline and restored runs, and the
  passing sabotage-detection test. Sabotage must not remain enabled in the
  handed-off code or fixture.
- [ ] **M-A8: Complete implementation evidence.** Link the runnable verifier,
  new test targets, parser/policy reuse, and all command results required by
  Validation. Record tested scope and any disagreements; none may be silently
  filtered from a passing claim. The receipt explicitly leaves issue #8's
  generation portion open and makes no production-executor or broad
  generalization claim.
- [ ] **M-R1: Hannah accepts the handoff evidence.** Hannah independently runs
  the verifier's positive, negative, invalid-record, and sabotage checks on
  Martin's submitted snapshot. Her receipt entry cites her own logs, confirms
  oracle independence by code inspection, and records no unresolved blocking
  finding. Missing real-PyMOL reproduction leaves this box unchecked.

### Hannah's acceptance checklist

H-01 hands off the hardened preview, real-PyMOL integration runner, and bounded
success/failure evidence. Hannah records H-A1 through H-A8 in the H-01 receipt;
Martin records H-R1 after independent reproduction. Her local controlled
fixture need not wait for Martin's fixture.

- [ ] **H-A1: Reproducible real-PyMOL invocation.** Retain the local fixture,
  provenance/checksum, pinned environment, and exact finite-deadline runner
  command. Logs must show registration and invocation of `copilot` through
  real PyMOL against the authenticated loopback server, not only an adapter
  callback. Record normal and failure-path process/scratch cleanup evidence.
- [ ] **H-A2: Digest and correlation rejection.** Retain named codec tests for
  a changed plan digest and a changed validation-report digest. Retain HTTP
  client tests where both response digests agree with each other but not with
  the request, and where request/session correlation is wrong. Each malformed
  response is rejected; the unchanged valid fixture still decodes successfully.
- [ ] **H-A3: Typed decode errors.** Retain a schema-shaped response containing
  an unsupported operation argument and the observed `ProtocolDecodeError`.
  Test that this does not leak a constructor `ValueError`; preserve valid V1
  payload behavior. Link the test inputs and expected/actual error categories.
- [ ] **H-A4: Bounded command failures.** Retain public-command output and
  assertions for returned typed rejection, unavailable transport, and malformed
  response. Known failures produce actionable diagnostics without traceback,
  plan text, or mutation. Link the exception-handling code to show that the
  correction does not swallow arbitrary programming errors.
- [ ] **H-A5: Honest success output.** Retain the real-PyMOL console transcript
  and an automated output assertion. It must show the exact canonical fixture
  plan, identify a fixed policy-checked preview, and state that nothing was
  applied. Loaded-state fidelity, execution, and scientific intent must not be
  described as validated; the placeholder digest is not a computed checksum.
- [ ] **H-A6: Real-session state remains unchanged.** For success, returned
  rejection, and unavailable-server cases, retain pre/post observations and
  comparison results for object identities, coordinates, selection membership,
  colors, and every additional declared field. Record zero differences within
  that scope. Retain the adapter-based regression results separately; neither
  result implies whole-session recovery or snapshot fidelity.
- [ ] **H-A7: Sabotage detects a mutation.** Retain the deliberate mutation,
  affected comparison, and failure output proving detection. Also retain the
  passing clean/restored runs and sabotage-detection test. Only disposable
  development sessions may be changed by this check.
- [ ] **H-A8: Complete implementation evidence.** Link the codec/command
  changes, integration runner, setup instructions, and all command results
  required by Validation. Report all skipped tests and limitations. No displayed
  plan is executed by the preview; no apply, fetch, rollback, sidecar, or
  inference capability is introduced by this item.
- [ ] **H-R1: Martin accepts the handoff evidence.** Martin independently runs
  the focused codec/command tests and real-PyMOL success/failure/sabotage suite
  on Hannah's submitted snapshot. His receipt entry cites his own logs,
  confirms fixture-only wording and unchanged state, and records no unresolved
  blocking finding. Missing real-PyMOL reproduction leaves this box unchecked.

## Final validation checkpoint

Martin coordinates one final check after both review handoffs are complete.
The team validates a single combined Git snapshot containing both reviewed
items; separate green branches are not combined evidence. This can use a
human-approved integration snapshot before merge and does not itself authorize
merging either item.

Complete this checklist in order and map every C-entry to evidence in
`docs/codev/wave/evidence/combined.md`. Do not copy branch-level green results
into the combined receipt as if they had been rerun.

- [ ] **C-1: Both handoffs are complete.** Martin links the M-01 and H-01
  receipts and their reviewed commit SHAs. M-A1 through M-A8, M-R1, H-A1 through
  H-A8, and H-R1 are satisfied with no unresolved blocking review findings.
- [ ] **C-2: One exact combined code snapshot.** Martin records the full
  combined commit SHA, both reviewed item SHAs, and the integration diff or
  ancestry mapping proving that both items are present. Both developers retain
  `git rev-parse HEAD` and `git status --short` output from their checkouts.
  The tested code, tests, and configuration must match that combined snapshot;
  conflict resolutions or additional code changes require affected re-review.
- [ ] **C-3: One verified input fixture.** Both developers record the checksum
  verification output for Martin's frozen structure, the fixture identity,
  canonical plan bytes, and actual contract versions. Their results must agree.
  Use separate disposable sessions for the mutating oracle reference run and
  the non-mutating preview test; neither may consume the other's altered state.
- [ ] **C-4: Oracle revalidated on the combined snapshot.** Hannah reruns
  M-01's positive, semantic-negative, invalid-record, round-trip, and sabotage
  checks. Retain the new per-assertion report, expected/actual atom sets, color
  and unintended-change observations, exact commands, and test logs. Correct
  behavior succeeds; wrong/invalid behavior receives its expected rejection.
- [ ] **C-5: Runtime revalidated with the exchanged fixture.** Martin reruns
  H-01's codec/command regressions and real-PyMOL success, rejection,
  unavailable-server, and sabotage checks using the verified structure.
  Retain the new console transcripts, pre/post state comparisons, cleanup
  results, exact commands, and test logs. The preview does not execute the plan.
- [ ] **C-6: Repository-wide checks pass on that same snapshot.** Martin runs
  every command in Validation and retains a separate command/result entry for
  build, tests, dependency boundaries, lint, format, and type checking. Include
  the new targets or explicitly separate real-PyMOL invocations from C-4/C-5.
  Record passed/failed/skipped counts; a required skipped check leaves this box
  unchecked. Historical CI and cached results for a different snapshot do not
  satisfy this entry.
- [ ] **C-7: Joint verdict is recorded.** Hannah records her oracle verdict;
  Martin records his runtime and repository-check verdicts, all against the
  combined SHA. The final receipt links C-1 through C-6, lists limitations and
  issue #8's outstanding generation work, and records no unresolved blocking
  finding. If any required result is missing or fails, record an incomplete
  checkpoint, return the affected item to its owner, and refresh affected
  validation/review on the corrected snapshot before checking C-7.

A passed checkpoint makes the wave ready for human acceptance, not automatic
closure or rollout. Keep issue #8 open for its remaining generation obligation.
Missing environment evidence, oracle disagreement, or unexpected session
mutation leaves the checkpoint incomplete; it is not waived by course scope.

The exchanged file's checksum identifies development fixture bytes. It is not
the future relevant-live-state digest. Oracle execution in a disposable process
does not demonstrate that the runtime can safely apply or recover a session.

## Risks and discovery

Only missing evidence that prevents a named task is a blocker. Other risks
remain separate, so an environment problem in one lane does not halt unrelated
work in the other.

| Risk or unknown | Impact / classification | Evidence-producing action | Owner | Decision point |
|---|---|---|---|---|
| Real-PyMOL version or Python mismatch | Risk track; blocks only the affected real-PyMOL implementation/evidence | Record and repeat the domain-local environment probe; preserve failed results | Each owner | Before the real-PyMOL portion of M-01 or H-01 becomes ready |
| Oracle duplicates the behavior it grades | Incorrect labels; high risk | Independent expected atom identities, wrong-result fixtures, and sabotage evidence | Martin; Hannah reviews | Before the gold case is accepted or used for labeling |
| One fixture provides limited semantic coverage | No broad training/generalization claim | Report tested scope and retain the generation portion of #8; consider more controlled structures without requiring new commands | Martin | At final validation checkpoint, before dataset generation is detailed |
| Missing production executor or live-state contract | Architecture-shaped, deferred | Return to the owning technical design; do not promote a local test harness into the shared API | Joint | Before production verified generation or sidecar work is made ready |
| New shared-file or API edits | Could turn parallel work into a dependency | Pause only the affected item and agree one writer and a contract fixture | Joint | Before overlapping implementation starts |
| Deadline pressure | Scope could exceed available course time | Keep later outcomes coarse and review scope using completed evidence, not the deleted schedule | Martin | At final validation checkpoint or when availability changes |

No new model, teacher, training-compute, latency-budget, or snapshot-format
decision is required to execute this bounded wave. Those choices remain
deferred to the work they actually govern. Open refactoring issues
[#6](https://github.com/urban233/pymol-copilot/issues/6) and
[#7](https://github.com/urban233/pymol-copilot/issues/7) are not prerequisites
and are not added to either developer's active work.

## Validation

Every implementation receipt names its exact base/head, changed paths, new
targets, commands, outcomes, and limitations. Historical PR checks are not a
substitute for rerunning the checks on the implemented slice.

H-01's existing focused targets are:

```bash
bazel test //tests/contract:protocol //tests/integration:command //tests/integration:loopback_transport //tests/integration:client_server_command --lockfile_mode=error
```

The repository-wide checks follow the [development setup](../../development_setup.md):

```bash
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

M-01 and H-01 additionally require their recorded real-PyMOL commands. A skipped
integration suite is not passing evidence. Do not add a broad model stack or
weaken the repository dependency checks to make a local probe convenient.

## Later waves

Later outcomes are deliberately coarse. Detail the next one only after this
wave's evidence and remaining issue #8 work have been reviewed.

- **Oracle-backed data and useful context:** Finish the initial generation
  obligation, establish the shared execution/context contracts it needs, and
  produce a small reproducible dataset with honest coverage limits.
- **Measured model and bounded runtime:** Compare an untuned baseline with a
  fine-tuning attempt while advancing local inference and real sidecar
  validation against accepted interfaces. Preserve negative or incomplete results.
- **Safe demonstration and course submission:** Establish approval/recovery
  evidence, integrate the compatible model/runtime pair, and complete the
  Notebook and the jointly rehearsed 40-minute presentation.

## Team agreements and handoff

The owner confirmed one active implementation item per developer and reciprocal
review availability. The plan adds no external reviewer requirement for this
course deliverable.

- Martin owns data/oracle/training; Hannah owns client/server/runtime. Shared
  core remains joint with Martin accountable, subject to the bounded file
  ownership stated for this wave.
- Each owner reserves time to review the other's slices. The proposed queue
  limit is two active reviews per reviewer; pause starting another slice when
  the backlog would exceed that limit. Nobody approves their own change.
- Martin coordinates integration evidence. Routine task status and changing
  availability live in this plan or the linked issues, not in architecture docs.
- Keep this document `Draft` until the human accepts the proposed wave. The
  accepted planning baseline and WIP agreement do not imply task acceptance.
- Before implementation, update the existing #8 with M-01's bounded scope and
  create one current-wave issue for H-01 through the normal guarded workflow.
  Record the returned URL here. Do not close #8 until its generation acceptance
  is also satisfied; do not create issues for the later waves yet.
- This planning change creates no issues, commits, pull requests, or product
  code. Human acceptance, merge, deployment, and publication remain separate.
