# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL test support for pmc_core.snapshot's round-trip evidence.

This is what remains of the H-02 discovery harness
(`tests/discovery/h02/harness.py`) once its production content (the
canonical extraction format, `extract()`, `reconstruct()`, the JSON codec,
`structure_digest()`, and `diff()`) moved to `pmc_core.snapshot`: the shared
real-PyMOL fixture (`real_pymol`/`loaded_fixture`) and the
nested-subprocess-via-environment-variable technique
(`run_nested_snapshot_process`) that spawns a genuinely fresh second PyMOL
process reading only whatever a path-bearing environment variable points it
at -- never the original source fixture file. Both stay test support: they
launch real PyMOL, which `pmc_core.snapshot` itself never does.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import winstage

#: The directory `winstage.py` itself lives in, so nested child processes
#: spawned below (which never inherit this process's own sys.path) can be
#: given it explicitly.
_WINSTAGE_DIR = str(Path(winstage.__file__).resolve().parent)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "h02_full_v1_fixture.pdb"
)

#: The nested child's own entire program, passed via `python -c`. Runs
#: pytest in-process exactly like each round-trip test module's own
#: `__main__` block does (`pytest.main()`, flush, `os._exit(code)`),
#: instead of `python -m pytest`, which runs the file as a module through
#: pytest's own runner and never reaches a `__main__` block -- see
#: run_nested_snapshot_process's docstring for why that distinction is not
#: cosmetic. `sys.argv[1]`/`sys.argv[2]` are the test file and `-k` filter,
#: appended after this source string in the child's argv. Starts with the
#: same Windows staging shim call every real-PyMOL process makes (see
#: winstage.py); a no-op everywhere else, and it must run here, in the
#: child, since staging it in this function's own parent process never
#: helps a separate process that imports pymol on its own.
_NESTED_RUNNER_SOURCE = (
    "import winstage\n"
    "winstage.ensure_importable()\n"
    "import os, sys, pytest\n"
    "code = pytest.main([sys.argv[1], '-k', sys.argv[2], '-q'])\n"
    "sys.stdout.flush()\n"
    "sys.stderr.flush()\n"
    "os._exit(code)\n"
)


def run_nested_snapshot_process(
    test_file: Path | str,
    test_name_filter: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Spawn a genuinely fresh nested pytest process for a round-trip test.

    Runs `pytest <test_file> -k <test_name_filter>` in a brand-new
    subprocess that inherits the current environment plus `env` -- the only
    channel this pattern uses to tell the nested process what to
    reconstruct (a snapshot JSON path). The nested process never receives
    the parent's live PyMOL objects directly, and never opens the original
    source fixture file; it only ever reads whatever `env` points it at.

    The child runs `python -c <_NESTED_RUNNER_SOURCE>` rather than
    `python -m pytest` on purpose. Real PyMOL's headless shutdown can
    complete after pytest's own process would otherwise exit, overriding a
    genuine failure's exit code with 0 -- the same defect every round-trip
    test module's own `__main__` block documents and works around by
    calling `os._exit` immediately after `pytest.main()` returns, once
    stdout and stderr are flushed. `python -m pytest` imports the file as a
    module and runs pytest's own runner directly, so it never reaches that
    `__main__` block and the workaround never applies to the child --
    confirmed empirically: an unconditional `raise AssertionError`
    substituted into a nested test still produced a zero exit code through
    `-m pytest`. `_NESTED_RUNNER_SOURCE` reproduces the exact same
    `pytest.main()` -> flush -> `os._exit()` sequence directly as the
    child's whole program, so this function's caller observes the child's
    real result.

    Args:
        test_file: The test module to re-invoke (normally the caller's own
            `__file__`), so the nested process re-collects that same
            module and can select just its own reconstruction test.
        test_name_filter: A `pytest -k` expression selecting only the
            nested reconstruction test, so the parent invocation's own
            tests are not re-run recursively inside the child.
        env: Extra environment variables the nested process reads to learn
            what to reconstruct from.

    Returns:
        The completed nested pytest subprocess, with captured stdout and
        stderr for the caller to report on failure.
    """
    environment = os.environ.copy()
    environment.update(env)
    # The child never inherits this process's own sys.path (it is spawned
    # fresh from sys.executable, not re-run through Bazel's own launcher),
    # so `_NESTED_RUNNER_SOURCE`'s `import winstage` needs its directory on
    # PYTHONPATH explicitly. Unlike winstage itself, `snapshot_support`
    # reaches the child for free here: it comes along with `test_file`'s
    # own directory, which pytest inserts into sys.path automatically while
    # collecting it.
    environment["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (_WINSTAGE_DIR, environment.get("PYTHONPATH", ""))
        if part
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _NESTED_RUNNER_SOURCE,
            str(test_file),
            test_name_filter,
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[Any]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL cmd module.
    """
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


@pytest.fixture
def loaded_fixture(real_pymol: Any) -> Iterator[Any]:
    """Load the full-V1 discovery fixture fresh for one test and delete it.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module with the fixture object loaded.
    """
    real_pymol.load(str(FIXTURE_PATH), "fx")
    real_pymol.color("red", "fx and chain A")
    real_pymol.show("sticks", "fx")
    real_pymol.show("spheres", "fx and resn ZN")
    real_pymol.label("fx and name CA", "name")
    real_pymol.set_view(
        (
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -0.5,
            0.5,
            -20.0,
        )
    )
    real_pymol.set("sphere_scale", "0.35", "fx")
    real_pymol.set("cartoon_transparency", "0.25", "fx")
    real_pymol.disable("fx")
    real_pymol.sync()
    try:
        yield real_pymol
    finally:
        real_pymol.delete("fx")
