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

This module also owns `probe_fidelity()` (docs/master_plan.md item 7, "the
live extraction and fidelity gate"): given a candidate snapshot alone -- no
plan -- reconstruct it in a fresh sidecar and hand back the child's own
re-extraction, so a caller holding the live session can `pmc_core.snapshot
.diff` the two without ever letting the sidecar touch the live session
itself. `execute()` and `probe_fidelity()` share every process-management
guarantee below through one private helper, `_run_child()`; each keeps its
own pre-spawn request validation and its own mapping from a spawned
attempt's outcome to its own report type.

This module never imports `pymol` and never imports `winstage`: the process
that actually touches PyMOL is one of two separate modules under
`src/pmc_sidecar/` -- `child.py`, which `execute()` spawns by module name
("python -m pmc_sidecar.child"), and `fidelity.py`, which `probe_fidelity()`
spawns the same way ("python -m pmc_sidecar.fidelity") -- never by import,
so this package's own Bazel dependency closure never acquires either
dependency (enforced by `tools/bazel/check_dependency_boundaries.py`).

`execute()` validates a request entirely in this process first -- an
unsupported request version, an oversized snapshot, malformed or
version-mismatched snapshot JSON, a mismatched plan/snapshot digest, and a
plan the default-deny policy denies are all rejected here, with no process
ever spawned and no scratch data ever written. `probe_fidelity()` runs the
same shape of validation minus the plan-specific checks it has no plan to
run them against. Only a request that passes every check spawns a fresh
child, gives it a hard wall-clock deadline, and reaps it on every exit path
-- success, timeout, crash, and an exception raised between spawn and the
child's own completion -- with its scratch directory removed only after
that termination and reap.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import contextlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import IO
from typing import Any

from pmc_core.plan import ActionPlan
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import PROTOCOL_VERSION
from pmc_core.protocol import encode_plan
from pmc_core.snapshot import from_json
from pmc_core.snapshot import SnapshotDecodeError
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

#: Maximum UTF-8 size of one per-command error copied into a report. A plan
#: can contain 128 commands, so this deliberately stays small enough that a
#: valid worst-case report remains within the HTTP response bound.
MAX_COMMAND_ERROR_BYTES = 128

#: Maximum UTF-8 size of the one captured-stderr warning the parent emits
#: when a child crashes without a trustworthy report.
MAX_WARNING_BYTES = 4 * 1024

_TRUNCATION_MARKER = "...[truncated]"

#: The scratch-directory prefix used for each spawned attempt's disposable
#: working directory. Also the glob pattern a test uses to confirm no
#: scratch data is left behind after execute() returns.
SCRATCH_DIR_PREFIX = "pmc-executor-"

#: `os.killpg`, `os.getpgid`, and `signal.SIGKILL` exist only on POSIX.
#: Resolved dynamically here, rather than referenced directly in
#: `_terminate`/`_kill` below, because pyrefly checks this project against
#: whichever platform actually runs it: a direct reference is a genuine
#: `missing-attribute` error on Windows CI, but a pyrefly ignore comment
#: on that same line becomes an `unused-ignore` error on Linux/macOS CI
#: instead, where the attributes genuinely exist. No single ignore
#: comment is correct on all three CI platforms at once; a dynamic
#: lookup sidesteps the static attribute check entirely, on every
#: platform, the same way `getattr` already does for `os.add_dll_directory`
#: in `tools/winstage/winstage.py` -- except that one is missing
#: everywhere except Windows, so a plain ignore comment is enough there.
_killpg = getattr(os, "killpg", None)
_getpgid = getattr(os, "getpgid", None)
_SIGKILL = getattr(signal, "SIGKILL", None)

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
REASON_SNAPSHOT_DIGEST_MISMATCH = "snapshot_digest_mismatch"
REASON_SPAWN_OR_LOAD_FAILURE = "spawn_or_load_failure"
REASON_TIMEOUT = "timeout"
REASON_CHILD_CRASH = "child_crash"
REASON_COMMAND_FAILURE = "command_failure"
REASON_FIDELITY_MISMATCH = "fidelity_mismatch"
#: Set only by a fidelity probe's own child (src/pmc_sidecar/fidelity.py)
#: when reconstruction itself succeeded but the child's own re-extraction of
#: the reconstructed object failed -- distinct from
#: REASON_SPAWN_OR_LOAD_FAILURE (the child never reached a live
#: reconstructed object at all) and REASON_CHILD_CRASH (no trustworthy
#: output file). probe_fidelity() never sets this itself; it only passes it
#: through from the child's own report.
REASON_RECONSTRUCTION_FAILURE = "reconstruction_failure"

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
        expected_snapshot_digest: The structural digest the plan was bound
            to. When supplied, a mismatch with `snapshot_json` is rejected
            before scratch data is written or a process is spawned.
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
    expected_snapshot_digest: str | None = None
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


@dataclass(frozen=True)
class FidelityRequest:
    """A request to reconstruct a candidate snapshot in a fresh sidecar.

    Unlike `ExecutionRequest`, this carries no plan: a fidelity probe never
    executes a command, and its own child (`src/pmc_sidecar/fidelity.py`)
    runs no policy evaluation, since there is nothing for policy to
    evaluate.

    Attributes:
        executor_version: This request shape's own contract version.
        snapshot_json: The candidate snapshot to reconstruct from, as
            `pmc_core.snapshot.to_json` serialized it -- validated and
            parsed inside `probe_fidelity()`, never trusted as already
            well-formed.
        max_snapshot_bytes: The maximum allowed size, in bytes, of
            `snapshot_json`'s UTF-8 encoding. A request whose snapshot
            exceeds this limit is rejected before any process is spawned.
        deadline_seconds: The wall-clock deadline for the whole spawned
            child process. Exceeding it causes a hard kill.
    """

    executor_version: int
    snapshot_json: str
    max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS


@dataclass(frozen=True)
class FidelityReport:
    """The result of one `probe_fidelity()` call.

    Deliberately shaped to mirror `ExecutionReport` minus the plan-specific
    fields (`resulting_fingerprint`, `selection_counts`, `command_outcomes`)
    it has no use for, plus the one field a fidelity probe exists to
    produce.

    Attributes:
        executor_version: This report shape's own contract version.
        status: `STATUS_OK`, `STATUS_REJECTED` (failed before any process
            was spawned), or `STATUS_FAILED` (failed during or after a
            spawned child's run).
        reason: One of this module's `REASON_*` constants; `REASON_OK` iff
            status is `STATUS_OK`. `REASON_RECONSTRUCTION_FAILURE` is set
            only by the child, never computed here.
        input_digest: `pmc_core.snapshot.structure_digest` of the request's
            own snapshot, set as soon as that snapshot at least parses, and
            None only when rejected before that parse.
        reconstructed_snapshot_json: The child's own re-extraction of the
            object it reconstructed, as `pmc_core.snapshot.to_json`
            serialized it, or None when status is not `STATUS_OK`. The
            caller runs `pmc_core.snapshot.diff` against this to judge
            fidelity; this module computes no diff of its own, since it
            never holds the live snapshot to diff against.
        child_pid: The spawned child's OS process ID, or None when no
            process was ever spawned.
        child_terminated: Whether `probe_fidelity()` itself observed, by
            the time it returns, that `child_pid` was no longer running.
            None exactly when `child_pid` is None.
        elapsed_seconds: Wall-clock time this `probe_fidelity()` call took.
        warnings: Bounded diagnostic text that does not itself change
            status or reason (for example, captured child stderr after an
            unexplained crash).
    """

    executor_version: int
    status: str
    reason: str
    input_digest: str | None
    reconstructed_snapshot_json: str | None
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


def _failed_with_no_process(
    reason: str, elapsed_seconds: float, *, input_digest: str | None
) -> ExecutionReport:
    """Build a report for a failure discovered before any process spawned.

    Unlike `_rejected`, this reports `STATUS_FAILED`, not
    `STATUS_REJECTED`: it shares `REASON_SPAWN_OR_LOAD_FAILURE` with the
    case where a process was genuinely spawned but failed to load the
    snapshot inside the child, and that reason already means
    `STATUS_FAILED` there. `child_pid`/`child_terminated` are still both
    None -- no process was ever created for either case.

    Args:
        reason: The typed failure reason.
        elapsed_seconds: Time spent before the failure was discovered.
        input_digest: The request snapshot's structure digest.

    Returns:
        A report with `STATUS_FAILED` and no fingerprints, outcomes, or
        process evidence.
    """
    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_FAILED,
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


def _fidelity_rejected(
    reason: str,
    elapsed_seconds: float,
    *,
    input_digest: str | None = None,
) -> FidelityReport:
    """Build a report for a probe rejected before any process was spawned.

    The `FidelityReport` analogue of `_rejected`.

    Args:
        reason: The typed rejection reason.
        elapsed_seconds: Time spent validating the request.
        input_digest: The request snapshot's structure digest, when the
            snapshot at least parsed before rejection, else None.

    Returns:
        A report with `STATUS_REJECTED` and no reconstruction.
    """
    return FidelityReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_REJECTED,
        reason=reason,
        input_digest=input_digest,
        reconstructed_snapshot_json=None,
        child_pid=None,
        child_terminated=None,
        elapsed_seconds=elapsed_seconds,
        warnings=(),
    )


def _fidelity_failed_with_no_process(
    reason: str, elapsed_seconds: float, *, input_digest: str | None
) -> FidelityReport:
    """Build a report for a failure discovered before any process spawned.

    The `FidelityReport` analogue of `_failed_with_no_process`.

    Args:
        reason: The typed failure reason.
        elapsed_seconds: Time spent before the failure was discovered.
        input_digest: The request snapshot's structure digest.

    Returns:
        A report with `STATUS_FAILED` and no reconstruction or process
        evidence.
    """
    return FidelityReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_FAILED,
        reason=reason,
        input_digest=input_digest,
        reconstructed_snapshot_json=None,
        child_pid=None,
        child_terminated=None,
        elapsed_seconds=elapsed_seconds,
        warnings=(),
    )


def _close_pipe(pipe: IO[str] | None) -> None:
    """Close a `Popen` pipe object defensively.

    `stdout`/`stderr` are None whenever a caller does not pipe that stream,
    and may already be closed by the time this runs (`communicate()`
    closes both as a side effect). Closing an already-closed file object is
    a documented no-op, but the underlying OS handle can still raise on
    some platforms, so `OSError` is swallowed too: this runs from a
    `finally` whose whole purpose is cleanup, and raising here would
    replace -- not add to -- whatever is already in flight.

    Args:
        pipe: The pipe object to close, or None if that stream was never
            piped.
    """
    if pipe is None:
        return
    with contextlib.suppress(OSError):
        pipe.close()


def bounded_diagnostic(value: str, *, maximum_bytes: int) -> str:
    """Return diagnostic text bounded by its UTF-8 byte length.

    Non-whitespace control characters are replaced before truncation so a
    short in-memory value cannot expand sixfold when JSON escapes it. The
    truncation marker is included in the byte budget.

    Args:
        value: Diagnostic text to bound.
        maximum_bytes: Maximum size of the returned UTF-8 encoding.

    Returns:
        Sanitized text no larger than `maximum_bytes` in UTF-8.

    Raises:
        ValueError: If `maximum_bytes` cannot contain the truncation marker.
    """
    marker = _TRUNCATION_MARKER.encode("utf-8")
    if maximum_bytes < len(marker):
        raise ValueError("diagnostic byte limit is smaller than marker")
    sanitized = "".join(
        character
        if character in "\n\r\t"
        or (ord(character) >= 32 and ord(character) != 127)
        else "?"
        for character in value
    )
    encoded = sanitized.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return sanitized
    prefix = encoded[: maximum_bytes - len(marker)].decode(
        "utf-8", errors="ignore"
    )
    return prefix + _TRUNCATION_MARKER


def _stderr_warning(stderr: str) -> tuple[str, ...]:
    """Build the bounded warning tuple for captured child stderr.

    Args:
        stderr: Text captured from the child process.

    Returns:
        Empty when stderr is empty, otherwise one bounded warning.
    """
    if not stderr:
        return ()
    return (
        bounded_diagnostic(
            f"child stderr: {stderr}", maximum_bytes=MAX_WARNING_BYTES
        ),
    )


def _terminate(process: subprocess.Popen[str]) -> None:
    """Send a plain termination signal to a spawned child's process group.

    On POSIX, the child was spawned with `start_new_session=True`, so its
    process group ID equals its own PID and `os.killpg` reaches it and
    every descendant it may have spawned (PyMOL's own subprocesses, if
    any) in one call. Windows exposes no equivalent group-signal API in
    the standard library, so there this reaches only the child process
    itself; closing that gap would need Job Objects, out of scope here
    (H02-S3-F5).

    Args:
        process: The spawned child's `Popen` handle.
    """
    if sys.platform == "win32":
        process.terminate()
        return
    assert _killpg is not None
    assert _getpgid is not None
    with contextlib.suppress(ProcessLookupError):
        _killpg(_getpgid(process.pid), signal.SIGTERM)


def _kill(process: subprocess.Popen[str]) -> None:
    """Send a hard kill signal to a spawned child's whole process group.

    Falls back to killing the process alone when its group is already
    gone (it may have exited between the caller's own liveness check and
    this call) -- see `_terminate`'s own docstring for the same POSIX/
    Windows asymmetry.

    Args:
        process: The spawned child's `Popen` handle.
    """
    if sys.platform == "win32":
        process.kill()
        return
    assert _killpg is not None
    assert _getpgid is not None
    assert _SIGKILL is not None
    try:
        _killpg(_getpgid(process.pid), _SIGKILL)
    except ProcessLookupError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()


def _terminate_and_reap(process: subprocess.Popen[str]) -> None:
    """Ensure a spawned child is stopped, reaped, and its pipes closed.

    Safe -- and a near no-op -- when the child has already exited and been
    waited on, which is true on every one of `execute()`'s own documented
    return paths: `communicate()` itself already waits for the child, and
    the timeout branch already kills and drains before returning. This
    function's own terminate-and-wait branch exists for the one path none
    of those returns covers at all: an exception raised between `Popen`
    and `communicate()` -- for example, the test-only `on_process_spawned`
    hook itself raising -- which would otherwise leave the child neither
    terminated nor reaped while its scratch directory is deleted out from
    under it (H02-S3-F3).

    Args:
        process: The spawned child's `Popen` handle.
    """
    if process.poll() is None:
        _terminate(process)
        try:
            process.wait(timeout=DEFAULT_KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _kill(process)
            process.wait()
    _close_pipe(process.stdout)
    _close_pipe(process.stderr)


def _crashed(
    *,
    input_digest: str | None,
    child_pid: int,
    child_terminated: bool,
    elapsed_seconds: float,
    warnings: tuple[str, ...] = (),
) -> ExecutionReport:
    """Build a report for a child that produced no trustworthy evidence.

    Covers both a child that exited without ever writing an output file,
    and one that wrote output this module cannot parse as a well-formed
    report -- corrupt JSON, a non-object payload, or one missing a
    required key. Both mean the same thing to a caller: this attempt
    produced nothing safe to trust, and REASON_CHILD_CRASH covers both
    rather than letting the parse failure escape as an unhandled
    exception (execute() itself never raises for its own documented
    failure modes).

    Args:
        input_digest: The request snapshot's structure digest.
        child_pid: The spawned child's OS process ID.
        child_terminated: Whether the child was confirmed no longer
            running by the time this report is built.
        elapsed_seconds: Wall-clock time this execute() call took.
        warnings: Bounded diagnostic text, such as captured child stderr.

    Returns:
        A report with STATUS_FAILED and REASON_CHILD_CRASH.
    """
    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_FAILED,
        reason=REASON_CHILD_CRASH,
        input_digest=input_digest,
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(),
        child_pid=child_pid,
        child_terminated=child_terminated,
        elapsed_seconds=elapsed_seconds,
        warnings=warnings,
    )


def _fidelity_crashed(
    *,
    input_digest: str | None,
    child_pid: int,
    child_terminated: bool,
    elapsed_seconds: float,
    warnings: tuple[str, ...] = (),
) -> FidelityReport:
    """Build a report for a child that produced no trustworthy evidence.

    The `FidelityReport` analogue of `_crashed`.

    Args:
        input_digest: The request snapshot's structure digest.
        child_pid: The spawned child's OS process ID.
        child_terminated: Whether the child was confirmed no longer
            running by the time this report is built.
        elapsed_seconds: Wall-clock time this probe_fidelity() call took.
        warnings: Bounded diagnostic text, such as captured child stderr.

    Returns:
        A report with STATUS_FAILED and REASON_CHILD_CRASH.
    """
    return FidelityReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_FAILED,
        reason=REASON_CHILD_CRASH,
        input_digest=input_digest,
        reconstructed_snapshot_json=None,
        child_pid=child_pid,
        child_terminated=child_terminated,
        elapsed_seconds=elapsed_seconds,
        warnings=warnings,
    )


@dataclass(frozen=True)
class _ChildAttempt:
    """The generic result of one spawn-deadline-reap attempt.

    Shared by `execute()` and `probe_fidelity()` through `_run_child()`,
    which owns every process-management guarantee the two entry points
    have in common; each caller still maps this generic result to its own
    report type.

    Attributes:
        reason: A fixed `REASON_*` constant this attempt already resolved
            on its own -- a pre-spawn I/O failure writing inputs, a spawn
            failure, a wall-clock timeout, or a crash (no output file, or
            output this module could not even parse as JSON) -- or None
            when the child exited within its deadline and wrote JSON this
            module could decode, leaving `payload`'s own "status" and
            "reason" fields for the caller to interpret against its own
            report type.
        payload: The child's decoded JSON output as a plain dict, set
            exactly when `reason` is None.
        child_pid: The spawned child's OS process ID, or None when no
            process was ever created (every reason fixed before `Popen`).
        child_terminated: Whether the child was confirmed no longer
            running by the time this attempt returned. None exactly when
            `child_pid` is None.
        elapsed_seconds: Wall-clock time this attempt took, from the
            caller's own `start`.
        warnings: Bounded diagnostic text, such as captured child stderr.
            Present whenever stderr was captured, whether or not the
            caller's own further field extraction from `payload` ends up
            needing it.
    """

    reason: str | None
    payload: dict[str, Any] | None
    child_pid: int | None
    child_terminated: bool | None
    elapsed_seconds: float
    warnings: tuple[str, ...]


def _run_child(
    *,
    runner_module: str,
    write_inputs: Callable[[Path], tuple[Path, ...]],
    deadline_seconds: float,
    start: float,
    on_process_spawned: Callable[[subprocess.Popen[str]], None] | None,
) -> _ChildAttempt:
    """Spawn one fresh child, give it a deadline, and reap it.

    Owns every process-management guarantee `execute()` and
    `probe_fidelity()` share, assuming each caller's own pre-spawn request
    validation already passed: preflighting `runner_module` via
    `importlib.util.find_spec`, a disposable scratch directory removed on
    every exit path, process-group spawn and SIGTERM/SIGKILL teardown, the
    wall-clock deadline with a bounded post-kill drain, and reading the
    child's single JSON output file. Each caller still performs its own
    mapping from the returned generic result -- a fixed failure reason, or
    a raw decoded payload whose own "status"/"reason" fields (and whatever
    else that caller's report type needs) it must extract itself -- to its
    own report type.

    Args:
        runner_module: The child module to spawn by name
            (`python -m <runner_module>`), never by import.
        write_inputs: Called with the fresh scratch directory; writes
            whatever input files the child needs and returns their paths,
            in the order they should appear on the child's command line
            before the one output-path argument this function appends
            itself. Raising `OSError` here is treated the same as any
            other pre-spawn I/O failure.
        deadline_seconds: The wall-clock deadline for the whole spawned
            child process.
        start: `time.monotonic()` at the caller's own attempt start, so
            `elapsed_seconds` covers validation time too.
        on_process_spawned: The test-only hook, forwarded unchanged.

    Returns:
        The generic result of this attempt. Never raises for any of this
        module's own documented failure modes.
    """
    try:
        spec_found = importlib.util.find_spec(runner_module) is not None
    except (
        ImportError,
        ValueError,
        ModuleNotFoundError,
        AttributeError,
        OSError,
    ):
        spec_found = False
    if not spec_found:
        return _ChildAttempt(
            reason=REASON_SPAWN_OR_LOAD_FAILURE,
            payload=None,
            child_pid=None,
            child_terminated=None,
            elapsed_seconds=time.monotonic() - start,
            warnings=(),
        )

    try:
        scratch_dir = Path(tempfile.mkdtemp(prefix=SCRATCH_DIR_PREFIX))
    except OSError:
        return _ChildAttempt(
            reason=REASON_SPAWN_OR_LOAD_FAILURE,
            payload=None,
            child_pid=None,
            child_terminated=None,
            elapsed_seconds=time.monotonic() - start,
            warnings=(),
        )
    try:
        try:
            input_paths = write_inputs(scratch_dir)
        except OSError:
            return _ChildAttempt(
                reason=REASON_SPAWN_OR_LOAD_FAILURE,
                payload=None,
                child_pid=None,
                child_terminated=None,
                elapsed_seconds=time.monotonic() - start,
                warnings=(),
            )
        output_path = scratch_dir / "output.json"

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(path for path in sys.path if path)

        # Puts the child in its own process group (POSIX) or its own
        # process-group ID (Windows), so _terminate/_kill can reach it and
        # any descendant it spawns, not just the immediate child -- see
        # their own docstrings for the platform asymmetry this leaves.
        creation_flags = 0
        start_new_session = False
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            start_new_session = True

        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    runner_module,
                    *(str(path) for path in input_paths),
                    str(output_path),
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation_flags,
                start_new_session=start_new_session,
            )
        except (OSError, ValueError):
            return _ChildAttempt(
                reason=REASON_SPAWN_OR_LOAD_FAILURE,
                payload=None,
                child_pid=None,
                child_terminated=None,
                elapsed_seconds=time.monotonic() - start,
                warnings=(),
            )
        child_pid = process.pid
        try:
            if on_process_spawned is not None:
                on_process_spawned(process)

            try:
                _stdout, stderr = process.communicate(timeout=deadline_seconds)
            except subprocess.TimeoutExpired:
                # Hard kill, then best-effort drain: the guaranteed reap
                # happens in the outer finally's _terminate_and_reap
                # regardless of whether this drain itself times out.
                _kill(process)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.communicate(timeout=DEFAULT_KILL_GRACE_SECONDS)
                return _ChildAttempt(
                    reason=REASON_TIMEOUT,
                    payload=None,
                    child_pid=child_pid,
                    child_terminated=process.poll() is not None,
                    elapsed_seconds=time.monotonic() - start,
                    warnings=(),
                )

            if not output_path.exists():
                # The child never reached its own output write -- a crash
                # rather than a reported failure. communicate() above
                # already waited for it, so it is reaped either way.
                return _ChildAttempt(
                    reason=REASON_CHILD_CRASH,
                    payload=None,
                    child_pid=child_pid,
                    child_terminated=process.poll() is not None,
                    elapsed_seconds=time.monotonic() - start,
                    warnings=_stderr_warning(stderr),
                )

            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeError, OSError):
                payload = None
            if not isinstance(payload, dict):
                # The output file exists but is not readable/parseable
                # JSON, or is syntactically valid JSON that is not even an
                # object (for example a bare `null`, simulating a crash
                # mid-write) -- exactly as untrustworthy as no output file
                # at all. A well-formed object that is still missing an
                # expected key is not this module's concern: each caller
                # extracts its own report-specific fields from `payload`
                # and treats that failure the same way.
                return _ChildAttempt(
                    reason=REASON_CHILD_CRASH,
                    payload=None,
                    child_pid=child_pid,
                    child_terminated=process.poll() is not None,
                    elapsed_seconds=time.monotonic() - start,
                    warnings=_stderr_warning(stderr),
                )

            return _ChildAttempt(
                reason=None,
                payload=payload,
                child_pid=child_pid,
                child_terminated=process.poll() is not None,
                elapsed_seconds=time.monotonic() - start,
                warnings=_stderr_warning(stderr),
            )
        finally:
            # H02-S3-F3: guarantee the child is terminated and reaped
            # before the outer finally below deletes the scratch directory
            # it may still be reading from -- including the exception path
            # between Popen and communicate() (for example,
            # on_process_spawned itself raising), which none of the
            # returns above run at all.
            _terminate_and_reap(process)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def execute(
    request: ExecutionRequest,
    *,
    runner_module: str = "pmc_sidecar.child",
    on_process_spawned: Callable[[subprocess.Popen[str]], None] | None = None,
) -> ExecutionReport:
    """Validate a request and execute its plan in a fresh sidecar process.

    Validates the request in this process first, in a fixed order: an
    unsupported request version, an oversized snapshot, malformed or
    version-mismatched snapshot JSON, a mismatched plan/snapshot digest,
    and a plan the default-deny policy denies are all rejected here, with
    no process ever spawned and no scratch data ever written. Only a request
    that passes every check spawns a fresh child, gives it
    request.deadline_seconds to run, and reaps it -- on every exit path,
    including timeout, an unhandled crash, and an exception raised between
    spawn and the child's own completion -- with its scratch directory
    removed only after that termination and reap.

    Args:
        request: The execution request to run.
        runner_module: The child module to spawn by name
            (`python -m <runner_module>`), never by import. Overridable so
            a test can spawn a sabotage runner instead of the production
            `pmc_sidecar.child` without this module ever importing it.
        on_process_spawned: An optional test-only hook invoked with the
            spawned child's `subprocess.Popen` handle immediately after it
            is created, so a sabotage test can independently confirm the
            process is later reaped and no longer running. Never used by
            `execute()` itself for anything but this notification.

    Returns:
        The execution report. Never raises for any of this module's own
        documented failure modes; every one of them is reported through the
        returned report's status/reason instead.
    """
    start = time.monotonic()

    if request.executor_version != EXECUTOR_VERSION:
        return _rejected(
            REASON_UNSUPPORTED_SCHEMA_VERSION, time.monotonic() - start
        )

    try:
        encoded_snapshot = request.snapshot_json.encode("utf-8")
    except UnicodeEncodeError:
        return _rejected(REASON_MALFORMED_INPUT, time.monotonic() - start)
    if len(encoded_snapshot) > request.max_snapshot_bytes:
        return _rejected(REASON_OVERSIZED_INPUT, time.monotonic() - start)

    try:
        snapshot = from_json(request.snapshot_json)
    except json.JSONDecodeError:
        return _rejected(REASON_MALFORMED_INPUT, time.monotonic() - start)
    except SnapshotDecodeError:
        # SnapshotDecodeError is reserved for recognized-but-unsupported
        # schema declarations. Other ValueErrors from malformed field shapes
        # belong to the malformed-input branch below.
        return _rejected(
            REASON_UNSUPPORTED_SCHEMA_VERSION, time.monotonic() - start
        )
    except (KeyError, AttributeError, TypeError, ValueError):
        # Syntactically valid JSON that from_json cannot treat as a
        # snapshot object at all -- a bare scalar/array/string (whose
        # .get("schema_version") raises AttributeError) or a JSON object
        # missing a required key (KeyError) -- is malformed input, not an
        # unsupported-but-recognized schema version.
        return _rejected(REASON_MALFORMED_INPUT, time.monotonic() - start)

    try:
        input_digest = structure_digest(snapshot)
    except ValueError:
        # structure_digest documents raising ValueError for a NaN or
        # infinite float field -- from_json performs no numeric-range
        # validation of its own, so a snapshot with such a value survives
        # parsing and only fails here. Not a valid finite structure, so
        # this is malformed input, not a process-worthy request.
        return _rejected(REASON_MALFORMED_INPUT, time.monotonic() - start)

    if (
        request.expected_snapshot_digest is not None
        and input_digest != request.expected_snapshot_digest
    ):
        return _rejected(
            REASON_SNAPSHOT_DIGEST_MISMATCH,
            time.monotonic() - start,
            input_digest=input_digest,
        )

    if not evaluate_plan(request.plan).allowed:
        return _rejected(
            REASON_POLICY_DENIED,
            time.monotonic() - start,
            input_digest=input_digest,
        )

    def write_inputs(scratch_dir: Path) -> tuple[Path, ...]:
        """Write this request's snapshot and plan into the scratch dir.

        Args:
            scratch_dir: The fresh, disposable scratch directory.

        Returns:
            The snapshot and plan paths, in the order the child expects
            them on its command line.
        """
        snapshot_path = scratch_dir / "snapshot.json"
        plan_path = scratch_dir / "plan.json"
        snapshot_path.write_text(request.snapshot_json, encoding="utf-8")
        plan_path.write_text(
            json.dumps(
                {
                    "planId": str(uuid.uuid4()),
                    "planVersion": PROTOCOL_VERSION,
                    "snapshotDigest": input_digest,
                    "commands": encode_plan(request.plan),
                }
            ),
            encoding="utf-8",
        )
        return (snapshot_path, plan_path)

    result = _run_child(
        runner_module=runner_module,
        write_inputs=write_inputs,
        deadline_seconds=request.deadline_seconds,
        start=start,
        on_process_spawned=on_process_spawned,
    )

    if result.reason is not None and result.child_pid is None:
        return _failed_with_no_process(
            result.reason, result.elapsed_seconds, input_digest=input_digest
        )
    # _run_child()'s own contract: child_pid/child_terminated are both None
    # only for the "no process" case just ruled out above -- every attempt
    # that reached Popen sets both.
    assert result.child_pid is not None
    assert result.child_terminated is not None
    if result.reason == REASON_TIMEOUT:
        return ExecutionReport(
            executor_version=EXECUTOR_VERSION,
            status=STATUS_FAILED,
            reason=REASON_TIMEOUT,
            input_digest=input_digest,
            resulting_fingerprint=None,
            selection_counts=(),
            command_outcomes=(),
            child_pid=result.child_pid,
            child_terminated=result.child_terminated,
            elapsed_seconds=result.elapsed_seconds,
            warnings=(),
        )
    if result.reason == REASON_CHILD_CRASH:
        return _crashed(
            input_digest=input_digest,
            child_pid=result.child_pid,
            child_terminated=result.child_terminated,
            elapsed_seconds=result.elapsed_seconds,
            warnings=result.warnings,
        )

    # _run_child()'s own contract: reason is None only when payload was
    # decoded successfully, and the three reason values ruled out above are
    # the only ones it ever returns.
    assert result.payload is not None
    payload = result.payload
    try:
        command_outcomes = tuple(
            CommandOutcome(
                index=outcome["index"],
                verb=outcome["verb"],
                status=outcome["status"],
                error=(
                    bounded_diagnostic(
                        outcome["error"],
                        maximum_bytes=MAX_COMMAND_ERROR_BYTES,
                    )
                    if outcome.get("error") is not None
                    else None
                ),
            )
            for outcome in payload.get("command_outcomes", [])
        )
        selection_counts = tuple(
            SelectionCount(name=item["name"], atom_count=item["atom_count"])
            for item in payload.get("selection_counts", [])
        )
        resulting_fingerprint = payload.get("resulting_fingerprint")
        status = payload["status"]
        reason = payload["reason"]
        if (
            not isinstance(status, str)
            or status not in (STATUS_OK, STATUS_FAILED)
            or not isinstance(reason, str)
            or reason
            not in (
                REASON_OK,
                REASON_SPAWN_OR_LOAD_FAILURE,
                REASON_COMMAND_FAILURE,
            )
            or (status == STATUS_OK) != (reason == REASON_OK)
            or (
                resulting_fingerprint is not None
                and not isinstance(resulting_fingerprint, str)
            )
        ):
            raise TypeError("child report fields violate their contract")
    except (KeyError, TypeError, AttributeError):
        # payload structurally does not match the well-formed report this
        # module's own child always writes, or its scalar fields violate
        # their types/invariants -- as untrustworthy as no output file at
        # all. _run_child() already guarantees payload is at least
        # syntactically valid JSON by the time reason is None.
        return _crashed(
            input_digest=input_digest,
            child_pid=result.child_pid,
            child_terminated=result.child_terminated,
            elapsed_seconds=result.elapsed_seconds,
            warnings=result.warnings,
        )

    if (
        status == STATUS_OK
        and request.expected_resulting_fingerprint is not None
        and resulting_fingerprint != request.expected_resulting_fingerprint
    ):
        status = STATUS_FAILED
        reason = REASON_FIDELITY_MISMATCH

    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status=status,
        reason=reason,
        input_digest=input_digest,
        resulting_fingerprint=resulting_fingerprint,
        selection_counts=selection_counts,
        command_outcomes=command_outcomes,
        child_pid=result.child_pid,
        child_terminated=result.child_terminated,
        elapsed_seconds=result.elapsed_seconds,
        warnings=(),
    )


def probe_fidelity(
    request: FidelityRequest,
    *,
    runner_module: str = "pmc_sidecar.fidelity",
    on_process_spawned: Callable[[subprocess.Popen[str]], None] | None = None,
) -> FidelityReport:
    """Validate a request and reconstruct its snapshot in a fresh sidecar.

    Validates the request in this process first, in a fixed order: an
    unsupported request version, an oversized snapshot, and malformed or
    version-mismatched snapshot JSON are all rejected here, with no process
    ever spawned and no scratch data ever written. Unlike `execute()`,
    there is no plan to check a digest or policy against -- a fidelity
    probe carries no plan at all. Only a request that passes every check
    spawns a fresh child, gives it request.deadline_seconds to run, and
    reaps it -- on every exit path, including timeout, an unhandled crash,
    and an exception raised between spawn and the child's own completion --
    with its scratch directory removed only after that termination and
    reap.

    This function computes no diff of its own: it never holds the live
    snapshot being compared against, only the candidate the caller supplies
    and the child's own re-extraction of what it reconstructed from that
    candidate. A caller judges fidelity by running
    `pmc_core.snapshot.diff` between the two.

    Args:
        request: The fidelity request to run.
        runner_module: The child module to spawn by name
            (`python -m <runner_module>`), never by import. Overridable so
            a test can spawn a sabotage runner instead of the production
            `pmc_sidecar.fidelity` without this module ever importing it.
        on_process_spawned: An optional test-only hook invoked with the
            spawned child's `subprocess.Popen` handle immediately after it
            is created, so a sabotage test can independently confirm the
            process is later reaped and no longer running. Never used by
            `probe_fidelity()` itself for anything but this notification.

    Returns:
        The fidelity report. Never raises for any of this module's own
        documented failure modes; every one of them is reported through the
        returned report's status/reason instead.
    """
    start = time.monotonic()

    if request.executor_version != EXECUTOR_VERSION:
        return _fidelity_rejected(
            REASON_UNSUPPORTED_SCHEMA_VERSION, time.monotonic() - start
        )

    try:
        encoded_snapshot = request.snapshot_json.encode("utf-8")
    except UnicodeEncodeError:
        return _fidelity_rejected(
            REASON_MALFORMED_INPUT, time.monotonic() - start
        )
    if len(encoded_snapshot) > request.max_snapshot_bytes:
        return _fidelity_rejected(
            REASON_OVERSIZED_INPUT, time.monotonic() - start
        )

    try:
        snapshot = from_json(request.snapshot_json)
    except json.JSONDecodeError:
        return _fidelity_rejected(
            REASON_MALFORMED_INPUT, time.monotonic() - start
        )
    except SnapshotDecodeError:
        # SnapshotDecodeError is reserved for recognized-but-unsupported
        # schema declarations. Other ValueErrors from malformed field shapes
        # belong to the malformed-input branch below.
        return _fidelity_rejected(
            REASON_UNSUPPORTED_SCHEMA_VERSION, time.monotonic() - start
        )
    except (KeyError, AttributeError, TypeError, ValueError):
        # Syntactically valid JSON that from_json cannot treat as a
        # snapshot object at all -- a bare scalar/array/string (whose
        # .get("schema_version") raises AttributeError) or a JSON object
        # missing a required key (KeyError) -- is malformed input, not an
        # unsupported-but-recognized schema version.
        return _fidelity_rejected(
            REASON_MALFORMED_INPUT, time.monotonic() - start
        )

    try:
        input_digest = structure_digest(snapshot)
    except ValueError:
        # structure_digest documents raising ValueError for a NaN or
        # infinite float field -- from_json performs no numeric-range
        # validation of its own, so a snapshot with such a value survives
        # parsing and only fails here. Not a valid finite structure, so
        # this is malformed input, not a process-worthy request.
        return _fidelity_rejected(
            REASON_MALFORMED_INPUT, time.monotonic() - start
        )

    def write_inputs(scratch_dir: Path) -> tuple[Path, ...]:
        """Write this request's snapshot into the scratch dir.

        Args:
            scratch_dir: The fresh, disposable scratch directory.

        Returns:
            The snapshot path, the only argument the fidelity child
            expects before the shared output-path argument.
        """
        snapshot_path = scratch_dir / "snapshot.json"
        snapshot_path.write_text(request.snapshot_json, encoding="utf-8")
        return (snapshot_path,)

    result = _run_child(
        runner_module=runner_module,
        write_inputs=write_inputs,
        deadline_seconds=request.deadline_seconds,
        start=start,
        on_process_spawned=on_process_spawned,
    )

    if result.reason is not None and result.child_pid is None:
        return _fidelity_failed_with_no_process(
            result.reason, result.elapsed_seconds, input_digest=input_digest
        )
    # _run_child()'s own contract: child_pid/child_terminated are both None
    # only for the "no process" case just ruled out above -- every attempt
    # that reached Popen sets both.
    assert result.child_pid is not None
    assert result.child_terminated is not None
    if result.reason == REASON_TIMEOUT:
        return FidelityReport(
            executor_version=EXECUTOR_VERSION,
            status=STATUS_FAILED,
            reason=REASON_TIMEOUT,
            input_digest=input_digest,
            reconstructed_snapshot_json=None,
            child_pid=result.child_pid,
            child_terminated=result.child_terminated,
            elapsed_seconds=result.elapsed_seconds,
            warnings=(),
        )
    if result.reason == REASON_CHILD_CRASH:
        return _fidelity_crashed(
            input_digest=input_digest,
            child_pid=result.child_pid,
            child_terminated=result.child_terminated,
            elapsed_seconds=result.elapsed_seconds,
            warnings=result.warnings,
        )

    # _run_child()'s own contract: reason is None only when payload was
    # decoded successfully, and the three reason values ruled out above are
    # the only ones it ever returns.
    assert result.payload is not None
    payload = result.payload
    try:
        status = payload["status"]
        reason = payload["reason"]
        reconstructed_snapshot_json = payload.get("reconstructed_snapshot_json")
    except (KeyError, TypeError, AttributeError):
        # payload structurally does not match the well-formed report this
        # module's own fidelity child always writes -- as untrustworthy as
        # no output file at all.
        return _fidelity_crashed(
            input_digest=input_digest,
            child_pid=result.child_pid,
            child_terminated=result.child_terminated,
            elapsed_seconds=result.elapsed_seconds,
            warnings=result.warnings,
        )

    return FidelityReport(
        executor_version=EXECUTOR_VERSION,
        status=status,
        reason=reason,
        input_digest=input_digest,
        reconstructed_snapshot_json=reconstructed_snapshot_json,
        child_pid=result.child_pid,
        child_terminated=result.child_terminated,
        elapsed_seconds=result.elapsed_seconds,
        warnings=(),
    )
