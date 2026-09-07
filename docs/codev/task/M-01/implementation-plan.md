# M-01: Chain-A/Red Gold-Case Verifier Implementation Plan

**Status:** Accepted — implemented, awaiting independent review; see [M-01 evidence](../../wave/evidence/M-01.md)
**Owner:** Martin Urban (`urban233`)
**Reviewer:** Hannah Kullik (`kullik01`)
**Risk:** High
**Containment:** N/A -- no flag; `pmc_data` is a new, currently-empty package
and no existing module is modified. Existing plan/parser/policy contracts in
`pmc_core` are consumed unchanged.
**Slices:** One pull request, two internal steps each independently testable:
  1. *Contract-first* -- gold-case schema, PDB reader, and independent oracle
     (M-A2, M-A3's derivation code), with pure-Python tests only (no PyMOL).
  2. *Behavior-vertical* -- the verifier that runs the canonical plan through
     real disposable PyMOL, the positive/negative/invalid conformance suite,
     and the sabotage test (M-A1, M-A3's differential evidence, M-A4-M-A7).
  If the combined diff exceeds a reasonable single-PR size, split into two
  independently tested pull requests along this same boundary instead.
**Base commit:** `09cd7eb632c756809c4fff0486cac51a1883a050` (branch `codev/M-01`)
**Issue/work item:** [#8](https://github.com/urban233/pymol-copilot/issues/8)
  (narrowed to M-01's bounded scope before this implementation started)
**Brief/design/API:** [Wave plan § M-01](../../wave/pymol-copilot.md#m-01-implement-the-gold-case-verifier),
  [oracle and assertion model](../../design/model-development/dataset-and-oracle.md#oracle-and-assertion-model),
  [initial implementation fixture](../../design/shared-core/plan-and-execution.md#initial-implementation-fixture)

## Focus card

- **Change:** Implement a runnable gold-case verifier in `pmc_data` that
  grades the accepted chain-A/red fixture against independently derived
  expected results, backed by one provenance-complete gold record.
- **Success:** M-A1 through M-A8 in the wave plan pass with linked evidence
  in `docs/codev/wave/evidence/M-01.md`; Hannah independently reproduces the
  positive, negative, invalid-record, and sabotage checks (M-R1).
- **Non-goals:** No parser/policy/runtime edits. No production executor or
  live-state snapshot contract. No teacher access, no curation/dedup/split
  pipeline, and no bulk program-first data generation -- issue #8 stays open
  for all of that. (Expanded after initial acceptance, with explicit
  developer sign-off: one bounded, no-teacher program-first generator that
  reapplies the same accepted plan to additional controlled structures --
  exactly the shortcut the wave plan's own M-01 Completion limit names --
  and its one verified output. See "Bounded program-first generation" below.)
- **Allowed scope:** `src/pmc_data/`, a new `tests/data/` test category and
  its fixture, `configs/generation/` only if actually needed, and
  `docs/codev/wave/evidence/M-01.md`. Expanded during outer-loop review, with
  explicit developer sign-off, to one `tags = ["exclusive"]` addition on the
  pre-existing `tests/contract:policy_sabotage` target (see CI note below).
  Expanded again after acceptance, with explicit developer sign-off, to
  `src/pmc_data/generate.py`, `src/pmc_data/generate_cli.py`, one new
  `configs/generation/*.json` config plus its `BUILD.bazel`, two new
  `tests/data/testdata/*.pdb` fixtures, `tests/data/test_generate*.py`, and
  one new checked-in `src/pmc_data/gold_cases/*.json` record -- bounded by
  M-01's existing containment rule (no teacher access, no production
  execution path).
- **Validation:** New `tests/data/*` Bazel targets (schema round-trip, oracle
  unit tests, real-PyMOL conformance, sabotage) plus the full repository
  checks listed below.
- **Stop if:** The environment probe fails, or a decision surfaces that
  needs a shared executor/snapshot contract change (architecture-shaped,
  deferred per the wave plan).
- **Work style:** Pair -- high risk, implemented interactively.

## Repository evidence

- `src/pmc_core/plan.py`, `policy.py`: the accepted fixture is fixed --
  `select copilot_selection, chain A` then `color red, copilot_selection` --
  and already immutable/typed. M-01 imports `initial_fixture_plan()` and
  `ActionPlan.render_pml()` rather than re-deriving the plan.
- `src/pmc_data/__init__.py`: currently a one-line skeleton; no gold-case,
  oracle, or verifier code exists anywhere in the repository yet.
- `requirements.in`: no PDB-parsing dependency present. M-01 adds none --
  a minimal ATOM-record reader (chain ID + serial only) is sufficient for
  this fixture and keeps the item dependency-free.
- `tests/integration/test_real_pymol_command.py`: the established real-PyMOL
  pattern this plan reuses -- module-scoped `pymol.finish_launching(['pymol',
  '-qc'])`, function-scoped fixture load/delete, `cmd.iterate`/
  `cmd.iterate_state` in place of `cmd.get_coords` (NumPy ABI issue),
  Windows excluded via `target_compatible_with` (issue #12).
- `tests/contract/test_policy_sabotage.py`: the established sabotage pattern
  -- copy the package to a temp dir, patch one safety-critical line, run the
  disposable suite as a subprocess, assert it fails with the expected test
  name in output.
- Environment probe: `bazel test //tests/integration:real_pymol_command
  --lockfile_mode=error` PASSED on this machine (darwin/arm64, Bazelisk
  1.29.0 / Bazel 9.2.0, Python 3.13.15, `pymol-open-source-whl==3.2.0.2`).
  M-01's "first step" real-PyMOL risk is retired; no new PyMOL/Python
  combination is introduced.
- `docs/codev/wave/evidence/M-01.md`: existing unchecked evidence template
  to fill in as this item progresses.

## Proposed change

1. **`src/pmc_data/pdb.py`** -- a dependency-free reader for `ATOM`/`HETATM`
   records (fixed-column serial and chain ID fields only) returning immutable
   atom records. Never touches PyMOL. Test: parses the new fixture correctly,
   rejects a malformed record.
2. **New controlled fixture** `tests/data/testdata/chain_a_gold_fixture.pdb`
   -- a small, self-authored synthetic structure with an asymmetric chain
   split (3 atoms on chain A, 2 on chain B) so a wrong-chain sabotage case is
   unambiguous. Provenance: self-authored for this repository, not derived
   from any external source, same convention as the existing
   `tests/integration/testdata/two_chain_fixture.pdb`. Record its SHA-256.
3. **`src/pmc_data/oracle.py`** -- `expected_chain_atom_ids(pdb_path,
   chain_id)` derived purely from `pdb.py`'s parse, independent of any PyMOL
   selection call. Test: expected set for chain A and chain B against the new
   fixture, by direct inspection of the fixture's recorded atoms.
4. **`src/pmc_data/gold_case.py`** -- frozen `GoldCase` dataclass (case id,
   structure path, checksum, source/provenance note, intent, category,
   difficulty, canonical plan reference, contract/PyMOL versions,
   assertions) with `to_dict`/`from_dict`. Validation rejects missing
   required provenance or an unsupported assertion kind rather than
   defaulting. Test: round-trip preserves provenance, assertions, and
   canonical plan identity (M-A2); missing-provenance rejection.
5. **Gold record fixture** `src/pmc_data/gold_cases/chain_a_red.json` --
   the one hand-authored gold case, loaded through `GoldCase.from_dict` and
   cross-checked against `initial_fixture_plan().render_pml()` so drift in
   `pmc_core`'s canonical rendering is caught.
6. **`src/pmc_data/verifier.py`** -- `verify_gold_case(case, cmd)` loads the
   fixture into a real (caller-supplied) PyMOL `cmd`, executes the canonical
   plan's rendered commands, captures actual chain-A membership, color, and
   non-target atom state, and compares against the oracle's expectations.
   Returns per-assertion results and `TaskSuccess`; missing provenance,
   unsupported assertions, and evaluator errors return/raise an explicit
   invalid result rather than `False`.
7. **`tests/data/test_verifier_real_pymol.py`** -- real disposable PyMOL
   reference run (same launch/fixture pattern as H-01's test): the true gold
   case passes every assertion (M-A4); separate wrong-chain, wrong-color, and
   unintended-change cases (deliberately corrupted `GoldCase`/expectation
   inputs) each fail their relevant assertion (M-A5); missing-provenance,
   unsupported-assertion, and evaluator-error cases invalidate rather than
   pass or default (M-A6). Large size, Windows excluded like the existing
   real-PyMOL target.
8. **`tests/data/test_verifier_sabotage.py`** -- subprocess-copy-and-patch
   sabotage test (mirrors `test_policy_sabotage.py`): corrupt the oracle's
   chain-membership function or the evaluator's comparison, prove the
   targeted conformance test then fails, and that the clean/restored run
   passes (M-A7). Same real-PyMOL dependency and Windows exclusion.
9. **`tests/data/BUILD.bazel`, `tests/data/README.md`** -- new test category
   parallel to `tests/contract`/`tests/adversarial`/etc., with `py_test`
   targets for each module above (schema/oracle targets need no PyMOL and
   stay small/fast; the real-PyMOL and sabotage targets mirror the existing
   `real_pymol_command` target's size/timeout/`target_compatible_with`).
10. Fill in `docs/codev/wave/evidence/M-01.md` with the exact commands, logs,
    and observations mapped to M-A1 through M-A8 as each step lands.

## Validation

- `bazel test //tests/data/... --lockfile_mode=error` -> all new targets pass,
  including the real-PyMOL and sabotage targets on this machine.
- `bazel build //... --lockfile_mode=error`
- `bazel test //... --lockfile_mode=error`
- `bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error`
- `bazel run //tools/quality:ruff --lockfile_mode=error -- check .`
- `bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .`
- `bazel run //tools/quality:pyrefly --lockfile_mode=error -- check`

## Risks and rollout

- **Oracle circularity:** the independent derivation (`pdb.py`/`oracle.py`)
  must never call into PyMOL's own selection machinery -- enforced by
  keeping those two modules PyMOL-import-free, checked by code inspection at
  review and by the sabotage test targeting the evaluator's comparison
  specifically.
- **Windows real-PyMOL exclusion** (issue #12) applies again to the two new
  real-PyMOL targets; this is a known, already-tracked limitation, not a new
  one introduced here.
- **No feature flag needed:** `pmc_data` has no existing consumers yet, so
  there is nothing in production to guard.
- Rollback is trivial: the branch is additive-only against an unused
  package; reverting the merge fully removes the new behavior.

## Decisions needed

- None outstanding. The two decisions with real design weight -- reusing vs.
  authoring a new controlled structure, and where the new tests live -- were
  made above (self-authored fixture; new `tests/data/` category) and stated
  to the developer before implementation began; flag here if either needs to
  be revisited.

## Completion evidence

- **Delivered:** A runnable chain-A/red gold-case verifier in `pmc_data`: an independent PDB reader and chain-membership oracle, a provenance-complete `GoldCase` schema with lossless round-trip, one hand-authored gold record, a self-authored controlled fixture, and a verifier that grades a real disposable PyMOL run against the oracle. `TaskSuccess` requires every declared assertion to pass; missing provenance, an unsupported assertion, an unrecognized PyMOL color, a missing assertion parameter, or policy denial of the accepted fixture all invalidate the result instead of defaulting. Additionally (developer-authorized scope expansion after initial acceptance): a bounded, no-teacher program-first generator (`pmc_data.generate`/`generate_cli`) that reapplies the same accepted plan to a second controlled structure, verifies the candidate through the same real-PyMOL path, and refuses to persist anything not verified -- one new gold record produced and checked in this way, plus a real-PyMOL test proving a mismatched request is rejected rather than written.
- **Changed:** `src/pmc_data/{pdb,oracle,gold_case,verifier,generate,generate_cli}.py`, `src/pmc_data/gold_cases/{chain_a_red,chain_a_red_second_fixture_gold_case}.json`, `src/pmc_data/BUILD.bazel`; `configs/generation/{README.md,BUILD.bazel,chain_a_red_structures.json}`; `tests/data/{BUILD.bazel,README.md,test_gold_case.py,test_oracle.py,test_oracle_sabotage.py,test_gold_case_verifier.py,test_generate.py,test_generate_real_pymol.py,testdata/chain_a_gold_fixture.pdb,testdata/second_gold_fixture.pdb,testdata/no_chain_a_fixture.pdb}`; `docs/codev/wave/evidence/M-01.md`.
- **Head commit/snapshot:** See [M-01 evidence](../../wave/evidence/M-01.md)'s Snapshot section for the exact tested head; this plan covers both the original acceptance and the later generation-scope expansion.
- **Validation actually run:** See the Commands and results table in [M-01 evidence](../../wave/evidence/M-01.md) -- new `tests/data/*` targets, full repository build/test, dependency-boundary check, ruff lint/format, and pyrefly, all passing at each recorded head.
- **Acceptance evidence:** M-A1 through M-A8 checked in [M-01 evidence](../../wave/evidence/M-01.md#checklist); M-R1 awaits Hannah's independent reproduction. The generation expansion is additive to this same acceptance evidence, not a new acceptance-criteria set.
- **Scope deviations:** M-A7's sabotage evidence targets the independent oracle (`pmc_data/oracle.py`) rather than the real-PyMOL verifier path, matching `tests/contract/test_policy_sabotage.py`'s own scope (a pure-logic module) and avoiding a fragile nested real-PyMOL subprocess; the real-PyMOL verifier's own negative-case tests separately prove the evaluator rejects wrong results differentially. The item exceeds the 600-line/12-file soft slicing guideline; kept as one PR per the wave plan's explicit preference for this item.
- **Known limitations:** Issue #8's bulk/teacher-based program-first generation, human-intent distillation, and curation remain open and out of scope -- only one additional structure's gold case was generated, through the bounded template-reuse path the wave plan's own Completion limit already names as acceptable for this wave. M-A6's "evaluator error" case is demonstrated via an unrecognized PyMOL color (a negative `get_color_index` result) rather than a raised exception, since real PyMOL's selection/iterate APIs print a diagnostic and match nothing on malformed input rather than raising -- confirmed empirically before being encoded as the negative test.
- **Review state:** Both the original scope and the generation expansion are independently outer-loop reviewed, machine review complete (`ok_machine_review_complete`) with zero open findings across all eight coverage dimensions, awaiting Hannah's independent human approval (M-R1).
