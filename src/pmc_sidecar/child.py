# Copyright 2026 PyMOL Copilot contributors.
"""The sidecar executor's fresh-process child.

This is the one module that imports real PyMOL and its Windows short-path
staging shim. `pmc_core.executor.execute()` spawns this module by name
(`python -m pmc_sidecar.child`), never by import, so `pmc_core` itself
never acquires either dependency (see
`tools/bazel/check_dependency_boundaries.py`). `main()` reads a snapshot
path, a plan path, and an output path from its command line, reconstructs
the snapshot in a freshly launched headless PyMOL, executes the plan's
operations through `run_plan()`'s closed dispatch, and writes a single JSON
report to the output path before exiting through `os._exit()` -- PyMOL's
headless shutdown can otherwise override a real exit code, and the parent
never relies on this process's exit status, only on the presence and
content of its output file.

`run_plan()` dispatches over the five allowlisted operation types via one
`match` with one branch per verb, never `getattr(cmd, verb)` on a verb
string: SPECIFICATION.md:486 requires "no raw-text execution" at every
execution boundary, and a closed dispatch is what keeps a plan's typed
operations, rather than any string a plan might carry, in control of what
PyMOL command actually runs. Its `case _` arm is unreachable while
`pmc_core.plan.OPERATION` stays exhaustive; it exists so that a verb added
to the language without a corresponding branch here fails closed with a
typed outcome instead of silently doing nothing or crashing the child.

Once every command succeeds, `main()` collects the atom count of every
selection the plan created or referenced (`cmd.count_atoms`, the same
technique `pmc_core.snapshot.extract` uses for per-representation
membership) and computes a resulting fingerprint over the reconstructed
object's full canonical re-extraction, so a caller can detect a fidelity
mismatch even when every command reported success.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_core.errors import normalize
from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import MAX_COMMAND_ERROR_BYTES
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_OK
from pmc_core.executor import REASON_SPAWN_OR_LOAD_FAILURE
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import bounded_diagnostic
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import ActionPlan
from pmc_core.plan import ColorOperation
from pmc_core.plan import HideOperation
from pmc_core.plan import OPERATION
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectOperation
from pmc_core.plan import ShowOperation
from pmc_core.plan import referenced_selection_name
from pmc_core.protocol import decode_plan
from pmc_core.snapshot import extract
from pmc_core.snapshot import from_json
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import to_json

import winstage

#: Every allowlisted verb's canonical spelling, keyed by its typed operation
#: type -- derived from pmc_core.plan's own declarative table rather than a
#: second literal copy, so the two can never drift apart.
_VERB_BY_TYPE: dict[type, str] = {
    rule.operation_type: rule.verb for rule in COMMAND_ALLOWLIST.values()
}


class UnsupportedOperationError(ValueError):
    """Raised when a typed operation has no dispatch branch in this module.

    Unreachable while `pmc_core.plan.OPERATION` stays exhaustive with
    `COMMAND_ALLOWLIST`; exists as a fail-closed guard against a verb added
    to the language without a matching branch in `_dispatch`.
    """


@dataclass(frozen=True)
class PlanRunResult:
    """The outcome of running one plan's operations against a live session.

    Attributes:
        status: `pmc_core.executor.STATUS_OK` or `STATUS_FAILED`.
        reason: `REASON_OK` or `REASON_COMMAND_FAILURE`.
        command_outcomes: Per-command outcomes, indexed by position.
            Shorter than the plan's operations whenever execution stopped
            early at the first failing command.
    """

    status: str
    reason: str
    command_outcomes: tuple[CommandOutcome, ...]


def _dispatch(cmd: Any, operation: OPERATION) -> str:
    """Execute one typed operation's verb against a live PyMOL `cmd`.

    Args:
        cmd: The live PyMOL `cmd` module (or a compatible stand-in).
        operation: The typed operation to execute.

    Returns:
        The verb string for the operation just dispatched.

    Raises:
        UnsupportedOperationError: If operation's type has no branch below.
        Exception: Whatever the underlying PyMOL command raises on failure.
    """
    match operation:
        case SelectOperation():
            cmd.select(operation.selection_name, operation.expression.render())
            return "select"
        case ColorOperation():
            cmd.color(operation.color, operation.target.render())
            return "color"
        case ShowOperation():
            cmd.show(operation.representation, operation.target.render())
            return "show"
        case HideOperation():
            cmd.hide(operation.representation, operation.target.render())
            return "hide"
        case OrientOperation():
            cmd.orient(operation.target.render())
            return "orient"
        case _:
            raise UnsupportedOperationError(
                f"no dispatch branch for operation type: {type(operation)!r}"
            )


def run_plan(cmd: Any, plan: ActionPlan) -> PlanRunResult:
    """Execute a plan's operations in order against an already-live session.

    Assumes the snapshot this plan targets has already been reconstructed
    into `cmd`'s session (see `main()`, or a caller such as a test that
    reconstructs directly against a real PyMOL fixture). Stops at the first
    failing command; no command is retried.

    Args:
        cmd: The live PyMOL `cmd` module (or a compatible stand-in).
        plan: The typed plan whose operations to execute, in order.

    Returns:
        The plan's outcome: STATUS_OK with one OUTCOME_OK per operation when
        every command succeeds, or STATUS_FAILED with REASON_COMMAND_FAILURE
        and one OUTCOME_ERROR at the failing index when any command --
        including one this module's own dispatch cannot recognize -- fails.
        A failing command's outcome carries a normalized `ExecutionErrorV1`
        whenever its verb is one `pmc_core.errors.normalize` accepts; the
        one case that is never a real PyMOL failure -- this module's own
        dispatch not recognizing the operation's type -- carries none.
    """
    outcomes: list[CommandOutcome] = []
    for index, operation in enumerate(plan.operations):
        try:
            verb = _dispatch(cmd, operation)
            cmd.sync()
        except Exception as error:
            verb = _VERB_BY_TYPE.get(type(operation), "__unsupported__")
            # normalize() is only ever called with a verb this module has
            # just confirmed is allowlisted: it is docs/master_plan.md item
            # 6's own contract that a verb outside COMMAND_ALLOWLIST is a
            # defect in this module's dispatch table, not a PyMOL failure
            # to normalize, and ExecutionErrorV1 refuses to construct one
            # anyway (pmc_core.errors.ExecutionErrorV1.__post_init__).
            envelope = (
                normalize(error, command_index=index, verb=verb)
                if verb in COMMAND_ALLOWLIST
                else None
            )
            outcomes.append(
                CommandOutcome(
                    index,
                    verb,
                    OUTCOME_ERROR,
                    bounded_diagnostic(
                        str(error), maximum_bytes=MAX_COMMAND_ERROR_BYTES
                    ),
                    envelope,
                )
            )
            return PlanRunResult(
                STATUS_FAILED, REASON_COMMAND_FAILURE, tuple(outcomes)
            )
        outcomes.append(CommandOutcome(index, verb, OUTCOME_OK, None, None))
    return PlanRunResult(STATUS_OK, REASON_OK, tuple(outcomes))


def _selection_names(plan: ActionPlan) -> tuple[str, ...]:
    """Collect every distinct selection name a plan creates or references.

    Args:
        plan: The typed plan whose selection names to collect.

    Returns:
        Each distinct name, in first-appearance order.
    """
    seen: dict[str, None] = {}
    for operation in plan.operations:
        if isinstance(operation, SelectOperation):
            seen.setdefault(operation.selection_name, None)
        referenced = referenced_selection_name(operation)
        if referenced is not None:
            seen.setdefault(referenced, None)
    return tuple(seen)


def _outcome_to_dict(outcome: CommandOutcome) -> dict[str, object]:
    """Convert one command outcome to its JSON-serializable form.

    Args:
        outcome: The outcome to convert.

    Returns:
        The outcome as a plain dict of JSON-safe values.
    """
    return {
        "index": outcome.index,
        "verb": outcome.verb,
        "status": outcome.status,
        "error": outcome.error,
        "error_envelope": (
            outcome.error_envelope.to_dict()
            if outcome.error_envelope is not None
            else None
        ),
    }


def main(argv: Sequence[str] | None = None) -> None:
    """Reconstruct a snapshot and run a plan's operations in a fresh PyMOL.

    Args:
        argv: `[snapshot_path, plan_path, output_path]`. Defaults to
            `sys.argv[1:]` when None.
    """
    snapshot_path, plan_path, output_path = (
        sys.argv[1:] if argv is None else argv
    )

    def _write(payload: dict[str, object]) -> None:
        with Path(output_path).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())

    snapshot_text = Path(snapshot_path).read_text(encoding="utf-8")
    plan_data = json.loads(Path(plan_path).read_text(encoding="utf-8"))

    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])

    try:
        parsed_snapshot = from_json(snapshot_text)
        plan = decode_plan(plan_data)
        reconstruct(cmd, parsed_snapshot)
    except Exception:
        _write(
            {
                "status": STATUS_FAILED,
                "reason": REASON_SPAWN_OR_LOAD_FAILURE,
                "command_outcomes": [],
            }
        )
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    result = run_plan(cmd, plan)
    status = result.status
    reason = result.reason
    command_outcomes = list(result.command_outcomes)
    selection_counts: list[dict[str, object]] = []
    resulting_fingerprint: str | None = None

    if status == STATUS_OK:
        try:
            for name in _selection_names(plan):
                selection_counts.append(
                    {"name": name, "atom_count": cmd.count_atoms(name)}
                )
            extracted = extract(cmd, parsed_snapshot.name)
            resulting_fingerprint = (
                "sha256:"
                + hashlib.sha256(to_json(extracted).encode("utf-8")).hexdigest()
            )
        except Exception as error:
            # A command each reported OUTCOME_OK, but the state they left
            # behind cannot even be re-extracted -- fails closed the same
            # way a command failure does, with a synthetic outcome at the
            # first index past the plan's own operations.
            status = STATUS_FAILED
            reason = REASON_COMMAND_FAILURE
            selection_counts = []
            command_outcomes.append(
                CommandOutcome(
                    index=len(plan.operations),
                    verb="__extract__",
                    status=OUTCOME_ERROR,
                    error=bounded_diagnostic(
                        str(error), maximum_bytes=MAX_COMMAND_ERROR_BYTES
                    ),
                )
            )

    _write(
        {
            "status": status,
            "reason": reason,
            "command_outcomes": [
                _outcome_to_dict(outcome) for outcome in command_outcomes
            ],
            "selection_counts": selection_counts,
            "resulting_fingerprint": resulting_fingerprint,
        }
    )
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
