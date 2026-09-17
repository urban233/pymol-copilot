# Lemonade capability spike

Disposable prototype for [plans/02-lemonade-capability-spike.md](../../../plans/02-lemonade-capability-spike.md).
Answers the four questions the master plan's day-one spike asks: whether
Lemonade can enforce a supplied grammar per request, whether a request can be
cancelled mid-generation, whether it reports model identity, and whether it
runs on CPU and on this machine's integrated GPU.

Nothing under this directory is a production contract, adapter, or engine
interface. `src/pmc_agent/inference/` (a later item) is designed from this
directory's findings, not from anything reused out of it. It is deliberately
outside the Bazel graph -- there is no `BUILD.bazel` here and it is not added
to `.bazelignore`, because a directory with no `BUILD.bazel` is never a Bazel
package and `bazel build //...` / `bazel test //...` never see it. `probe.py`
is still linted by ruff and type-checked by pyrefly, both of which cover the
whole `tests/` tree.

The container rig (`compose.yaml`, `Dockerfile.arm64`) is a throwaway harness
for re-running the same probes later, not a shipped deployment artifact.

See [FINDINGS.md](FINDINGS.md) for the answers and their evidence.
