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
    try:
        before = extract(cmd, object_name)
        names_before = tuple(sorted(cmd.get_names("all")))
    except Exception as error:
        # Never str(error): extract() and get_names() reach real PyMOL
        # query APIs, and a raised message can carry selection or object
        # text this module must not put on the console unbounded.
        return ApplyOutcome(
            APPLY_REFUSED,
            None,
            (),
            None,
            None,
            failure_message=(
                "could not inspect the pre-apply session "
                f"(internal error: {type(error).__name__})"
            ),
        )
    try:
        path = store.save(cmd, plan_id)
    except RecoveryPointError:
        return ApplyOutcome(APPLY_REFUSED, before, names_before, None, None)
    try:
        result = dispatcher(cmd, plan)
    except Exception as error:
        # Never str(error) either: the dispatcher's own exception can
        # likewise carry plan or selection text from whichever command was
        # executing when it raised.
        result = PlanRunResult(STATUS_FAILED, "dispatcher_exception", ())
        dispatcher_error = (
            f"the dispatcher raised an internal error: {type(error).__name__}"
        )
    else:
        dispatcher_error = None
    if result.status == STATUS_OK:
        try:
            post_apply_digest = structure_digest(extract(cmd, object_name))
        except Exception as error:
            # Dispatch has already mutated the live session. Treat failed
            # post-apply inspection exactly like a command failure: restore
            # and verify the saved whole-session point before reporting.
            result = PlanRunResult(STATUS_FAILED, "post_apply_inspection", ())
            dispatcher_error = (
                f"post-apply inspection failed (internal error: "
                f"{type(error).__name__})"
            )
        else:
            return ApplyOutcome(
                APPLY_APPLIED,
                before,
                names_before,
                post_apply_digest,
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
