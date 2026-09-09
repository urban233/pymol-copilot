# H-02: Prove full-V1 snapshot reconstruction and execution boundaries -- Implementation Plan

**Status:** In progress -- slice 1 (`fixture-matrix-and-candidate-a`) complete
and under review; slices 2-4 not started
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
- **Head commit/snapshot:** Working tree on `codev/H-02`, not yet
  committed (see next step).
- **Validation actually run:**
  - `bazel test //tests/discovery/h02:full_v1_snapshot_candidate_a
    --test_output=errors` -> 1 test target, all 4 test functions pass
    (fixture-category check, fresh-process round trip, nested
    reconstruct-and-diff, measurement-object negative result).
  - `bazel test //...` -> all 19 repository test targets pass; no
    regression in any existing target.
  - `bazel run //tools/quality:ruff -- check tests/discovery/` -> all
    checks passed.
  - `bazel run //tools/quality:ruff -- format --check tests/discovery/`
    -> clean after one `ruff format` pass (applied).
  - `bazel run //tools/quality:pyrefly -- check` -> 0 errors repository-wide.
  - `bazel run //tools/bazel:check_dependency_boundaries` -> exit 0.
- **Acceptance evidence:**
  - "Fixture matrix covers object/state identity; atom identity and
    coordinates; chain/residue/insertion/atom/element/alternate-location/
    polymer/hetero metadata; bonds; ... visibility/representation/color
    state; view and supported setting state" -> covered and round-tripped
    with zero mismatches, except measurement objects (see below) and
    polymer/hetero classification beyond the `hetatm` flag already
    recorded (polymer status is derivable from resn/hetatm but not
    separately stored -- a candidate-A schema gap for slice 4's
    write-up, not a fidelity failure).
  - "Modified coordinates, multiple states, ... and hetero atoms must be
    represented" -> the fixture's second MODEL state shifts every atom's
    z-coordinate, and both states round-trip exactly.
  - "It must define explicit unsupported-state behavior rather than
    silently dropping fields" -> satisfied for measurement objects via
    the dedicated negative-result test, not a silent omission.
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
- **Review state:** Not yet reviewed. Builder round to be closed and a
  fresh lightweight-reviewer pass requested next.
