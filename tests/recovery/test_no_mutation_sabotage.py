# Copyright 2026 PyMOL Copilot contributors.
"""Sabotage proof for the automatic-restore containment boundary."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import cast

import pytest

from pmc_client.apply import APPLY_REFUSED
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
    """Return minimal comparable evidence for a fake live session.

    `view` is a real 18-float PyMOL view tuple, not `()`: `pmc_core.snapshot
    .diff()` zips `expected.view` against `actual.view` with `strict=True`,
    which raises on a length mismatch rather than reporting one as an
    ordinary difference -- an empty `before.view` paired with a
    differently-shaped `after.view` would make `compare_recovery()` itself
    raise, not report a mismatch.
    """
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="molecule",
        enabled=True,
        states=(),
        bonds=(),
        view=tuple(0.0 for _ in range(18)),
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
    after = replace(before, view=(1.0, *before.view[1:]))
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


def test_a_pre_apply_inspection_exception_never_leaks_its_own_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-apply inspection failure is reported by exception type only.

    docs/master_plan.md item 11: `apply_plan`'s own pre-apply `extract()`
    reaches real PyMOL query APIs this module cannot enumerate every
    failure mode of, and a raised message can carry a selection
    expression -- plan text. Sabotage: interpolate ``str(error)`` at this
    call site instead of ``type(error).__name__``, and this row goes red.
    """
    sentinel = "LEAK select chain A"
    cmd = _Cmd()
    store = RecoveryStore(tmp_path)
    monkeypatch.setattr(
        "pmc_client.apply.extract",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(sentinel)),
    )

    outcome = apply_plan(
        cmd,
        object_name="molecule",
        plan_id="33333333-3333-4333-8333-333333333333",
        plan=cast(ActionPlan, object()),
        store=store,
        dispatcher=lambda *_a: PlanRunResult(
            STATUS_FAILED, REASON_COMMAND_FAILURE, ()
        ),
    )

    assert outcome.status == APPLY_REFUSED
    assert outcome.failure_message == (
        "could not inspect the pre-apply session (internal error: RuntimeError)"
    )
    assert sentinel not in (outcome.failure_message or "")


def test_a_dispatcher_exception_never_leaks_its_own_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dispatcher exception is reported by exception type only.

    A dispatched PyMOL command's own exception can likewise carry a
    selection expression, so `apply_plan` never interpolates it either.
    """
    sentinel = "LEAK select chain A"
    cmd = _Cmd()
    store = RecoveryStore(tmp_path)
    before = _snapshot()
    monkeypatch.setattr("pmc_client.apply.extract", lambda *_args: before)

    def _raising_dispatcher(_cmd: object, _plan: ActionPlan) -> PlanRunResult:
        raise RuntimeError(sentinel)

    outcome = apply_plan(
        cmd,
        object_name="molecule",
        plan_id="33333333-3333-4333-8333-333333333333",
        plan=cast(ActionPlan, object()),
        store=store,
        dispatcher=_raising_dispatcher,
    )

    assert outcome.status == APPLY_RESTORED
    assert outcome.failure_message == (
        "the dispatcher raised an internal error: RuntimeError"
    )
    assert sentinel not in (outcome.failure_message or "")


def test_a_post_apply_inspection_exception_never_leaks_its_own_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-apply inspection failure is reported by exception type only.

    Dispatch has already mutated the live session by this point, so this
    is treated like a command failure and restored -- but the message
    describing why must still never carry the query API's own raw text.
    """
    sentinel = "LEAK select chain A"
    cmd = _Cmd()
    store = RecoveryStore(tmp_path)
    before = _snapshot()
    calls = 0

    def _extract(*_args: object) -> ObjectSnapshot:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError(sentinel)
        return before

    monkeypatch.setattr("pmc_client.apply.extract", _extract)

    outcome = apply_plan(
        cmd,
        object_name="molecule",
        plan_id="33333333-3333-4333-8333-333333333333",
        plan=cast(ActionPlan, object()),
        store=store,
        dispatcher=lambda *_a: PlanRunResult(STATUS_OK, REASON_OK, ()),
    )

    assert outcome.status == APPLY_RESTORED
    assert outcome.failure_message == (
        "post-apply inspection failed (internal error: RuntimeError)"
    )
    assert sentinel not in (outcome.failure_message or "")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
