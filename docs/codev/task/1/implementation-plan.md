# Issue #1 Bazel Workspace and Python Subsystem Skeleton Implementation Plan

**Status:** Implemented — awaiting independent review
**Owner:** Martin Urban (`urban233`)
**Reviewer:** Hannah Kullik (`kullik01`)
**Risk:** Normal
**Base commit:** `a802c10ce29b66377c69283b41c574d06d7837aa`
**Issue/work item:** [GitHub issue #1](https://github.com/urban233/pymol-copilot/issues/1)
**Brief/design/API:** [`SPECIFICATION.md`](../../../../SPECIFICATION.md), [shared-core design](../../design/shared-core/design.md), [runtime-application design](../../design/runtime-application/design.md), [model-development design](../../design/model-development/design.md)

## Focus card

- **Change:** Establish a Bzlmod-only Bazel workspace with a pinned Bazel and Python toolchain, deterministic Python dependencies, four importable subsystem packages with enforced dependency direction, Bazel-driven tests and quality tools, and a three-OS smoke CI matrix.
- **Success:** From a clean checkout, the pinned toolchain resolves without WORKSPACE fallback; `bazel build //...`, `bazel test //...`, dependency-boundary checks, Ruff, and Pyrefly pass on Windows, macOS, and Linux; each subsystem imports; and the runtime/core dependency closures contain no data or training packages.
- **Non-goals:** Implementing shared contracts, runtime or PyMOL behavior, dataset generation, model training, CUDA/GPU support, distributable packaging, model selection, teacher integration, or behavioral subsystem stubs.
- **Allowed scope:** Root Bazel/Python/dependency metadata; `.github/workflows/`; `src/pmc_core`, `src/pmc_agent`, `src/pmc_data`, and `src/pmc_train`; initial `configs/`, `tests/`, `data/`, and `results/` layout; `tools/bazel/` and `tools/quality/`; existing Python-tool configuration; `README.md`, `CONTRIBUTING.md`, and developer setup documentation.
- **Validation:** Run the exact local command sequence in this plan with lockfiles in error mode, inspect the two required Bazel dependency closures, and require the same build/test/boundary/quality sequence in the Windows, macOS, and Linux GitHub Actions matrix.
- **Stop if:** Bazel 9.2.0, CPython 3.13.13, `rules_python` 2.3.1, or a locked quality dependency cannot resolve or execute on any candidate CI OS; a fix would require vendoring PyMOL, disabling sandboxing, adding training dependencies to runtime/core, using WORKSPACE fallback, weakening existing Ruff/Pyrefly/pytest policy, or expanding into product behavior; or the accepted architecture documents change materially from the base commit.
- **Work style:** Bounded delegate. The work crosses build, package, CI, and documentation components, but it is isolated, explicitly specified, testable from a clean checkout, reversible by reverting one setup change, and must receive independent review.

## Repository evidence

- `a802c10ce29b66377c69283b41c574d06d7837aa`: `bazel-build-setup` and `main` are aligned at the clean planning base; no product source tree or uncommitted work exists.
- [GitHub issue #1](https://github.com/urban233/pymol-copilot/issues/1): owns the initial layout, Bzlmod requirement, dependency direction, smoke targets, quality-tool integration, three-OS CI, documentation, and exact acceptance commands.
- `SPECIFICATION.md:157-160,193-210`: Windows, macOS, and Linux are candidate environments; runtime dependencies must not import the ML training stack into PyMOL; platform support remains evidence-based.
- `SPECIFICATION.md:579-584`: every supported matrix entry must eventually name exact OS, architecture, Open-Source PyMOL, Python, Lemonade, model, and core-contract versions. This task establishes only the build/Python candidate baseline and does not claim platform qualification.
- `docs/codev/design/shared-core/design.md:11-24,61-75`: `pmc_core` is a lightweight runtime-safe authority and must not import training frameworks, LangGraph, Lemonade, or UI dependencies; the repository currently has no product implementation, tests, or package manifest.
- `docs/codev/design/shared-core/design.md:245-256`: independent runtime/training implementations and placing shared contracts in training are rejected; one independent shared core is required.
- `docs/codev/design/runtime-application/design.md:11-24,40-72`: runtime is a thin PyMOL bridge plus a separate companion, while LangGraph and Lemonade stay outside PyMOL's process. This task creates only the package boundary, not those dependencies or behaviors.
- `docs/codev/design/model-development/design.md:28-33,75-97`: model development consumes shared core without reimplementing it, and training frameworks/GPUs are absent from deployed runtime.
- `README.md:16`: currently advertises Python 3.11+, while `ruff.toml:5` and `pyrefly.toml:5` target Python 3.13. The human resolved this conflict in favor of exact CPython 3.13.13 and authorized updating the README.
- `pytest.ini:1-36`, `ruff.toml:1-91`, `pyrefly.toml:1-22`: contain policy that must be preserved rather than copied into Bazel flags. Their stale `test`/`pymol_copilot` paths must be aligned to `tests/` and `src/pmc_*`.
- `CONTRIBUTING.md:4`: already links `docs/development_setup.md`, but that document does not exist. This issue should create it as the developer-command authority instead of introducing a second setup guide.
- `.gitignore`: already ignores Python/Bazel-adjacent transient content but does not protect generated `data/` and `results/` trees or Bazel output symlinks.
- `.github/workflows/`: does not exist at the planning base; no CI behavior needs migration.
- Current stable releases verified on 2026-08-20: Bazel `9.2.0` (latest Bazel 9), Bazelisk `1.29.0`, `rules_python` `2.3.1`, Ruff `0.16.3`, Pyrefly `1.2.0`, and pytest `9.1.1`.

## Proposed change

### 1. Pin Bazel, Bazelisk, Bzlmod, and the Python toolchain

1. Add `.bazelversion` containing exactly `9.2.0`. This is the current latest stable Bazel 9 release as of 2026-08-20; upgrades are intentional pull requests, never floating `latest` values.
2. Add `.bazelrc` with repository-wide, cross-platform defaults:
   - use Bzlmod and the committed module lockfile;
   - require explicit Python package initializers rather than Bazel-generated implicit `__init__.py` files;
   - enable useful test failure output without embedding pytest options;
   - set the Windows symlink startup option required by `rules_python` 2.x;
   - do not disable sandboxing or add a WORKSPACE compatibility path.
3. Add `MODULE.bazel` with module name `pymol_copilot`, `bazel_dep(name = "rules_python", version = "2.3.1")`, and a hermetic CPython `3.13.13` toolchain.
4. Make `pyproject.toml` the human-authoritative Python declaration using `requires-python = "==3.13.13"`. Configure `python.defaults` and `pip.parse` to read that field through their `pyproject_toml` attributes. `python.toolchain` must repeat the exact version because the `rules_python` API requires its tag value; cover that mechanical duplicate with a test that asserts the running interpreter is exactly `3.13.13`.
5. Configure `pip.parse` against the committed hashed requirements lock for Python 3.13.13 and explicitly evaluate the candidate wheel platforms `linux_x86_64`, `osx_x86_64`, `osx_aarch64`, and `windows_x86_64`. Import one `@pypi` hub; do not create separate uncoordinated runtime and training resolutions in this setup task.
6. Generate and commit `MODULE.bazel.lock` after all module extensions and candidate platforms have been evaluated. Normal builds and CI use `--lockfile_mode=error`; only the documented dependency-update command may use update mode.

### 2. Consolidate Python policy and lock only setup dependencies

1. Add `pyproject.toml` project metadata without declaring a distributable application. Move the effective pytest, Ruff, and Pyrefly settings from `pytest.ini`, `ruff.toml`, and `pyrefly.toml` into `[tool.pytest.ini_options]`, `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`, and `[tool.pyrefly]` tables, then remove the three superseded files.
2. Preserve existing strictness: pytest strict markers/config and warnings-as-errors; Ruff's selected/ignored rules, 80-column formatting, double quotes, and copyright check; and Pyrefly's strict preset and existing intentional error overrides. Change only stale paths to `tests` and the four `src/pmc_*` packages. Let Ruff infer Python 3.13 semantics from `project.requires-python`, and let Pyrefly execute under the hermetic 3.13.13 toolchain instead of maintaining another independent version declaration.
3. Add `requirements.in` containing only exact setup/quality requirements: `pytest==9.1.1`, `ruff==0.16.3`, and `pyrefly==1.2.0`. Do not add LangGraph, Lemonade, PyMOL, Torch, Transformers, PEFT, TRL, Unsloth, CUDA, or product dependencies.
4. Generate `requirements_lock.txt` as a universal, hash-checked transitive lock using exact UV `0.12.5`:

   ```text
   uvx --from uv==0.12.5 uv pip compile requirements.in --python-version 3.13.13 --universal --generate-hashes --output-file requirements_lock.txt
   ```

5. Add a lock-consistency check to CI by resolving only from `requirements_lock.txt` under `--lockfile_mode=error`; dependency updates must regenerate both Python and Bzlmod locks and pass the complete OS matrix before review.

### 3. Create the four real package boundaries without product behavior

1. Add `src/BUILD.bazel` package groups that encode allowed consumers and make visibility the first enforcement layer:
   - `pmc_core` is visible to all four subsystem trees and tests but depends on none of them;
   - `pmc_agent` may consume `pmc_core` and is not an allowed consumer of `pmc_data` or `pmc_train`;
   - `pmc_data` may consume `pmc_core` and is visible to `pmc_train` and tests, not `pmc_agent`;
   - `pmc_train` may consume `pmc_core` and `pmc_data` and is not visible to runtime/core.
2. Add `src/pmc_core`, `src/pmc_agent`, `src/pmc_data`, and `src/pmc_train`, each with an explicit `__init__.py` and `BUILD.bazel` `py_library` target named after the package. The files contain package documentation/metadata only—no fake contracts, adapters, data records, training APIs, or behavior that could survive into production.
3. Declare only the accepted direct edges in BUILD targets: agent → core, data → core, train → core + data. Keep core dependency-free and do not attach the shared quality-tool hub to product libraries.
4. Use an explicit `src` import root so all packages import as `pmc_core`, `pmc_agent`, `pmc_data`, and `pmc_train`, not as `src.*`. Validate this on every candidate OS.

### 4. Add smoke, Python-version, and dependency-boundary evidence

1. Add `tests/integration/test_subsystem_imports.py` and a Bazel `py_test` target that runs through locked pytest, imports all four packages, and verifies the imports resolve to the repository packages. Include an assertion that `sys.version_info` is exactly `(3, 13, 13, ...)` so the authoritative version and registered toolchain cannot drift silently.
2. Add `tools/bazel/check_dependency_boundaries.py` as a small cross-platform `py_binary`. It invokes the current workspace's `bazel query --output=label` and fails with the offending labels when:
   - the `pmc_core` closure contains `pmc_agent`, `pmc_data`, or `pmc_train`;
   - the `pmc_agent` closure contains `pmc_data` or `pmc_train`;
   - either core or agent closure contains training-only external repositories, including normalized names for Torch, Transformers, PEFT, TRL, or Unsloth;
   - core contains future runtime-only dependencies such as LangGraph or Lemonade.
3. Keep the boundary checker independent of shell syntax so the same target works under PowerShell, macOS, and Linux. Its required invocation is:

   ```text
   bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
   ```

4. Retain Bazel visibility restrictions even with the query checker: visibility gives analysis-time prevention for declared package edges, while the checker produces explicit acceptance evidence and catches external dependency-closure contamination.

### 5. Expose locked quality-tool entry points without copying configuration

1. Add `tools/quality/BUILD.bazel` targets using `rules_python` console-script entry points for the locked Ruff and Pyrefly wheels. The targets must read `pyproject.toml`; do not restate rule selection, excludes, path lists, or type-checker overrides in BUILD files.
2. Define and document these exact invocations:

   ```text
   bazel run //tools/quality:ruff --lockfile_mode=error -- check .
   bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
   bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
   ```

3. Keep quality targets outside product dependency closures. `bazel query 'deps(//src/pmc_core:pmc_core)'` and the agent equivalent must not include pytest, Ruff, or Pyrefly.

### 6. Establish the non-source repository layout

1. Add tracked README placeholders under `configs/runtime`, `configs/generation`, and `configs/training` that state ownership and that no schema or behavior is defined by this task.
2. Add the requested test-category directories (`tests/unit`, `tests/contract`, `tests/integration`, `tests/adversarial`, and `tests/recovery`) with concise ownership notes. Only integration contains an executable smoke test in this issue.
3. Add `data/README.md` and `results/README.md` describing generated/content-addressed artifact expectations. Do not add BUILD files beneath `data/` or `results/`, and update `.gitignore` to ignore their generated contents while retaining the README files.
4. Ignore Bazel output symlinks (`bazel-bin`, `bazel-out`, `bazel-testlogs`, and the workspace-name symlink) without broad patterns that could hide source.

### 7. Add exact three-OS GitHub Actions smoke CI

1. Add `.github/workflows/bazel.yml` for pull requests and pushes to `main`, with `contents: read`, no write permissions, `fail-fast: false`, and this explicit runner matrix:

   ```text
   ubuntu-24.04
   macos-15
   windows-2025
   ```

2. Pin actions to immutable commits and annotate their release tags:
   - `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (`v7.0.1`);
   - `bazel-contrib/setup-bazel@c5acdfb288317d0b5c0bbd7a396a3dc868bb0f86` (`0.19.0`).
3. Configure setup-bazel with exact `bazelisk-version: 1.29.0`, Bazelisk cache, repository cache keyed by `MODULE.bazel`, `MODULE.bazel.lock`, and `requirements_lock.txt`, and a per-workflow disk cache. Do not cache generated `data/` or `results/`.
4. Run these steps independently on every matrix entry, using the platform's default shell only for direct `bazel` commands:

   ```text
   bazel version
   bazel mod graph --lockfile_mode=error
   bazel build //... --lockfile_mode=error
   bazel test //... --lockfile_mode=error
   bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
   bazel run //tools/quality:ruff --lockfile_mode=error -- check .
   bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
   bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
   ```

5. Treat any matrix failure as a showstopper for issue #1 unless the failure is documented and the accepted support policy is explicitly revised by a human. Do not silently exclude a runner, disable a check on one OS, use an unpinned system Python, vendor PyMOL, or weaken sandboxing to obtain green CI.

### 8. Document developer setup and dependency updates

1. Create the already-linked `docs/development_setup.md` and make it the command authority for this task. Cover exact Bazel `9.2.0`, Bazelisk `1.29.0`, hermetic CPython `3.13.13`, supported candidate runner families, initial download/network expectations, and the command sequence below.
2. Update `README.md` to advertise Python 3.13.13 instead of 3.11+ and link the setup guide. Clarify that the three OSes are candidate build environments, not qualified product support.
3. Keep `CONTRIBUTING.md`'s existing setup link and correct wording only if needed to match the new document; do not duplicate its command table.
4. Document the exact dependency-update procedure:

   ```text
   uvx --from uv==0.12.5 uv pip compile requirements.in --python-version 3.13.13 --universal --generate-hashes --output-file requirements_lock.txt
   bazel mod deps --lockfile_mode=update
   bazel mod tidy --lockfile_mode=update
   bazel mod graph --lockfile_mode=error
   bazel build //... --lockfile_mode=error
   bazel test //... --lockfile_mode=error
   bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
   bazel run //tools/quality:ruff --lockfile_mode=error -- check .
   bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
   bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
   ```

5. Document cache cleanup as `bazel clean` for ordinary cleanup and `bazel clean --expunge` only for deliberate full cache reset/troubleshooting.

### 9. Finish with a clean-checkout and complete-diff inspection

1. Generate both lockfiles, run formatting if needed, then execute the complete local validation sequence below from the repository root.
2. Re-run at least `bazel mod graph`, `bazel build //...`, and `bazel test //...` after removing Bazel output symlinks/caches sufficiently to demonstrate the checkout does not depend on undeclared local files. Do not delete shared user caches merely to claim a clean checkout.
3. Inspect the complete diff for accidental generated artifacts, platform-specific absolute paths, executable-bit drift, duplicated tool configuration, broad visibility, product behavior, ignored lockfiles, weakened lint/type/test policy, and any BUILD target under `data/` or `results/`.
4. Record matrix URLs and exact local command outcomes in the implementation evidence receipt. A command not run is a limitation, not a pass.

## Expected file map

- **Add:** `.bazelversion`, `.bazelrc`, `MODULE.bazel`, `MODULE.bazel.lock`, `BUILD.bazel`, `pyproject.toml`, `requirements.in`, `requirements_lock.txt`.
- **Add:** `.github/workflows/bazel.yml`.
- **Add:** `src/BUILD.bazel` plus `src/pmc_{core,agent,data,train}/{BUILD.bazel,__init__.py}`.
- **Add:** `tools/bazel/{BUILD.bazel,check_dependency_boundaries.py}` and `tools/quality/BUILD.bazel`.
- **Add:** `tests/integration/{BUILD.bazel,test_subsystem_imports.py}` and concise category README files under the five requested test directories.
- **Add:** ownership README files under `configs/{runtime,generation,training}`, `data/`, and `results/`.
- **Add:** `docs/development_setup.md`.
- **Update:** `.gitignore`, `README.md`, and only the minimal necessary wording in `CONTRIBUTING.md`.
- **Remove after policy migration:** `pytest.ini`, `ruff.toml`, and `pyrefly.toml`.

The expected file count exceeds the usual small-change warning because the issue deliberately establishes four packages, five test categories, three config categories, generated-artifact boundaries, CI, and build metadata at once. Keep each placeholder minimal, avoid unrelated cleanup, and do not split the build graph from the CI evidence that proves it works.

## Validation

Run locally from a clean working tree with Bazelisk `1.29.0` available as `bazel`:

```text
bazelisk bazeliskVersion
bazel version
bazel mod graph --lockfile_mode=error
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel query --output=label 'deps(//src/pmc_agent:pmc_agent)'
bazel query --output=label 'deps(//src/pmc_core:pmc_core)'
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
git diff --check
git status --short
```

Expected evidence:

- `bazelisk bazeliskVersion` reports `Bazelisk version: v1.29.0` and `bazel version` reports Bazel `9.2.0`.
- `bazel mod graph --lockfile_mode=error` resolves `rules_python@2.3.1` and does not create or request a WORKSPACE fallback.
- `bazel build //...` and `bazel test //...` complete successfully without changing `MODULE.bazel.lock` or `requirements_lock.txt`.
- The integration smoke imports all four package names under exact CPython 3.13.13 and is actually collected/executed by pytest.
- The core query contains no agent, data, train, LangGraph, Lemonade, quality, or training-only targets.
- The agent query may contain core but contains no data, train, quality, Torch, Transformers, PEFT, TRL, or Unsloth targets.
- The boundary checker exits zero and prints the checked closures; deliberate local mutation of an agent edge to data/train should make analysis or the checker fail before that mutation is discarded.
- Ruff lint, Ruff format-check, and Pyrefly all consume `pyproject.toml` and exit zero.
- `git diff --check` reports no whitespace errors, and `git status --short` contains only intended issue files before commit.
- The GitHub Actions matrix repeats the build, test, boundary, and quality commands successfully on `ubuntu-24.04`, `macos-15`, and `windows-2025`. A local macOS pass alone is not cross-platform acceptance evidence.

## Risks and rollout

- **Fresh toolchain releases:** Bazel 9.2.0 and `rules_python` 2.3.1 are recent. Exact pins, immutable CI action SHAs, committed locks, and the three-OS matrix contain drift. Roll back by reverting this setup change or pinning the last matrix-green versions in a reviewed dependency update—not by floating versions.
- **Python/PyMOL compatibility:** CPython 3.13.13 is the accepted build baseline, but this issue does not prove compatibility with Open-Source PyMOL. Keep PyMOL out of the smoke graph and retain later platform qualification as a separate evidence gate.
- **Cross-platform wheels:** Ruff, Pyrefly, pytest, or a transitive package may lack a candidate wheel or behave differently on one runner. Treat that as a showstopper for this plan and select a reviewed compatible version; do not add per-OS unpinned installs.
- **Windows symlinks:** `rules_python` 2.x requires Windows symlink support. Enable its documented Bazel startup setting and rely on hosted-runner capability; if local policy prevents symlinks, document the environment requirement rather than changing sandbox/security behavior.
- **Lock portability:** A lock generated on one host can hide marker or wheel differences. Use universal hashed resolution, explicit target platforms in `pip.parse`, lockfile error mode, and all three CI runners before accepting it.
- **Boundary-check brittleness:** External repository labels can change format across rules releases. Visibility restrictions are the primary structural guard; keep the query checker small, normalize labels explicitly, and test a deliberate forbidden edge so a false-green checker is caught.
- **Initial broad file count:** The skeleton necessarily touches more than eight files. Limit every new package/config/test placeholder to boundary documentation or executable smoke evidence and reject opportunistic product implementation or cleanup.
- **Rollout:** This change affects development and CI only. It introduces no production runtime, migration, published package, user exposure, or data conversion. Merge remains a human decision after independent review and green matrix evidence.

### Standalone Approach/Risks summary

- Pin Bazel 9.2.0, Bazelisk 1.29.0, `rules_python` 2.3.1, and hermetic CPython 3.13.13; commit both Bzlmod and universal hashed Python dependency locks and enforce lockfile error mode in normal use.
- Create minimal importable `pmc_core`, `pmc_agent`, `pmc_data`, and `pmc_train` targets with visibility plus query-based dependency guards, while keeping product, PyMOL, runtime-framework, and training behavior out of scope.
- Preserve pytest/Ruff/Pyrefly policy in one `pyproject.toml`, expose locked Bazel entry points, and run build, test, boundary, lint, format, and type checks on pinned Ubuntu, macOS, and Windows GitHub-hosted runners.
- Main risks are fresh Bazel/rules releases, Python 3.13/PyMOL compatibility not yet proven, cross-platform wheel availability, and Windows symlink behavior; exact pins and the mandatory three-OS matrix contain them, and any platform failure stops the task rather than weakening isolation or package boundaries.

## Decisions needed

- None. The human explicitly selected Python 3.13.13 and the latest stable Bazel 9 line; repository/release evidence resolves that line to Bazel 9.2.0 as of 2026-08-20. Any later version change requires an explicit plan revision rather than silently following a newer release.

## Completion evidence

- **Delivered:** Bzlmod-only Bazel workspace, locked CPython/tooling, four package boundaries, smoke tests, dependency checker, quality entry points, CI workflow, layout placeholders, and setup documentation.
- **Changed:** Root Bazel/Python/dependency metadata and locks; `.github/workflows/bazel.yml`; four `src/pmc_*` packages; `tests/`, `tools/`, config/data/results placeholders; setup docs; and the Python-tool configuration migration described in the Expected file map.
- **Head commit/snapshot:** `eb3999cbab9284afc46995903734ecfaef99e846` (the fully implemented code snapshot after the documentation/style cleanup); the following metadata-only commit corrects this completion record.
- **Validation actually run:** Bazelisk `1.29.0`; Bazel `9.2.0`; module graph, build, tests, dependency queries, boundary checker, Ruff check/format check, Pyrefly (0 errors), `git diff --check`, and a clean rebuild/test after `bazel clean` all passed locally.
- **Acceptance evidence:** `rules_python@2.3.1` and lockfile error mode resolve; the smoke test verifies CPython `3.13.13`; visibility, queries, and the checker enforce package direction; and the pinned three-OS CI workflow runs the required build, test, boundary, and quality commands.
- **Scope deviations:** Locked Ruff/Pyrefly wheels lack `entry_points.txt`, so their minimal Bazel wrappers execute bundled native binaries rather than console-script metadata; this preserves the same locked tool behavior without adding dependencies.
- **Known limitations:** Three-OS CI is pending remote execution; Open-Source PyMOL compatibility and product platform qualification intentionally remain outside issue #1. Ruff/Pyrefly wheels lack `entry_points.txt`, so their minimal Bazel wrappers execute bundled native binaries rather than console-script metadata.
- **Review state:** AWAITING INDEPENDENT REVIEW.
