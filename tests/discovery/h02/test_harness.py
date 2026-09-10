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
candidate and without needing real PyMOL at all: a deliberately failing
nested test function, targeted the same way every candidate's own
reconstruction test is (the `-k` selector mechanism), is enough to prove
the returned exit code is the nested process's real one.
"""

from __future__ import annotations

from pathlib import Path

from harness import run_nested_snapshot_process

#: A minimal nested test module: one test function that unconditionally
#: fails, so exercising it never depends on real PyMOL or any candidate's
#: reconstruction logic -- only on run_nested_snapshot_process's own
#: process-spawning and exit-code plumbing.
_FAILING_TEST_SOURCE = (
    "def test_deliberately_fails() -> None:\n"
    "    raise AssertionError('h02 harness meta-test induced failure')\n"
)


def test_run_nested_snapshot_process_propagates_a_genuine_failure(
    tmp_path: Path,
) -> None:
    """A genuinely failing nested test's exit code must reach the caller.

    Proves the defect this harness works around cannot silently return: a
    nested process whose one selected test genuinely fails must report a
    nonzero exit code, not a PyMOL-shutdown-masked 0.

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
