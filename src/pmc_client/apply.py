# Copyright 2026 PyMOL Copilot contributors.
"""Closed-dispatch live application with automatic whole-session recovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Callable

from pmc_client.recovery import RecoveryPointError
from pmc_client.recovery import RecoveryStore
from pmc_core.executor import STATUS_OK
from pmc_core.plan import ActionPlan
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import diff
from pmc_core.snapshot import extract
from pmc_core.snapshot import structure_digest
from pmc_sidecar.child import PlanRunResult
from pmc_sidecar.child import run_plan


APPLY_APPLIED = "applied"
APPLY_RESTORED = "restored"
APPLY_RESTORE_FAILED = "restore_failed"
APPLY_REFUSED = "refused"


@dataclass(frozen=True)
class ApplyOutcome:
    """One immutable result from the live apply/recovery boundary."""

    status: str
    before: ObjectSnapshot | None
    post_apply_digest: str | None
    recovery_path: Path | None
    mismatches: tuple[str, ...] = ()


def apply_plan(
    cmd: Any,
    *,
    object_name: str,
    plan_id: str,
    plan: ActionPlan,
    store: RecoveryStore,
    dispatcher: Callable[[Any, ActionPlan], PlanRunResult] = run_plan,
) -> ApplyOutcome:
    """Save, run the closed dispatcher, and restore on its first failure."""
    before = extract(cmd, object_name)
    names_before = tuple(sorted(cmd.get_names("all")))
    try:
        path = store.save(cmd, plan_id)
    except RecoveryPointError:
        return ApplyOutcome(APPLY_REFUSED, before, None, None)
    result = dispatcher(cmd, plan)
    if result.status == STATUS_OK:
        return ApplyOutcome(
            APPLY_APPLIED,
            before,
            structure_digest(extract(cmd, object_name)),
            path,
        )
    try:
        store.restore(cmd, path)
        restored = extract(cmd, object_name)
        mismatches = tuple(diff(before, restored))
        if tuple(sorted(cmd.get_names("all"))) != names_before:
            mismatches += ("session names differ after restore",)
    except (RecoveryPointError, Exception):
        return ApplyOutcome(
            APPLY_RESTORE_FAILED, before, None, store.preserve()
        )
    if mismatches:
        return ApplyOutcome(
            APPLY_RESTORE_FAILED, before, None, store.preserve(), mismatches
        )
    return ApplyOutcome(APPLY_RESTORED, before, None, path)
