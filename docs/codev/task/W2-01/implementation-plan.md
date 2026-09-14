# W2-01: Make real-PyMOL targets runnable on Windows -- Implementation Plan

**Status:** Draft
**Owner:** Hannah Kullik (`kullik01`)
**Reviewer:** Martin Urban (`urban233`)
**Risk:** normal
**Containment:** Test-support code only. The staging shim returns immediately
on every non-Windows platform, so Linux and macOS behavior is unchanged by
construction; the Windows path is reached only where the targets are
currently skipped outright.
**Slices:** One pull request, behavior-vertical: the shim, its call sites,
and the removal of both Windows exclusions land together, because neither
half is meaningful alone.
**Base commit:** `354dff7203d905b46974309961fd8ec669f36210`
**Issue/work item:** [#12](https://github.com/urban233/pymol-copilot/issues/12)
**Brief/design/API:** Not needed -- this is a defect fix against an existing
tracked issue, adding no product contract. It unblocks H-02's unmeasured
portability axis
([H02-A7](../../wave/evidence/H-02.md#checklist)) and H-01's disclosed
Linux/macOS-only coverage gap.

## Focus card

- **Change:** Stage `pymol` and its delvewheel `.libs` directory to a short
  filesystem path on Windows before the extension is imported, so the
  compiled `_cmd` extension's dependency DLLs resolve within `MAX_PATH`.
  Then drop the Windows exclusion from every real-PyMOL target in the
  repository, so issue #12 closes rather than narrowing.
- **Success:** All nine previously-skipped real-PyMOL targets execute and
  pass on `windows-2025` CI, and continue to pass unchanged on
  `ubuntu-24.04` and `macos-15`. No `target_compatible_with` Windows
  exclusion citing issue #12 remains anywhere in the repository.
- **Non-goals:** No change to any candidate's snapshot logic, the execution
  boundary's *public* `execute()` contract, or H-02's recorded conclusions.
  No upstream change to `pymol-open-source-whl`. No use of the staging shim
  by any target inside a runtime dependency closure -- `pmc_core` and
  `pmc_agent` must not gain it, directly or transitively.
- **Allowed scope:** `tools/winstage/` (new), `tests/discovery/h02/`
  (`conftest.py`, `harness.py`, `execution_boundary.py`,
  `test_execution_boundary.py`, `build_defs.bzl`, `BUILD.bazel`),
  `tests/integration/` (`test_real_pymol_command.py`, `BUILD.bazel`),
  `tests/data/` (`BUILD.bazel`, `test_generate_real_pymol.py`,
  `test_gold_case_verifier.py`), `src/pmc_data/` (`BUILD.bazel` and
  `generate_cli.py`), `pyproject.toml` (pyrefly `search-path` and
  `project-includes`), `.gitattributes`, and
  `tools/bazel/check_dependency_boundaries.py`.
- **Validation:** Full Bazel test suite on all three platforms via CI, plus
  the repository's ruff, format, pyrefly, and dependency-boundary gates.
- **Stop if:** The staged import fails on Windows CI for any target, any
  currently-passing target regresses on any platform, or
  `check_dependency_boundaries` reports the shim inside a runtime closure.
- **Work style:** Pair. Recorded as pair style when round 2's correction
  work was absorbed, and the item has since been driven interactively
  round by round against real Windows CI results rather than as one
  bounded delegation.

## Scope amendments

Recorded rather than applied silently, because finding W201-R3-ARCH-4
correctly flagged that two earlier expansions were never written down. The
accepted authority and the delivered change should not disagree on paper.

1. **`pyproject.toml`** (rounds 1-2). `winstage.py` is a bare top-level
   module reached through Bazel's `imports = ["."]`, exactly like
   `tests/discovery/h02/harness.py`, which pyrefly's `search-path` already
   lists. Without the entry the type-check gate fails.
2. **`tests/discovery/h02/test_execution_boundary.py`** (rounds 2-5). Windows
   CI exposed a POSIX-only assertion and, later, a genuine resource leak in
   `_terminate_and_reap`. Both were load-bearing for this plan's own success
   criterion: `pyproject.toml`'s `filterwarnings = ["error"]` makes a leaked
   pipe's `ResourceWarning` a hard test failure, so neither fix could be
   split out without leaving Windows red. The non-goal above is narrowed to
   the boundary's *public* contract accordingly: `execute()` is untouched;
   its private cleanup helper was extended.
3. **`tools/winstage/`, `tests/data/`, `src/pmc_data/BUILD.bazel`**
   (round 6). Martin's review of PR #22 observed that the pull request
   declares `Closes #12` while three real-PyMOL targets remain
   Windows-excluded citing that issue. Rather than weaken the claim, the
   scope widens to make it true. This requires relocating the shim out of
   `tests/support/`: `//src/pmc_data:generate_cli` cannot depend on a
   `tests/` package without inverting the dependency direction that
   `src/BUILD.bazel`'s own package groups establish. `tools/` is the
   neutral home -- nothing ships from it, and the dependency-boundary
   checker's forbidden sets live entirely under `src/`. The earlier
   "production runtime facility" non-goal overstated the obstacle:
   `check_dependency_boundaries` forbids `//src/pmc_data:pmc_data` from
   every runtime closure it enforces, so `generate_cli` is a developer
   data-generation tool, not production runtime. The non-goal is restated
   above in the terms that actually matter -- no runtime closure gains the
   shim.

4. **`.gitattributes`** (round 7). Removing the Windows exclusions exposed a
   defect that pre-dates this task: gold-case provenance records a SHA-256 of
   the structure fixture and the verifier checks it on every run, but the
   repository had no line-ending policy, so git rewrote LF to CRLF on Windows
   checkout and changed the digest. Proven rather than inferred --
   `chain_a_gold_fixture.pdb` hashes to `0f2cd04e` with committed LF endings
   and to `823ac3e4` converted to CRLF, and `823ac3e4` is exactly what Windows
   reported. `*.pdb -text` is load-bearing for this plan's own success
   criterion by the same argument amendment 2 makes: without it the two
   newly-unblocked targets are red on Windows, so splitting it out would mean
   landing a knowingly-failing pull request or re-adding exclusions only to
   remove them again.

5. **`src/pmc_data/generate_cli.py`** (round 6) and
   **`pyproject.toml`'s `project-includes`**, **`tools/bazel/check_dependency_boundaries.py`**
   (round 8). Amendment 3 named only `src/pmc_data/BUILD.bazel`, but wiring
   `generate_cli` also required the one-line shim call in its Python source --
   the first source change under `src/` in this task. The round-8 additions
   repair two defects this task introduced: relocating the shim in round 6
   took it out of pyrefly's `project-includes` (the `search-path` entry makes
   a module resolvable, not checked), so rounds 6 and 7 both reported pyrefly
   clean for a file pyrefly was no longer reading; and the Stop-if clause
   below named a gate that could not fire, since the boundary checker's
   `FORBIDDEN` set contained only `//src/...` libraries.

These amendments were themselves incomplete on first writing -- finding
W201-R7-scope-amendments-incomplete caught amendments 1 to 3 omitting
`.gitattributes` and `generate_cli.py`, reproducing the very defect
W201-R3-ARCH-4 had described. Recorded here rather than quietly corrected,
because a scope-discipline section that silently drifts is worth less than
no section at all.

## Repository evidence

Measured on a real `windows-2025` runner by the throwaway probe in
[#21](https://github.com/urban233/pymol-copilot/pull/21); full numbers
recorded on [issue #12](https://github.com/urban233/pymol-copilot/issues/12).

- `LongPathsEnabled` is already `1` on `windows-2025`, and the hermetic
  interpreter honors it: a 317-character file path was created, written, and
  read back in the same process that then failed to import `pymol`. Windows'
  file APIs honor long paths; the DLL loader does not. This direction was
  already tried and reverted in `683aa99` and is closed.
- The longest bundled DLL is
  `vcomp140-f96f3a14d88d8846f31f3ab38a490304.dll`, 267 characters at the
  shortest workable Bazel target path (7 over the limit) and 305 characters
  under `tests/discovery/h02/full_v1_snapshot_candidate_a` (45 over). Only
  two DLLs are bundled.
- Copying the package and its `.libs` directory to `C:\p`, adding that
  directory with `os.add_dll_directory()`, and inserting the root on
  `sys.path` imported cleanly: `IMPORT OK C:\p\pymol\__init__.py`. Path
  length alone is the whole failure.
- Shortening Bazel target names alone reaches 267 (still over), and removing
  the upstream 33-character hash suffix alone reaches 272 (still over).
  Neither is sufficient; staging is, and is entirely in-repository.
- `tests/discovery/h02/build_defs.bzl:45` applies the Windows exclusion to
  all five h02 targets through one macro; `tests/integration/BUILD.bazel:69`
  applies it to `real_pymol_command`.
- Three distinct processes import `pymol` and each needs the shim:
  `harness.py:526` (the `real_pymol` fixture, in the test process),
  `harness.py`'s `_NESTED_RUNNER_SOURCE` child, and
  `execution_boundary.py`'s `_CHILD_RUNNER_SOURCE` child. The latter two are
  string-literal programs run via `python -c`, so the shim must be prepended
  to their source, not merely imported by the parent.
- `tests/` has no shared test-support library yet; `grep py_library
  tests/*/BUILD.bazel` returns nothing. This change introduces the first.
- `tools/bazel/check_dependency_boundaries.py` only inspects the
  `//src/pmc_core` and `//src/pmc_agent` closures, so a new `tests/support`
  package does not affect it.

## Proposed change

1. Add `tests/support/winstage.py` exposing one function,
   `ensure_importable() -> str | None`:
   - Returns `None` immediately when `sys.platform != "win32"`, so no other
     platform changes behavior.
   - Locates the staged `pymol` package with
     `importlib.util.find_spec("pymol")`, which finds it without executing
     its `__init__` -- necessary, because executing it is exactly what
     fails.
   - Returns `None` when the longest path under the sibling
     `pymol_open_source_whl.libs` directory already fits within `MAX_PATH`,
     so the shim is inert wherever it is not needed.
   - Otherwise copies `pymol/` and `pymol_open_source_whl.libs/` to a short
     root, adds the staged `.libs` directory via `os.add_dll_directory()`,
     inserts the root at the front of `sys.path`, and returns it.
   - Is idempotent and safe under concurrent targets: stage into a
     process-private temporary directory and move it into place atomically,
     treating an existing destination as success rather than an error.
   - Fails closed with an explicit error if staging is impossible, rather
     than silently leaving the caller to hit the original opaque
     `ImportError`.
2. Add `tests/support/BUILD.bazel` declaring a `winstage` `py_library` with
   `imports = ["."]`, visible to the test packages that need it.
3. Call it before every `pymol` import:
   - `tests/discovery/h02/conftest.py` at module import, covering every test
     module in that directory.
   - `tests/discovery/h02/harness.py`'s `real_pymol` fixture, so the harness
     is correct when imported directly rather than through the conftest.
   - Prepend `import winstage` and the call to `_NESTED_RUNNER_SOURCE` in
     `harness.py` and `_CHILD_RUNNER_SOURCE` in `execution_boundary.py`,
     before their own `import pymol` lines.
   - `tests/integration/test_real_pymol_command.py`, before its PyMOL import.
4. Remove the `target_compatible_with` Windows exclusion from
   `h02_pymol_py_test` in `tests/discovery/h02/build_defs.bzl` and from
   `real_pymol_command` in `tests/integration/BUILD.bazel`, updating both
   comments to record why the exclusion is no longer needed. Add the
   `//tests/support:winstage` dependency wherever the shim is now imported.

## Validation

- `bazel test //tests/discovery/h02/... --nocache_test_results` -> 5 of 5
  pass on Linux, unchanged from H-02's recorded baseline.
- `bazel test //... --nocache_test_results` -> no regression in any
  pre-existing target on Linux.
- `bazel run //tools/quality:ruff -- check .` and `-- format --check .` ->
  clean.
- `bazel run //tools/quality:pyrefly -- check` -> 0 errors, matching the
  20-suppressed baseline.
- `bazel run //tools/bazel:check_dependency_boundaries` -> exit 0.
- Windows CI on the pull request -> the six previously-skipped targets
  execute and pass; `macos-15` and `ubuntu-24.04` stay green. This is the
  acceptance signal and cannot be produced locally on Linux.

## Risks and rollout

- **The shim masks a real portability limitation.** It is disclosed, not
  hidden: H-02's portability evidence must state that Windows required a
  staging step, since that is itself a portability fact about every
  candidate equally and does not change their relative ranking.
- **Concurrent targets racing on the staged directory.** Contained by
  atomic move plus treating an existing destination as success. The five h02
  targets are additionally tagged `exclusive`.
- **Disk and time cost of copying the package per runner.** Bounded: the
  copy happens at most once per staged root, and only on Windows.
- **Rollback:** revert the single pull request. The Windows exclusions
  return and the repository is exactly as it is today.

## Decisions needed

- None. The lever was selected by measurement, not preference, and the two
  alternatives were shown insufficient on their own.

## Completion evidence

To be filled in by the builder's receipt and this task's rounds.
