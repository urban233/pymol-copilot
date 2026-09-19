# Copyright 2026 PyMOL Copilot contributors.
"""The positive path: execute() against an independently computed value.

Unlike every sabotage test in test_executor_boundary.py, this module
computes its expected values entirely outside the boundary under test: it
reconstructs the same snapshot and runs the same plan directly against the
module-scoped `real_pymol` fixture (re-exported by this directory's
conftest.py), and only then asks `pmc_core.executor.execute()` to do the
same work in a genuinely separate, spawned process, through the real
production `src/pmc_sidecar/child.py`.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import SelectionCount
from pmc_core.executor import execute
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import NamedSelection
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot
from pmc_core.snapshot import extract
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import to_json

#: A real 18-float PyMOL view matrix, required by reconstruct()'s own
#: unconditional cmd.set_view() call.
_IDENTITY_VIEW = (
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


def chain_a() -> SelectionExpression:
    """Build the expression `chain A`.

    Returns:
        A one-term expression matching chain A.
    """
    return SelectionExpression(
        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
    )


def _sample_snapshot() -> ObjectSnapshot:
    """Build a two-atom snapshot, both atoms in chain A.

    Deliberately without name collisions, altlocs, or insertion codes --
    simple enough for reconstruct()'s technique without needing a fixture
    file, matching what this slice's own boundary properties need to
    prove, not full-fidelity coverage (that lives in
    tests/integration/test_snapshot_round_trip.py).

    Returns:
        A well-formed two-atom, one-state snapshot.
    """
    atoms = tuple(
        AtomRecord(
            serial=serial,
            name=name,
            alt="",
            resn="LIG",
            chain="A",
            resv=1,
            ins_code="",
            elem="C",
            hetatm=False,
            q=1.0,
            b=0.0,
            color=0,
            reps=(),
            label=None,
            coord=(float(serial), 0.0, 0.0),
        )
        for serial, name in ((1, "C1"), (2, "C2"))
    )
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="fx",
        enabled=True,
        states=(StateSnapshot(atoms=atoms),),
        bonds=(),
        view=_IDENTITY_VIEW,
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )


def _sample_plan() -> ActionPlan:
    """Build a plan exercising a real selection and a real color.

    Returns:
        A two-command plan: select chain A into a named selection, then
        color that selection blue.
    """
    return ActionPlan(
        operations=(
            SelectOperation(selection_name="copilot_sel", expression=chain_a()),
            ColorOperation(color="blue", target=NamedSelection("copilot_sel")),
        )
    )


def test_positive_path_matches_independently_computed_expected_values(
    real_pymol: Any,
) -> None:
    """execute()'s report matches values computed entirely outside it.

    Args:
        real_pymol: The real PyMOL cmd module, used only to compute the
            expected values -- never passed to execute() itself, which
            spawns its own, genuinely separate process.
    """
    snapshot = _sample_snapshot()
    plan = _sample_plan()

    reconstruct(real_pymol, snapshot)
    try:
        for operation in plan.operations:
            match operation:
                case SelectOperation():
                    real_pymol.select(
                        operation.selection_name,
                        operation.expression.render(),
                    )
                case ColorOperation():
                    real_pymol.color(operation.color, operation.target.render())
        real_pymol.sync()
        expected_selection_counts = (
            SelectionCount(
                name="copilot_sel",
                atom_count=real_pymol.count_atoms("copilot_sel"),
            ),
        )
        expected_extraction = extract(real_pymol, snapshot.name)
        expected_fingerprint = (
            "sha256:"
            + hashlib.sha256(
                to_json(expected_extraction).encode("utf-8")
            ).hexdigest()
        )
        blue_index = real_pymol.get_color_index("blue")
    finally:
        real_pymol.delete(snapshot.name)
        real_pymol.sync()

    assert expected_selection_counts[0].atom_count == 2
    assert all(
        atom.color == blue_index for atom in expected_extraction.states[0].atoms
    )

    request = ExecutionRequest(
        executor_version=EXECUTOR_VERSION,
        plan=plan,
        snapshot_json=to_json(snapshot),
    )

    spawned: list[Any] = []
    first_report = execute(request, on_process_spawned=spawned.append)
    second_report = execute(request, on_process_spawned=spawned.append)

    for report in (first_report, second_report):
        assert report.status == STATUS_OK
        assert report.reason == REASON_OK
        assert report.resulting_fingerprint == expected_fingerprint
        assert report.selection_counts == expected_selection_counts
        assert report.command_outcomes == (
            CommandOutcome(0, "select", OUTCOME_OK, None),
            CommandOutcome(1, "color", OUTCOME_OK, None),
        )
        assert report.child_terminated is True

    # Determinism across two independent attempts.
    assert first_report.resulting_fingerprint == (
        second_report.resulting_fingerprint
    )
    assert first_report.command_outcomes == second_report.command_outcomes

    # A fresh process per attempt: two distinct PIDs, both reaped.
    assert len(spawned) == 2
    assert first_report.child_pid == spawned[0].pid
    assert second_report.child_pid == spawned[1].pid
    assert first_report.child_pid != second_report.child_pid


if __name__ == "__main__":
    import os
    import sys

    import pytest

    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
