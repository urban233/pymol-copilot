# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic ordering and restore tests for the live apply boundary."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from pmc_client.apply import APPLY_APPLIED
from pmc_client.apply import APPLY_RESTORE_FAILED
from pmc_client.apply import APPLY_RESTORED
from pmc_client.apply import apply_plan
from pmc_client.recovery import RecoveryStore
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.plan import ActionPlan
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_sidecar.child import PlanRunResult


def _snapshot() -> ObjectSnapshot:
    """Return a minimal snapshot suitable for isolated engine tests."""
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="molecule",
        enabled=True,
        states=(),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )


class _Cmd:
    """Record recovery and dispatcher ordering without importing PyMOL."""

    def __init__(self, events: list[str], *, load_fails: bool = False) -> None:
        self.events = events
        self.load_fails = load_fails

    def get_names(self, _kind: str) -> list[str]:
        """Return a stable complete-session name list."""
        return ["molecule"]

    def save(self, filename: str) -> None:
        """Materialize the requested recovery file."""
        self.events.append("save")
        Path(filename).write_bytes(b"session")

    def load(self, _filename: str, *, partial: int) -> None:
        """Record a whole-session restore, optionally failing it."""
        assert partial == 0
        self.events.append("load")
        if self.load_fails:
            raise RuntimeError("restore failed")


def _plan() -> ActionPlan:
    """Return a cast plan because injected dispatchers never inspect it."""
    return cast(ActionPlan, object())


def test_save_precedes_successful_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No live command can be dispatched before the recovery point exists."""
    events: list[str] = []
    cmd = _Cmd(events)
    monkeypatch.setattr("pmc_client.apply.extract", lambda *_args: _snapshot())
    monkeypatch.setattr(
        "pmc_client.apply.structure_digest", lambda _value: "sha256:after"
    )

    def dispatch(_cmd: object, _plan: ActionPlan) -> PlanRunResult:
        events.append("dispatch")
        return PlanRunResult(STATUS_OK, REASON_OK, ())

    outcome = apply_plan(
        cmd,
        object_name="molecule",
        plan_id="one",
        plan=_plan(),
        store=RecoveryStore(tmp_path),
        dispatcher=dispatch,
    )

    assert outcome.status == APPLY_APPLIED
    assert events == ["save", "dispatch"]
    assert outcome.recovery_path is not None and outcome.recovery_path.exists()


def test_failed_dispatch_restores_before_reporting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first command failure restores the complete saved session once."""
    events: list[str] = []
    cmd = _Cmd(events)
    monkeypatch.setattr("pmc_client.apply.extract", lambda *_args: _snapshot())
    monkeypatch.setattr("pmc_client.apply.diff", lambda *_args: [])

    def dispatch(_cmd: object, _plan: ActionPlan) -> PlanRunResult:
        events.append("dispatch")
        return PlanRunResult(STATUS_FAILED, REASON_COMMAND_FAILURE, ())

    outcome = apply_plan(
        cmd,
        object_name="molecule",
        plan_id="one",
        plan=_plan(),
        store=RecoveryStore(tmp_path),
        dispatcher=dispatch,
    )

    assert outcome.status == APPLY_RESTORED
    assert events == ["save", "dispatch", "load"]


def test_failed_restore_preserves_the_manual_recovery_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restore exception preserves its recovery point for manual repair."""
    events: list[str] = []
    cmd = _Cmd(events, load_fails=True)
    monkeypatch.setattr("pmc_client.apply.extract", lambda *_args: _snapshot())

    outcome = apply_plan(
        cmd,
        object_name="molecule",
        plan_id="one",
        plan=_plan(),
        store=RecoveryStore(tmp_path),
        dispatcher=lambda *_args: PlanRunResult(
            STATUS_FAILED, REASON_COMMAND_FAILURE, ()
        ),
    )

    assert outcome.status == APPLY_RESTORE_FAILED
    assert outcome.recovery_path is not None and outcome.recovery_path.exists()


def test_sabotaged_restore_comparison_refuses_to_consume_the_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deliberately injected post-restore difference trips containment.

    This is the small sabotage proof for the assertion layer itself: if the
    full-session comparison were removed, this test would incorrectly report
    a clean restore and the private point would be discarded.
    """
    events: list[str] = []
    cmd = _Cmd(events)
    monkeypatch.setattr("pmc_client.apply.extract", lambda *_args: _snapshot())
    monkeypatch.setattr(
        "pmc_client.apply.diff", lambda *_args: ["sabotaged snapshot differs"]
    )

    outcome = apply_plan(
        cmd,
        object_name="molecule",
        plan_id="one",
        plan=_plan(),
        store=RecoveryStore(tmp_path),
        dispatcher=lambda *_args: PlanRunResult(
            STATUS_FAILED, REASON_COMMAND_FAILURE, ()
        ),
    )

    assert outcome.status == APPLY_RESTORE_FAILED
    assert outcome.mismatches == ("sabotaged snapshot differs",)
    assert outcome.recovery_path is not None and outcome.recovery_path.exists()


if __name__ == "__main__":
    raise SystemExit(0)
