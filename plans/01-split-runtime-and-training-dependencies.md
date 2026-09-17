# Split runtime and training dependencies

## Context

The repository has exactly one dependency closure today. `requirements.in` pins
four packages (pytest, ruff, pyrefly, pymol-open-source-whl), `requirements_lock.txt`
is compiled from it, and `MODULE.bazel` feeds that lock straight into
`pip.parse` for four target platforms. Everything Python in the repo is
governed by that one file.

That is about to become a problem. `SPECIFICATION.md:285-286` states the
constraint directly: *"Runtime dependencies must coexist with Open-Source PyMOL
without importing the ML training stack into PyMOL's Python process."*
`SPECIFICATION.md:656` places LangGraph in the managed server, and
`SPECIFICATION.md:660-661` says training, teacher access and fine-tuning "run in
a separate development environment and are absent from deployment." Nothing
enforces that split mechanically yet — if torch, transformers and peft went into
`requirements.in`, they would enter the hermetic Bazel closure that
`bazel build //...` materialises on ubuntu-24.04, macos-15 and windows-2025, and
share a toolchain with the process that loads real PyMOL.

`src/pmc_train/` is still a skeleton (`__init__.py` only), but it is wired into
the Bazel graph as a `py_library` and into pyrefly's `project-includes`. It is
the seam through which the ML stack would arrive.

**Outcome:** two pinned dependency sets. A runtime set stays Bazel-governed,
hermetic and cross-platform, and gains langgraph plus httpx as real, used
dependencies of `src/pmc_agent`. A training set is pinned separately in
`requirements-train.txt`, lives entirely outside Bazel, and is documented in
`docs/development_setup.md`. `src/pmc_train/` leaves the Bazel graph and
pyrefly so it cannot pull torch back in.

**Decisions already taken** (from the clarifying questions):

- httpx is pinned explicitly rather than arriving transitively via langgraph-sdk.
- langgraph and httpx are wired into `src/pmc_agent` for real, not left as
  unreferenced lock lines that CI would never fetch.
- `src/pmc_train/BUILD.bazel` is deleted and the directory added to
  `.bazelignore`.
- Fine-tuning is done mainly with **Unsloth**, to keep training on
  consumer-grade hardware. So the training set pins `unsloth` and `trl`
  alongside torch/transformers/peft, and targets **Linux + CUDA on Python 3.12**,
  from default PyPI, hash-pinned. `SPECIFICATION.md:642` rules out NVIDIA GPUs
  as a *deployment* assumption and says nothing about training hardware, so this
  is consistent with the spec.
- The whole task ships on one dedicated branch as **one PR**; CI evidence comes
  from watching that PR's three-OS matrix.

---

## Delivery: one dedicated branch, one PR

All seven steps below ship together on a single branch as a single pull
request. They are not independently mergeable — step 4 breaks two gates that
only step 5 repairs, and step 3's lock is only proven by step 4's test — so
splitting them would put `main` through a knowingly red intermediate state.

**Before any file is touched**, cut the branch from an up-to-date `main`:

```text
git checkout main && git pull --ff-only
git checkout -b deps/split-runtime-and-training
```

Two things to know about doing this in this repo:

- `.claude/CLAUDE.md` installs a `PreToolUse` hook that pauses before the first
  source edit or the first repository-mutating git command when no plan document
  exists for the active branch. **The very first commit on the branch is
  `plans/01-split-runtime-and-training-dependencies.md`** — this plan, copied
  in verbatim. That satisfies the guardrail's repo-wide fallback and gives the
  PR its own rationale in-tree.
- If you would rather this be registered as a CoDev task and use the
  `codev/<ID>` branch convention (as with `codev/M-02`), say so and I will use
  `codev git branch` instead of raw `git checkout -b`. Absent that, the branch
  is a plain topic branch.

Commit in the step order below, one commit per step, so the PR reads as the
sequence it is. Everything lands in one PR against `main`.

---

## Step 1 — Take `src/pmc_train/` out of the Bazel graph and out of pyrefly

**Files**

- Delete [src/pmc_train/BUILD.bazel](src/pmc_train/BUILD.bazel).
- [.bazelignore](.bazelignore) — add `src/pmc_train`.
- [src/pmc_data/BUILD.bazel:20](src/pmc_data/BUILD.bazel#L20) — drop
  `//src/pmc_train:__pkg__` from `visibility`. A visibility label pointing into
  an ignored package has no BUILD file to resolve against; leave it and package
  loading fails before anything else does.
- [tests/integration/BUILD.bazel:24](tests/integration/BUILD.bazel#L24) — drop
  `//src/pmc_train:pmc_train` from the `subsystem_imports` deps.
- [tests/integration/test_subsystem_imports.py:13](tests/integration/test_subsystem_imports.py#L13)
  — drop `"pmc_train"` from the tuple, and say in a comment why (it is
  deliberately outside the Bazel closure, not forgotten).
- [pyproject.toml:112](pyproject.toml#L112) — remove `"src/pmc_train"` from
  `[tool.pyrefly] project-includes`.
- [tools/bazel/check_dependency_boundaries.py:12](tools/bazel/check_dependency_boundaries.py#L12)
  — `//src/pmc_train:pmc_train` can no longer appear in any closure. Keep the
  entry with a comment explaining it is inert-by-construction now; it costs
  nothing and regains meaning if the package ever returns to the graph.

Ruff still lints `src/pmc_train/` — that is intentional, it is Python in the
repo. Only Bazel and pyrefly stop looking at it.

**Test that proves it**

```text
bazel query 'kind(rule, //...)' --lockfile_mode=error | grep pmc_train   # expect no output
bazel build //... --lockfile_mode=error
bazel test //tests/integration:subsystem_imports --lockfile_mode=error
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

The `grep` returning nothing is the load-bearing check: before this step it
returns `//src/pmc_train:pmc_train`.

---

## Step 2 — Create the pinned training requirement set, outside Bazel

**Files:** new `requirements-train.in`, new `requirements-train.txt`.

Fine-tuning is done mainly with **Unsloth**, to keep training on consumer-grade
hardware. That decides the shape of this lock: it is Linux + CUDA, on Python
3.12, and it is not universal.

`requirements-train.in` pins the direct requirements with `==` versions, matching
the style of [requirements.in](requirements.in): `unsloth`, `trl`, `torch`,
`transformers`, `peft`. The last three are named explicitly even though Unsloth
pulls them anyway — they are the packages the dependency boundary check forbids
by name, so they should be visible as first-class lines rather than buried in the
transitive closure. Unsloth additionally drags in `unsloth_zoo`, `accelerate`,
`bitsandbytes`, `datasets` and `triton`.

```text
uvx --from uv==0.12.5 uv pip compile requirements-train.in \
  --python-version 3.12 \
  --python-platform x86_64-unknown-linux-gnu \
  --generate-hashes \
  --output-file requirements-train.txt
```

Three deliberate departures from how the runtime lock is built, each for a
reason worth recording in the doc at step 6:

- **No `--universal`.** The runtime lock is universal because Bazel resolves
  four target platforms from one file. This one is not: `triton` has no Windows
  wheel, `bitsandbytes` has no macOS wheel, and torch's wheels are
  accelerator-specific. A universal resolution would fail outright or pin the
  wrong variant. `--python-platform` lets this compile from macOS without a
  Linux box.
- **Python 3.12, not 3.13.13.** The Bazel side stays hard-pinned at 3.13.13
  ([pyproject.toml:4](pyproject.toml#L4), [MODULE.bazel:15](MODULE.bazel#L15)).
  The Unsloth stack — bitsandbytes, triton, xformers — is best-tested on 3.11/3.12
  and 3.13 support across it is still patchy. The training set is outside Bazel,
  so it is free to differ. This is safe for shared code: the newest syntax in
  `pmc_core`/`pmc_data` is the PEP 695 `type` statement
  ([pmc_core/parser.py:57](src/pmc_core/parser.py#L57),
  [pmc_core/plan.py:103](src/pmc_core/plan.py#L103)), which is 3.12+. Keep it
  that way — anything `pmc_train` may import must stay 3.12-compatible.
- **Default PyPI, hashed.** PyPI's Linux torch wheels already bundle CUDA, so no
  `--extra-index-url` is needed and `--generate-hashes` keeps the repo's
  convention that every lock is hash-pinned. (This is exactly the reason the
  target is Linux rather than Windows, where CUDA torch requires the separate
  PyTorch index.)

The new files must be referenced by nothing in the build.

**Test that proves it**

```text
grep -rn "requirements-train" MODULE.bazel $(find . -name BUILD.bazel -not -path './bazel-*')        # expect no output
grep -nE "^(torch|transformers|peft|trl|unsloth)==" requirements_lock.txt                            # expect no output
grep -nE "^(unsloth|trl|torch|transformers|peft)==" requirements-train.txt                           # expect five hits
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error                            # exit 0
uv pip install --dry-run --python-version 3.12 -r requirements-train.txt                             # resolves
```

The second and third greps together are the actual statement of this change: all
five training names are pinned in one file and absent from the other.

**Risk to expect here.** Unsloth's closure on Python 3.12 is the single most
likely thing in this plan to fail to resolve. If it does, the fallback is 3.11
for the training environment only — the Bazel side is untouched either way.

---

## Step 3 — Add langgraph and httpx to the runtime lock

**Files:** [requirements.in](requirements.in),
[requirements_lock.txt](requirements_lock.txt), `MODULE.bazel.lock`.

Add `langgraph==<pin>` and `httpx==<pin>` to `requirements.in`, then regenerate
both locks with the sequence already documented in `docs/development_setup.md`:

```text
uvx --from uv==0.12.5 uv pip compile requirements.in --python-version 3.13.13 --universal --generate-hashes --output-file requirements_lock.txt
bazel mod deps --lockfile_mode=update
bazel mod tidy --lockfile_mode=update
```

The `bazel mod` steps are not optional. `pip.parse` in
[MODULE.bazel:17-30](MODULE.bazel#L17-L30) hashes `requirements_lock.txt`, CI
runs every command with `--lockfile_mode=error`, and `bazel mod graph
--lockfile_mode=error` is the first thing that fails if `MODULE.bazel.lock` is
stale.

Expect the lock to grow from ~10 packages to roughly 30: langchain-core,
langgraph-checkpoint / -prebuilt / -sdk, langsmith, pydantic + pydantic-core,
orjson, ormsgpack, xxhash, zstandard, jsonpatch, jsonpointer, tenacity, PyYAML,
httpcore, h11, anyio, sniffio, idna, certifi, typing-extensions,
typing-inspection, requests-toolbelt. Five of those are compiled
(pydantic-core, orjson, ormsgpack, xxhash, zstandard) and the universal lock
must carry a wheel for each of the four `target_platforms` at
[MODULE.bazel:24-29](MODULE.bazel#L24-L29). If any one lacks a wheel for a
platform, that is where this change fails first, and it fails at compile time
rather than in CI.

**Test that proves it**

```text
bazel mod graph --lockfile_mode=error     # exit 0 proves MODULE.bazel.lock is in sync
bazel build //... --lockfile_mode=error
```

Cross-platform resolution is only really proven by step 7.

---

## Step 4 — Wire langgraph and httpx into `src/pmc_agent`

**Files:** new `src/pmc_agent/runtime.py`,
[src/pmc_agent/BUILD.bazel](src/pmc_agent/BUILD.bazel), new
`tests/unit/test_agent_runtime.py`, [tests/unit/BUILD.bazel](tests/unit/BUILD.bazel).

`runtime.py` stays deliberately thin — two functions, no orchestration logic.
The point is a real, used dependency edge, not the agent layer:

- `build_intent_graph()` — a compiled `langgraph.graph.StateGraph` with one
  pass-through node over a `TypedDict` state.
- `build_engine_client(base_url, timeout)` — a configured `httpx.Client` for the
  local Lemonade endpoint. It constructs the client and returns it; it sends
  nothing.

Match the house style: the copyright header and `CPY001`, Google-style
docstrings with `Args:`/`Returns:` for `D`/`DOC`, full annotations for the
`ANN00x`/`ANN2xx` selections, 80 columns, double quotes, and the split-import
`from __future__ import annotations` form used at
[src/pmc_client/transport.py:4](src/pmc_client/transport.py#L4).

`src/pmc_agent/BUILD.bazel` gains `"runtime.py"` in `srcs` and
`"@pypi//langgraph"`, `"@pypi//httpx"` in `deps`.

`tests/unit/test_agent_runtime.py` invokes the compiled graph and asserts the
client's `base_url` and timeout. Add a `py_test` named `agent_runtime` to
`tests/unit/BUILD.bazel` following the `server_lifecycle` pattern, depending on
`@pypi//pytest` and `//src/pmc_agent:pmc_agent`. **This test is what actually
forces the wheels to download and import on all three runners** — without it,
rules_python fetches `@pypi` spokes lazily and CI would never touch the new pins.

**Watch:** [pyproject.toml](pyproject.toml) sets `filterwarnings = ["error"]`.
Any import-time `DeprecationWarning` from the langgraph/pydantic stack becomes a
test failure. If that fires, add a narrow `ignore::DeprecationWarning:<module>`
entry — do not weaken the global setting.

**Test that proves it**

```text
bazel test //tests/unit:agent_runtime --lockfile_mode=error
```

---

## Step 5 — Update the two gates that step 4 breaks

Wiring langgraph into `pmc_agent` breaks two existing checks. Both must move
deliberately, not be loosened.

**File:** [tools/bazel/check_dependency_boundaries.py](tools/bazel/check_dependency_boundaries.py)

Lines 26-27 define `TRAINING_NAMES` and `RUNTIME_NAMES`, and lines 66-70 check
the union of both against *both* roots. So `langgraph` appearing in
`pmc_agent`'s closure fails the gate as written. Split the name policy per
root, mirroring the existing `FORBIDDEN_BY_ROOT` structure:

- `//src/pmc_core:pmc_core` — forbids training names **and** runtime
  orchestration names. `pmc_core` is the shared contract layer that the
  in-PyMOL client imports, so LangGraph must never reach it.
- `//src/pmc_agent:pmc_agent` — forbids training names only. Per
  `SPECIFICATION.md:656`, the managed server is exactly where LangGraph belongs.

The check is a substring match over joined labels (line 69), and it prints the
full closure. Read that printed closure once after langgraph lands and confirm
no transitive package name contains `trl`, `peft` or `torch` as a substring and
false-positives.

**File:** [tools/quality/pyrefly_main.py:35-36](tools/quality/pyrefly_main.py#L35-L36)

`PYTHONPATH` is built from a single hard-coded lookup of pytest's
`site-packages`. `pyproject.toml` sets `missing-import = "error"`, so
`import langgraph` / `import httpx` in a `project-includes` file fails the type
check. Add `@pypi//langgraph` and `@pypi//httpx` to the `pyrefly` `py_binary`
deps in [tools/quality/BUILD.bazel](tools/quality/BUILD.bazel), and build
`PYTHONPATH` by globbing every `*/site-packages` directory in runfiles, joined
with `os.pathsep`, rather than naming pytest.

**Test that proves it**

```text
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error   # exit 0; printed pmc_core closure has no langgraph
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check            # exit 0
```

Plus one negative check, which is the only thing that proves the gate still
gates: temporarily add `"@pypi//langgraph"` to `//src/pmc_core:pmc_core`'s deps,
confirm the boundary check exits 1 naming langgraph, then revert.

---

## Step 6 — Document the split

**File:** [docs/development_setup.md](docs/development_setup.md)

Add a `## Training dependencies` section after the existing update block,
covering:

- that the training stack is deliberately outside Bazel, and why
  (`SPECIFICATION.md:285-286`);
- that fine-tuning uses Unsloth on consumer-grade hardware, so the environment
  is Linux + a consumer NVIDIA GPU;
- that it runs on **Python 3.12** while everything Bazel touches stays on
  3.13.13, and that this divergence is intentional rather than drift;
- how to create the venv and install `requirements-train.txt`;
- the standing rule that `torch`, `transformers`, `peft`, `trl` and `unsloth`
  must never appear in `requirements.in`, enforced by
  `//tools/bazel:check_dependency_boundaries`.

Update the existing "To update dependencies" block so it names both compile
commands, not just the runtime one.

**Test that proves it:** a reader can reproduce the training environment from
the section alone, and the documented command sequence still runs clean:

```text
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
```

---

## Step 7 — Open the single PR and get cross-OS CI evidence

Push `deps/split-runtime-and-training` to `urban233/pymol-copilot` and open
**one PR** against `main` carrying all seven commits. The workflow at
[.github/workflows/bazel.yml:5-8](.github/workflows/bazel.yml#L5-L8) triggers on
`pull_request` and on pushes to `main` only — a bare branch push runs no matrix
at all, so the PR is what produces the evidence.

The PR description should state the split in one paragraph (runtime closure
gains langgraph + httpx; training closure moves to `requirements-train.txt`
outside Bazel; `src/pmc_train` leaves the graph), and link the in-tree plan at
`plans/01-split-runtime-and-training-dependencies.md` rather than restating it.

Two things to expect:

- The cache key at [bazel.yml:24](.github/workflows/bazel.yml#L24) hashes
  `MODULE.bazel`, `MODULE.bazel.lock` and `requirements_lock.txt`. This change
  invalidates it on every runner, so the first run downloads the whole langgraph
  tree cold and will be slow.
- windows-2025 is the highest-risk leg. It already needed
  `//tools/winstage` to get under `MAX_PATH`
  ([tests/integration/BUILD.bazel:62-70](tests/integration/BUILD.bazel#L62-L70)),
  and langgraph's tree adds many deeply nested wheel paths under Bazel's output
  base.

**Test that proves it:** all three matrix legs green on `bazel mod graph`,
`bazel build //...`, `bazel test //...`, `check_dependency_boundaries`,
`ruff check`, `ruff format --check` and `pyrefly check`.

---

## Verification (end to end)

Locally on macOS, the full sequence from `docs/development_setup.md`:

```text
bazel mod graph --lockfile_mode=error
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Then the four assertions that are specific to this change:

1. `bazel query 'kind(rule, //...)' | grep pmc_train` returns nothing.
2. `grep -nE "^(torch|transformers|peft|trl|unsloth)==" requirements_lock.txt`
   returns nothing, and the same grep against `requirements-train.txt` returns
   all five.
3. `//tests/unit:agent_runtime` passes, proving langgraph and httpx import.
4. The negative boundary check from step 5 exits 1, then is reverted.

Finally, the PR matrix green on ubuntu-24.04, macos-15 and windows-2025.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| A compiled transitive dep (pydantic-core, orjson, ormsgpack, xxhash, zstandard) lacks a wheel for one of the four `target_platforms` | `uv pip compile` or `bazel build` | Surfaces at step 3 compile time; if it does, pin a version that has all four wheels |
| `filterwarnings = ["error"]` turns a langgraph import warning into a test failure | Step 4, `//tests/unit:agent_runtime` | Narrow per-module ignore, never a global loosening |
| windows-2025 `MAX_PATH` with langgraph's deep wheel tree | Step 7, windows leg only | Known territory (issue #12); `//tools/winstage` exists if it recurs |
| Substring matching in the boundary checker false-positives on a new transitive name | Step 5 | Read the printed closure once, deliberately |
| Unsloth's closure fails to resolve on Python 3.12 | Step 2, at `uv pip compile` | Fall back to 3.11 for the training env only; the Bazel side is untouched either way |
| Training lock is Linux+CUDA only and silently wrong on another machine | Step 2 / 6 | Record the platform, Python version and GPU assumption in the doc |
