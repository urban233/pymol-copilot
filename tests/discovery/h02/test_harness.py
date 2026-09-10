# Copyright 2026 PyMOL Copilot contributors.
"""H-02 discovery: meta-test for the shared nested-subprocess harness.

`run_nested_snapshot_process` (harness.py) is what every full-V1 snapshot
candidate's fresh-process round-trip test relies on to learn whether
reconstruction in a genuinely separate process actually matched the
original. It launches the nested process through the same
`pytest.main()` -> flush -> `os._exit()` sequence each candidate module's
own `__main__` block uses, specifically so real PyMOL's headless shutdown
can never override a genuine nested failure's exit code with 0 (see that
function's own docstring for the full empirical finding this fixes).

This module tests that guarantee directly, independent of any one
candidate's own reconstruction logic -- but it cannot do so without real
PyMOL involved: a nested failure that never launches PyMOL already returns
nonzero under both the current `python -c` spawn and the old, broken
`python -m pytest` one, so it cannot tell the two apart (confirmed
empirically -- see below). The nested test below therefore launches real
headless PyMOL and lets it reach the same shutdown sequence every
candidate's own reconstruction test does before it fails, reproducing the
exact masking condition run_nested_snapshot_process's own docstring
documents. That makes this module's own test a genuine regression guard:
temporarily reverting run_nested_snapshot_process's spawn back to
`python -m pytest` makes this test fail, exactly as a guard for that
regression must.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from harness import run_nested_snapshot_process

#: A minimal nested test module: one test function that launches real
#: headless PyMOL, lets it reach the same `finish_launching` -> `sync()`
#: point every candidate's own reconstruction test does, and only then
#: unconditionally fails. Launching real PyMOL here is not incidental: the
#: shutdown-masking condition run_nested_snapshot_process works around only
#: manifests once real PyMOL has actually been started in the nested
#: process (confirmed empirically -- a PyMOL-free failing test already
#: returns nonzero under both the current `python -c` spawn and the old,
#: broken `python -m pytest` one, so it cannot discriminate between them).
_FAILING_TEST_SOURCE = (
    "def test_deliberately_fails() -> None:\n"
    "    import pymol\n"
    "    from pymol import cmd\n"
    "\n"
    "    pymol.finish_launching(['pymol', '-qc'])\n"
    "    cmd.sync()\n"
    "    raise AssertionError('h02 harness meta-test induced failure')\n"
)


def test_run_nested_snapshot_process_propagates_a_genuine_failure(
    tmp_path: Path,
) -> None:
    """A genuinely failing nested test's exit code must reach the caller.

    The nested test launches real headless PyMOL and lets it reach its own
    shutdown before failing, reproducing the exact masking condition
    run_nested_snapshot_process works around -- a PyMOL-free nested failure
    would return nonzero regardless of which spawn form ran it, and so
    would prove nothing about this harness's own defect-avoidance.

    Args:
        tmp_path: A pytest-provided temporary directory for the nested
            test file.

    Raises:
        AssertionError: If the nested failure's exit code was masked back
            to 0, or the failing test's own name is missing from the
            captured output.
    """
    failing_test_file = tmp_path / "test_h02_harness_deliberate_failure.py"
    failing_test_file.write_text(_FAILING_TEST_SOURCE)

    result = run_nested_snapshot_process(
        failing_test_file, "test_deliberately_fails", {}
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert "test_deliberately_fails" in result.stdout + result.stderr


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (the same defect documented and
    # fixed the same way in tests/integration/test_real_pymol_command.py
    # and candidate A's own __main__ block). os._exit bypasses that
    # interpreter-shutdown window entirely, so pytest's real result is what
    # Bazel actually sees. os._exit skips the normal stdio flush, so flush
    # explicitly first -- otherwise a real failure's traceback and summary
    # can be silently lost from the captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
