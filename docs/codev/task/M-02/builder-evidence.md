# M-02 Builder Evidence

**Status:** Snapshot-independent discovery complete; card work blocked on H-02
**Task:** M-02
**Base snapshot:** `f217965a45de12199e48d41c901b829700827f37`

## Delivered

- Defined a V1 taxonomy and controlled-fixture catalog that covers loaded
  object selection, representations/colors, constrained labels, views, safe
  settings, geometric measurements, controlled fetch, clarification, refusal,
  no-op, and repair.
- Recorded for every category its required snapshot facts, oracle status,
  assertion type, command-policy dependency, and ready/deferred state.
- Defined candidate dataset sample and artifact-manifest field inventories,
  including snapshot/card, plan, assertions, execution evidence, provenance,
  and contract versions.
- Recorded the developer-authorized W2-00 closure as a scope amendment. C-2,
  C-3, C-5, and Martin's half of C-7 remain explicitly unsatisfied and are not
  represented as passed.

## Changed

- `docs/codev/task/M-02/implementation-plan.md`
- `docs/codev/task/M-02/taxonomy-and-fixture-catalog.md`
- `docs/codev/task/M-02/dataset-sample-and-artifact-manifest.md`
- `docs/codev/wave/pymol-copilot-full-v1-contracts.md`
- `docs/codev/wave/pymol-copilot.md`
- `docs/codev/wave/evidence/combined.md`
- `docs/codev/task/W2-00/implementation-plan.md`

## Validation Actually Run

- `git diff --check` -> passed.
- No automated M-02 card or parity test is applicable: H-02 has not supplied
  candidate canonical snapshots or the shared fixture catalog.
- Supporting macOS W2-00 runtime and repository validation is appended to
  `docs/codev/wave/evidence/combined.md`; its exact commands and outcomes are
  recorded there.

## Acceptance Evidence

- Taxonomy coverage and explicit deferred states: `taxonomy-and-fixture-catalog.md`.
- Candidate sample/manifest provenance and version needs:
  `dataset-sample-and-artifact-manifest.md`.
- Honest scope amendment and retained incomplete prior-wave evidence:
  `combined.md` and the two wave-plan status entries.

## Scope and Limitations

- The developer explicitly authorized the W2-00 closure amendment to unblock
  M-02. That documented dependency update is outside M-02's initial task-local
  paths but is required to reflect the authorized start state.
- The taxonomy and manifest documents are Draft discovery evidence, not frozen
  contracts or production schemas.
- Deterministic card bytes, field-mutation tests, caller parity tests, and
  reciprocal contract acceptance remain blocked on H-02 evidence.

## Review State

Not independently reviewed.
