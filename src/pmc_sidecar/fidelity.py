# Copyright 2026 PyMOL Copilot contributors.
"""The fidelity probe's fresh-process child.

This is the second of two modules that import real PyMOL (the other is
`src/pmc_sidecar/child.py`), one of docs/master_plan.md item 7's own
requirements: "reconstruct that snapshot in a sidecar, compare it against
the live session". `pmc_core.executor.probe_fidelity()` spawns this module
by name (`python -m pmc_sidecar.fidelity`), never by import, so
`pmc_core` itself never acquires either PyMOL dependency (see
`tools/bazel/check_dependency_boundaries.py`). `main()` reads a snapshot
path and an output path from its command line, reconstructs that snapshot
in a freshly launched headless PyMOL, re-extracts what it reconstructed,
and writes a single JSON report to the output path before exiting through
`os._exit()` -- PyMOL's headless shutdown can otherwise override a real
exit code, and the parent never relies on this process's exit status, only
on the presence and content of its output file.

Unlike `child.py`, this module runs no plan and dispatches no command: its
whole job is to prove -- or fail to prove -- that a candidate snapshot
reconstructs faithfully, by handing its own re-extraction back to the
parent. The parent, not this module, holds the live snapshot to compare
against and computes the actual diff (`pmc_core.snapshot.diff`); this
module never sees the live session at all.

`probe()` is the module's own reconstruct-and-re-extract logic, kept
separate from `main()` so a test can drive it directly against an
already-launched real PyMOL fixture -- exactly as `child.py`'s own
`run_plan()` is tested directly rather than through `child.main()`, since
PyMOL supports only one `pymol.finish_launching()` call per interpreter and
a test fixture that already made that call cannot let `main()` make it
again.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_core.executor import REASON_OK
from pmc_core.executor import REASON_RECONSTRUCTION_FAILURE
from pmc_core.executor import REASON_SPAWN_OR_LOAD_FAILURE
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.snapshot import extract
from pmc_core.snapshot import from_json
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import to_json

import winstage


@dataclass(frozen=True)
class FidelityProbeResult:
    """The outcome of reconstructing and re-extracting one candidate snapshot.

    Attributes:
        status: `pmc_core.executor.STATUS_OK` or `STATUS_FAILED`.
        reason: `REASON_OK`, `REASON_SPAWN_OR_LOAD_FAILURE` (the snapshot
            did not even parse, or reconstruction itself failed), or
            `REASON_RECONSTRUCTION_FAILURE` (reconstruction succeeded but
            this module's own re-extraction of it failed).
        reconstructed_snapshot_json: The re-extracted object's canonical
            JSON, as `pmc_core.snapshot.to_json` serialized it, or None
            unless status is `STATUS_OK`.
    """

    status: str
    reason: str
    reconstructed_snapshot_json: str | None


def probe(cmd: Any, snapshot_text: str) -> FidelityProbeResult:
    """Reconstruct a candidate snapshot and re-extract what was built.

    Assumes a live PyMOL session already exists in `cmd` (see `main()`, or
    a caller such as a test that reconstructs directly against a real
    PyMOL fixture). Never raises; every failure mode is reported through
    the returned result's status/reason.

    Args:
        cmd: The live PyMOL `cmd` module (or a compatible stand-in).
        snapshot_text: The candidate snapshot, as
            `pmc_core.snapshot.to_json` serialized it.

    Returns:
        The probe's outcome.
    """
    try:
        parsed_snapshot = from_json(snapshot_text)
        reconstruct(cmd, parsed_snapshot)
    except Exception:
        return FidelityProbeResult(
            status=STATUS_FAILED,
            reason=REASON_SPAWN_OR_LOAD_FAILURE,
            reconstructed_snapshot_json=None,
        )

    try:
        reextracted = extract(cmd, parsed_snapshot.name)
        reconstructed_snapshot_json = to_json(reextracted)
    except Exception:
        # Reconstruction itself succeeded, but this module's own
        # re-extraction of the object it just built failed -- distinct
        # from the case above, where reconstruction never produced a live
        # object at all.
        return FidelityProbeResult(
            status=STATUS_FAILED,
            reason=REASON_RECONSTRUCTION_FAILURE,
            reconstructed_snapshot_json=None,
        )

    return FidelityProbeResult(
        status=STATUS_OK,
        reason=REASON_OK,
        reconstructed_snapshot_json=reconstructed_snapshot_json,
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Reconstruct a snapshot in a fresh PyMOL and report its re-extraction.

    Args:
        argv: `[snapshot_path, output_path]`. Defaults to `sys.argv[1:]`
            when None.
    """
    snapshot_path, output_path = sys.argv[1:] if argv is None else argv

    snapshot_text = Path(snapshot_path).read_text(encoding="utf-8")

    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])

    result = probe(cmd, snapshot_text)

    with Path(output_path).open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "status": result.status,
                "reason": result.reason,
                "reconstructed_snapshot_json": (
                    result.reconstructed_snapshot_json
                ),
            },
            handle,
            ensure_ascii=False,
        )
        handle.flush()
        os.fsync(handle.fileno())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
