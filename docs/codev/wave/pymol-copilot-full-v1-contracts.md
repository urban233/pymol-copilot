# PyMOL-Copilot full-V1 contract wave

**Status:** Accepted — accepted by Martin Urban (`urban233`), 2026-09-09
**Owner:** Martin Urban (`urban233`)
**Brief:** [Course-scoped specification](../../../SPECIFICATION.md#current-wave-planning-authority-2026-09-05)
**Design:** [Structure context](../design/shared-core/structure-context.md), [plan and execution](../design/shared-core/plan-and-execution.md), and [request pipeline](../design/runtime-application/request-pipeline.md)
**Project tracker:** [GitHub issues](https://github.com/urban233/pymol-copilot/issues)
**Supersedes:** [The first-fixture evidence wave](pymol-copilot.md)
**Last reviewed:** 2026-09-09

## Changes since last review

- Martin and Hannah merged both previous-wave implementation items. GitHub
  records Martin's approval of H-01 and Hannah's approval of M-01.
- M-01 review proved that PyMOL shutdown can replace pytest's failing exit code
  with zero. H-01's real-PyMOL target still uses the affected shutdown pattern,
  so its green result is not yet trustworthy.
- The product owner kept data and structure context ahead of demo or training
  shortcuts and selected a full-V1 contract rather than a fixture-only slice.

## Current wave

**Outcome:** Retire the full-V1 snapshot and fresh-process execution design
risk. The team will close the previous evidence gap, compare serialization and
reconstruction candidates against representative real-PyMOL state, define the
model-facing structure card and dataset needs, and freeze one shared contract
that both runtime and model-development code can implement next.

**Evidence:** On each developer's supported environment, a prototype round
trip reconstructs the accepted fixture matrix in a fresh PyMOL process and
reports every declared state difference. The same canonical snapshot produces
byte-identical card output. Forced timeout, crash, malformed input, unsupported
state, and PyMOL-command failure cases produce bounded reports and leave no
child process or promoted dataset record.

**Target:** Not committed. The wave protects the course deadline by ending at
an accepted contract and implementation-ready follow-up tasks, not by building
the full runtime, model, or dataset in the same wave.

This is a risk-retirement wave. It produces reviewable evidence and accepted
designs rather than claiming that a useful trained model or safe apply path is
implemented.

## Authority and uncertainty

The specification fixes local execution, exact relevant-state fidelity,
default-deny policy, fresh sidecar processes, and shared train/serve contracts.
The product owner fixed this wave's width at the full planned V1 state surface.
No repository artifact selects the serialization or proves reconstruction
fidelity, so implementation against a guessed format is blocked.

- **Fixed:** Full planned V1 snapshot field coverage; one shared
  snapshot/card/execution contract; a fresh process per execution; and no
  model or teacher dependency.
- **Architecture-shaped:** Serialization, canonical bytes, reconstruction,
  execution request/report, finite limits, and unsupported-state behavior.
  This wave resolves them with real-PyMOL evidence.
- **Requirements-shaped:** The card fields and truncation markers that help
  the accepted V1 intent taxonomy. Martin tests representative cards with
  Hannah as the runtime consumer.
- **Risk track:** PyMOL platform/API differences and process cleanup. Each
  environment is recorded separately without a multi-platform support claim.
- **Deferred:** Grammar generation, command-policy expansion, inference,
  training, apply, recovery, and model packaging.

## Current work

The previous-wave repair lands first. H-02 and M-02 then proceed as discovery
items in parallel. Neither may add a production snapshot, card, or executor API;
their joint checkpoint freezes those contracts before implementation begins.

| ID | Task | Owner / reviewer | Risk | Status |
|---|---|---|---|---|
| W2-00 | Restore trust in H-01 and close the previous wave | Hannah / Martin | normal | in progress -- runner fixed and re-verified in both directions at `a181cce`; combined checkpoint recorded partially complete (C-2, C-3, C-5, and Martin's half of C-7 outstanding), awaiting independent review |
| H-02 | Prove full-V1 snapshot reconstruction and execution boundaries | Hannah / Martin | high | blocked by W2-00 |
| M-02 | Define full-V1 card and dataset contract needs | Martin / Hannah | high | blocked by W2-00 |

### W2-00: Restore trust and close the previous wave

**Outcome and acceptance:** Fix the H-01 real-PyMOL test entry point so Bazel
receives pytest's actual exit code and complete output. A temporary failing
assertion must make the target fail, and the restored suite must pass. Re-run
the prior wave's combined checks on one `main` snapshot, then update M-01,
H-01, and combined receipts with the merged pull requests, reciprocal human
approvals, exact commands, limitations, and joint verdict. Do not rewrite
historical evidence as if it had run on another commit.

- **Authority:** [M-01 exit-code finding](evidence/M-01.md#outer-loop-finding-real-pymol-test-targets-exit-code-could-not-be-trusted-fixed) and [previous final checkpoint](pymol-copilot.md#final-validation-checkpoint).
- **Dependencies:** None. H-02 and M-02 are blocked until this item establishes
  a trustworthy real-PyMOL test runner and records the previous wave's result.
- **Slices:** Behavior-vertical, one small pull request containing the runner
  fix, its two-direction proof, and evidence reconciliation.
- **Validation:** `//tests/integration:real_pymol_command` with a temporary
  failing probe and after restoration; affected H-01 and M-01 targets; full
  repository build, test, dependency-boundary, lint, format, and type checks.
- **Containment:** Test and documentation changes only. No runtime behavior,
  snapshot schema, executor, or dataset change.

### H-02: Prove full-V1 snapshot and execution boundaries

**Outcome and acceptance:** Produce a differential report and disposable
prototype that selects one canonical serialization and reconstruction path for
all state relevant to planned V1 selections, representations, colors, labels,
views, safe settings, and geometric measurements. The fixture matrix covers
object and state identity; atom identity and coordinates; chain, residue,
insertion, atom, element, alternate-location, polymer, and hetero metadata;
bonds; object and atom visibility/representation/color state; view and
supported setting state; and measurement objects. Modified coordinates,
multiple states, alternate locations, and hetero atoms must be represented.

The report compares at least canonical structured data, a standard molecular
export plus an explicit state manifest, and PyMOL session serialization. It
selects one approach by fidelity, boundedness, inspectability, portability on
the two development environments, and reconstruction cost. It must define
explicit unsupported-state behavior rather than silently dropping fields.

The same prototype exercises a candidate fresh-process request/report boundary
with finite input size, wall-clock deadline, process termination, and scratch
cleanup. Success reports the input and resulting fingerprints plus
command-indexed outcomes. Malformed input, incompatible versions, spawn/load
failure, timeout, forced crash, PyMOL command failure, and fidelity mismatch
fail closed without internal retry.

- **Authority:** [Structure context design](../design/shared-core/structure-context.md#structure-snapshot-and-digest), [execution design](../design/shared-core/plan-and-execution.md#execution-and-validation-report), and [sidecar invocation](../design/runtime-application/request-pipeline.md#apis-and-contracts).
- **Dependencies:** Blocked by W2-00. Integrates with M-02 through a jointly
  agreed fixture catalog and candidate canonical snapshot fixtures.
- **Slices:** Bounded discovery. Retain probes, fixtures, and machine-readable
  results only when they are useful acceptance evidence; do not ship a
  production API before the contract-freeze checkpoint.
- **Validation:** Small, narrow canonicalization and malformed-input probes;
  medium-scope subprocess timeout/crash/cleanup probes; and large, broad
  real-PyMOL differential runs that earn their cost by testing reconstruction
  fidelity unavailable to doubles.
- **Containment:** Controlled synthetic structures only. Scratch data is
  private and deleted. No live-session mutation beyond the disposable source
  fixtures, no model, no network, and no apply path.

### M-02: Define full-V1 card and dataset needs

**Outcome and acceptance:** Define the smallest V1 intent taxonomy and fixture
catalog that exercise the full planned command families without fixing dataset
size. For each category, record required snapshot facts, oracle status,
assertion type, command-policy dependency, and whether the category is ready,
unsupported, or deferred. Controlled fetch, clarification, refusal, no-op, and
repair remain explicit non-execution categories.

Using H-02's candidate canonical snapshots, prototype the deterministic
structure card. Record exact field order, escaping, numeric normalization,
collection ordering, bounded truncation markers, card version, and unsupported
state behavior. Equivalent snapshots must produce byte-identical cards, and a
mutation of each model-relevant field must either change the bytes or be
documented as deliberately omitted. Define the dataset sample and artifact
manifest fields needed to preserve snapshot, card, plan, assertions, execution
evidence, provenance, and contract versions. Do not package a training-ready
dataset in this discovery item.

- **Authority:** [Dataset and oracle design](../design/model-development/dataset-and-oracle.md#dataset-representation-and-provenance) and [structure card design](../design/shared-core/structure-context.md#structure-card).
- **Dependencies:** Blocked by W2-00. Integrates with H-02 through the fixture
  catalog and candidate canonical snapshots; it does not choose the live-state
  serialization independently.
- **Slices:** Bounded discovery with golden card candidates and schema examples,
  followed by one joint design update. No production dataset or training code.
- **Validation:** Small, narrow golden-byte and field-mutation tests over
  candidate cards; medium-scope parity checks that data and runtime callers use
  the same pure card function candidate; human review of taxonomy coverage and
  truncation wording.
- **Containment:** Public or self-authored controlled fixtures only. No teacher,
  model, training compute, runtime user data, or publication claim.

## Integration checkpoints

- **Prior-wave closeout:** Martin coordinates W2-00 after the H-01 runner is
  trustworthy and both merged approvals are linked. Completion is a combined
  receipt for one tested `main` snapshot with a joint verdict.
- **Fixture freeze:** Hannah coordinates H-02 and M-02 after the previous wave
  closes and both draft fixture catalogs exist. Completion is one reviewed
  catalog mapping each full-V1 state and intent category to a controlled
  fixture or explicit unsupported case.
- **Contract freeze:** Martin coordinates H-02 and M-02 after the differential,
  failure, card-byte, and taxonomy reports are complete. Completion requires
  exact schemas, guarantees, errors, limits, compatibility rules, and contract
  fixtures in the revised designs, accepted by both owners.

The contract-freeze checkpoint, not a prototype branch, makes later
implementation work ready. If no candidate preserves the declared state, the
checkpoint records the failed evidence and returns the affected V1 behavior to
product scope instead of weakening fidelity silently.

## Risks and discovery

| Risk or unknown | Impact | Evidence-producing action | Owner | Decision point |
|---|---|---|---|---|
| H-01 can report false success | Previous-wave evidence is unreliable | Two-direction exit-code probe and combined rerun | Hannah | Before any new real-PyMOL evidence is accepted |
| No candidate preserves full V1 state | Full-V1 scope may not be feasible in the course window | Differential candidate matrix with explicit field-level gaps | Hannah | At fixture freeze; product owner decides scope if all candidates fail |
| Card omits or destabilizes model-relevant facts | Train/serve skew or poor model inputs | Golden bytes and one-field mutation matrix | Martin | Before structure-card contract acceptance |
| Full-V1 discovery consumes implementation time | Course deliverable may lose time for training and demo integration | Time-box each probe in the task plan and review evidence at fixture freeze | Martin | Before starting a second probe for the same unresolved root cause |
| Development environments disagree | A format may work on only one demo machine | Record both environments separately and compare exact failures | Hannah | Before claiming portability or choosing the demo environment |

## Later waves

- **Implement oracle-backed data and useful context:** Implement the frozen
  snapshot, card, and fresh-process execution contracts, then produce a small
  versioned oracle-verified dataset with honest category limits.
- **Measure a model and bounded runtime:** Compare an untuned baseline with one
  fine-tuning attempt while integrating local inference and sidecar validation
  against the frozen contracts.
- **Complete the safe course demonstration:** Prove approval and recovery,
  connect one compatible model/runtime pair, and deliver the Notebook and
  rehearsed joint presentation.

## Team agreements

- Martin owns data, oracle, card, and training concerns. Hannah owns live
  snapshot extraction, sidecar/process behavior, and runtime concerns. Shared
  contracts require reciprocal review.
- Default implementation work in progress is one item per developer. W2-00
  uses Hannah's slot first; H-02 and M-02 may then run concurrently.
- Each reviewer handles at most two active reviews. Owners do not approve their
  own work.
- Martin coordinates the contract-freeze checkpoint. Routine status lives in
  this plan or its current-wave GitHub issues after the plan is accepted.
- Create issues only for current-wave work after plan acceptance. Later-wave
  outcomes do not become issues until their wave becomes current.
