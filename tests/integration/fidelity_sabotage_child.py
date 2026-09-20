# Copyright 2026 PyMOL Copilot contributors.
"""A sabotage fidelity child: reconstructs faithfully, then lies about it.

Test-owned, in the spirit of tests/integration/sabotage_child.py (item 4's
own sabotage runner for `pmc_core.executor.execute()`): this module
honours the exact same `[snapshot_path, output_path]` argv contract as
`src/pmc_sidecar/fidelity.py`, so `pmc_core.executor.probe_fidelity()` can
spawn it as a drop-in replacement via `runner_module=`. Unlike that
production child, it genuinely reconstructs and re-extracts the candidate
snapshot in real PyMOL first -- proving the sabotage lives in the
*reported* fidelity, not in a shortcut that never touches PyMOL at all --
then perturbs exactly one field of its own honest re-extraction before
writing it out.

This is what makes tests/integration/test_client_fidelity_real_pymol.py's
five `FIDELITY_EXACT` cases meaningful: without this module proving
`check_fidelity()` can still catch a real, named discrepancy, a
`check_fidelity()` hard-wired to report `FIDELITY_EXACT` unconditionally
would pass every one of those five too.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.snapshot import extract
from pmc_core.snapshot import from_json
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import to_json

import winstage

#: The perturbation this sabotage applies to its own honest re-extraction:
#: the first state's first atom's occupancy, offset by a fixed amount a
#: genuine fixture value is not expected to collide with.
PERTURBATION_DELTA = 0.1234


def main(argv: Sequence[str] | None = None) -> None:
    """Reconstruct and re-extract for real, then perturb one atom's q.

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

    parsed_snapshot = from_json(snapshot_text)
    reconstruct(cmd, parsed_snapshot)
    reextracted = extract(cmd, parsed_snapshot.name)

    first_state = reextracted.states[0]
    sabotaged_atom = dataclasses.replace(
        first_state.atoms[0], q=first_state.atoms[0].q + PERTURBATION_DELTA
    )
    sabotaged_first_state = dataclasses.replace(
        first_state, atoms=(sabotaged_atom, *first_state.atoms[1:])
    )
    sabotaged = dataclasses.replace(
        reextracted, states=(sabotaged_first_state, *reextracted.states[1:])
    )

    with Path(output_path).open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "status": STATUS_OK,
                "reason": REASON_OK,
                "reconstructed_snapshot_json": to_json(sabotaged),
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
