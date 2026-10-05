# Portable Windows bundle of the notebook (master plan item 20)

## Context

Item 19 is merged (PR #61, `main` = `5c245db`). The
deliverable notebook (`notebooks/pymol_copilot.ipynb`, item 18) only runs in
Martin's WSL2 setup:

- kernel `.venv-notebook` (5.5 GB, Linux-only CUDA training lock);
- section 7 downloads the tokenizer from the HF Hub;
- section 9 (live demo) hard-codes `--backend cuda` and the Docker-internal
  checkpoint `/models/…Q4_K_M.gguf` (`notebooks/source/pymol_copilot.py:672-694`)
  and needs Lemonade in Docker on `localhost:13305`;
- the licence cell crashes without torch/unsloth (`notebook_support.package_licence`).

**Goal:** one ZIP a colleague on Windows x64 (no Python, no GPU, no admin, offline)
extracts, double-clicks `Start PyMOL Copilot.bat`, gets JupyterLab with the notebook
open, and *Run All* re-executes every section — including the live demo against the
fine-tuned model on CPU.

### Decisions (settled with Martin)

1. **Full bundle with live demo**, the 770 MiB GGUF (sha256 `6c5c76a0…bdbd`) inside.
2. **CPU only**: llama.cpp `cpu`, the engine of `configs/evaluation/finetuned_cpu.json`
   (Lemonade 11.9.0, llama.cpp b10723).
3. **Bundled JupyterLab**, opened in the browser by a `.bat` launcher.
4. **Model shipped in the ZIP**, with the Llama 3.2 Community Licence and the
   "Built with Llama" notice in `LICENSES\`.

### Decisions I took (overrule if you want)

- **CPython 3.13.13 (python-build-standalone `install_only`, Windows x64)**: the
  runtime's interpreter, CI-tested on `windows-2025`; `requirements_lock.txt` already
  has Windows hashes. No training stack (torch/unsloth/peft/trl) — sections 1–8 do not
  import it (`pmc_train.config/examples/render` are stdlib-only; torch only behind
  `RUN_TRAINING`).
- **Embeddable Lemonade 11.9.0** (`lemonade-embeddable-11.9.0-windows-x64.zip`, official
  release asset): self-contained folder, `lemond <dir>` keeps `config.json` there,
  `lemonade backends install` pre-downloads llama.cpp into `bin\`.
- **Build natively on Windows** (Martin's host, from a Windows clone of a pushed commit,
  output *outside* the repo) with `uv`; CI builds the same bundle without the model.
- **The notebook owns the engine** (`notebook_support`, only when `PMC_BUNDLE_ROOT` is
  set); `src/` gets no lifecycle code (as in plan 15) — its only change is the Windows
  checkpoint fix.
- Master plan **item 20**, `plans/16-portable-bundle.md`, branch `feat/portable-bundle`,
  owner Martin.

### Bundle layout

```
pymol-copilot\
  Start PyMOL Copilot.bat   launcher
  README.txt                unblock, extract (tar -xf or Explorer), double-click, troubleshooting
  bundle.json               commit, versions, sha256 of model / python / lemonade / lock
  LICENSES\                 project, Llama 3.2 + "Built with Llama", PyMOL, Lemonade,
                            llama.cpp, CPython, third-party notices
  python\                   CPython 3.13.13 + requirements-bundle.txt (+ share\jupyter
                            lab settings overrides: no news / update checks)
  lemonade\                 lemond.exe, lemonade.exe, resources\, bin\llamacpp\cpu\,
                            config.template.json (llamacpp.args, host 127.0.0.1)
  model\…-Q4_K_M.gguf
  hf\                       HF_HOME: only the tokenizer files @ 5a8abab…
  repo\                     git archive: notebooks\, src\, tools\winstage\, tools\bundle\,
                            tests\notebook\, configs\, docs\ evidence, LICENSE
```

Launcher (`cd /d "%~dp0"`, every `set "VAR=…"` quoted, no `( )` blocks — survives
`pymol-copilot (1)` folders): clears `PYTHONPATH`/`PYTHONHOME`/`PYTHONSTARTUP`; sets
`PYTHONUTF8=1`, `PYTHONNOUSERSITE=1`, `HF_HOME`, `HF_HUB_OFFLINE=1`,
`TRANSFORMERS_VERBOSITY=error`, `MPLCONFIGDIR`, `JUPYTER_CONFIG_DIR`/`JUPYTER_DATA_DIR`/
`IPYTHONDIR` (all inside the bundle), `PMC_NOTEBOOK_DEMO=1`, `PMC_BUNDLE_ROOT`; runs
`python\python.exe -m jupyterlab --ServerApp.root_dir=repo
notebooks\pymol_copilot.ipynb`.

## Delivery

- **Step 0 — update the local repository first:** `git fetch --prune origin`,
  `git switch main`, `git pull --ff-only` (leave the untracked `uv.lock` alone). Open
  the GitHub issue for item 20 (confirm its text with Martin before posting), branch
  `feat/portable-bundle` from `origin/main`, copy this plan to `plans/16-portable-bundle.md`.
- Conventional Commits, one per step; gate after every step:
  `bazel test //... --lockfile_mode=error`, `check_dependency_boundaries`, ruff check +
  format, pyrefly. Sabotage-check each new test. Sonnet cross-review.
- **May edit:** `notebooks/**`, `tests/notebook/**`, `src/pmc_agent/inference/lemonade.py`
  + its probe test (step 3 only), `tools/bundle/**`, `configs/bundle/**`,
  `requirements-bundle.{in,txt}`, `.github/workflows/bundle.yml`, root `BUILD.bazel`
  (`exports_files`), `.bazelignore`, `pyproject.toml` (pyrefly includes), `docs/bundle.md`,
  `docs/master_plan.md`, `README.md` (one pointer).
  **May not touch:** other `src/` packages, training/eval configs, committed evidence
  under `docs/evaluation`, `docs/dataset`, `docs/training`, `requirements-notebook.*`.
- **Human gates:** model runs (re-executing the committed notebook, the Windows spike and
  builds) need Martin's explicit yes — print command, commit, model, expected time,
  outputs. Windows-host steps (1, 5 full build, 8) are done with Martin.

---

## Step 1 — Spike: embeddable Lemonade on native Windows (findings only)

By hand on the Windows host; record in a draft `docs/bundle.md`:
- `backends install llamacpp:cpu` → installed build (expect b10723; else pin via
  `resources/backend_versions.json`). Are `python.exe` / Lemonade / llama.cpp binaries
  signed (Smart App Control / WDAC)? Are MSVC runtime DLLs needed?
- How to set port and host; llama-server's `--host` must be 127.0.0.1 (no firewall prompt).
- `extra_models_dir`: absolute or relative; Lemonade rescans only when the setting
  changes (`configs/evaluation/engine/setup.sh:86-93`).
- `llamacpp.args` on Windows: health's `launch_command` must contain
  `--chat-template-kwargs` followed by exactly `{"date_string":"26 Jul 2024"}`.
- `GET /api/v1/models/<name>`: exact `checkpoint` string and the `-m` path form in
  `launch_command`; the `device` string health reports (probe expects `"cpu"`,
  `lemonade.py:936-942`).
- Where lemond writes logs/caches; whether it touches the network at start.
- Run the server from a plain Windows venv against it with `--backend cpu`; expected
  failure before step 3: grammar canary "unexpected model" (the `C:` colon split).
- Run `gold_056` and the section 9 unseen intent on Windows CPU; record outputs vs the
  committed CUDA ones.
**Test:** findings table; stop and re-plan if args quoting or `extra_models_dir` fail.

## Step 2 — The bundle's lock

- `requirements-bundle.in`: `pymol-open-source-whl`, `langgraph`, `httpx` (pinned via
  `-c requirements_lock.txt`, not `-r requirements.in`, which drags in ruff/pyrefly/pytest),
  `transformers==5.5.0`, `matplotlib`, `ipykernel==7.4.0`, `jupyterlab`, `nbclient`,
  `nbformat`, `pytest` (for `check_bundle`).
- `requirements-bundle.txt`: `uv pip compile --python-version 3.13 --python-platform
  x86_64-pc-windows-msvc --generate-hashes --only-binary :all:`; header records the command.
**Test:** Bazel py_test on the pattern of `tests/demo/test_demo_environment.py`
(`tests/demo/BUILD.bazel:59-69`; `exports_files` in root `BUILD.bazel`): every shared pin
equals `requirements_lock.txt` (sabotage: bump one).

## Step 3 — Windows-absolute checkpoints in the Lemonade client

`src/pmc_agent/inference/lemonade.py:837` `_served_model_path` only treats `startswith("/")`
as a local path. Add the Windows case: `PureWindowsPath(path) == PureWindowsPath(checkpoint)`
when the checkpoint is Windows-absolute (case and slash insensitive), still returning the
launch-form `path` (it becomes the allowed streamed `model` id, `:953`, `:632-637`).
**Test:** beside `test_a_local_gguf_served_in_place_connects`
(`tests/unit/test_inference_lemonade_probe.py:697-740`, `_pulled_handler`): Windows
checkpoint matches with differing slashes/case; mismatching path refused; `repo:file`
still parses (sabotage: revert).

## Step 4 — Make the notebook portable (repo side)

`notebooks/notebook_support.py` (stdlib-only at import, as today):
- `bundle_root()`; `engine_settings()` → backend (bundle: `cpu`; else env
  `PMC_NOTEBOOK_BACKEND`, default `cuda`), base URL and checkpoint.
- `start_engine()` (bundle only): verify the GGUF sha256 against `bundle.json`; write
  `config.json` fresh from the template (free port, 127.0.0.1, `extra_models_dir`);
  spawn `lemond.exe` (`CREATE_NO_WINDOW`) inside a Job Object with
  KILL_ON_JOB_CLOSE held by the kernel (ctypes) plus an `atexit` hook; wait for health;
  assert the chat-template date in `launch_command`; read the `checkpoint` from the
  catalog and confirm `os.path.samefile` with the verified GGUF. Re-adopt a healthy
  engine it started earlier. `stop_engine()`.
- **Non-ASCII paths** (spike finding: Lemonade 11.9.0 exits silently when its own
  folder, cache, config or `extra_models_dir` holds e.g. `ü`): pass `lemond` the 8.3
  short form of every path; where the volume has no short names, stage `lemonade\`
  and a hard link of the GGUF into an ASCII folder, as `winstage` does for PyMOL.
- Server joins the same Job Object; `--lemonade-base-url http://127.0.0.1:<port>`
  (avoids `localhost` → `::1` stalls against health's 2 s budget, `lemonade.py:78`).
- `launch_pymol()`: idempotent (one `finish_launching` per process) and calls
  `winstage.ensure_importable()` first.
- `package_licence()` → `not installed` on `PackageNotFoundError`; `host_description()`
  uses `platform.platform()` when there is no `/etc/os-release`.

`notebooks/source/pymol_copilot.py`: section 9 uses these helpers; the demo checks the
preview succeeded before parsing `copilot plan <id>` (`:756-758`); prose that describes
the CUDA run's exact plan (`:744-752`) becomes outcome-neutral (informed by step 1); the
intro's "you need Linux" and the hard-coded "under WSL2" / "training and this notebook"
labels mention the bundle.

Rebuild the `.ipynb`; re-execute it (forced: `test_notebook_source.py:52-60`,
`test_notebook_record.py:89-108`) **on CPU** against Docker Lemonade with
`PMC_NOTEBOOK_BACKEND=cpu` — human gate — so the committed outputs show what colleagues see.
**Test:** new `tests/notebook/test_notebook_support.py` (loaded via
`spec_from_file_location` as `test_notebook_source.py:23-36`; runs on windows-2025 CI):
`engine_settings`, `package_licence` on a missing package, config writing, launcher-free
paths; `tests/notebook/*` pass on the re-executed notebook.

## Step 5 — `tools/bundle/` build (runs on Windows)

`tools/bundle/bundle_spec.py` (stdlib only, Bazel-tested): contents list, pins
(`configs/bundle/pins.json`: python-build-standalone URL+sha256, Lemonade embeddable
URL+sha256, tokenizer revision + files), manifest, launcher text, path budget.
`tools/bundle/build_bundle.py` (thin orchestration, outside Bazel):
`uv run --python 3.13 tools\bundle\build_bundle.py --model <gguf> --out C:\pmc-dist`
(`--no-model` for CI). It refuses a dirty tree and an output inside the repo, then:
1. `git -c core.autocrlf=false archive HEAD <contents>` → `repo\`.
2. CPython 3.13.13 → `python\`; `uv pip install --python python\python.exe
   --require-hashes --only-binary :all: -r requirements-bundle.txt` (with
   `--system`/`--break-system-packages` if uv needs it); `compileall
   --invalidation-mode unchecked-hash`; JupyterLab `overrides.json`.
3. Lemonade embeddable → `lemonade\`; `backends install llamacpp:cpu`; write
   `config.template.json`; assert the build equals `finetuned_cpu.json`'s; MSVC DLLs
   app-local (step 1: the llama.cpp binaries import `MSVCP140.dll` and
  `VCRUNTIME140.dll` and do not ship them).
4. GGUF → `model\` (sha256 checked); tokenizer files → `hf\` (`snapshot_download`,
   `allow_patterns`).
5. Launcher, README, LICENSES, `bundle.json`; path budget (≤150 chars per entry; the
   longest pymol DLL path is ~98); deterministic ZIP `pymol-copilot-<shortsha>-win64.zip`
   + `.sha256`.
Add `tools/bundle` to pyrefly `project-includes`; `configs/bundle` gets its own filegroup.
**Test:** py_tests for manifest, launcher (quoting, cleared variables), path budget
(sabotage: a 300-char entry fails); one full build on the host.

## Step 6 — `tools/bundle/check_bundle.py` (smoke check inside the bundle)

With the bundle's `python.exe` and the launcher's environment:
1. Kernel PyMOL check (the two-cell pattern of `notebooks/tests/test_environment.py:94-118`)
   and one `pmc_core.executor.execute` call (spawns the sidecar with the relocated python).
2. Execute a **copy** of the notebook headless (cwd `notebooks\`, as `build_notebook.py:110-116`),
   then run the shipped `tests/notebook/test_notebook_record.py` on that copy (notebook path
   overridable by env var) — it recomputes every value from the evidence; the record is
   host-independent.
3. With the model: the engine checks of step 4 passed and section 9 previewed and applied.
**Test:** passes in the bundle; sabotage: corrupt one `report.json` in an extracted bundle.

## Step 7 — CI smoke on `windows-2025`

`.github/workflows/bundle.yml` (paths: `notebooks/`, `src/`, `tools/bundle/`,
`requirements-bundle.*`, `requirements_lock.txt`): build `--no-model`, extract to a deep path,
run `check_bundle.py` with the demo off.
**Test:** green on the PR.

## Step 8 — Clean-machine acceptance (with Martin)

Full build; Windows Sandbox (or a fresh local user) **with an umlaut and a space in the
user name**, network off: unblock, extract into `Downloads`, double-click, *Run All*, then
`check_bundle.py`. Record ZIP size, extract time (Explorer vs `tar -xf`), first-start time,
demo latency, any SmartScreen / Mark-of-the-Web prompts in `docs/bundle.md`.
**Test:** every cell runs; demo applies the change; no process left after closing Jupyter.

## Step 9 — Docs, master plan, hand-over

`docs/bundle.md` (build, share, contents, licences, limits, troubleshooting),
`README.md` pointer, master plan item 20 section + blockers row
`| 20 | Portable Windows bundle | Martin | … | 18 ✓, 19 ✓ | — |`, "State as of".

---

## Verification (end to end)

```
# WSL (repo gate)
bazel test //... --lockfile_mode=error
# Windows host
uv run --python 3.13 tools\bundle\build_bundle.py --model <gguf> --out C:\pmc-dist
# Windows Sandbox, network off
tar -xf pymol-copilot-<sha>-win64.zip -C %USERPROFILE%\Downloads
"%USERPROFILE%\Downloads\pymol-copilot\Start PyMOL Copilot.bat"   # Run All
…\pymol-copilot\python\python.exe …\repo\tools\bundle\check_bundle.py
```

**Acceptance:**
1. One ZIP; extract + double-click is the only action; no install, admin or network.
2. All cells run on CPU; `test_notebook_record` passes on the bundle's executed copy.
3. Section 9 previews and applies with the fine-tuned model; the chat-template date and
   GGUF sha256 are verified before use.
4. Licences in `LICENSES\`; nothing written outside the folder except `%TEMP%` and the
   `winstage` stage when MAX_PATH forces it; no `lemond`/server left running.
5. CI builds and smoke-checks the model-less bundle on `windows-2025`.

## Risks

- **Native Windows Lemonade unproven** — step 1 spike; stop if args quoting /
  `extra_models_dir` fail.
- **CPU output may differ from the committed CUDA demo** — prose made outcome-neutral;
  demo checks success before applying.
- **Corporate lock-down** (Smart App Control, AppLocker, WDAC, denied `C:\` folder
  creation for winstage) — not visible in Sandbox; record signing status; document.
- **Extraction** — Explorer is slow for tens of thousands of files and spreads
  Mark-of-the-Web; README offers `tar -xf` and *Unblock*; avoid OneDrive-synced folders.
- **Console QuickEdit** pauses Jupyter when clicked — launcher disables it or README warns.
- **Size** ~1.2–1.5 GB (GGUF barely compresses) — share via file share/OneDrive.
- **CPU speed** — the spike measured 45–70 s per request on a 2019 4-core APU
  (prompt reading at ~48 tokens/s dominates); newer CPUs are faster. Section 9 says
  so up front; timeouts stay 600 s.
- **Loopback llama-server allows any CORS origin** (as in the Docker engine) — a page
  in the user's browser could reach it while the demo runs; documented.
