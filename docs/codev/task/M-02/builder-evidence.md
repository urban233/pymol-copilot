# M-02 Builder Evidence

**Status:** Candidate A card discovery complete; contract freeze pending
**Task:** M-02
**Base snapshot:** `914bc6e299665085b82b9f4c3e5ede4a54975353`

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
- Added a disposable, candidate-private renderer for H-02 Candidate A
  `ObjectSnapshot` values. It defines stable order, ASCII escaping, numeric
  normalization, per-state atom bounds, unsupported-schema rejection, and
  visible markers for measurement objects and polymer classification that are
  not yet captured.
- Added golden-byte, permutation, caller-parity, rendered-field mutation,
  truncation, unsupported-schema, and real Candidate A extraction checks.

## Changed

- `docs/codev/task/M-02/implementation-plan.md`
- `docs/codev/task/M-02/taxonomy-and-fixture-catalog.md`
- `docs/codev/task/M-02/dataset-sample-and-artifact-manifest.md`
- `docs/codev/task/M-02/builder-evidence.md`
- `docs/codev/task/M-02/builder-evidence.json`
- `tests/discovery/m02/card_candidate.py`
- `tests/discovery/m02/test_card_candidate.py`
- `tests/discovery/m02/BUILD.bazel`
- `tests/discovery/h02/BUILD.bazel`
- `pyproject.toml`

## Validation Actually Run

- `git diff --check` -> passed.
- `bazel test //tests/discovery/m02:card_candidate_test --lockfile_mode=error
  --cache_test_results=no --test_output=all` -> 25 passed.
- `bazel test //tests/data/... //tests/discovery/m02:card_candidate_test
  //tests/discovery/h02:full_v1_snapshot_candidate_a --lockfile_mode=error
  --cache_test_results=no --test_output=errors` -> 9 of 9 targets passed.
- `bazel run //tools/quality:ruff --lockfile_mode=error -- check .` -> passed.
- `bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .`
  -> 108 files already formatted.
- `bazel run //tools/quality:pyrefly --lockfile_mode=error -- check` -> 0
  errors, 20 existing suppressions.

## Acceptance Evidence

- Taxonomy coverage and explicit deferred states: `taxonomy-and-fixture-catalog.md`.
- Candidate sample/manifest provenance and version needs:
  `dataset-sample-and-artifact-manifest.md`.
- Candidate-card determinism, parity, mutation sensitivity, bounds, and H-02
  extraction: `tests/discovery/m02/test_card_candidate.py`.

## Scope and Limitations

- The taxonomy and manifest documents are Draft discovery evidence, not frozen
  contracts or production schemas.
- H-02 Candidate A's `harness` target has package-limited visibility only to
  `//tests/discovery/m02`; it does not expose a production snapshot API.
- The joint full-V1 fixture catalog, card schema, compatibility policy, and
  reciprocal contract acceptance remain deferred.

## Review State

Not independently reviewed.
