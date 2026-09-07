# Copyright 2026 PyMOL Copilot contributors.
"""Runnable entry point that generates and writes verified gold cases.

Launches real headless Open-Source PyMOL once, runs every request declared
in configs/generation/chain_a_red_structures.json through
pmc_data.generate.generate_gold_case, and writes each verified result into
src/pmc_data/gold_cases/. A rejected generation is reported on stdout and
never written; the process exits non-zero if any request was rejected, so a
rerun after fixing a template or structure is unambiguous.

This is the one file in pmc_data that imports real PyMOL directly -- every
other module in this package takes a caller-supplied PyMOLCmd instead, the
same separation pmc_data.verifier already keeps.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pmc_data.generate import generate_gold_case
from pmc_data.generate import load_generation_requests
from pmc_data.generate import write_generated_gold_case

#: Under `bazel run`, __file__ resolves inside a runfiles tree whose writes
#: never reach the real source tree; Bazel sets BUILD_WORKSPACE_DIRECTORY to
#: the actual workspace root in that case (the same convention
#: tools/bazel/check_dependency_boundaries.py already relies on), so prefer
#: it for both reading the checked-in config and writing generated records.
#: Falls back to a __file__-derived root for direct (non-bazel-run)
#: invocation, where __file__ already is the real source tree.
_WORKSPACE_ROOT_OVERRIDE = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
REPO_ROOT = (
    Path(_WORKSPACE_ROOT_OVERRIDE)
    if _WORKSPACE_ROOT_OVERRIDE
    else Path(__file__).resolve().parent.parent.parent
)
CONFIG_PATH = (
    REPO_ROOT / "configs" / "generation" / "chain_a_red_structures.json"
)
GOLD_CASES_DIR = REPO_ROOT / "src" / "pmc_data" / "gold_cases"


def run() -> int:
    """Generate every checked-in request, writing only verified results.

    Returns:
        0 if every request was verified and written, 1 if any was rejected.
    """
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        exit_code = 0
        requests = load_generation_requests(CONFIG_PATH, repo_root=REPO_ROOT)
        for index, request in enumerate(requests):
            object_name = f"generation_object_{index}"
            cmd.load(str(request.structure_path), object_name)
            try:
                result = generate_gold_case(request, cmd)
            finally:
                cmd.delete(object_name)

            if result.gold_case is None:
                print(
                    f"REJECTED {request.case_id}: "
                    f"invalid_reason={result.verifier_result.invalid_reason!r} "
                    f"task_success={result.verifier_result.task_success}"
                )
                exit_code = 1
                continue

            written_path = write_generated_gold_case(result, GOLD_CASES_DIR)
            print(f"WROTE {written_path}")
        return exit_code
    finally:
        cmd.do("quit")


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine non-zero
    # exit code with 0 (same defect confirmed empirically and fixed the same
    # way in tests/data/test_gold_case_verifier.py's __main__ block). os._exit
    # bypasses that interpreter-shutdown window entirely, so a rejected
    # generation's non-zero exit code is what the caller actually sees.
    # os._exit skips the normal stdio flush, so flush explicitly first.
    _exit_code = run()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
