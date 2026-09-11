# H-02: Prove full-V1 snapshot reconstruction and execution boundaries -- Implementation Plan

**Status:** In progress -- slices 1 to 3 are complete, outer-loop reviewed, and
merged: slice 1 (`fixture-matrix-and-candidate-a`) as pull request
[#16](https://github.com/urban233/pymol-copilot/pull/16), slice 2
(`candidate-b-and-c`) as [#17](https://github.com/urban233/pymol-copilot/pull/17),
and slice 3 (`fresh-process-execution-boundary`) as
[#18](https://github.com/urban233/pymol-copilot/pull/18), whose head `902064b`
has a tree identical to the resulting `main` at `2387fd2`. Slice 4
(`differential-report-and-design-updates`), this task's final slice, is
implemented on branch `codev/H-02--differential-report-and-design-updates`,
cut from that merged slice-3 head -- see Slice 4 completion evidence, below --
but not yet committed, code-audited, outer-loop reviewed, or merged, so H-02
as a whole remains in progress.
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

Implemented at `c82fed6`; F1 and the initial F2 correction landed at `daff445`,
then F2's remaining blind spot was closed in the follow-up recorded below.

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

**Validation before the final F2 correction (`daff445`):**

- `//tests/discovery/h02/...` with `--nocache_test_results` -> 5 of 5
  targets PASSED; the probe module itself is 16 tests, up from 9.
- `bazel test //...` -> 23 of 23 targets pass, no regression.
- Ruff check and `format --check`, Pyrefly (0 errors, 20 suppressed,
  matching the slice-1 baseline), and the dependency-boundary check
  (exit 0) all clean.

**Takeover validation (after the final F2 correction):**

- `bazel test //tests/discovery/h02:execution_boundary_probes
  --nocache_test_results --test_output=errors` -> PASSED (1 of 1 target;
  16 probe tests).
- The correctness specialist temporarily wrapped the shared command handler
  containing both the sentinel and real PyMOL dispatch in a three-attempt
  silent retry, then ran the two no-retry tests uncached. The original
  outcome-only test passed, while the counter test failed with
  `AssertionError: assert '3' == '1'` (1 failed, 1 passed, 14 deselected).
  After restoration, the source checksum matched exactly and the clean
  16-test target above passed again.
- `bazel test //... --nocache_test_results --test_output=errors` -> all 23
  repository test targets passed.
- `bazel build //...` -> all 36 targets built successfully.
- Ruff check and `format --check` passed for `tests/discovery/`; Pyrefly
  reported 0 errors (20 suppressed); the dependency-boundary check exited 0.

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
CHANGES_REQUIRED with fifteen findings, two of them blocking. F1 was triaged
"address" and fixed at `daff445`; the F2 correction below was found to need a
further narrow takeover correction. What makes them worth recording is that
both were found by *running* the code rather than reading it, and both
concerned guarantees this module documents about itself.

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

### "No internal retry" was asserted only by a test name (H02-S3-F2) -- final correction below

The design authority requires that errors "terminate the process with no
internal retry". The test named for that guarantee asserted only on
`command_outcomes` -- one recorded failure at index 0 -- which a child
silently retrying three times before recording one final failure
satisfies perfectly. The specialist proved it: with such a retry
injected, all nine probes passed, including that one.

The first counter-sentinel fix added `COUNT_THEN_FAIL_VERB`, but it lived before
the shared `try` and duplicated the failure bookkeeping. That structure only
caught a retry around the whole per-command loop; a three-attempt retry at the
actual real-command handler still invoked `cmd.color` three times while both
tests passed. The final correction moves the sentinel inside the shared
`try`, increments and fsyncs its counter, then raises through the shared
handler. A separate test asserts the counter reads exactly `1`. Attempt count,
not outcome count, is the load-bearing assertion.

The first attempt at this fix *replaced* the original test rather than
adding to it, which would have silently dropped the only coverage of a
genuine `pymol.CmdException` travelling through the child's real
exception handler. At that point the sentinel was special-cased before
the handler and never reached it. Caught in review before it landed; the
two tests now sit side by side, one exercising the real PyMOL failure path
and one counting attempts through the same handler.

The correctness specialist verified the final correction with the decisive
three-attempt real-handler mutation: the original outcome-only test still
passed, but the sentinel travelled through the retried shared handler three
times and the counter test failed with `assert '3' == '1'`. The specialist
restored the source byte-for-byte, verified its checksum, and reran all 16
clean probes successfully.

### Open, deliberately deferred

Twelve non-blocking findings remained deferred after H02-S3-F13 (this
document's own Status header still read "slices 3-4 not started" in the commit
that implemented slice 3) was corrected. H02-S3-F15 is resolved by the final
F2 correction because its only issue was the same real-handler retry test gap;
eleven non-blocking findings remain deferred.

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
`__main__` boilerplate, extending slice 2's H02-S2-F11), and F14 (the
memory-bound gap recorded above).

F3 and F10 compound: the reap gap F3 demonstrates is invisible from the
report a real caller sees. Slice 4 should take both together.

## Proposed change (slice 4: differential-report-and-design-updates)

The task's final slice. It writes the differential report H-02 exists to
produce, carries its conclusions into the design contracts Hannah owns, and
closes the one deferred prototype gap those conclusions depend on. It ships no
production API, and it does not close either joint checkpoint: M-02 has not
started, so neither the fixture-freeze nor the contract-freeze checkpoint can
complete here. This slice produces H-02's half of both.

### Decisions accepted before this slice began

Four material decisions were put to the owner and answered before any file was
touched. They are recorded here because the rest of this section follows from
them, and a reviewer should be able to see that they were decided rather than
assumed.

1. **Candidate A is selected** -- canonical structured data. It achieves exact
   fidelity on every acceptance category except measurement objects, tying B
   and C rather than winning uniquely, and wins boundedness and inspectability
   outright against C's opaque, un-independently-inspectable format and
   undeclared field set. It ties B and C on portability instead of winning it
   outright: every candidate was measured on Linux only (issue #12), so the
   axis did not discriminate, and the decision point on claiming portability
   stays open. Its higher reconstruction cost is recorded rather than
   minimized.
2. **Measurement objects move to the plan and report layer.** Candidate A
   cannot read them back from PyMOL at all, and they are created by the
   copilot's own commands in the first place, so they are recorded where they
   originate. The snapshot contract names them an explicit declared-unsupported
   category, satisfying the wave's "never silently drop a field" rule.
3. **Design edits stay inside Hannah-owned sections.**
   `structure-context.md` states "Hannah owns the snapshot and grammar
   contracts", and `request-pipeline.md` states "Hannah owns every contract
   below". `plan-and-execution.md` states "Martin owns every contract below",
   which includes the hermetic execution protocol and every open question
   there. This slice supplies evidence for Martin's open question; it does not
   edit his contract.
4. **The prototype is retained as acceptance evidence, and H02-S3-F3 plus
   H02-S3-F10 are fixed here.** Those two compound into the one gap the report
   itself leans on: the report's "fresh process, no leaked process" conclusion
   is currently observable only through a test-only hook. The other nine
   deferred findings get a recorded disposition, not a fix.

### 1. The differential report

Add `docs/codev/wave/evidence/H-02.md`, following the shape this repository's
existing wave evidence already uses (`H-01.md`, `M-01.md`): Snapshot,
Environment, Fixture and contracts, Checklist, Commands and results,
Observations, Review. Its subject-specific core is three tables.

- **Candidate matrix.** Candidates A, B, and C against the five declared axes
  -- fidelity, boundedness, inspectability, portability, reconstruction cost.
  Every cell cites an executed test or a recorded empirical probe by name. A
  cell with no execution behind it says so rather than carrying a judgment.
- **Acceptance-category matrix.** Each state category the wave names --
  object and state identity; atom identity and coordinates; chain, residue,
  insertion, atom, element, altloc, polymer, and hetero metadata; bonds;
  object and atom visibility, representation, and color; view and supported
  settings; measurement objects -- against each candidate, resolved as exact
  match, lossy with evidence, or not representable, each citing its test.
- **Deferred-finding disposition.** Every finding left open by slices 2 and 3
  -- H02-S2-F4 through F9, F11, F13, and H02-S3-F3 through F12, F14 -- with
  its disposition: fixed in this slice, retained with a stated reason, or
  carried to the contract-freeze checkpoint as an owner's decision.

Three things the report must state plainly rather than leave to inference:

- **Candidate C's measurement recovery was never demonstrated across the
  fresh-process boundary.** It was shown same-process only -- save, delete,
  reload inside one session (H02-S2-F13). The report must not let that read as
  fresh-process evidence, since that is precisely the boundary this task
  exists to prove.
- **The portability axis did not discriminate.** Every real-PyMOL target here
  is excluded on Windows for the same delvewheel/MAX_PATH reason (issue #12),
  so all three candidates were measured on Linux only. The wave's own risk
  table puts a decision point at "before claiming portability or choosing the
  demo environment", owned by Hannah; that decision point stays open, and the
  report says so instead of claiming an axis it did not measure.
- **Neither checkpoint closes here.** The report is H-02's input to the
  fixture-freeze checkpoint Hannah coordinates and the contract-freeze
  checkpoint Martin coordinates. Both need M-02's fixture catalog, card-byte,
  and taxonomy reports, which do not exist yet.

Per the artifact-authority rule, the report references upstream facts by link
rather than restating them, and uses commits as the revision identifier.

### 2. Design updates, Hannah-owned sections only

- `docs/codev/design/shared-core/structure-context.md`, "Structure snapshot
  and digest" and the `StructureSnapshotV1` and digest contract block: record
  that canonical structured data is the selected serialization and
  reconstruction path, the field set the prototype demonstrated it carries,
  the measurement-object category as explicitly declared-unsupported with its
  recording moved to the plan and report layer, and the polymer-classification
  gap the prototype found (derivable from `resn`/`hetatm`, not separately
  stored). Digest scope wording follows the evidence, not the other way round.
- `docs/codev/design/runtime-application/request-pipeline.md`, the "Sidecar
  invocation" contract block: record the request and report boundary the
  prototype proved -- fresh process, reconstruction from the snapshot alone,
  command-indexed outcomes, unconditional termination with reap, scratch
  cleanup on every exit path, and typed fail-closed reasons with no internal
  retry. Record the limits actually prototyped (maximum input bytes and a
  wall-clock deadline) and state that no memory bound was prototyped
  (H02-S3-F14), so a reader cannot mistake the prototyped subset for the
  design's full finite-resources guarantee.
- `docs/codev/design/shared-core/plan-and-execution.md` is **not** edited.
  Martin owns the hermetic execution protocol contract and the open question
  "Which request, report, limit, and teardown contract supports one shared
  full-V1 executor?". The report supplies that question's evidence; he decides.

### 3. Close the one prototype gap the report depends on

In `tests/discovery/h02/execution_boundary.py` and its probe module:

- **H02-S3-F3:** a child that escapes between `Popen` and `communicate()` is
  today neither killed nor reaped, and its scratch directory is deleted while
  the child may still be live. Order every exit path so the child is
  terminated, killed if it does not stop, and reaped *before* scratch data is
  removed -- including the exception path between spawn and communicate.
- **H02-S3-F10:** the report a real caller sees carries no process evidence,
  so "fresh process, terminated, not leaked" is observable only through the
  module's test-only hook. Add the child's process identity and its observed
  termination to the report shape, and bump the report schema version, since
  both shapes in this module are versioned.

Each fix needs a probe that fails without it. Slice 3's own review is the
standard here: a guard that cannot fail is worse than no guard, because it
reports safety it does not provide. Demonstrate each probe's teeth by
reverting the fix under a trap that restores the file, exactly as slices 2
and 3 did.

**Validation (slice 4):** `bazel test //tests/discovery/h02/...
--nocache_test_results` for the candidate and boundary targets, so every
number the report quotes is re-executed rather than recalled; `bazel test
//...` for regression; `bazel run //tools/quality:ruff -- check` and `format
--check` over `tests/discovery/`; `bazel run //tools/quality:pyrefly -- check`;
`bazel run //tools/bazel:check_dependency_boundaries`; and `git diff --check`.
The report records the exact commands and their outcomes, and records nothing
it did not run.

**Explicitly not in this slice:** no production snapshot, card, or executor
API -- the wave's no-production-API-before-contract-freeze rule still binds;
no fourth candidate; no edit to Martin-owned design sections; no closure of
either joint checkpoint; and no sweep of the nine deferred findings outside
H02-S3-F3 and F10.

**Expected budget overage:** this slice will exceed the 600-line review budget,
almost entirely in the report itself. A differential report is one indivisible
reviewer-facing document -- splitting it across pull requests would leave a
reviewer unable to check any conclusion against the evidence that supports it.
The file count stays inside the budget of twelve. Flagged here rather than
explained after the fact.

## Slice 4 completion evidence (differential-report-and-design-updates)

**Delivered:** [`docs/codev/wave/evidence/H-02.md`](../../wave/evidence/H-02.md),
the differential report this task exists to produce: a candidate matrix, an
acceptance-category matrix, and a deferred-finding disposition table, every
cell citing a real test name or a recorded empirical probe, plus the three
required plain statements (candidate C's measurement recovery is same-process
only, the portability axis did not discriminate, and neither joint checkpoint
closes here). `docs/codev/design/shared-core/structure-context.md`'s
"Structure snapshot and digest" section now records candidate A's selection,
the field set the prototype demonstrated, the measurement-object declared-
unsupported disposition, and the polymer-classification gap.
`docs/codev/design/runtime-application/request-pipeline.md`'s "Sidecar
invocation" contract block now records the request/report boundary the
prototype proved and states plainly that only two of the design's finite-
resource limits were prototyped. `docs/codev/design/shared-core/
plan-and-execution.md` was not edited. H02-S3-F3 and H02-S3-F10 -- the one
gap this task's own report depends on -- are fixed in
`tests/discovery/h02/execution_boundary.py`: a child that escapes between
`Popen` and `communicate()` is now terminated and reaped
(`_terminate_and_reap`, invoked from a `finally` wrapping the child's whole
lifecycle) before scratch data is removed, and `ExecutionReport` now carries
`child_pid`/`child_terminated` (schema bumped 1 -> 2) so "fresh process,
terminated, not leaked" is observable from the report itself rather than only
through the module's test-only `on_process_spawned` hook. Both fixes are
demonstrated in both directions with a SHA-256-checksum-verified revert and
restore; see H-02.md's "Two-direction fix demonstration" section for the
exact failing assertions and restored-clean re-runs. The other nine findings
slice 3 deferred, and the eight slice 2 deferred (plus the un-numbered
`pyproject.toml` observation), each get a recorded disposition in the report
rather than a fix, exactly as this slice's own plan specified.

**Changed:** `docs/codev/wave/evidence/H-02.md` (new, 351 lines) -- the
differential report itself.
`tests/discovery/h02/execution_boundary.py` -- added `_terminate_and_reap`
and its call from `execute()`'s own `finally` (H02-S3-F3); added
`ExecutionReport.child_pid`/`child_terminated`, populated at every return
site, and bumped `EXECUTION_REPORT_SCHEMA_VERSION` from 1 to 2 (H02-S3-F10).
`tests/discovery/h02/test_execution_boundary.py` -- added
`test_child_that_escapes_before_communicate_is_terminated_and_reaped` (F3);
added `child_pid`/`child_terminated` assertions to the five rejected-path
tests and to `test_spawn_or_load_failure_fails_closed_with_no_leak`,
`test_wall_clock_timeout_is_hard_killed_and_reaped`,
`test_forced_child_crash_leaves_no_live_process_or_scratch_data`, and
`test_positive_path_matches_independently_computed_expected_values` (F10).
`docs/codev/design/shared-core/structure-context.md` and
`docs/codev/design/runtime-application/request-pipeline.md` -- the two
Hannah-owned design edits described under Delivered. This implementation
plan -- this Status header and this section.

**Validation actually run:**
- `bazel test //tests/discovery/h02/... --nocache_test_results
  --test_output=errors` -> 5 of 5 targets PASSED (`execution_boundary_probes`
  28.3s/17 tests, `full_v1_snapshot_candidate_a` 13.3s, `_candidate_b` 11.3s,
  `_candidate_c` 11.5s, `harness_test` 1.9s).
- `bazel test //... --test_output=errors` -> 23 of 23 test targets pass; no
  regression in any pre-existing target.
- `bazel run //tools/quality:ruff -- check tests/discovery/` -> all checks
  passed.
- `bazel run //tools/quality:ruff -- format --check tests/discovery/` -> 10
  files already formatted.
- `bazel run //tools/quality:pyrefly -- check` -> 0 errors (20 suppressed),
  matching every prior slice's baseline.
- `bazel run //tools/bazel:check_dependency_boundaries` -> exit 0.
- `git diff --check` -> exit 0 (clean).
- H02-S3-F3 two-direction demonstration: `_terminate_and_reap`'s body
  temporarily replaced with a bare `return`; `bazel test
  //tests/discovery/h02:execution_boundary_probes --nocache_test_results
  --test_output=errors` -> 1 failed (the new escape test, `AssertionError:
  child process was not reaped`), 16 passed. File restored from a pre-revert
  copy; SHA-256 matched
  `7b2ae72d0a9e239da3d352b04217e6521c038bdb307830427fc4efb00cd1ac44` exactly;
  same command re-run -> 17 passed.
- H02-S3-F10 two-direction demonstration: every `child_pid=child_pid`/
  `child_terminated=process.poll() is not None` construction-site pair
  temporarily replaced with `child_pid=None`/`child_terminated=None`; same
  command -> 4 failed (`test_spawn_or_load_failure_fails_closed_with_no_leak`,
  `test_wall_clock_timeout_is_hard_killed_and_reaped`,
  `test_forced_child_crash_leaves_no_live_process_or_scratch_data`,
  `test_positive_path_matches_independently_computed_expected_values`, each
  `AssertionError: assert None == <pid>`), 13 passed. File restored; SHA-256
  matched the same checksum exactly (confirmed by checksum and a
  byte-for-byte `diff`); same command re-run -> 17 passed.

**Acceptance evidence:** H-02.md's own Checklist (H02-A1 through H02-A6
satisfied; H02-A7 -- portability on both development environments -- and
H02-R1 -- independent review -- explicitly left open, not this slice's to
close) maps every acceptance sentence in the
[wave plan](../../wave/pymol-copilot-full-v1-contracts.md#h-02-prove-full-v1-snapshot-and-execution-boundaries)
to the test or probe that supports it; see that document rather than
restating it here.

**Scope deviations:** None from this slice's own plan. One documentation
choice worth naming: H-02.md's Checklist introduces `H02-A1`-`H02-A8`/`H02-R1`
identifiers for its own acceptance items, since the wave plan's H-02 section
states its acceptance criteria in prose rather than as a pre-existing ID
scheme (unlike H-01's `H-A1`-style checklist); the report says so explicitly
where the IDs are introduced, rather than implying they were a pre-existing
contract.

**Known limitations:**
- The three required plain statements (candidate C's same-process-only
  measurement recovery, the non-discriminating portability axis, and the two
  joint checkpoints staying open) are recorded in H-02.md and not repeated
  here; they are limitations of the evidence, not of this slice's execution
  of its own plan.
- Of the nineteen deferred findings this slice was asked to give a
  disposition to (H02-S2-F4 through F9/F11/F13 plus the un-numbered
  `pyproject.toml` observation, and H02-S3-F4 through F9/F11/F12/F14), none
  besides F3 and F10 was fixed, exactly as planned; several (H02-S2-F7,
  H02-S3-F7/F8/F9/F14) are explicitly carried to the contract-freeze
  checkpoint as an owner's decision rather than resolved here.
- H02-S3-F8 (`input_fingerprint`'s docstring contradicts `_rejected()`'s
  unconditional `None`) was confirmed still present while investigating
  H02-S3-F10 and was deliberately left unfixed, being outside this slice's
  two named fixes.
- `pyproject.toml`'s `search-path` entry (flagged in slice 2 as outliving the
  disposable prototype) remains unremoved: `pyproject.toml` is not one of
  this slice's six allowed files.
- This document's own Status header now describes slice 4 as implemented but
  not yet committed, code-audited, outer-loop reviewed, or merged; H-02 as a
  whole is not complete until that review happens.

**Review state:** Not yet reviewed. This slice's own builder evidence receipt
records `AWAITING INDEPENDENT REVIEW`; no code-audit, outer-loop, or human
review has occurred against any commit of this slice, because none exists yet
(see Snapshot in H-02.md).
