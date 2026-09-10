# H-02: Prove full-V1 snapshot reconstruction and execution boundaries -- Implementation Plan

**Status:** In progress -- slice 1 (`fixture-matrix-and-candidate-a`) complete,
outer-loop reviewed, and its pull request (#16) open and approved; slice 2
(`candidate-b-and-c`) complete, outer-loop reviewed, and its pull request (#17)
open and approved; slice 3 (`fresh-process-execution-boundary`) implemented and
outer-loop reviewed on a stacked branch
(`codev/H-02--fresh-process-execution-boundary`, based on
`codev/H-02--candidate-b-and-c` since #17 is not yet merged), with both blocking
findings corrected at `daff445` -- see slice 3's own completion evidence below;
slice 4 (`differential-report-and-design-updates`) not started
**Owner:** Hannah Kullik (`kullik01`)
**Reviewer:** Martin Urban (`urban233`)
**Risk:** high
**Containment:** N/A -- disposable discovery prototype, no production API, no flag
**Slices:** Ordered, behavior-vertical, discovery-bounded:
1. `fixture-matrix-and-candidate-a` -- synthetic fixture covering full-V1 relevant
   state; canonical-structured-data extraction, reconstruction, and diff.
2. `candidate-b-and-c` -- standard export plus state manifest, and PyMOL session
   serialization, against the same fixture and harness.
3. `fresh-process-execution-boundary` -- subprocess spawn, deadline, forced
   crash, malformed input, cleanup.
4. `differential-report-and-design-updates` -- write-up feeding fixture-freeze
   and contract-freeze checkpoints with M-02.
**Base commit:** `f217965a45de12199e48d41c901b829700827f37`
**Issue/work item:** H-02 (current-wave task; no GitHub issue created yet --
see Decisions needed)
**Brief/design/API:** [Structure context](../../design/shared-core/structure-context.md#structure-snapshot-and-digest),
[Plan and execution](../../design/shared-core/plan-and-execution.md#execution-and-validation-report),
[Request pipeline](../../design/runtime-application/request-pipeline.md#apis-and-contracts),
[wave plan](../../wave/pymol-copilot-full-v1-contracts.md#h-02-prove-full-v1-snapshot-and-execution-boundaries)

## Focus card

- **Change:** Produce a differential report and disposable prototype that
  selects one canonical serialization/reconstruction path for all state
  relevant to planned V1 selections, representations, colors, labels, views,
  safe settings, and geometric measurements, and prototypes a fresh-process
  execution request/report boundary.
- **Success:** A fixture matrix round-trips through a fresh Open-Source PyMOL
  process with every declared state difference reported; one candidate is
  selected by fidelity, boundedness, inspectability, portability (both
  development environments), and reconstruction cost; malformed input,
  timeout, crash, and PyMOL command failure all fail closed with no leaked
  process or scratch data.
- **Non-goals:** No production snapshot/card/executor API before the joint
  contract-freeze checkpoint with M-02. No model, network, training, or apply
  path. No expansion of the command policy or plan language.
- **Allowed scope:** A new disposable prototype location (not `pmc_data`,
  which is Martin's), controlled synthetic fixtures, and this task's own
  documents. Production `pmc_core`/`pmc_server` packages are read for context
  only in this slice.
- **Validation:** Small, narrow canonicalization and malformed-input probes
  first; medium subprocess timeout/crash/cleanup probes next; large real-
  PyMOL differential runs last, run under both an exploratory venv pinned to
  the same `pymol-open-source-whl==3.2.0.2` wheel and, for retained evidence,
  the project's hermetic Bazel `py_test` target.
- **Stop if:** No candidate preserves the required state (returns to the
  product owner for a scope decision per the wave's risk table), or the
  prototype reveals a shared contract is needed before further probing can
  proceed safely.
- **Work style:** Pair -- architecture-shaped discovery with continuous
  judgment calls, not mechanical implementation.

## Repository evidence

- `src/pmc_core/protocol.py:187-229` (`StructureSnapshotV1`): today only a
  schema version, digest, and fixture identifier -- no canonical live state.
  Confirms the design doc's claim that no snapshot implementation exists yet.
- `src/pmc_data/pdb.py`: an independent, dependency-free PDB reader limited to
  atom serial and chain ID. Does not cover altlocs, insertion codes, elements,
  or hetero/polymer classification -- H-02's fixture and oracle need more.
- `src/pmc_data/verifier.py`: the only real-PyMOL evaluation code in the repo;
  operates on the fixed `select`/`color` fixture only, in-process (no fresh
  subprocess, no snapshot reconstruction). Confirms no prior art exists for
  H-02's fresh-process execution boundary.
- `tests/integration/test_real_pymol_command.py`: the project's real-PyMOL
  test convention -- session-scoped `finish_launching`, `cmd.sync()` before
  reading state back (headless PyMOL's command loop runs on a worker thread),
  and the `os._exit`-after-flush pattern for a trustworthy pytest exit code
  under Bazel. `pymol-open-source-whl==3.2.0.2`'s compiled `_cmd` extension
  breaks `cmd.get_coords()` under NumPy 2.x in this sandbox; use
  `cmd.iterate_state` instead.
- No existing code spawns a fresh PyMOL subprocess anywhere in the repo
  (`grep -rn subprocess src tests` only finds nested-pytest sabotage tests) --
  the fresh-process execution boundary (slice 3) is new territory.
- Verified `pymol-open-source-whl==3.2.0.2` installs and launches headlessly
  in a throwaway venv on this machine, matching the pinned Bazel dependency
  (`requirements_lock.txt:91`), giving a fast exploratory loop before
  committing probes to the hermetic Bazel target.

## Proposed change (slice 1: fixture-matrix-and-candidate-a)

1. Author a synthetic multi-object PDB/session fixture covering: two chains,
   multiple residues with an insertion code, an altloc-bearing residue, a
   hetero group, a modified-coordinate case, and a second NMR-style state
   (MODEL/ENDMDL). Keep it small and hand-inspectable.
2. Extract "canonical structured data" (candidate A) via PyMOL query APIs
   (`iterate`/`iterate_state`/`get_view`/settings getters) into an explicit,
   versioned Python structure covering: object/state identity; atom identity
   and coordinates; chain/residue/insertion/atom/element/altloc/polymer/
   hetero metadata; bonds; visibility/representation/color; view and
   supported settings; and measurement objects.
3. Reconstruct a fresh PyMOL process from that structured data alone (no
   access to the original file) and re-extract the same structured data.
4. Diff the two extractions field by field; report exact matches and any
   unsupported or lossy field, never silently dropping one.
5. Record the result against fidelity, boundedness, inspectability,
   portability, and reconstruction cost -- the same axes used to select among
   all three candidates at the end of slice 2.

## Validation

- Exploratory venv run (`h02-explore-venv`, pinned to
  `pymol-open-source-whl==3.2.0.2`) -> fast iteration while the fixture and
  extractor shape is still moving.
- `bazel test //<new target>` once the probe stabilizes -> the same evidence
  reproduced under the project's real portability/hermeticity guarantee.

## Risks and rollout

- Disposable prototype only; nothing ships to a production package in this
  slice. No rollout risk.
- Risk of scope creep into all four slices at once -- contained by keeping
  this plan to slice 1 and checking in before slice 2.

## Decisions needed

- No GitHub issue exists yet for H-02. The wave plan's team agreement is to
  create issues for current-wave work after plan acceptance; recommend
  creating one once this slice-1 plan is confirmed, rather than blocking
  start of the exploratory work on it.

## Completion evidence

- **Delivered:** A candidate-A (canonical structured data) extractor and
  reconstructor covering object/state identity, atom identity and
  coordinates, chain/residue/insertion-code/altloc/element/hetero metadata,
  bonds, per-atom color and representation, camera view, and a bounded set
  of safe object-level settings. A synthetic fixture exercises two chains,
  two coordinate states (a modified-coordinate NMR-style case), an
  insertion code, an altloc pair, and a hetero atom. The reconstructor
  runs in a genuinely fresh second process that only ever reads the
  extracted JSON snapshot, never the source fixture file, matching H-02's
  fresh-process requirement. A negative-result test records that
  measurement objects are not recoverable through this candidate's query
  APIs (`iterate`/`get_model`) at all -- `cmd.get_session()` is the only
  introspection path found, and it returns raw baked-in data structurally
  belonging to candidate C, not this candidate's query-based extraction.
- **Changed:** `tests/discovery/README.md` (new), `tests/discovery/h02/`
  (new: `README.md`, `BUILD.bazel`,
  `test_full_v1_snapshot_candidate_a.py`,
  `testdata/h02_full_v1_fixture.pdb`), this implementation plan.
- **Head commit/snapshot:** Slice 1 was committed at
  `9fd60570c0cc90cc1744a43d0c5923a4e32b744e`. Its round-1 lightweight
  reviewer independently recorded `READY_FOR_OUTER_LOOP` at that same commit
  after rerunning the full reported validation. H-02 was then reopened into
  outer recovery round 3; it is not completed, published, or outer-loop
  reviewed.
- **Validation actually run:**
  - `bazel test //tests/discovery/h02:full_v1_snapshot_candidate_a
     --test_output=errors` -> pytest collected 8 tests: 7 passed and 1
    expected parent-process skip. The skipped reconstruction helper runs
    successfully in the nested subprocess selected by the fresh-process
    round-trip test.
  - `bazel test //...` -> all 19 repository test targets pass; no
    regression in any existing target.
  - `bazel run //tools/quality:ruff -- check tests/discovery/` -> all
    checks passed.
  - `bazel run //tools/quality:ruff -- format --check tests/discovery/`
    -> clean after one `ruff format` pass (applied).
  - `bazel run //tools/quality:pyrefly -- check` -> 0 errors repository-wide.
  - `bazel run //tools/bazel:check_dependency_boundaries` -> exit 0.
- The required code-audit gate was interrupted by an API rate limit after
  partial documentation-only changes. Outer recovery round 3 added the
  triaged Candidate-A corrections and reran the targeted and full Bazel tests,
  Ruff check and format, Pyrefly (0 errors), the dependency-boundary check,
  and `git diff --check`; all passed. The Windows incompatibility remains
  explicit, so Windows smoke is not Candidate-A fidelity evidence.
- **Acceptance evidence:**
  - "Fixture matrix covers object/state identity; atom identity and
    coordinates; chain/residue/insertion/atom/element/alternate-location/
    polymer/hetero metadata; bonds; ... visibility/representation/color
    state; view and supported setting state" -> covered and round-tripped
    with zero mismatches, including representative labels and object enabled
    state, except measurement objects (see below) and
    polymer/hetero classification beyond the `hetatm` flag already
    recorded (polymer status is derivable from resn/hetatm but not
    separately stored -- a candidate-A schema gap for slice 4's
    write-up, not a fidelity failure).
  - "Modified coordinates, multiple states, ... and hetero atoms must be
    represented" -> the fixture's second MODEL state shifts every atom's
    z-coordinate, and both states round-trip exactly.
  - "It must define explicit unsupported-state behavior rather than
    silently dropping fields" -> satisfied for measurement objects via
    the dedicated negative-result test, and unknown candidate-A schema
    versions fail explicitly in `from_json`.
  - Outer findings H02-OUTER-F1 through H02-OUTER-F4 are addressed by the
    candidate-private label/enabled fields, version validation, identity diff,
    and independent expected-value/mutation tests. H02-OUTER-F5 is recorded:
    the discovery target is incompatible/skipped on Windows because of the
    PyMOL wheel path limitation, so green Windows smoke does not establish
    Candidate-A fidelity there; Martin's environment remains needed.
- **Scope deviations:** None from slice 1's own scope. Settings and
  measurement-object coverage were originally flagged as open items
  during the session and completed within this same slice at the
  developer's direction, rather than deferred.
- **Known limitations:**
  - Measurement objects are an explicit, evidenced gap for candidate A;
    slice 2's comparison against candidate C should resolve whether any
    candidate can represent them, or whether the wave returns them to
    product scope per the risk table.
  - `SAFE_SETTINGS` covers two representative settings only, not the full
    safe-setting surface; the contract-freeze checkpoint decides the real
    accepted set.
  - Polymer/hetero classification beyond the `hetatm` boolean (e.g. an
    explicit polymer flag) is not yet in the schema.
  - Candidates B and C (slice 2) and the fresh-process failure-mode
    prototype (slice 3) are not started.
- **Review state:** Slice 1 was independently recorded `READY_FOR_OUTER_LOOP`
  in round 1 at `9fd60570c0cc90cc1744a43d0c5923a4e32b744e`. Outer recovery
  round 4 then ran the outer-loop specialist review against the corrected
  `f769a51` snapshot (`correctness-tests-specialist` and
  `architecture-maintainability-specialist`) and recorded
  `READY_FOR_HUMAN_APPROVAL` with no blocking findings. The slice is published
  as pull request [#16](https://github.com/urban233/pymol-copilot/pull/16)
  (open, not draft) but has zero recorded GitHub reviews as of this note;
  merge still requires that independent human approval before slice 1 is
  actually landed upstream. Slice 2 (below) proceeds on a branch stacked on
  top of `codev/H-02`'s current head rather than waiting for that merge, per
  the task's own stacked-slice model -- it will need rebasing onto `main`
  once #16 merges.

## Proposed change (slice 2: candidate-b-and-c)

Reuses the slice 1 fixture (`tests/discovery/h02/testdata/h02_full_v1_fixture.pdb`)
and PyMOL harness unchanged; extends the same differential method to the
task's other two candidate serializations.

1. Extract the candidate-agnostic parts of slice 1's harness --
   `ObjectSnapshot`/`AtomRecord`/`BondRecord`/`StateSnapshot`, `extract()`,
   `_diff()`, `SAFE_SETTINGS`, `REP_NAMES`, the `real_pymol`/`loaded_fixture`
   fixtures, and the nested-subprocess-via-env-var pattern -- into a shared
   `tests/discovery/h02/harness.py` module. Update
   `test_full_v1_snapshot_candidate_a.py` to import from it instead of
   defining its own copies (behavior-preserving refactor; slice 1's own test
   still passes unchanged). This is what "against the same fixture and
   harness" means mechanically, and avoids duplicating ~500 lines per new
   candidate.
2. Candidate B (standard export + manifest): export the loaded fixture with
   `cmd.save(..., format="pdb")` (matching the fixture's own format and the
   diff engine's existing 1e-3 coordinate tolerance, itself derived from
   PDB's 3-decimal precision). Pair it with an explicit JSON manifest for
   everything PDB cannot carry: per-atom color/representation, camera view,
   `SAFE_SETTINGS`, labels, and bonds (recorded explicitly rather than
   trusting PDB `CONECT` emission, which is a real empirical unknown this
   probe should record either way). Reconstruct in a genuinely fresh second
   process fed only the exported `.pdb` and manifest paths (never the source
   fixture), apply the manifest, then re-extract with the shared `extract()`
   and diff against the original extraction.
3. Candidate C (PyMOL session): export with `cmd.save(..., format="pse")`.
   Reconstruct in a fresh process via `cmd.load()` of only the `.pse` file --
   no manifest, since session serialization is native. Re-extract with the
   same shared `extract()` and diff. Add a positive-result test for
   measurement objects (`cmd.distance`), directly contrasting slice 1's
   negative result for candidate A.
4. Record fidelity, boundedness, inspectability, portability, and
   reconstruction-cost evidence for both candidates on the same axes as
   slice 1, including whether PDB's `CONECT` records actually round-trip
   bonds and whether `.pse` recovers measurement objects.
5. Update this plan's known limitations with the findings. No candidate is
   selected in this slice -- selection is slice 4's job once all three
   candidates have differential evidence.

**Validation (slice 2):** Same three-tier pattern as slice 1 -- an
exploratory venv loop while the harness refactor and new extractors are
still moving, then hermetic Bazel `py_test` targets
(`full_v1_snapshot_candidate_b`, `full_v1_snapshot_candidate_c`), tagged
`exclusive` and Windows-incompatible for the same nested-subprocess reasons
as slice 1's target, plus a full `bazel test //...` regression run and the
same lint/format/type/dependency-boundary checks.

## Slice 2 completion evidence (candidate-b-and-c)

- **Delivered:** `tests/discovery/h02/harness.py`, a shared, candidate-
  agnostic differential harness factored out of slice 1's candidate-A
  module: the `ObjectSnapshot`/`AtomRecord`/`BondRecord`/`StateSnapshot`
  dataclasses, `extract()`, `_diff()`, `SAFE_SETTINGS`, `REP_NAMES`,
  `FIXTURE_PATH`, the `real_pymol`/`loaded_fixture` fixtures, and
  `run_nested_snapshot_process()` (the nested-subprocess-via-environment-
  variable technique, now a reusable helper rather than inlined once per
  candidate). `to_json`/`from_json` moved too, renamed from candidate A's
  private `CANDIDATE_A_SCHEMA_VERSION` to a shared `SNAPSHOT_SCHEMA_VERSION`
  -- not explicitly named in this plan's own slice-2 list, but unavoidable
  once `extract()` itself is shared: every candidate's nested-process diff
  needs the same JSON round trip to carry the parent's
  "expected" extraction across the process boundary, so keeping that logic
  in one place is exactly what avoids the ~500-line-per-candidate
  duplication this slice exists to avoid. Candidate A's own `reconstruct()`
  and its own `SNAPSHOT_ENV_VAR` stayed candidate-specific, as planned.
  Candidate B (`test_full_v1_snapshot_candidate_b.py`): exports the loaded
  fixture with `cmd.save(..., "fx", state=0, format="pdb")`, paired with an
  explicit JSON manifest (`CandidateBManifest`,
  `CANDIDATE_B_MANIFEST_SCHEMA_VERSION`) carrying per-atom color/
  representation/label, camera view, `SAFE_SETTINGS`, and bonds -- keyed by
  each atom's `(chain, resi, resn, name, alt)` identity rather than a
  reconstruction-time positional index. Reconstruction in a fresh nested
  process loads only the exported `.pdb` and manifest, applies the
  manifest, then re-extracts and diffs with the shared harness. Candidate C
  (`test_full_v1_snapshot_candidate_c.py`): exports with
  `cmd.save(..., format="pse")` (no selection argument -- see finding
  below) and reconstructs with a bare `cmd.load()` of only the `.pse` file
  in a fresh nested process, no manifest, then re-extracts and diffs with
  the same shared harness.
- **Changed:** `tests/discovery/h02/harness.py` (new),
  `tests/discovery/h02/conftest.py` (new, see Scope deviations),
  `tests/discovery/h02/test_full_v1_snapshot_candidate_b.py` (new),
  `tests/discovery/h02/test_full_v1_snapshot_candidate_c.py` (new),
  `tests/discovery/h02/test_full_v1_snapshot_candidate_a.py` (refactored to
  import the above from harness.py instead of defining its own copies;
  candidate-specific `reconstruct()` and its tests are otherwise
  unchanged), `tests/discovery/h02/BUILD.bazel` (added a `harness` py_library
  and `full_v1_snapshot_candidate_b`/`full_v1_snapshot_candidate_c` py_test
  targets mirroring candidate A's), this implementation plan.
- **Fidelity/boundedness/inspectability/portability/reconstruction-cost
  findings (candidates B and C):**
  - **CONECT (candidate B, fidelity):** confirmed empirically that PyMOL's
    PDB writer emits **zero** `CONECT` records for this fixture's
    `cmd.save(..., format="pdb")` export, even though every bond in the
    fixture is an ordinary single bond between geometrically bonded atoms
    -- there is no partial or conditional CONECT emission to rely on here,
    at least for this fixture. Despite that, reloading the plain PDB in a
    fresh process still reports the original 15 bonds with the original
    orders -- but only because PyMOL's PDB loader independently
    *re-perceives* a bond graph from interatomic geometry by default, not
    because the file encodes those bonds; that auto-perceived graph would
    silently mask a broken or missing manifest bond list for this
    particular fixture (every bond happens to be a single bond between
    close, plausible partners). Candidate B's `apply_manifest()` therefore
    calls `cmd.unbond()` to strip PyMOL's own guess before re-adding only
    the manifest's explicit bonds, so its round trip is genuine evidence
    for the manifest mechanism, not a coincidence of auto-perception. This
    confirms the plan's own expectation: candidate B must record bonds
    explicitly and cannot rely on CONECT.
  - **Multi-state export (candidate B, fidelity):** `cmd.save`'s default
    `state=-1` (current state only) silently drops every state but one;
    `state=0` is required to write every coordinate state as its own
    MODEL/ENDMDL block. Confirmed empirically for this fixture's two
    states.
  - **Atom addressing (candidate B, boundedness/inspectability):** a plain
    atom-identity selection (`chain "<chain>" and resi "<resi>" and resn
    "<resn>" and name "<name>" and alt "<alt>"`) addresses exactly one atom
    for every atom in this fixture, including the insertion-code residue
    and both members of the altloc pair -- confirmed empirically. Atom
    order was also observed to survive this fixture's PDB round trip
    unchanged, but the manifest keys atoms by this identity tuple rather
    than by position, since the order guarantee is fixture-specific, not
    general.
  - **Measurement objects (candidate B, fidelity -- negative result,
    matching candidate A):** exporting a measurement object through
    `cmd.save(..., format="pdb")` fails outright (`pymol.parsing
    .QuietException`, confirmed empirically to carry an *empty* message,
    unlike the `pymol.CmdException` with a real message that candidate A's
    equivalent negative test observes for `count_atoms`) -- a measurement
    object is not a selectable set of atoms by either path, so no standard
    export format can carry one.
  - **Session export selection (candidate C, reconstruction cost/
    inspectability pitfall):** `cmd.save(path, format="pse")` must be
    called with **no** `selection` argument to capture the whole session.
    Passing an explicit `selection="all"` was tried first and produced a
    broken, effectively empty session file for this fixture (a fraction of
    the size of the default save; reloading it yielded zero objects,
    confirmed empirically) -- `"all"` is not a safe stand-in for PyMOL's
    own true default in `cmd.save`'s session handling.
  - **Object naming on load (candidate C, reconstruction cost):**
    `cmd.load()` of a `.pse` file does not accept a meaningful target
    object name the way it does for a plain structure file; every object
    regains whatever name it was saved under (confirmed empirically).
    Reconstruction therefore calls `cmd.load(pse_path)` with no name
    argument and refers to the fixture by its original name afterward.
  - **Measurement objects (candidate C, fidelity -- positive result,
    contrasting candidates A and B):** a `cmd.distance` measurement object
    *does* survive this candidate's round trip: reloading a `.pse` file
    saved while "d1" existed restores "d1" as a real `object:measurement`
    again, confirmed empirically in the same process (save, delete all,
    reload). Session serialization is not limited to an atom-based
    selection the way a query API or a structure-file export is.
  - **Portability:** neither candidate B nor C is expected to change this
    task's existing Windows finding (H02-OUTER-F5): both new targets carry
    the same `pymol-open-source-whl` dependency and the same
    `target_compatible_with` exclusion as candidate A, for the same
    delvewheel/MAX_PATH reason (issue #12); this was not independently
    re-tested on Windows in this slice.
- **Validation actually run:**
  - Exploratory venv (`pymol-open-source-whl==3.2.0.2`, matching slice 1's
    pin): `python -m pytest test_full_v1_snapshot_candidate_a.py -q` after
    the harness refactor -> 7 passed, 1 skipped (the nested-process
    reconstruction test, which only runs meaningfully in its spawned
    child) -- identical to slice 1's own recorded result, confirming the
    refactor is behavior-preserving.
  - Exploratory venv: `python -m pytest
    test_full_v1_snapshot_candidate_b.py -q` (candidate B, first pass,
    before the exception-matching fix below) -> 1 failed, 3 passed, 1
    skipped. The one failure was
    `test_measurement_objects_are_not_recoverable_via_pdb_export` asserting
    `pytest.raises(Exception, match="Invalid selection name")`; the actual
    exception is `pymol.parsing.QuietException` with an empty message (the
    diagnostic text only reaches PyMOL's own stdout). Fixed by asserting
    only that an exception is raised, and recorded as a finding above
    rather than papered over. This fix was **not** re-executed afterward
    (see Known limitations) -- the tool-execution restriction below began
    immediately after this run.
  - Standalone empirical probe scripts (not part of the retained test
    suite; run directly against the pinned wheel in the exploratory venv,
    outside pytest) established every finding above before it was encoded
    into `harness.py`/candidate B/candidate C: PDB `CONECT` emission and
    bond re-perception on reload, PDB atom-identity/order preservation,
    `cmd.save(..., format="pse")` selection-argument sensitivity, and
    `cmd.load()`'s name-argument handling for `.pse` files.
  - Isolated ruff repro (two-line helper module, a conftest.py-style
    re-export, and a two-test module -- not part of the retained test
    suite): `python -m ruff check . --select F401,F811` reported zero
    errors for the conftest.py re-export pattern, and the corresponding
    `pytest` run passed both tests, confirming the pattern this slice's
    real `conftest.py` uses is sound in principle.
  - `bazel run //tools/quality:ruff -- check tests/discovery/`, run once
    against the real files **before** the conftest.py fix, reported real,
    expected findings: 11 `F811` "redefinition of unused" errors (7 in
    candidate A, 4 in candidate B) from every test function's
    `loaded_fixture` parameter shadowing the then-direct
    `from harness import loaded_fixture` import -- this is exactly the
    problem conftest.py was introduced to fix (see Scope deviations).
  - **Deferred, then completed externally:** the implementing session's
    tool-execution layer began refusing every `bazel`, `ruff`, `pip`, and
    even previously-successful `pytest` invocation partway through this
    slice, each time reporting the refusal was about earlier conversation
    content rather than the specific command; plain read/search/edit
    operations kept working, which is how implementation continued. That
    left candidate C written but never executed, and candidate B's
    exception-matching fix unverified. The remaining validation was
    therefore run to completion outside that session, against the exact
    files on disk, and is recorded below. The refusal was a tool-level
    limitation of one session, not a project or code finding.
  - `bazel test //tests/discovery/h02:full_v1_snapshot_candidate_a
    //tests/discovery/h02:full_v1_snapshot_candidate_b
    //tests/discovery/h02:full_v1_snapshot_candidate_c
    --test_output=errors` -> 3 of 3 PASSED (candidate A 16.3s, candidate B
    11.9s, candidate C 10.5s).
    **This result was later shown to be meaningless and must not be read
    as fidelity evidence.** Outer-loop review established that all three
    fresh-process round-trip tests were structurally incapable of failing
    at this commit; see "Outer-loop corrections" below for what was
    actually wrong and what the genuine results turned out to be. The line
    is kept rather than deleted so the evidence trail shows what was
    believed at the time and how it was corrected.
  - `bazel test //...` -> 21 of 21 test targets pass; no regression in any
    pre-existing target. Re-run after the formatting fix below, with
    candidate A re-executing in 18.7s.
  - `bazel run //tools/quality:ruff -- check tests/discovery/` -> all
    checks passed; the 11 pre-fix `F811` errors are fully resolved by the
    `conftest.py` re-export.
  - `bazel run //tools/quality:ruff -- format --check tests/discovery/` ->
    initially reported one violation (a `pytest.raises` call split across
    three lines in candidate A that the formatter joins); after applying
    it, 7 files already formatted.
  - `bazel run //tools/quality:pyrefly -- check` -> initially **22 errors**,
    every one `Cannot find module 'harness' [missing-import]` from the bare
    sibling-module imports in candidates A/B/C and `conftest.py` -- a real
    regression against slice 1's recorded 0 errors, since `pyproject.toml`
    deliberately sets `missing-import = "error"`. Resolved by the
    `search-path` addition recorded under Scope deviations, not by
    suppression; re-run afterward -> **0 errors** (20 suppressed), matching
    slice 1's baseline.
  - `bazel run //tools/bazel:check_dependency_boundaries` -> exit 0.
  - `git diff --check` -> clean.
- **Scope deviations:**
  - `tests/discovery/h02/conftest.py` was added; it is not named in this
    plan. It exists solely to make `real_pymol`/`loaded_fixture` (moved to
    harness.py, exactly as planned) available to every candidate test
    module's own fixture-by-parameter-name requests without each module
    importing those two names directly -- confirmed empirically that a
    direct `from harness import loaded_fixture` import, combined with
    every test function's own `loaded_fixture` parameter (pytest's
    ordinary fixture convention), trips `ruff`'s F811 ("redefinition of
    unused name") once per test function, for a real 11 errors across the
    two affected files before the fix. A directory-scoped `conftest.py`
    re-export is pytest's own standard mechanism for exactly this sharing
    case and removes the shadowing entirely, at the cost of one new file
    this plan did not anticipate.
  - `to_json`/`from_json` (renamed to use a shared `SNAPSHOT_SCHEMA_VERSION`
    in place of candidate A's private `CANDIDATE_A_SCHEMA_VERSION`) moved
    into harness.py alongside `extract()`/`_diff()`, though not separately
    named in this plan's own slice-2 list -- see Delivered above for why
    this was unavoidable rather than optional cleanup.
  - `pyproject.toml` was modified to add
    `search-path = ["tests/discovery/h02"]` to `[tool.pyrefly]`. This is
    outside this slice's stated allowed scope (a disposable prototype
    location and this task's own documents) and was explicitly authorized
    by Hannah after the alternatives were weighed. The bare
    `from harness import ...` imports resolve at runtime because pytest and
    Bazel place the test's own directory on `sys.path`, but pyrefly cannot
    see that. Suppressing the 22 errors with `# pyrefly: ignore.` was
    rejected deliberately: `pyproject.toml:128` sets
    `missing-import = "error"` with the comment "Keeps missing
    architectural imports guarded as hard failures", and blanket-
    suppressing that error class would work against a stated project
    policy. The search path makes the imports genuinely resolve instead,
    leaving the hard-failure guarantee intact everywhere else.
  - No candidate was selected; selection remains slice 4's job, as planned.
- **Known limitations:**
  - Windows compatibility for the two new targets is asserted by
    construction (same wheel, same exclusion as candidate A) but not
    independently tested here, consistent with H02-OUTER-F5's existing
    scope.
  - Candidate B's manifest schema (`CANDIDATE_B_MANIFEST_SCHEMA_VERSION`)
    and candidate A's extraction schema
    (`harness.SNAPSHOT_SCHEMA_VERSION`) are both private prototype
    versions, not the contract-freeze checkpoint's real accepted schema,
    exactly as slice 1 already recorded for its own schema version.
- **Review state:** Inner loop complete (round 5, `READY_FOR_OUTER_LOOP`).
  Outer-loop review then ran across rounds 6-8 and materially corrected
  the evidence above -- see the next section, which supersedes it wherever
  the two disagree.

## Outer-loop corrections (slice 2, rounds 6-8)

Outer-loop review found that slice 2's headline validation result did not
mean what it appeared to. The corrections below are recorded at the same
level of detail as the original claims, because the original claims were
wrong and a reader needs to know exactly how.

### The round-trip tests could not fail (H02-S2-F1) -- fixed at `252e41a`

`run_nested_snapshot_process` spawned its nested "genuinely fresh process"
as `python -m pytest <file>`. That runs the file through pytest's own
runner as an imported module, so it never reaches the module's `__main__`
block -- and that block is the only place the repository's `os._exit`
workaround for PyMOL's headless shutdown clobbering the exit code is
applied. The child's real exit code could therefore silently become 0
after a genuine failure.

Proven, not inferred: substituting an unconditional `raise AssertionError`
into a nested test still produced a `PASSED` Bazel target. Every
fresh-process round-trip test in this directory -- candidates A, B and C
-- was structurally incapable of failing. The recorded "3 of 3 PASSED"
established nothing about reconstruction fidelity.

The fix spawns the child via `python -c` running a runner that reproduces
`pytest.main()` -> flush -> `os._exit(code)` directly, preserving the `-k`
selector so the child still runs exactly one test and cannot recurse.
Independently confirmed with real PyMOL: a nested failure after
`finish_launching` yields parent exit 1 under the new spawn and parent
exit 0 under the old one.

**This defect also affects slice 1.** Candidate A's round-trip test used
the same `-m pytest` invocation inline, so slice 1's recorded
fresh-process evidence in pull request #16 was masked in exactly the same
way. The fix lives here in slice 2, stacked on top of it.

### Candidate B did not actually round-trip (H02-S2-F2) -- fixed at `252e41a`

With the masking removed, candidate B's reconstruction showed 8 real
mismatches: `cmd.save(..., format="pdb")` renumbers atom serials by write
order rather than preserving them, so the hetero ZN atom's serial 13
reloaded as 10, shifting IDs 10-13 across both states. Atom identity is an
explicit wave acceptance category, so this was a genuine fidelity gap that
the inert test had been hiding.

Repaired rather than documented away: the manifest now carries each atom's
`serial` and `apply_manifest` restores it via `cmd.alter(sel, f"ID=...")`.
The identity selection uses only chain/resi/resn/name/alt and no serial
term, so restoration is order-independent and cannot invalidate the
selection driving it. This is squarely the candidate-B thesis -- a
standard export plus an explicit manifest for what the format cannot
carry.

### Candidate C was never actually measured (H02-S2-F3) -- resolved at `252e41a`

Candidate C's fidelity had only ever been asserted, never executed under a
working exit-code check. It now genuinely passes. Its measurement-object
recovery is demonstrated by real executing assertions, but **same-process**
(save/delete/reload within one session), not across the fresh-process
boundary -- recorded as H02-S2-F13 so slice 4 does not overread it.

### The first regression guard was itself inert (H02-S2-F12) -- fixed at `86893d4`

The guard added alongside the F1 fix did not work either, in two
independent ways: `test_harness.py` had no `__main__` block while its
`py_test` set `main` to that file, so Bazel ran it as a script that
defined a function and exited 0 with empty test output; and its nested
child was PyMOL-free, so `-m pytest` returned nonzero for it anyway and it
could not have discriminated the spawn forms. Its docstring nonetheless
claimed it proved the defect could not return.

Now fixed and verified in both directions, twice independently: with the
pre-fix spawn restored the target FAILS (bazel exit 3), with the fix in
place it PASSES. The child launches headless PyMOL before failing, so the
masking condition is actually present. Cost of that: the target needed
real PyMOL and so lost the Windows coverage it previously had, a
deliberate trade stated in `BUILD.bazel`.

### Genuine validation at `86893d4`

Every check below was run against the corrected files, with the
round-trip tests now demonstrably able to fail:

- Three candidate targets, `--nocache_test_results` -> 3 of 3 PASSED.
- `//tests/discovery/h02:harness_test` -> PASSES with the fix, FAILS with
  the pre-fix spawn restored (the property that makes the above
  meaningful).
- `bazel test //...` -> 22 of 22 targets pass.
- Ruff check and `format --check`, Pyrefly (0 errors), and the
  dependency-boundary check all clean.

### Open, deliberately deferred

Non-blocking and untouched by design: H02-S2-F4 (candidate B's module
docstring still describes the measurement-export failure as the
message-bearing `Invalid selection name` error rather than the
empty-message `QuietException` its own corrected test records), F5 (no
test exercises candidate B's manifest schema-version guard), F6
(`pytest.raises(Exception)` is near-vacuous), F7 (`_diff` is
private-named but is the shared public seam), F8 (candidate-agnostic
display-state read duplicated between `harness.py` and candidate B), F9
(three near-identical Bazel target blocks), F11 (the same explanatory
comment repeated in three modules), F13 (candidate C's same-process
measurement caveat above), and the observation that the `pyproject.toml`
`search-path` entry outlives the disposable prototype and should be
removed in slice 4.

Coverage for `security_privacy_data_compatibility`, `concurrency` and
`rollout` was waived for this slice with recorded reasons, not verified.

## Proposed change (slice 3: fresh-process-execution-boundary)

Prototypes the request/report boundary the accepted design calls the
hermetic execution protocol, whose stated guarantees are "fresh process,
finite resources, command-indexed outcomes, and deterministic evidence
where declared", and whose stated error behavior is that "timeout,
resource, and PyMOL errors terminate the process with no internal retry"
([plan and execution](../../design/shared-core/plan-and-execution.md#apis-and-contracts)).
This slice builds a disposable prototype of that boundary and the sabotage
fixtures that prove it fails closed. It ships no production API.

1. Add a new `tests/discovery/h02/execution_boundary.py` process primitive.
   It must be its own primitive, **not** an extension of
   `run_nested_snapshot_process`: that helper is a nested-pytest runner
   with no deadline and no kill path, and growing it with timeout/kill flags
   would both overload one function and put this slice's failure modes
   inside the harness every candidate test depends on. Outer-loop review of
   slice 2 called this out explicitly.
2. Define the request and report shapes. A request carries a candidate
   snapshot (reuse the shared harness's `ObjectSnapshot` and its JSON round
   trip), an ordered command list, and explicit finite limits -- maximum
   input size in bytes and a wall-clock deadline. A report carries the
   input fingerprint, the resulting fingerprint, per-command outcomes
   indexed by position, timing, and any warnings. Both are versioned like
   the slice-1 and slice-2 schemas, and both remain candidate-private
   prototype shapes, not the contract-freeze checkpoint's accepted
   contract.
3. Implement the boundary itself: spawn a genuinely fresh PyMOL process,
   reconstruct from the snapshot alone, execute the commands in order,
   collect per-command outcomes, and return the report. Enforce the
   deadline with a hard kill, reap the child so no process is left behind,
   and delete all scratch data on every exit path, success or failure.
4. Probe each failure mode with its own sabotage fixture, asserting the
   boundary fails closed, reports a typed reason, performs no internal
   retry, leaves no live child process, and leaves no scratch data:
   oversized input, malformed input, incompatible schema version,
   spawn or load failure, wall-clock timeout, forced child crash, PyMOL
   command failure, and fidelity mismatch between the expected and
   resulting fingerprints.
5. Assert the positive path too: a well-formed request returns a report
   whose command-indexed outcomes and fingerprints match independently
   computed expected values, and repeat it to show the evidence is
   deterministic where the design says it is declared to be.

**Validation (slice 3):** The focus card's middle tier -- medium-scope
subprocess timeout, crash and cleanup probes. Each failure mode gets a
Bazel `py_test` following the established pattern for this directory
(`exclusive` tag, Windows exclusion where real PyMOL is involved, and the
`__main__` + flush + `os._exit` discipline slice 2 proved is load-bearing
for a trustworthy exit code). Plus the full repository suite, Ruff check
and format, Pyrefly, and the dependency-boundary check.

**Explicitly not in this slice:** no candidate is selected (slice 4), no
production snapshot, card, or executor API ships before the joint
contract-freeze checkpoint with M-02, and the ten non-blocking findings
left open by slice 2's review are not swept up here unless one is directly
in the way.

## Slice 3 completion evidence (fresh-process-execution-boundary)

Implemented at `c82fed6`, corrected at `daff445` after outer-loop review.

**Delivered:** `tests/discovery/h02/execution_boundary.py`, a disposable
prototype of the design's hermetic execution protocol -- versioned,
candidate-private request and report shapes plus an `execute()` primitive
that spawns a genuinely fresh PyMOL child, reconstructs from the snapshot
alone, runs an ordered command list, enforces a wall-clock deadline with a
hard kill, reaps the child, and deletes all scratch data on every exit
path. `tests/discovery/h02/test_execution_boundary.py` probes all eight
declared failure modes plus the positive path.
`tests/discovery/h02/build_defs.bzl` collapses the repeated `py_test`
shape this directory had copied four times, retiring most of slice 2's
H02-S2-F9.

**Validation at `daff445`:**

- `//tests/discovery/h02/...` with `--nocache_test_results` -> 5 of 5
  targets PASSED; the probe module itself is 16 tests, up from 9.
- `bazel test //...` -> 23 of 23 targets pass, no regression.
- Ruff check and `format --check`, Pyrefly (0 errors, 20 suppressed,
  matching the slice-1 baseline), and the dependency-boundary check
  (exit 0) all clean.

**Known limitations:** "Finite resources" is prototyped as two of the
design's limits only -- maximum input bytes and a wall-clock deadline --
with no memory bound and nowhere in either shape to record that omission
(H02-S3-F14). A `STATUS_OK` report is therefore not evidence that the
design's full finite-resources guarantee holds. Windows is excluded from
these targets as it is for every real-PyMOL target here (issue #12), so
the green Windows smoke job did not execute them. Coverage for
`security_privacy_data_compatibility` and `rollout` was waived for this
slice with recorded reasons, not verified.

## Outer-loop corrections (slice 3, rounds 11-12)

Round 11 ran three specialists -- correctness/tests, concurrency, and
architecture/maintainability -- against `c82fed6` and returned
CHANGES_REQUIRED with fifteen findings, two of them blocking. Both
blocking findings were triaged "address" and are fixed at `daff445`. What
makes them worth recording is that both were found by *running* the code
rather than reading it, and both concerned guarantees this module
documents about itself.

### The boundary raised instead of failing closed (H02-S3-F1) -- fixed at `daff445`

`execute()` documents that it "never raises for any of this module's own
documented failure modes". It did. `harness.from_json` does `json.loads`,
then `data.get("schema_version")`, then indexes required keys, so any
syntactically valid JSON that is not a snapshot object escaped the
`except (json.JSONDecodeError, ValueError)` clause entirely: `42`, `null`,
`[]`, `"hello"` and `true` each raised `AttributeError`, and an object
missing a key raised `KeyError`. The specialist demonstrated this against
the shipped code with no mutation at all.

The fix broadens the clause to `(KeyError, AttributeError, TypeError)`
mapped to `REASON_MALFORMED_INPUT`, placed after the version check so an
unsupported-but-recognized version still reports as
`REASON_UNSUPPORTED_SCHEMA_VERSION`. Six new probes cover the class.
Reverting the clause makes all six fail with exactly the uncaught
`AttributeError`/`KeyError` the finding described -- so the probes are
load-bearing, not decorative.

### "No internal retry" was asserted only by a test name (H02-S3-F2) -- fixed at `daff445`

The design authority requires that errors "terminate the process with no
internal retry". The test named for that guarantee asserted only on
`command_outcomes` -- one recorded failure at index 0 -- which a child
silently retrying three times before recording one final failure
satisfies perfectly. The specialist proved it: with such a retry
injected, all nine probes passed, including that one.

The fix adds `COUNT_THEN_FAIL_VERB`, a sentinel the child always fails on
but only after incrementing a counter file on each real invocation, and a
separate test asserting the counter reads exactly `1`. Attempt count, not
outcome count, is now the load-bearing assertion.

The first attempt at this fix *replaced* the original test rather than
adding to it, which would have silently dropped the only coverage of a
genuine `pymol.CmdException` travelling through the child's real
exception handler -- the sentinel is special-cased before that handler
and never reaches it. Caught in review before it landed; the two tests
now sit side by side, one exercising the real PyMOL failure path and one
counting attempts.

Verified in both directions at `daff445`: with a genuine three-attempt
retry injected into the child runner, the new test fails on
`assert '3' == '1'` while the other fifteen pass -- including the
original command-failure test, which is precisely the blind spot the new
test closes. Restored and re-run clean, with the file confirmed
byte-identical by checksum before and after each experiment.

### Open, deliberately deferred

Thirteen non-blocking findings were recorded and left unaddressed, except
H02-S3-F13 (this document's own Status header still read "slices 3-4 not
started" in the commit that implemented slice 3), corrected here because
the same edit was already touching that header.

Deferred: H02-S3-F3 (a child escaping between spawn and `communicate()`
is neither killed nor reaped, and its scratch directory is deleted while
it may still be live -- reachable only through the test-only hook or an
async exception, demonstrated empirically), F4 (the post-kill drain is
unbounded, latent today because the child never forks), F5
(orphan-on-parent-SIGKILL is undocumented; Bazel's sandbox is the
backstop), F6 (the child's entire 91-line program is a string literal,
invisible to Ruff and Pyrefly, re-hardcoding the `STATUS_*`/`OUTCOME_*`
literals the parent compares against), F7 (reconstruction technique and
sabotage verbs are hardwired into the primitive rather than injected),
F8 (`input_fingerprint`'s docstring contradicts `_rejected()`'s
unconditional `None`), F9 (`execute()` adjudicates a caller expectation
under the same status as real failures), F10 (the report carries no
process evidence, so "fresh process, no leak" is observable only through
a test-only hook), F11 (the new Bazel macro still leaves redundant `deps`
and `data` at each call site), F12 (a fifth verbatim copy of the
`__main__` boilerplate, extending slice 2's H02-S2-F11), F14 (the
memory-bound gap recorded above), and F15 (the module docstring's retry
claim is broader than what the fixed tests verify).

F3 and F10 compound: the reap gap F3 demonstrates is invisible from the
report a real caller sees. Slice 4 should take both together.
