# Copyright 2026 PyMOL Copilot contributors.
"""H-02 discovery: sabotage and positive-path probes for the execution boundary.

Each sabotage test below targets exactly one of the accepted design's stated
error behaviors -- "timeout, resource, and PyMOL errors terminate the
process with no internal retry"
([plan and execution](../../design/shared-core/plan-and-execution.md#apis-and-contracts))
-- and asserts all four of: a typed `reason` (never a raw exception
string), no internal retry (the boundary never re-attempts a failed
command or a failed spawn on its own), no live child process left behind,
and no scratch data left behind. The eight sabotage fixtures below map
exactly to slice 3's own plan list: oversized input, malformed input, an
incompatible snapshot schema version, spawn/load failure, wall-clock
timeout, a forced child crash, a failing PyMOL command, and a fidelity
mismatch between an independently supplied expected fingerprint and the
boundary's own resulting fingerprint.

The first three (oversized, malformed, incompatible schema version) are
rejected in the parent process before any child is ever spawned -- so "no
live child process" and "no scratch data" hold by construction for those
three, and each test also asserts directly that `on_process_spawned` was
never invoked, rather than only trusting that construction. The remaining
five genuinely spawn a real headless PyMOL child process and are verified
after the fact: the spawned `subprocess.Popen` handle (captured through
`execution_boundary.execute()`'s own `on_process_spawned` test hook) must
be reaped (`poll() is not None`) and its PID must no longer answer to
`os.kill(pid, 0)`, and this directory's scratch-directory prefix
(`h02-execution-boundary-*`) must not appear under the system temp
directory after `execute()` returns.

The positive-path test does not use the shared `real_pymol`/`loaded_fixture`
fixtures at all: unlike candidates A/B/C, this slice does not need the full
fixture matrix to prove the boundary's own properties (fresh process,
deadline, kill, cleanup, command execution), so it builds one small,
synthetic `ObjectSnapshot` directly, with no name collisions, altlocs, or
insertion codes -- simple enough for `reconstruct()`'s minimal technique
without candidate A's tag-based addressing workaround. It computes its
expected fingerprint independently: not by re-running `execute()` again,
but by launching real PyMOL directly in this test process (harness.py's
own `real_pymol` fixture, re-exported by this directory's `conftest.py`)
and reconstructing, running the same commands, and extracting there,
entirely outside the boundary being tested.

Two further probes close slice 4's own deferred gap (H02-S3-F3 and
H02-S3-F10, both fixed in this slice, not this module's own sabotage
fixtures above):

- `test_child_that_escapes_before_communicate_is_terminated_and_reaped`
  exploits the only hook `execute()` exposes between `Popen` and
  `communicate()` (`on_process_spawned`) to simulate an exception on that
  exact boundary, and asserts the child is terminated and reaped anyway
  (H02-S3-F3).
- Every genuinely-spawned-process test above (`test_spawn_or_load_failure_
  fails_closed_with_no_leak`, `test_wall_clock_timeout_is_hard_killed_and_
  reaped`, `test_forced_child_crash_leaves_no_live_process_or_scratch_data`,
  and the positive-path test) also asserts `report.child_pid` matches the
  spawned handle's own PID and `report.child_terminated` is `True`, and
  every parent-rejected test above also asserts both fields are `None` --
  a real caller's own evidence for "fresh process, terminated, not leaked"
  where before only the test-only `on_process_spawned` hook could show it
  (H02-S3-F10).
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

import execution_boundary as eb
from execution_boundary import Command
from execution_boundary import fingerprint
from execution_boundary import reconstruct
from harness import AtomRecord
from harness import BondRecord
from harness import ObjectSnapshot
from harness import SNAPSHOT_SCHEMA_VERSION
from harness import StateSnapshot
from harness import extract
from harness import to_json

# real_pymol (a pytest fixture defined in harness.py) is not imported here:
# this directory's conftest.py re-exports it so pytest's directory-scoped
# fixture discovery makes it available by parameter name without a direct
# import that a same-named test parameter would shadow (ruff's F811,
# confirmed empirically for this exact pattern -- see conftest.py's own
# docstring).

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


def _sample_snapshot() -> ObjectSnapshot:
    """A small, hand-built snapshot with no collisions this slice must dodge.

    Returns:
        A two-atom, singly bonded, single-state ObjectSnapshot: enough for
        `reconstruct()`'s minimal technique, deliberately without the
        altlocs, insertion codes, or same-residue name collisions
        candidate A's own reconstruction needs a tag-based workaround for.
    """
    atoms = (
        AtomRecord(
            serial=1,
            name="C1",
            alt="",
            resn="LIG",
            chain="A",
            resv=1,
            ins_code="",
            elem="C",
            hetatm=False,
            q=1.0,
            b=20.0,
            color=0,
            reps=("sticks",),
            label=None,
            coord=(0.0, 0.0, 0.0),
        ),
        AtomRecord(
            serial=2,
            name="C2",
            alt="",
            resn="LIG",
            chain="A",
            resv=1,
            ins_code="",
            elem="C",
            hetatm=False,
            q=1.0,
            b=20.0,
            color=0,
            reps=("sticks",),
            label=None,
            coord=(1.5, 0.0, 0.0),
        ),
    )
    return ObjectSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        name="fx",
        enabled=True,
        states=(StateSnapshot(atoms=atoms),),
        bonds=(BondRecord(atom_index_a=0, atom_index_b=1, order=1),),
        view=_IDENTITY_VIEW,
        settings=(("sphere_scale", "1.00000"),),
    )


def _base_request(**overrides: Any) -> eb.ExecutionRequest:
    """An otherwise well-formed request, with any field overridden.

    Args:
        **overrides: Fields to override on the well-formed default.

    Returns:
        The constructed ExecutionRequest.
    """
    fields: dict[str, Any] = {
        "schema_version": eb.EXECUTION_REQUEST_SCHEMA_VERSION,
        "snapshot_json": to_json(_sample_snapshot()),
        "commands": (),
        "max_input_bytes": 1_000_000,
        "deadline_seconds": 30.0,
    }
    fields.update(overrides)
    return eb.ExecutionRequest(**fields)


def _scratch_dirs() -> set[Path]:
    """Every execution-boundary scratch directory currently on disk.

    Returns:
        The set of matching paths under the system temp directory.
    """
    return set(Path(tempfile.gettempdir()).glob("h02-execution-boundary-*"))


def _assert_process_not_running(process: subprocess.Popen[str]) -> None:
    """Assert a spawned child process was reaped and is no longer alive.

    Args:
        process: The Popen handle captured via `on_process_spawned`.

    Raises:
        AssertionError: If the process was never reaped.
    """
    assert process.poll() is not None, "child process was not reaped"
    with pytest.raises(ProcessLookupError):
        os.kill(process.pid, 0)


def _refuse_to_spawn(process: subprocess.Popen[str]) -> None:
    """An `on_process_spawned` hook that fails the test if ever called.

    Args:
        process: The Popen handle the boundary would have spawned.

    Raises:
        AssertionError: Always -- being called at all is the failure.
    """
    raise AssertionError(
        f"a child process (pid={process.pid}) was spawned for a request "
        "that should have been rejected before any process is created"
    )


def test_oversized_input_is_rejected_with_no_process_spawned() -> None:
    """A snapshot larger than the declared limit fails closed, unspawned."""
    scratch_before = _scratch_dirs()

    report = eb.execute(
        _base_request(max_input_bytes=10), on_process_spawned=_refuse_to_spawn
    )

    assert report.status == eb.STATUS_REJECTED
    assert report.reason == eb.REASON_OVERSIZED_INPUT
    assert report.input_fingerprint is None
    assert report.resulting_fingerprint is None
    # H02-S3-F10: no process was ever spawned for a rejected request, so
    # neither process-evidence field has anything to report.
    assert report.child_pid is None
    assert report.child_terminated is None
    assert report.command_outcomes == ()
    assert _scratch_dirs() == scratch_before


def test_malformed_input_is_rejected_with_no_process_spawned() -> None:
    """Snapshot JSON that does not even parse fails closed, unspawned."""
    scratch_before = _scratch_dirs()

    report = eb.execute(
        _base_request(snapshot_json="{not valid json"),
        on_process_spawned=_refuse_to_spawn,
    )

    assert report.status == eb.STATUS_REJECTED
    assert report.reason == eb.REASON_MALFORMED_INPUT
    # H02-S3-F10: no process was ever spawned for a rejected request.
    assert report.child_pid is None
    assert report.child_terminated is None
    assert _scratch_dirs() == scratch_before


@pytest.mark.parametrize("scalar_json", ["42", "null", "[]", '"hello"', "true"])
def test_non_object_snapshot_json_is_rejected_with_no_process_spawned(
    scalar_json: str,
) -> None:
    """Syntactically valid JSON that is not an object fails closed.

    `harness.from_json` parses this text successfully (it is valid JSON)
    but then calls `.get("schema_version")` on the result, which raises
    `AttributeError` for a scalar, string, or list -- confirmed empirically,
    not merely a `json.JSONDecodeError` or `ValueError`. `execute()` must
    still fail closed with `REASON_MALFORMED_INPUT` rather than let that
    exception escape.
    """
    scratch_before = _scratch_dirs()

    report = eb.execute(
        _base_request(snapshot_json=scalar_json),
        on_process_spawned=_refuse_to_spawn,
    )

    assert report.status == eb.STATUS_REJECTED
    assert report.reason == eb.REASON_MALFORMED_INPUT
    # H02-S3-F10: no process was ever spawned for a rejected request.
    assert report.child_pid is None
    assert report.child_terminated is None
    assert _scratch_dirs() == scratch_before


def test_snapshot_missing_a_key_is_rejected_with_no_process_spawned() -> None:
    """A well-formed JSON object missing a required snapshot key fails closed.

    `harness.from_json` reads several required keys (for example `name`)
    straight off the parsed dict with `data["name"]`, which raises
    `KeyError` when a key is absent -- confirmed empirically, not a
    `json.JSONDecodeError` or `ValueError`. `execute()` must still fail
    closed with `REASON_MALFORMED_INPUT` rather than let that exception
    escape.
    """
    payload = json.loads(to_json(_sample_snapshot()))
    del payload["name"]
    scratch_before = _scratch_dirs()

    report = eb.execute(
        _base_request(snapshot_json=json.dumps(payload)),
        on_process_spawned=_refuse_to_spawn,
    )

    assert report.status == eb.STATUS_REJECTED
    assert report.reason == eb.REASON_MALFORMED_INPUT
    # H02-S3-F10: no process was ever spawned for a rejected request.
    assert report.child_pid is None
    assert report.child_terminated is None
    assert _scratch_dirs() == scratch_before


def test_incompatible_schema_version_is_rejected_with_no_process_spawned() -> (
    None
):
    """A snapshot whose own schema_version is unsupported fails closed."""
    payload = json.loads(to_json(_sample_snapshot()))
    payload["schema_version"] = SNAPSHOT_SCHEMA_VERSION + 1
    scratch_before = _scratch_dirs()

    report = eb.execute(
        _base_request(snapshot_json=json.dumps(payload)),
        on_process_spawned=_refuse_to_spawn,
    )

    assert report.status == eb.STATUS_REJECTED
    assert report.reason == eb.REASON_UNSUPPORTED_SCHEMA_VERSION
    # H02-S3-F10: no process was ever spawned for a rejected request.
    assert report.child_pid is None
    assert report.child_terminated is None
    assert _scratch_dirs() == scratch_before


def test_spawn_or_load_failure_fails_closed_with_no_leak() -> None:
    """A snapshot PyMOL cannot load fails closed, with no leaked process/data.

    A non-numeric coordinate survives `from_json` (the dataclass performs
    no type validation) but PyMOL's own `pseudoatom` rejects it while
    reconstructing -- confirmed empirically to raise `ValueError` -- so this
    reaches the boundary's own reconstruction step rather than the parent's
    schema/size checks above.
    """
    payload = json.loads(to_json(_sample_snapshot()))
    payload["states"][0]["atoms"][0]["coord"] = ["a", "b", "c"]
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []

    report = eb.execute(
        _base_request(snapshot_json=json.dumps(payload)),
        on_process_spawned=spawned.append,
    )

    assert report.status == eb.STATUS_FAILED
    assert report.reason == eb.REASON_SPAWN_OR_LOAD_FAILURE
    assert report.command_outcomes == ()
    assert report.resulting_fingerprint is None
    assert len(spawned) == 1
    # H02-S3-F10: the report's own process-evidence fields, not only the
    # test-only on_process_spawned hook, show the spawned child by PID and
    # confirm it was terminated before execute() returned.
    assert report.child_pid == spawned[0].pid
    assert report.child_terminated is True
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_wall_clock_timeout_is_hard_killed_and_reaped() -> None:
    """A command that outlives the deadline is killed, not waited out."""
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []
    sleep_seconds = 5.0
    deadline_seconds = 1.0

    report = eb.execute(
        _base_request(
            commands=(Command(eb.SLEEP_VERB, (str(sleep_seconds),)),),
            deadline_seconds=deadline_seconds,
        ),
        on_process_spawned=spawned.append,
    )

    assert report.status == eb.STATUS_FAILED
    assert report.reason == eb.REASON_TIMEOUT
    assert report.command_outcomes == ()
    assert report.resulting_fingerprint is None
    # A hard kill, not "wait for the sleep to finish": elapsed time stays
    # well under the sleep duration even though it exceeds the deadline
    # (process teardown and reaping both take some real time).
    assert report.elapsed_seconds < sleep_seconds
    assert len(spawned) == 1
    # H02-S3-F10: process evidence is present even for a hard-killed child.
    assert report.child_pid == spawned[0].pid
    assert report.child_terminated is True
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_forced_child_crash_leaves_no_live_process_or_scratch_data() -> None:
    """A child that hard-exits mid-run is detected and cleaned up after."""
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []

    report = eb.execute(
        _base_request(commands=(Command(eb.CRASH_VERB, ()),)),
        on_process_spawned=spawned.append,
    )

    assert report.status == eb.STATUS_FAILED
    assert report.reason == eb.REASON_CHILD_CRASH
    assert report.command_outcomes == ()
    assert report.resulting_fingerprint is None
    assert len(spawned) == 1
    # H02-S3-F10: process evidence is present even after a forced crash.
    assert report.child_pid == spawned[0].pid
    assert report.child_terminated is True
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_child_that_escapes_before_communicate_is_terminated_and_reaped() -> (
    None
):
    """H02-S3-F3: an exception between spawn and `communicate()` still reaps.

    `on_process_spawned` is the only hook `execute()` invokes between
    `Popen` and `communicate()`; making it raise reproduces exactly the
    exception window the finding described -- a real caller could just as
    well hit an unrelated exception on that same boundary, not only this
    test's own injected one. Before the fix, `execute()`'s only `finally`
    clause deleted the scratch directory and left the spawned child
    neither terminated nor reaped. After the fix, the inner `finally`
    guarding the child's own lifecycle confirms it is stopped and reaped
    before the injected exception ever reaches this test.
    """
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []

    def _escape(process: subprocess.Popen[str]) -> None:
        spawned.append(process)
        raise RuntimeError("simulated escape between spawn and communicate()")

    with pytest.raises(RuntimeError, match="simulated escape"):
        eb.execute(_base_request(), on_process_spawned=_escape)

    assert len(spawned) == 1
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_pymol_command_failure_fails_closed_with_no_retry() -> None:
    """A command PyMOL itself rejects stops execution at that command.

    `cmd.color` with an unknown color name raises `pymol.CmdException`
    (confirmed empirically) -- the boundary must report that one command's
    failure and stop, never attempt it again, and never run any command
    after it.
    """
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []

    report = eb.execute(
        _base_request(
            commands=(
                Command("color", ("not_a_real_color_zzz", "fx")),
                Command("show", ("spheres", "fx")),
            )
        ),
        on_process_spawned=spawned.append,
    )

    assert report.status == eb.STATUS_FAILED
    assert report.reason == eb.REASON_COMMAND_FAILURE
    # Exactly one outcome: the failing command, at its own position, with
    # no outcome recorded for the never-attempted second command and no
    # sign of a retried attempt at the same position.
    assert len(report.command_outcomes) == 1
    assert report.command_outcomes[0].index == 0
    assert report.command_outcomes[0].verb == "color"
    assert report.command_outcomes[0].status == eb.OUTCOME_ERROR
    assert report.command_outcomes[0].error
    assert report.resulting_fingerprint is None
    assert len(spawned) == 1
    _assert_process_not_running(spawned[0])
    assert _scratch_dirs() == scratch_before


def test_failing_command_is_attempted_exactly_once_with_no_retry() -> None:
    """A failing command's own outcome count cannot prove "no retry" alone.

    `test_pymol_command_failure_fails_closed_with_no_retry` above only
    asserts on `command_outcomes` -- exactly one recorded failure -- which
    a child runner silently retrying the same failing command some number
    of times before recording one final failure would still satisfy
    (confirmed empirically: such a mutation still passes that test, and
    the whole `execution_boundary_probes` suite). This test instead uses
    `COUNT_THEN_FAIL_VERB`, a sentinel the child runner always fails on but
    only after incrementing a counter file on disk each time it is
    actually invoked, regardless of outcome. That counter -- not the
    outcome count -- is what can actually distinguish "attempted once"
    from "attempted, then silently retried:" a silent 3-attempt retry
    before the one recorded failure would leave this counter at "3", not
    "1".
    """
    scratch_before = _scratch_dirs()
    spawned: list[subprocess.Popen[str]] = []

    with tempfile.TemporaryDirectory(
        prefix="h02-attempt-counter-"
    ) as counter_dir:
        counter_path = Path(counter_dir) / "attempts.txt"

        report = eb.execute(
            _base_request(
                commands=(
                    Command(eb.COUNT_THEN_FAIL_VERB, (str(counter_path),)),
                    Command("show", ("spheres", "fx")),
                )
            ),
            on_process_spawned=spawned.append,
        )

        assert report.status == eb.STATUS_FAILED
        assert report.reason == eb.REASON_COMMAND_FAILURE
        # Exactly one outcome: the failing command, at its own position,
        # with no outcome recorded for the never-attempted second command.
        assert len(report.command_outcomes) == 1
        assert report.command_outcomes[0].index == 0
        assert report.command_outcomes[0].verb == eb.COUNT_THEN_FAIL_VERB
        assert report.command_outcomes[0].status == eb.OUTCOME_ERROR
        assert report.command_outcomes[0].error
        # The load-bearing assertion this module's docstring's "no internal
        # retry" claim actually needs: exactly one real invocation, not
        # merely one recorded outcome.
        assert counter_path.read_text().strip() == "1"
        assert report.resulting_fingerprint is None
        assert len(spawned) == 1
        _assert_process_not_running(spawned[0])
        assert _scratch_dirs() == scratch_before


def test_fidelity_mismatch_fails_closed_even_though_commands_succeeded() -> (
    None
):
    """A wrong expected fingerprint fails the report despite command success.

    Every command in this request genuinely succeeds; the boundary still
    reports failure, because the caller-supplied expected fingerprint
    (standing in for an independently computed value from elsewhere in the
    system) does not match what was actually produced.
    """
    scratch_before = _scratch_dirs()

    report = eb.execute(
        _base_request(
            commands=(Command("color", ("blue", "fx")),),
            expected_resulting_fingerprint="0" * 64,
        )
    )

    assert report.status == eb.STATUS_FAILED
    assert report.reason == eb.REASON_FIDELITY_MISMATCH
    assert len(report.command_outcomes) == 1
    assert report.command_outcomes[0].status == eb.OUTCOME_OK
    assert report.resulting_fingerprint is not None
    assert report.resulting_fingerprint != "0" * 64
    assert _scratch_dirs() == scratch_before


def test_positive_path_matches_independently_computed_expected_values(
    real_pymol: Any,
) -> None:
    """A well-formed request's report matches real, independent expectations.

    Reconstructs the same snapshot and runs the same commands directly in
    this test process's own real PyMOL (`real_pymol`, not the boundary's
    spawned child) to compute a genuinely independent expected fingerprint
    and expected extracted field values, then asserts the boundary's report
    matches them -- not merely that no exception was raised. Runs the
    request twice to demonstrate the evidence is deterministic, as the
    design's "deterministic evidence where declared" guarantee requires.

    Args:
        real_pymol: The real PyMOL cmd module (harness.py's fixture,
            re-exported by this directory's conftest.py), used only for
            this test's own independent verification -- never by the
            boundary itself, which always uses its own spawned child.
    """
    snapshot = _sample_snapshot()
    commands = (
        Command("color", ("blue", "fx")),
        Command("show", ("spheres", "fx")),
    )

    reconstruct(real_pymol, snapshot)
    try:
        for command in commands:
            getattr(real_pymol, command.verb)(*command.args)
        real_pymol.sync()
        expected_extraction = extract(real_pymol, snapshot.name)
    finally:
        real_pymol.delete(snapshot.name)
        real_pymol.sync()

    expected_fingerprint = fingerprint(to_json(expected_extraction))
    assert real_pymol.get_color_index("blue") in (
        atom.color for atom in expected_extraction.states[0].atoms
    )
    assert all(
        "spheres" in atom.reps for atom in expected_extraction.states[0].atoms
    )

    spawned: list[subprocess.Popen[str]] = []
    request = _base_request(commands=commands)
    first_report = eb.execute(request, on_process_spawned=spawned.append)
    second_report = eb.execute(request, on_process_spawned=spawned.append)

    for report in (first_report, second_report):
        assert report.status == eb.STATUS_OK
        assert report.reason == eb.REASON_OK
        assert report.resulting_fingerprint == expected_fingerprint
        assert report.command_outcomes == (
            eb.CommandOutcome(0, "color", eb.OUTCOME_OK, None),
            eb.CommandOutcome(1, "show", eb.OUTCOME_OK, None),
        )

    assert (
        first_report.resulting_fingerprint
        == second_report.resulting_fingerprint
    )
    assert first_report.command_outcomes == second_report.command_outcomes
    # H02-S3-F10: process evidence on the success path too, and each of the
    # two "deterministic evidence" runs above used a genuinely distinct
    # fresh child, not one process reused or memoized across calls.
    assert len(spawned) == 2
    assert first_report.child_pid == spawned[0].pid
    assert second_report.child_pid == spawned[1].pid
    assert first_report.child_pid != second_report.child_pid
    assert first_report.child_terminated is True
    assert second_report.child_terminated is True
    _assert_process_not_running(spawned[0])
    _assert_process_not_running(spawned[1])


if __name__ == "__main__":
    # Real PyMOL's headless launch (in the positive-path test's real_pymol
    # fixture) leaves behind cleanup that can complete after this process
    # would otherwise exit, overriding a genuine pytest failure with process
    # exit code 0 (the same defect documented and fixed the same way in
    # tests/integration/test_real_pymol_command.py and every other module in
    # this directory). os._exit bypasses that interpreter-shutdown window
    # entirely, so pytest's real result is what Bazel actually sees. os._exit
    # skips the normal stdio flush, so flush explicitly first -- otherwise a
    # real failure's traceback and summary can be silently lost from the
    # captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
