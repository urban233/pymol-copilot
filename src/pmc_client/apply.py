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
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import OUTCOME_ERROR
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
    names_before: tuple[str, ...]
    post_apply_digest: str | None
    recovery_path: Path | None
    mismatches: tuple[str, ...] = ()
    failure_index: int | None = None
    failure_verb: str | None = None
    failure_message: str | None = None


def compare_recovery(
    cmd: Any,
    *,
    object_name: str,
    before: ObjectSnapshot,
    names_before: tuple[str, ...],
) -> tuple[str, ...]:
    """Compare a restored live session with its pre-apply evidence.

    ``structure_digest`` intentionally excludes the view and settings, so
    recovery is compared with the complete snapshot diff as well as the full
    name list.  The latter catches plan-created selections that a partial
    restore accidentally left behind.
    """
    mismatches = tuple(diff(before, extract(cmd, object_name)))
    if tuple(sorted(cmd.get_names("all"))) != names_before:
        mismatches += ("session names differ after restore",)
    return mismatches


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
        return ApplyOutcome(APPLY_REFUSED, before, names_before, None, None)
    try:
        result = dispatcher(cmd, plan)
    except Exception as error:
        result = PlanRunResult(STATUS_FAILED, "dispatcher_exception", ())
        dispatcher_error = str(error)
    else:
        dispatcher_error = None
    if result.status == STATUS_OK:
        return ApplyOutcome(
            APPLY_APPLIED,
            before,
            names_before,
            structure_digest(extract(cmd, object_name)),
            path,
        )
    failed = next(
        (
            outcome
            for outcome in result.command_outcomes
            if outcome.status == OUTCOME_ERROR
        ),
        None,
    )
    try:
        store.restore(cmd, path)
        mismatches = compare_recovery(
            cmd,
            object_name=object_name,
            before=before,
            names_before=names_before,
        )
    except Exception:
        return ApplyOutcome(
            APPLY_RESTORE_FAILED,
            before,
            names_before,
            None,
            store.preserve(),
            failure_index=failed.index if failed is not None else None,
            failure_verb=failed.verb if failed is not None else None,
            failure_message=(
                failed.error if failed is not None else dispatcher_error
            ),
        )
    if mismatches:
        return ApplyOutcome(
            APPLY_RESTORE_FAILED,
            before,
            names_before,
            None,
            store.preserve(),
            mismatches,
            failed.index if failed is not None else None,
            failed.verb if failed is not None else None,
            failed.error if failed is not None else dispatcher_error,
        )
    return ApplyOutcome(
        APPLY_RESTORED,
        before,
        names_before,
        None,
        path,
        failure_index=failed.index if failed is not None else None,
        failure_verb=failed.verb if failed is not None else None,
        failure_message=failed.error
        if failed is not None
        else dispatcher_error,
    )
