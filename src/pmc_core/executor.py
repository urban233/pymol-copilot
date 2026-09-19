# Copyright 2026 PyMOL Copilot contributors.
"""The fresh-process execution boundary: typed plan and snapshot in, report out.

This module promotes
[tests/discovery/h02/execution_boundary.py](../../tests/discovery/h02/execution_boundary.py)
into production code -- docs/master_plan.md item 4, "the sidecar executor" --
and implements the "validation sidecar" SPECIFICATION.md describes: a
component that "reconstruct[s] exact relevant session state and execute[s] a
plan without touching the live session", taking a session snapshot and a
typed plan and returning "a validation report and resulting state evidence"
from a "fresh Open-Source PyMOL process".

The contract is: a typed `pmc_core.plan.ActionPlan` plus a canonical
`pmc_core.snapshot.ObjectSnapshot` (already serialized to JSON) in, an
`ExecutionReport` out. One fresh PyMOL process per attempt, a finite input
size, a finite wall-clock deadline, a hard kill and reap on timeout, scratch
cleanup on every exit path, and no internal retry -- exactly the guarantees
the prototype it promotes calls "fresh process, finite resources,
command-indexed outcomes, and deterministic evidence where declared".

This module never imports `pymol` and never imports `winstage`: the process
that actually touches PyMOL is a separate module,
`src/pmc_sidecar/child.py`, which `execute()` spawns by module name
("python -m pmc_sidecar.child") rather than by import, so this package's own
Bazel dependency closure never acquires either dependency (enforced by
`tools/bazel/check_dependency_boundaries.py`).

This module does not yet spawn a child process: that lands in a later step
of the same promotion (see `plans/05-sidecar-executor.md`, step 4). Today it
owns the typed contract and the parent-side validation that must happen
before any process is ever created -- an unsupported request version, an
oversized snapshot, malformed or version-mismatched snapshot JSON, and a
plan the default-deny policy denies are all rejected here, with no scratch
data ever written for any of them.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import time
from dataclasses import dataclass
from dataclasses import field

from pmc_core.plan import ActionPlan
from pmc_core.policy import evaluate_plan
from pmc_core.snapshot import from_json
from pmc_core.snapshot import structure_digest

#: This module's own contract version for ExecutionRequest/ExecutionReport,
#: independent of pmc_core.snapshot.SNAPSHOT_VERSION and the command
#: language's own version: a request pins all three, but only a mismatch on
#: this one means "this executor cannot even parse the request shape".
EXECUTOR_VERSION = 1

#: The default ceiling, in bytes, on a request's snapshot_json before it is
#: even parsed. A canonical snapshot for a large structure can be
#: substantial; this bounds resource use in the parent process, independent
#: of pmc_core.plan.MAX_INPUT_BYTES, which bounds only a plan's own rendered
#: .pml text.
DEFAULT_MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024

#: The default wall-clock deadline, in seconds, for the whole spawned child
#: process.
DEFAULT_DEADLINE_SECONDS = 30.0

#: How long to wait for a plain terminate() (SIGTERM) to take effect before
#: escalating to a hard kill (SIGKILL).
DEFAULT_KILL_GRACE_SECONDS = 5.0

#: The scratch-directory prefix used for each spawned attempt's disposable
#: working directory. Also the glob pattern a test uses to confirm no
#: scratch data is left behind after execute() returns.
SCRATCH_DIR_PREFIX = "pmc-executor-"

#: Top-level report outcomes.
STATUS_OK = "ok"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"

#: Typed, stable failure reasons -- every fail-closed path below sets
#: exactly one of these, never a raw exception string.
REASON_OK = "ok"
REASON_OVERSIZED_INPUT = "oversized_input"
REASON_MALFORMED_INPUT = "malformed_input"
REASON_UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
REASON_POLICY_DENIED = "policy_denied"
REASON_SPAWN_OR_LOAD_FAILURE = "spawn_or_load_failure"
REASON_TIMEOUT = "timeout"
REASON_CHILD_CRASH = "child_crash"
REASON_COMMAND_FAILURE = "command_failure"
REASON_FIDELITY_MISMATCH = "fidelity_mismatch"

#: Per-command outcome statuses.
OUTCOME_OK = "ok"
OUTCOME_ERROR = "error"


@dataclass(frozen=True)
class CommandOutcome:
    """The observed outcome of one command, indexed by its position.

    Attributes:
        index: The command's zero-based position in the plan's operations.
        verb: The verb that was executed (`select`, `color`, `show`, `hide`,
            or `orient`).
        status: `OUTCOME_OK` or `OUTCOME_ERROR`.
        error: A bounded error message when status is `OUTCOME_ERROR`, else
            None.
    """

    index: int
    verb: str
    status: str
    error: str | None


@dataclass(frozen=True)
class SelectionCount:
    """The atom count a plan's named selection matched after execution.

    Attributes:
        name: The selection name, in the order it first appears in the plan.
        atom_count: The number of atoms the selection matched. Zero is a
            valid, reported count, not an error: a plan that selects nothing
            is scientifically useful information, not a failure.
    """

    name: str
    atom_count: int


@dataclass(frozen=True)
class ExecutionRequest:
    """A request to execute a typed plan against a canonical snapshot.

    Attributes:
        executor_version: This request shape's own contract version.
        plan: The typed, immutable plan to execute. Never raw `.pml` text.
        snapshot_json: The candidate snapshot to reconstruct from, as
            `pmc_core.snapshot.to_json` serialized it -- validated and
            parsed inside `execute()`, never trusted as already-well-formed.
        max_snapshot_bytes: The maximum allowed size, in bytes, of
            `snapshot_json`'s UTF-8 encoding. A request whose snapshot
            exceeds this limit is rejected before any process is spawned.
        deadline_seconds: The wall-clock deadline for the whole spawned
            child process. Exceeding it causes a hard kill.
        expected_resulting_fingerprint: An optional independently computed
            fingerprint (see `ExecutionReport.resulting_fingerprint`) that
            the boundary must match after a fully successful run. A
            mismatch fails the report closed with
            `REASON_FIDELITY_MISMATCH`, even though every command
            succeeded.
    """

    executor_version: int
    plan: ActionPlan
    snapshot_json: str
    max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS
    expected_resulting_fingerprint: str | None = None


@dataclass(frozen=True)
class ExecutionReport:
    """The result of one `execute()` call.

    Attributes:
        executor_version: This report shape's own contract version.
        status: `STATUS_OK`, `STATUS_REJECTED` (failed before any process
            was spawned), or `STATUS_FAILED` (failed during or after a
            spawned child's run).
        reason: One of this module's `REASON_*` constants; `REASON_OK` iff
            status is `STATUS_OK`.
        input_digest: `pmc_core.snapshot.structure_digest` of the request's
            own snapshot, set as soon as that snapshot at least parses -- so
            it is present on a policy denial, not only on success, and None
            only when rejected before that parse (an unsupported executor
            version, an oversized snapshot, or malformed/version-mismatched
            snapshot JSON).
        resulting_fingerprint: A fingerprint of the reconstructed object's
            canonical extraction after every command ran, or None when no
            such extraction was ever produced.
        selection_counts: The atom count of every selection the plan names,
            in first-appearance order, or empty when execution never
            reached extraction.
        child_pid: The spawned child's OS process ID, or None when no
            process was ever spawned (every `STATUS_REJECTED` report).
        child_terminated: Whether `execute()` itself observed, by the time
            it returns, that `child_pid` was no longer running. None
            exactly when `child_pid` is None, mirroring `input_digest`'s own
            None-when-not-applicable convention.
        command_outcomes: Per-command outcomes, indexed by position. Shorter
            than the plan's own operations whenever execution stopped early
            (a command failure or a crash).
        elapsed_seconds: Wall-clock time this `execute()` call took.
        warnings: Bounded diagnostic text that does not itself change status
            or reason (for example, captured child stderr after an
            unexplained crash).
    """

    executor_version: int
    status: str
    reason: str
    input_digest: str | None
    resulting_fingerprint: str | None
    selection_counts: tuple[SelectionCount, ...]
    command_outcomes: tuple[CommandOutcome, ...]
    child_pid: int | None
    child_terminated: bool | None
    elapsed_seconds: float
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _rejected(
    reason: str,
    elapsed_seconds: float,
    *,
    input_digest: str | None = None,
) -> ExecutionReport:
    """Build a report for a request rejected before any process was spawned.

    Args:
        reason: The typed rejection reason.
        elapsed_seconds: Time spent validating the request.
        input_digest: The request snapshot's structure digest, when the
            snapshot at least parsed before rejection, else None.

    Returns:
        A report with `STATUS_REJECTED` and no fingerprints or outcomes.
    """
    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_REJECTED,
        reason=reason,
        input_digest=input_digest,
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(),
        child_pid=None,
        child_terminated=None,
        elapsed_seconds=elapsed_seconds,
        warnings=(),
    )


def execute(request: ExecutionRequest) -> ExecutionReport:
    """Validate a request and execute its plan in a fresh sidecar process.

    Validates the request in this process first, in a fixed order: an
    unsupported request version, an oversized snapshot, malformed or
    version-mismatched snapshot JSON, and a plan the default-deny policy
    denies are all rejected here, with no process ever spawned and no
    scratch data ever written. Only a request that passes every check
    proceeds to execution.

    Args:
        request: The execution request to run.

    Returns:
        The execution report. Never raises for any of this module's own
        documented failure modes; every one of them is reported through the
        returned report's status/reason instead.

    Raises:
        NotImplementedError: Always, once a request passes every check
            above -- spawning a sidecar process is not implemented yet. See
            `plans/05-sidecar-executor.md` step 4.
    """
    start = time.monotonic()

    if request.executor_version != EXECUTOR_VERSION:
        return _rejected(
            REASON_UNSUPPORTED_SCHEMA_VERSION, time.monotonic() - start
        )

    encoded_snapshot = request.snapshot_json.encode("utf-8")
    if len(encoded_snapshot) > request.max_snapshot_bytes:
        return _rejected(REASON_OVERSIZED_INPUT, time.monotonic() - start)

    try:
        snapshot = from_json(request.snapshot_json)
    except json.JSONDecodeError:
        return _rejected(REASON_MALFORMED_INPUT, time.monotonic() - start)
    except ValueError:
        # Catches pmc_core.snapshot.SnapshotDecodeError, a ValueError
        # subclass raised for both a schema_version mismatch and a
        # declared-unsupported-set mismatch.
        return _rejected(
            REASON_UNSUPPORTED_SCHEMA_VERSION, time.monotonic() - start
        )
    except (KeyError, AttributeError, TypeError):
        # Syntactically valid JSON that from_json cannot treat as a
        # snapshot object at all -- a bare scalar/array/string (whose
        # .get("schema_version") raises AttributeError) or a JSON object
        # missing a required key (KeyError) -- is malformed input, not an
        # unsupported-but-recognized schema version.
        return _rejected(REASON_MALFORMED_INPUT, time.monotonic() - start)

    input_digest = structure_digest(snapshot)

    if not evaluate_plan(request.plan).allowed:
        return _rejected(
            REASON_POLICY_DENIED,
            time.monotonic() - start,
            input_digest=input_digest,
        )

    raise NotImplementedError(
        "execute() does not yet spawn a sidecar process; added in "
        "plans/05-sidecar-executor.md step 4"
    )
