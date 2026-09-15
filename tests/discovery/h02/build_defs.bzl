"""Shared py_test shape for this directory's real-PyMOL discovery probes.

Every target in `tests/discovery/h02` that spawns a subprocess running real
headless PyMOL (a nested pytest process for candidates A/B/C and the harness
meta-test, or the execution boundary's own child) shares the same
size/timeout budget and the same `exclusive` scheduling tag. Slice 2's
outer-loop review flagged three near-identical `py_test` blocks as a
maintainability finding (H02-S2-F9); slice 3 adds a fourth and fifth block
sharing the exact same shape, which is directly what justifies factoring it
into one macro here instead of copying it a third and fourth time.
"""

load("@rules_python//python:py_test.bzl", "py_test")

def h02_pymol_py_test(name, srcs, deps, data = []):
    """Declare one H-02 py_test that spawns a real headless PyMOL subprocess.

    Args:
        name: The Bazel target name.
        srcs: This test's own single-element source list; `main` is always
            set to `srcs[0]`.
        deps: This target's own deps, in addition to `@pypi//pytest`
            (added automatically below).
        data: Optional extra runtime data files (for example, this
            directory's `conftest.py` and fixture PDB).
    """
    py_test(
        name = name,
        size = "large",
        timeout = "moderate",
        srcs = srcs,
        main = srcs[0],
        data = data,
        # Spawns a subprocess that launches its own real PyMOL process;
        # excluded from concurrent scheduling for the same reason as
        # tests/data:oracle_sabotage and tests/contract:policy_sabotage, so
        # it never races another subprocess-spawning test under Windows's
        # unsandboxed local execution strategy (observed CI flake).
        tags = ["exclusive"],
        # No longer excluded on Windows: pymol-open-source-whl's Windows
        # wheel bundles delvewheel-repaired DLLs whose long hash-suffixed
        # names, combined with Bazel's generated repository name, used to
        # exceed Windows' MAX_PATH. //tools/winstage:winstage now stages a
        # short-path copy before every real-PyMOL import in this directory
        # (a no-op on every other platform). See issue #12.
        deps = deps + ["@pypi//pytest"],
    )
