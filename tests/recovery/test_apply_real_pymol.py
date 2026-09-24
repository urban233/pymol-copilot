# Copyright 2026 PyMOL Copilot contributors.
"""Real headless-PyMOL proof that a partial live apply is restored cleanly."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from pmc_client.apply import APPLY_RESTORED
from pmc_client.apply import apply_plan
from pmc_client.recovery import RecoveryStore
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import NamedSelection
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.snapshot import diff
from pmc_core.snapshot import extract

import winstage

_OBJECT = "two_chain_fixture"


class _FailColorProxy:
    """Delegate to real PyMOL except for the second plan operation."""

    def __init__(self, cmd: Any) -> None:
        """Retain the real command module that owns every mutable state."""
        self._cmd = cmd

    def color(self, _color: str, _target: str) -> None:
        """Fail after the real select operation has already changed PyMOL."""
        raise RuntimeError("deliberate real-PyMOL mid-plan failure")

    def __getattr__(self, name: str) -> Any:
        """Delegate every non-failing API call to real PyMOL."""
        return getattr(self._cmd, name)


@pytest.fixture(scope="module")
def real_pymol() -> Any:
    """Launch one real headless PyMOL process for this recovery module."""
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


def _plan() -> ActionPlan:
    """Build a plan whose first operation visibly succeeds before failure."""
    return ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_selection",
                expression=SelectionExpression(
                    clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
                ),
            ),
            ColorOperation("red", NamedSelection("copilot_selection")),
        )
    )


def test_real_mid_plan_failure_restores_complete_session(
    real_pymol: Any, tmp_path: Path
) -> None:
    """A real mutation before a real failure is removed by complete restore."""
    store = RecoveryStore(tmp_path)
    real_pymol.pseudoatom(
        _OBJECT,
        name="CA",
        resn="ALA",
        resi="1",
        chain="A",
        pos=(0.0, 0.0, 0.0),
    )
    real_pymol.pseudoatom(
        _OBJECT,
        name="CA",
        resn="GLY",
        resi="1",
        chain="B",
        pos=(1.0, 0.0, 0.0),
    )
    try:
        before = extract(real_pymol, _OBJECT)
        names_before = tuple(sorted(real_pymol.get_names("all")))
        outcome = apply_plan(
            _FailColorProxy(real_pymol),
            object_name=_OBJECT,
            plan_id="33333333-3333-4333-8333-333333333333",
            plan=_plan(),
            store=store,
        )

        assert outcome.status == APPLY_RESTORED
        assert outcome.mismatches == ()
        assert diff(before, extract(real_pymol, _OBJECT)) == []
        assert tuple(sorted(real_pymol.get_names("all"))) == names_before
        assert outcome.recovery_path is not None
        if os.name != "nt":
            assert outcome.recovery_path.stat().st_mode & 0o777 == 0o600
    finally:
        store.discard()
        real_pymol.delete("all")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
