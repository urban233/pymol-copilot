# Copyright 2026 PyMOL Copilot contributors.
"""Real-process evidence for pmc_core.executor.execute()'s failure modes.

Each sabotage test below targets exactly one of the fail-closed modes
docs/master_plan.md item 4 requires -- spawn failure, a wall-clock
timeout, a forced child crash, a failing command with no internal retry,
and a fidelity mismatch -- and asserts a typed `reason` (never a raw
exception string), no internal retry, no live child process left behind,
and no scratch data left behind.

Two genuinely different children are spawned across this file:

- `spawn_or_load_failure` and `fidelity_mismatch` spawn the real,
  production `src/pmc_sidecar/child.py`, exactly as a real caller would.
  tests/integration/test_sidecar_child.py already proves that module's own
  closed dispatch against real PyMOL in detail; here it is only the
  boundary around it -- reap, cleanup, fidelity adjudication -- under
  test.
- Every other test spawns `sabotage_child.py`, this directory's own
  test-owned child (see its module docstring for why a genuine PyMOL
  command failure cannot reach the strict `pmc_core.protocol.decode_plan`
  wire this boundary uses, and how the sabotage child sidesteps that
  without weakening the wire's own re-validation).

`_assert_process_not_running`'s POSIX-only `os.kill(pid, 0)` probe and its
Windows caveat are ported verbatim from the H-02 prototype's own sabotage
suite (`tests/discovery/h02/test_execution_boundary.py`), including the
rationale for asserting `stdout`/`stderr` are closed rather than relying
on `filterwarnings = ["error"]` to catch a leaked pipe.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from pmc_core.executor import REASON_CHILD_CRASH
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_FIDELITY_MISMATCH
from pmc_core.executor import REASON_SPAWN_OR_LOAD_FAILURE
from pmc_core.executor import REASON_TIMEOUT
from pmc_core.executor import SCRATCH_DIR_PREFIX
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import MAX_COMMAND_ERROR_BYTES
from pmc_core.executor import MAX_WARNING_BYTES
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import execute
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import Factor
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectionExpression
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot
from pmc_core.snapshot import to_json

from sabotage_child import SABOTAGE_MODE_ENV_VAR

#: A real 18-float PyMOL view matrix. reconstruct() calls cmd.set_view()
#: unconditionally, which rejects an empty tuple -- unlike the zero-atom
#: snapshots tests/contract/test_executor.py uses, every snapshot in this
#: file is reconstructed by a genuinely spawned real PyMOL child.
_IDENTITY_VIEW = (
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    -0.5,
    0.5,
    -20.0,
)

#: The module name this test's own sabotage child is spawned by. Bazel's
#: py_library `imports = ["."]` puts this directory on the child's own
#: PYTHONPATH the same way it puts src/pmc_sidecar on it for the real one.
_SABOTAGE_RUNNER = "sabotage_child"


def chain_a() -> SelectionExpression:
    """Build the expression `chain A`.

    Returns:
        A one-term expression matching chain A.
    """
    return SelectionExpression(
        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
    )


def _valid_plan() -> ActionPlan:
    """Build a plan that the default-deny policy allows.

    Returns:
        A one-command plan every field of which is within its allowlist.
    """
    return ActionPlan(operations=(OrientOperation(target=chain_a()),))


def _one_atom_snapshot() -> ObjectSnapshot:
    """Build the smallest snapshot with at least one real atom.

    Returns:
        A one-atom, one-state snapshot -- enough for reconstruct() to
        attempt real work, unlike the zero-atom snapshots the parent-side
        validation tests use.
    """
    atom = AtomRecord(
        serial=1,
        name="CA",
        alt="",
        resn="ALA",
        chain="A",
        resv=1,
        ins_code="",
        elem="C",
        hetatm=False,
        q=1.0,
        b=0.0,
        color=0,
        reps=(),
        label=None,
        coord=(0.0, 0.0, 0.0),
    )
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="fx",
        enabled=True,
        states=(StateSnapshot(atoms=(atom,)),),
        bonds=(),
        view=_IDENTITY_VIEW,
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )


def _base_request(**overrides: Any) -> ExecutionRequest:
    """Build a well-formed ExecutionRequest, with fields overridden.

    Args:
        **overrides: Fields to override on the well-formed default.

    Returns:
        The constructed ExecutionRequest.
    """
    fields: dict[str, Any] = {
        "executor_version": EXECUTOR_VERSION,
        "plan": _valid_plan(),
        "snapshot_json": to_json(_one_atom_snapshot()),
        "deadline_seconds": 30.0,
    }
    fields.update(overrides)
    return ExecutionRequest(**fields)


def _scratch_dirs() -> set[Path]:
    """Every executor scratch directory currently on disk.

    Returns:
        The set of matching paths under the system temp directory.
    """
    return set(Path(tempfile.gettempdir()).glob(f"{SCRATCH_DIR_PREFIX}*"))


def _assert_process_not_running(process: subprocess.Popen[str]) -> None:
    """Assert a spawned child process was reaped and is no longer alive.

    `process.poll() is not None` alone already proves the child was reaped
    on every platform. On POSIX, this goes further: `os.kill(pid, 0)`
    raising `ProcessLookupError` proves the kernel itself has no process
    table entry for that PID anymore. That second check has no reliable
    Windows equivalent -- Windows recycles PIDs aggressively enough that
    probing a reaped PID could pass spuriously against an unrelated
    process that has since reused it -- so on Windows this relies on
    `poll()` alone, ported verbatim from the H-02 prototype's own
    sabotage suite.

    Args:
        process: The Popen handle captured via `on_process_spawned`.
    """
    assert process.poll() is not None, "child process was not reaped"
    if sys.platform != "win32":
        with pytest.raises(ProcessLookupError):
            os.kill(process.pid, 0)
    assert process.stdout is not None and process.stdout.closed
    assert process.stderr is not None and process.stderr.closed


def test_spawn_or_load_failure_fails_closed_with_no_leak() -> None:
    """A snapshot surviving parsing but not reconstruction fails closed."""
    payload = json.loads(to_json(_one_atom_snapshot()))
    # Survives from_json (the dataclass performs no type validation on its
    # own field contents) but PyMOL's own pseudoatom rejects a non-numeric
    # position when the real child calls pmc_core.snapshot.reconstruct().
    payload["states"][0]["atoms"][0]["coord"] = ["a", "b", "c"]
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []

    report = execute(
        _base_request(snapshot_json=json.dumps(payload)),
        on_process_spawned=spawned.append,
    )

    assert report.status == STATUS_FAILED
    assert report.reason == REASON_SPAWN_OR_LOAD_FAILURE
    assert report.command_outcomes == ()
    assert report.resulting_fingerprint is None
    assert len(spawned) == 1
    assert report.child_pid == spawned[0].pid
    assert report.child_terminated is True
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_wall_clock_timeout_is_hard_killed_and_reaped() -> None:
    """A child that outlives its deadline is hard-killed, not awaited."""
    sleep_seconds = 30.0
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []
    os.environ[SABOTAGE_MODE_ENV_VAR] = f"sleep:{sleep_seconds}"
    try:
        report = execute(
            _base_request(deadline_seconds=1.0),
            runner_module=_SABOTAGE_RUNNER,
            on_process_spawned=spawned.append,
        )
    finally:
        del os.environ[SABOTAGE_MODE_ENV_VAR]

    assert report.status == STATUS_FAILED
    assert report.reason == REASON_TIMEOUT
    assert report.command_outcomes == ()
    assert report.resulting_fingerprint is None
    # A hard kill, not "wait for the sleep to finish": elapsed time stays
    # well under the sleep duration even though it exceeds the deadline.
    assert report.elapsed_seconds < sleep_seconds
    assert len(spawned) == 1
    assert report.child_pid == spawned[0].pid
    assert report.child_terminated is True
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_forced_child_crash_leaves_no_live_process_or_scratch_data() -> None:
    """A child exiting without writing output is a crash, not a hang."""
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []
    os.environ[SABOTAGE_MODE_ENV_VAR] = "crash"
    try:
        report = execute(
            _base_request(),
            runner_module=_SABOTAGE_RUNNER,
            on_process_spawned=spawned.append,
        )
    finally:
        del os.environ[SABOTAGE_MODE_ENV_VAR]

    assert report.status == STATUS_FAILED
    assert report.reason == REASON_CHILD_CRASH
    assert report.command_outcomes == ()
    assert report.resulting_fingerprint is None
    assert len(spawned) == 1
    assert report.child_pid == spawned[0].pid
    assert report.child_terminated is True
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_child_crash_stderr_is_bounded() -> None:
    """A chatty crashing child cannot inflate the typed report."""
    os.environ[SABOTAGE_MODE_ENV_VAR] = "stderr_crash:100000"
    try:
        report = execute(_base_request(), runner_module=_SABOTAGE_RUNNER)
    finally:
        del os.environ[SABOTAGE_MODE_ENV_VAR]

    assert report.reason == REASON_CHILD_CRASH
    assert len(report.warnings) == 1
    assert len(report.warnings[0].encode("utf-8")) <= MAX_WARNING_BYTES
    assert report.warnings[0].endswith("...[truncated]")


def test_malformed_child_output_fails_closed_like_a_crash() -> None:
    """A child that writes garbage instead of a report is a crash too.

    Distinct from `test_forced_child_crash_leaves_no_live_process_or_
    scratch_data` above: that child writes no output file at all, while
    this one writes a syntactically valid JSON value that is not the
    well-formed report `execute()` expects (simulating a crash mid-write,
    or a corrupt write). Both must fail closed with a typed reason rather
    than let a parse exception escape `execute()` itself.
    """
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []
    os.environ[SABOTAGE_MODE_ENV_VAR] = "malformed_output"
    try:
        report = execute(
            _base_request(),
            runner_module=_SABOTAGE_RUNNER,
            on_process_spawned=spawned.append,
        )
    finally:
        del os.environ[SABOTAGE_MODE_ENV_VAR]

    assert report.status == STATUS_FAILED
    assert report.reason == REASON_CHILD_CRASH
    assert report.command_outcomes == ()
    assert report.resulting_fingerprint is None
    assert len(spawned) == 1
    assert report.child_pid == spawned[0].pid
    assert report.child_terminated is True
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


@pytest.mark.parametrize(
    "payload",
    [
        {
            "status": 1,
            "reason": "ok",
            "resulting_fingerprint": None,
            "command_outcomes": [],
            "selection_counts": [],
        },
        {
            "status": "ok",
            "reason": 1,
            "resulting_fingerprint": None,
            "command_outcomes": [],
            "selection_counts": [],
        },
        {
            "status": "ok",
            "reason": "ok",
            "resulting_fingerprint": 42,
            "command_outcomes": [],
            "selection_counts": [],
        },
        {
            "status": "ok",
            "reason": "policy_denied",
            "resulting_fingerprint": None,
            "command_outcomes": [],
            "selection_counts": [],
        },
    ],
    ids=[
        "non-string-status",
        "non-string-reason",
        "non-string-fingerprint",
        "inconsistent-status-and-reason",
    ],
)
def test_untrustworthy_child_report_fields_fail_closed_like_a_crash(
    payload: dict[str, object],
) -> None:
    """Invalid scalar fields cannot escape in a nominal report.

    Args:
        payload: The otherwise well-shaped sabotage report to write.
    """
    scratch_before = _scratch_dirs()
    os.environ[SABOTAGE_MODE_ENV_VAR] = "report:" + json.dumps(payload)
    try:
        report = execute(_base_request(), runner_module=_SABOTAGE_RUNNER)
    finally:
        del os.environ[SABOTAGE_MODE_ENV_VAR]

    assert report.status == STATUS_FAILED
    assert report.reason == REASON_CHILD_CRASH
    assert report.command_outcomes == ()
    assert report.selection_counts == ()
    assert report.resulting_fingerprint is None
    assert report.child_terminated is True
    assert _scratch_dirs() == scratch_before


def test_child_that_escapes_before_communicate_is_terminated_and_reaped() -> (
    None
):
    """The one exception window between Popen and communicate() still reaps.

    `on_process_spawned` is the only hook execute() invokes between Popen
    and communicate(); making it raise reproduces exactly the exception
    window H02-S3-F3 described, where the child was previously left
    neither terminated nor reaped while its scratch directory was deleted
    out from under it.
    """
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []

    def _escape(process: subprocess.Popen[str]) -> None:
        spawned.append(process)
        raise RuntimeError("simulated escape between spawn and communicate")

    os.environ[SABOTAGE_MODE_ENV_VAR] = "sleep:30"
    try:
        with pytest.raises(RuntimeError, match="simulated escape"):
            execute(
                _base_request(),
                runner_module=_SABOTAGE_RUNNER,
                on_process_spawned=_escape,
            )
    finally:
        del os.environ[SABOTAGE_MODE_ENV_VAR]

    assert len(spawned) == 1
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_command_failure_stops_with_no_second_command_attempted() -> None:
    """A reported command failure is one outcome, nothing attempted after."""
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []
    with tempfile.TemporaryDirectory(
        prefix="pmc-attempt-counter-"
    ) as counter_dir:
        counter_path = Path(counter_dir) / "attempts.txt"
        os.environ[SABOTAGE_MODE_ENV_VAR] = f"count_then_fail:{counter_path}"
        try:
            report = execute(
                _base_request(),
                runner_module=_SABOTAGE_RUNNER,
                on_process_spawned=spawned.append,
            )
        finally:
            del os.environ[SABOTAGE_MODE_ENV_VAR]

    assert report.status == STATUS_FAILED
    assert report.reason == REASON_COMMAND_FAILURE
    assert len(report.command_outcomes) == 1
    assert report.command_outcomes[0].index == 0
    assert report.command_outcomes[0].error
    assert report.resulting_fingerprint is None
    assert len(spawned) == 1
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_child_command_error_is_bounded_defensively() -> None:
    """Even a non-production child cannot return an unbounded error."""
    os.environ[SABOTAGE_MODE_ENV_VAR] = "long_error:100000"
    try:
        report = execute(_base_request(), runner_module=_SABOTAGE_RUNNER)
    finally:
        del os.environ[SABOTAGE_MODE_ENV_VAR]

    assert report.reason == REASON_COMMAND_FAILURE
    assert len(report.command_outcomes) == 1
    error = report.command_outcomes[0].error
    assert error is not None
    assert len(error.encode("utf-8")) <= MAX_COMMAND_ERROR_BYTES
    assert error.endswith("...[truncated]")


def test_failing_command_is_attempted_exactly_once_with_no_retry() -> None:
    """The counter file, not the outcome count, proves no internal retry.

    A single recorded failure alone does not distinguish "attempted once"
    from "attempted, then silently retried, with only the final failure
    recorded" -- confirmed against the H-02 prototype this ports, where a
    mutation that retried once before recording still passed a
    outcome-count-only version of this assertion. The load-bearing check
    is the counter file: it is incremented on every real invocation, so
    the boundary's own "no internal retry" claim requires it to read
    exactly `"1"`.
    """
    with tempfile.TemporaryDirectory(
        prefix="pmc-attempt-counter-"
    ) as counter_dir:
        counter_path = Path(counter_dir) / "attempts.txt"
        os.environ[SABOTAGE_MODE_ENV_VAR] = f"count_then_fail:{counter_path}"
        try:
            execute(_base_request(), runner_module=_SABOTAGE_RUNNER)
        finally:
            del os.environ[SABOTAGE_MODE_ENV_VAR]

        assert counter_path.read_text(encoding="utf-8").strip() == "1"


def test_fidelity_mismatch_fails_closed_even_though_commands_succeeded() -> (
    None
):
    """A caller-supplied expected fingerprint that disagrees fails closed.

    Uses the real production child: every command genuinely succeeds
    there, and the mismatch is adjudicated in the parent afterward.
    """
    scratch_before = _scratch_dirs()

    report = execute(
        _base_request(expected_resulting_fingerprint="sha256:" + "0" * 64)
    )

    assert report.status == STATUS_FAILED
    assert report.reason == REASON_FIDELITY_MISMATCH
    assert report.command_outcomes != ()
    assert all(outcome.status == "ok" for outcome in report.command_outcomes)
    assert report.resulting_fingerprint != "sha256:" + "0" * 64
    assert _scratch_dirs() == scratch_before


if __name__ == "__main__":
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
