# Copyright 2026 PyMOL Copilot contributors.
"""A test-owned sidecar child that behaves however PMC_SABOTAGE_MODE says.

This module never ships in `src/`: it exists so
`test_executor_boundary.py` can exercise `pmc_core.executor.execute()`'s
process-management guarantees -- hard kill, reap, scratch cleanup, no
internal retry -- without needing a genuinely pathological PyMOL failure
for every scenario. `execute()` writes the request's real snapshot and
plan files exactly as it would for the production
`src/pmc_sidecar/child.py`; this module simply never reads either one, so
its presence is invisible to `execute()` itself. Only `PMC_SABOTAGE_MODE`
-- set by the calling test, inherited through `execute()`'s own
`env = os.environ.copy()` -- picks this module's behavior.

Real PyMOL command failures are covered elsewhere, not reproduced here:
`tests/integration/test_sidecar_child.py` already proves, against real
PyMOL, that a genuine command exception stops `run_plan()`'s dispatch loop
with a typed outcome at that index -- this module only needs to prove that
whatever a spawned child reports, `execute()` propagates, reaps, and
cleans up after correctly, regardless of why the child failed.

Modes, a single string in `PMC_SABOTAGE_MODE`:
    `"crash"` -- `os._exit(1)` immediately, before writing any output.
    `"sleep:<seconds>"` -- sleep for `<seconds>`, then write a normal
        success report (only reached if a caller's deadline exceeds the
        sleep; the timeout test's whole point is that it does not).
    `"count_then_fail:<counter_path>"` -- append one invocation to the
        counter file at `<counter_path>` (creating it if absent), then
        write a single-command `REASON_COMMAND_FAILURE` report. The
        counter file, not the report, is what proves a caller invoked
        this exactly once rather than silently retrying it.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK

#: The environment variable a calling test sets to select this module's
#: behavior. Read, never written, by this module.
SABOTAGE_MODE_ENV_VAR = "PMC_SABOTAGE_MODE"


def main(argv: Sequence[str] | None = None) -> None:
    """Read PMC_SABOTAGE_MODE and behave accordingly.

    Args:
        argv: `[snapshot_path, plan_path, output_path]`, matching
            `pmc_core.executor.execute()`'s own calling convention exactly
            -- unused here, since every mode ignores both input files.
            Defaults to `sys.argv[1:]` when None.

    Raises:
        ValueError: If `PMC_SABOTAGE_MODE` is unset or names no known mode
            -- a test author's own mistake, not a scenario under test.
    """
    _snapshot_path, _plan_path, output_path = (
        sys.argv[1:] if argv is None else argv
    )
    mode = os.environ.get(SABOTAGE_MODE_ENV_VAR, "")

    def _write(payload: dict[str, object]) -> None:
        with Path(output_path).open("w") as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())

    if mode == "crash":
        os._exit(1)

    if mode.startswith("sleep:"):
        time.sleep(float(mode.removeprefix("sleep:")))
        _write(
            {"status": STATUS_OK, "reason": REASON_OK, "command_outcomes": []}
        )
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    if mode.startswith("count_then_fail:"):
        counter_path = Path(mode.removeprefix("count_then_fail:"))
        existing = (
            counter_path.read_text().strip() if (counter_path.exists()) else ""
        )
        count = int(existing) + 1 if existing else 1
        counter_path.write_text(str(count))
        _write(
            {
                "status": STATUS_FAILED,
                "reason": REASON_COMMAND_FAILURE,
                "command_outcomes": [
                    {
                        "index": 0,
                        "verb": "__sabotage__",
                        "status": OUTCOME_ERROR,
                        "error": "sentinel always fails; counts invocations",
                    }
                ],
            }
        )
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    raise ValueError(
        f"{SABOTAGE_MODE_ENV_VAR} is unset or names no known mode: {mode!r}"
    )


if __name__ == "__main__":
    main()
