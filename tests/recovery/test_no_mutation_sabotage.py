# Copyright 2026 PyMOL Copilot contributors.
"""Sabotage proof for the automatic-restore containment boundary."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import cast

import pytest

from pmc_client.apply import APPLY_RESTORE_FAILED
from pmc_client.apply import apply_plan
from pmc_client.recovery import RecoveryStore
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import STATUS_FAILED
from pmc_core.plan import ActionPlan
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_sidecar.child import PlanRunResult


def _snapshot() -> ObjectSnapshot:
    """Return minimal comparable evidence for a fake live session."""
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
    """A small mutable session whose restore can deliberately be sabotaged."""

    def __init__(self) -> None:
        self.changed = False

    def get_names(self, _kind: str) -> list[str]:
        """Return a stable complete-session name list."""
        return ["molecule"]

    def save(self, filename: str) -> None:
        """Materialize a recovery file for the real RecoveryStore lifecycle."""
        Path(filename).write_bytes(b"before")

    def load(self, _filename: str, *, partial: int) -> None:
        """Provide the normal load surface; the store below sabotages it."""
        assert partial == 0


class _NoRestoreStore(RecoveryStore):
    """A source-sabotage equivalent: count restore, but leave mutation live."""

    def __init__(self, root: Path) -> None:
        """Create a hermetic store and initialize its observable counter."""
        super().__init__(root)
        self.restore_calls = 0

    def restore(self, cmd: Any, path: Path) -> None:  # noqa: ARG002
        """Simulate a deleted `store.restore(...)` effect after a failure."""
        self.restore_calls += 1


def test_sabotaged_restore_is_detected_and_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing restore cannot look clean or consume its manual recovery file.

    This is deliberately behavioral rather than a fragile textual source
    scan.  If the production failure branch stops calling ``store.restore``,
    ``restore_calls`` is zero; if it calls a broken restore, the actual
    comparison detects the surviving mutation and preserves the point.
    """
    cmd = _Cmd()
    store = _NoRestoreStore(tmp_path)
    before = _snapshot()
    after = replace(before, view=(1.0,))
    monkeypatch.setattr(
        "pmc_client.apply.extract",
        lambda *_args: after if cmd.changed else before,
    )

    def dispatch(_cmd: object, _plan: ActionPlan) -> PlanRunResult:
        cmd.changed = True
        return PlanRunResult(STATUS_FAILED, REASON_COMMAND_FAILURE, ())

    outcome = apply_plan(
        cmd,
        object_name="molecule",
        plan_id="33333333-3333-4333-8333-333333333333",
        plan=cast(ActionPlan, object()),
        store=store,
        dispatcher=dispatch,
    )

    assert store.restore_calls == 1
    assert outcome.status == APPLY_RESTORE_FAILED
    assert outcome.mismatches
    assert outcome.recovery_path is not None
    assert outcome.recovery_path.exists()
