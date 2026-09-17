# Development setup

Issue #1 uses Bazelisk 1.29.0 to select Bazel 9.2.0 from `.bazelversion` and
the hermetic CPython 3.13.13 toolchain. Windows, macOS, and Linux are candidate
runner families; product support is not claimed by this setup.

The first build downloads Bazel, the hermetic Python runtime, rules, and the
locked quality wheels, so network access is expected. Normal commands use the
committed locks in error mode:

```text
bazelisk bazeliskVersion
bazel version
bazel mod graph --lockfile_mode=error
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

To update runtime dependencies, regenerate both locks and repeat the complete
sequence:

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

To update the training dependency set, see the section below.

Use `bazel clean` for ordinary cleanup. Use `bazel clean --expunge` only for a
deliberate full cache reset or troubleshooting.

## Training dependencies

`SPECIFICATION.md:285-286` requires that runtime dependencies coexist with
Open-Source PyMOL without importing the ML training stack into PyMOL's Python
process, and `SPECIFICATION.md:660-661` places training, teacher access, and
fine-tuning in a separate development environment, absent from deployment.
The repository enforces this mechanically: `requirements-train.in` and
`requirements-train.txt` are pinned outside Bazel entirely, referenced by no
`MODULE.bazel` or `BUILD.bazel` file, and `//tools/bazel:check_dependency_boundaries`
fails if `torch`, `transformers`, `peft`, `trl`, or `unsloth` ever enter
`requirements.in` or a Bazel dependency closure.

Fine-tuning is done mainly with **Unsloth**, chosen to keep training runnable
on consumer-grade hardware, so the training environment is Linux with a
consumer NVIDIA GPU. It targets **Python 3.12**, not the 3.13.13 that every
Bazel-built and Bazel-tested target uses ([pyproject.toml](../pyproject.toml),
[MODULE.bazel](../MODULE.bazel)) -- the Unsloth stack (bitsandbytes, triton,
xformers) is best-supported there today. This divergence is intentional: it
is safe for code shared with the Bazel side because the newest syntax there,
the PEP 695 `type` statement, is itself 3.12+. Code `pmc_train` imports from
`pmc_core` or `pmc_data` must stay 3.12-compatible.

To create the training environment and install its locked dependencies:

```text
uv venv --python 3.12 .venv-train
source .venv-train/bin/activate
uv pip install -r requirements-train.txt
```

To update the training dependency set, edit `requirements-train.in` and
recompile its hash-pinned lock the same way, but for Linux + CUDA on Python
3.12 rather than the runtime lock's universal Python 3.13.13 resolution:

```text
uvx --from uv==0.12.5 uv pip compile requirements-train.in --python-version 3.12 --python-platform x86_64-unknown-linux-gnu --generate-hashes --output-file requirements-train.txt
```

This is not `--universal`: `triton` has no Windows wheel, `bitsandbytes` has
no macOS wheel, and torch's wheels are accelerator-specific, so a universal
resolution would fail outright or pin the wrong variant. `--python-platform`
lets it compile from any host without needing a Linux machine. It stays
hash-pinned like every other lock in the repository, from default PyPI --
PyPI's Linux torch wheels already bundle CUDA, so no extra index is needed.
