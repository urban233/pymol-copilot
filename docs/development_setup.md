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

To update dependencies, regenerate both locks and repeat the complete sequence:

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

Use `bazel clean` for ordinary cleanup. Use `bazel clean --expunge` only for a
deliberate full cache reset or troubleshooting.
