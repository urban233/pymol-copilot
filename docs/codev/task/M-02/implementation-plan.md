# M-02: Define Full-V1 Card and Dataset Contract Needs

**Status:** Accepted by Martin Urban (`urban233`), 2026-09-14; Candidate A
card discovery complete, round-5 bond correction validated, independent review
pending, contract freeze pending
**Owner:** Martin Urban (`urban233`)
**Reviewer:** Hannah Kullik (`kullik01`)
**Risk:** High
**Containment:** No production snapshot, card, executor, dataset, model, or
training API. Use only public or self-authored controlled fixtures; do not use
runtime user data, a teacher, training compute, or a publication claim.
**Slices:** One pair-work discovery slice, bounded to acceptance evidence and
a joint design update. The work is behavior-vertical: each taxonomy category
maps an intent, controlled fixture, snapshot facts, oracle/assertion state, and
policy dependency before any candidate card bytes are evaluated.
**Base commit:** `f217965a45de12199e48d41c901b829700827f37`
**Issue/work item:** [M-02](../../wave/pymol-copilot-full-v1-contracts.md#m-02-define-full-v1-card-and-dataset-needs)
**Brief/design/API:** [Current-wave authority](../../../../SPECIFICATION.md#current-wave-planning-authority-2026-09-05), [M-02 wave task](../../wave/pymol-copilot-full-v1-contracts.md#m-02-define-full-v1-card-and-dataset-needs), [dataset and oracle design](../../design/model-development/dataset-and-oracle.md#dataset-representation-and-provenance), and [structure-card design](../../design/shared-core/structure-context.md#structure-card).

## Focus card

- **Change:** Produce M-02's bounded discovery evidence for the V1 intent taxonomy, controlled fixture catalog, deterministic structure-card candidate, and dataset sample/manifest needs.
- **Success:** Each planned command family and explicit non-execution category has a documented controlled fixture or explicit unsupported case; equivalent candidate snapshots yield identical card bytes; each model-relevant candidate field has a mutation result; and schema examples preserve the required evidence and versions.
- **Non-goals:** Select live-state serialization, implement or promote a production shared-core API, package a training-ready dataset, run a teacher/model/training job, process runtime user data, or claim portability or publication readiness.
- **Allowed scope:** `docs/codev/task/M-02/` discovery records and controlled schema/card fixtures; focused tests or probes that consume H-02's candidate canonical snapshots; the two owning design documents only for a jointly accepted contract-freeze update.
- **Validation:** Golden-byte and one-field-mutation checks for candidate cards; parity checks using the same pure candidate function in data and runtime callers; human review of taxonomy coverage and truncation wording.
- **Stop if:** H-02 has not supplied candidate canonical snapshots and a shared fixture catalog for card work; a card field, truncation rule, dataset field, or compatibility behavior requires a new material contract decision; or Martin/Hannah cannot reciprocally accept the frozen contract.
- **Work style:** Pair, because the task discovers a shared high-risk contract and needs an accountable human decision before implementation or contract acceptance.

## Repository evidence

- `docs/codev/wave/pymol-copilot-full-v1-contracts.md`: M-02 is a bounded discovery task, contains no production API work, depends on W2-00, and must integrate with H-02's candidate canonical snapshots and shared fixture catalog.
- `docs/codev/wave/evidence/combined.md`: W2-00 is closed by a developer-authorized scope amendment. Its shared-fixture and joint-verdict requirements remain explicitly unsatisfied, while newly recorded macOS focused and repository validation passes are available as supporting evidence.
- `src/pmc_core/protocol.py:StructureSnapshotV1`: the current snapshot is only a fixture identity containing `schemaVersion`, `digest`, and `fixtureId`; it cannot supply a full-V1 card candidate.
- `src/pmc_core/plan.py` and `src/pmc_core/policy.py`: the implemented command surface is the fixed `select` then `color` fixture; the planned V1 display, label, view, setting, and measurement families remain unimplemented and default-denied.
- `src/pmc_data/gold_case.py` and `tests/data/test_gold_case.py`: the repository already has strict, fail-closed provenance and assertion-record conventions suitable as evidence, but no dataset sample schema or structure-card artifact.
- `docs/codev/design/shared-core/structure-context.md`: the card must be a pure function of the versioned snapshot, with stable order/escaping and explicit truncation or unsupported markers; its exact format is deliberately Draft pending this wave.

## Proposed change

1. Author a taxonomy and controlled fixture catalog under `docs/codev/task/M-02/`. Cover loaded-object selection, representations/colors, constrained labels, views, safe settings, and geometric measurements. Keep controlled fetch, clarification, refusal, no-op, and repair as explicit non-execution categories. For every category, record required snapshot facts, oracle status, assertion type, command-policy dependency, and ready/unsupported/deferred state.
2. At the fixture-freeze checkpoint, consume only H-02's candidate canonical snapshots and joint fixture catalog. Add self-authored candidate snapshot/card fixtures and a pure, disposable card renderer outside production packages. Specify field order, string escaping, numeric normalization, collection ordering, bounded truncation markers, versioning, and unsupported-state behavior. Add golden-byte and field-mutation checks; do not select serialization or expose an importable production API.
3. Document dataset sample and artifact-manifest schema examples alongside the candidate cards. Include structure snapshot/card identities and versions, intent and category, plan, assertions and oracle status, execution evidence, provenance, and all contract versions. Reject missing or unknown required evidence in the prototype schema rather than default-filling it.
4. After the H-02 differential/failure evidence and M-02 byte/taxonomy evidence are complete, revise `structure-context.md` and `dataset-and-oracle.md` once with the jointly chosen contract: schemas, guarantees, errors, limits, compatibility policy, and contract fixtures. Request reciprocal review; do not self-accept the result.

## Round-5 corrective scope

The developer authorized this corrective round on 2026-09-14 after independent
review found that sorting atoms without remapping bond endpoints can change a
bond's meaning. Remap each original atom position to its canonical rendered
position before emitting bonds, and add a three-atom permutation regression
test. This remains candidate-private discovery work and does not alter H-02's
snapshot schema or select a production card contract.

## Validation

- `bazel test //tests/data/... --lockfile_mode=error` -> preserve existing gold-case/oracle behavior while adding candidate-card checks only when their fixtures exist.
- Focused candidate-card test target(s), to be named with the first H-02 snapshot fixture -> equivalent snapshot permutations are byte-identical; each model-relevant field mutation changes bytes or has a documented deliberate omission; malformed/unsupported input fails closed with the declared marker.
- Focused data/runtime parity test target(s), to be named with the candidate function -> both consumers produce the same bytes from one candidate snapshot.
- `bazel run //tools/quality:ruff --lockfile_mode=error -- check .` -> lint evidence for any Python probes/tests.
- `bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .` -> formatting evidence for any Python probes/tests.
- Human review by Hannah -> taxonomy coverage, unsupported/deferred states, and truncation wording are reviewed before contract freeze.

## Risks and rollout

- **Waived prior-wave gate:** A developer-authorized scope amendment closes W2-00 while preserving its incomplete shared-fixture and joint-verdict evidence. M-02 discovery may proceed, but cannot cite W2-00 as a passed checkpoint or portability claim.
- **Shared-contract risk:** H-02 alone chooses no serialization. M-02 consumes its candidate snapshots only after the jointly reviewed fixture catalog; any mismatch returns to the fixture-freeze checkpoint.
- **Train/serve skew:** Keep the renderer pure and call it from both candidate callers, then prove byte parity with the same fixture. No consumer-specific formatting is permitted.
- **Silent omission:** Represent every bounded omission with a stable marker. An unknown required state makes the candidate unsupported, not partially exact.
- **Rollback:** All artifacts remain task-local discovery evidence until both owners accept the contract-freeze update. Remove or revise only those disposable artifacts; no runtime or dataset migration exists.

## Decisions needed

- **Recorded decision:** The developer authorized W2-00 to close with C-2, C-3, C-5, and Martin's half of C-7 still unsatisfied. This removes the discovery gate only; it does not convert missing evidence into a passed checkpoint.
- **After fixture freeze:** Martin and Hannah must jointly select the candidate snapshot fixture catalog before card-byte experiments. Do not infer or invent a live-state serialization in M-02.

## Completion evidence

- **Delivered:** The snapshot-independent taxonomy and dataset field inventory,
  plus a candidate-private deterministic renderer that consumes H-02 Candidate
  A `ObjectSnapshot` values. The renderer has stable order, escaping, number
  normalization, bounded per-state atom output, schema rejection, and explicit
  markers for measurement objects and polymer classification that remain
  unsupported.
- **Changed:** M-02 task records; `tests/discovery/m02/` candidate renderer
  and test target; narrow H-02 harness visibility; and the Pyrefly discovery
  search path.
- **Committed head:** Round-5 bond correction validated at
  `3b5253efb3c10dcce7fece06699367857210059a`.
- **Validation actually run:** Focused M-02 candidate-card test: 26 passed
  against a synthetic snapshot and H-02's controlled Candidate A fixture;
  repository Pyrefly, Ruff, data tests, and diff checks pass.
- **Acceptance evidence:** Golden bytes, collection-order determinism,
  canonical bond endpoints across a three-atom permutation, data/runtime caller
  parity, mutations of every rendered field, truncation, schema rejection, and
  H-02 Candidate A extraction are covered. The taxonomy and sample/manifest
  inventory remain draft discovery evidence.
- **Scope deviations:** None.
- **Known limitations:** W2-00's historical combined checkpoint remains
  incomplete under the recorded scope amendment. H-02 Candidate A provides a
  controlled experiment input, but the joint full-V1 fixture catalog,
  production schema, compatibility policy, and reciprocal contract acceptance
  remain pending.
- **Review state:** Awaiting fresh independent review.
