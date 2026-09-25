# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL, real-server evidence for preview, apply, and rollback.

Every collaborator here is a real production component: real headless
Open-Source PyMOL (`pymol.finish_launching(['pymol', '-qc'])`), PyMOL's own
command registry (`cmd.extend`/`cmd.do`), the real authenticated loopback
server (`pmc_server.transport.LoopbackPlanServer`) driven by the real
`pmc_server.lifecycle.RequestGraphLifecycle` and request graph
(`pmc_agent.graph`), and the real `pmc_client.transport.LoopbackPlanClient`
and `pmc_client.command.register_copilot`. Nothing here is a transport,
server, policy, or PyMOL test double -- except the inference engine
(`pmc_agent.inference.fake.FakeEngine`, scripted to render the same plan the
old fixture lifecycle always returned) and the sidecar executor (a fake
reporting success without spawning a second real PyMOL process): item 8
docs its own graph tests exhaustively against a fake engine, and this
module's own real-PyMOL evidence is about the client's live extraction and
the transport/lifecycle/policy path around the graph, not about a second
real sidecar spawn stacked on top of `check_fidelity`'s existing one.

PyMOL only supports one `finish_launching` call per interpreter, so it is
launched exactly once for the whole test module (session-scoped fixture) and
shut down with `cmd.do('quit')` at final teardown. The two-chain fixture
object is loaded and deleted fresh for every test function so state from one
test can never leak into the next.

Coordinate capture uses `cmd.iterate_state` (per-atom Python floats) rather
than `cmd.get_coords("all")`: the pinned `pymol-open-source-whl==3.2.0.2`
wheel declares `numpy>=2.2` but its compiled `_cmd`/chempy extension was
built against NumPy's pre-2.0 C API, so `cmd.get_coords()` raises
`SystemError: <built-in function get_coords> returned a result with an
exception set` under any NumPy 2.x -- confirmed reproducible in this
hermetic Bazel sandbox, and confirmed unfixable by pinning `numpy<2` (`uv`
reports the pin as unsatisfiable against the wheel's own declared
`numpy>=2.2` requirement). `cmd.iterate_state`/`cmd.count_atoms`/
`cmd.iterate`/`cmd.get_color_index` all work normally in this same sandbox,
so this substitutes one real PyMOL query API for another to capture the same
observable (per-atom coordinates) without touching production code.

This target used to be excluded on Windows: the wheel's Windows build
bundles delvewheel-repaired DLLs with long hash-suffixed names, and
combined with Bazel's generated repository name for this dependency the
resulting path exceeded Windows' MAX_PATH when the compiled `_cmd`
extension loaded its bundled dependencies. A short Bazel output-base and
unsandboxed test execution were both tried against real Windows CI and
neither changed the error; only staging a copy to a short path did (see
`tools/winstage/winstage.py`, called below before this module's own
`import pymol`). Tracked in
[issue #12](https://github.com/urban233/pymol-copilot/issues/12).
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
import sys
import threading
import time
from collections.abc import Callable
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Protocol

import pytest

from preview_support import find_preview
from preview_support import plan_id_from
from preview_support import section
from pmc_agent.graph import MAX_REPAIR_ATTEMPTS
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.session import RequestGraphSession
from pmc_client.command import register_copilot
from pmc_client.recovery import RecoveryStore
from pmc_client.transport import LoopbackPlanClient
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_server.lifecycle import RequestGraphLifecycle
from pmc_server.transport import LoopbackPlanServer

import winstage

CREDENTIAL = "real-pymol-integration-secret"
OBJECT_NAME = "two_chain_fixture"
FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "two_chain_fixture.pdb"
)
#: The intent this module's own `copilot` invocations send.
INTENT = "Select chain A and color it red."
#: The completion `FakeEngine` renders for `INTENT`: the same two-command
#: plan the old fixture lifecycle always returned, so this module's own
#: printed-output assertions stay meaningful unchanged.
_FIXTURE_COMPLETION = (
    "select copilot_selection, chain A\ncolor red, copilot_selection\n"
)
#: Raised from the pre-item-7 value of 5.0: copilot now spawns a real
#: sidecar subprocess for its own fidelity check on every invocation
#: (docs/master_plan.md item 7), not just a loopback round trip. This
#: module's own three real invocations, each gated on this exact deadline,
#: passed repeatedly in this sandbox; set with headroom above that
#: observed margin rather than a tight per-call measurement, since
#: capturing a background PyMOL worker thread's own stdout to log the
#: precise figure was not straightforward.
INVOCATION_DEADLINE_SECONDS = 15.0


class PyMOLCmd(Protocol):
    """Subset of PyMOL's real `cmd` module used to drive this test module."""

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register a command callback with real PyMOL.

        Args:
            name: Command name to register.
            callback: Function invoked for the registered command.
        """

    def load(self, filename: str, name: str) -> None:
        """Load a structure file into a named object.

        Args:
            filename: Path to the structure file to load.
            name: Name of the object to create.
        """

    def delete(self, name: str) -> None:
        """Delete a named object or selection.

        Args:
            name: Name of the object or selection to delete.
        """

    def do(self, command: str) -> None:
        """Execute one PML command line exactly as a user would type it.

        Args:
            command: The command line text to execute.
        """

    def count_atoms(self, selection: str) -> int:
        """Count the atoms matched by a selection expression.

        Args:
            selection: The selection expression to evaluate.

        Returns:
            The number of atoms matched.
        """

    def get_names(
        self, kind: str = "objects", *, enabled_only: int = 0
    ) -> list[str]:
        """Return the names of every loaded object of the given kind.

        Args:
            kind: The PyMOL name-kind selector, e.g. "objects".
            enabled_only: When 1, list only enabled objects.

        Returns:
            The list of matching names.
        """

    def get_type(self, name: str) -> str:
        """Return the PyMOL type string for one named object.

        Args:
            name: The object or selection name to query.

        Returns:
            The object's PyMOL type string, e.g. "object:molecule".
        """

    def count_states(self, selection: str) -> int:
        """Return the number of coordinate states an object has.

        Args:
            selection: The object or selection to count states for.

        Returns:
            The number of coordinate states.
        """

    def get_model(self, selection: str, *, state: int) -> Any:
        """Return one coordinate state's atoms and bonds as a chempy model.

        Args:
            selection: The object or selection to query.
            state: The 1-based coordinate state to read.

        Returns:
            A chempy model exposing `.atom` and `.bond`.
        """

    def get_view(self) -> tuple[float, ...]:
        """Return the current camera view.

        Returns:
            The 18-float view tuple PyMOL's own get_view() returns.
        """

    def get(self, setting: str, selection: str) -> str:
        """Return one object-scoped setting's current value.

        Args:
            setting: The PyMOL setting name.
            selection: The object to read the setting for.

        Returns:
            The setting's current value, as PyMOL's own get() returns it.
        """

    def iterate(
        self, selection: str, expression: str, *, space: dict[str, object]
    ) -> None:
        """Run a per-atom Python expression over a selection.

        Args:
            selection: The selection expression to iterate over.
            expression: The Python expression evaluated once per atom.
            space: The namespace exposed to the expression.
        """

    def iterate_state(
        self,
        state: int,
        selection: str,
        expression: str,
        *,
        space: dict[str, object],
    ) -> None:
        """Run a per-atom Python expression over one coordinate state.

        Args:
            state: The 1-based coordinate state to iterate over.
            selection: The selection expression to iterate over.
            expression: The Python expression evaluated once per atom.
            space: The namespace exposed to the expression.
        """

    def color(self, color: str, selection: str) -> None:
        """Apply a color to every atom matched by a selection.

        Args:
            color: The PyMOL color name to apply.
            selection: The selection expression to color.
        """


@dataclass(frozen=True)
class SessionSnapshot:
    """An observable, comparable slice of PyMOL session state.

    Attributes:
        object_names: The sorted names of every loaded object.
        atom_count: The total atom count across the whole session.
        chain_a_atom_count: The atom count selected by chain A.
        chain_b_atom_count: The atom count selected by chain B.
        coordinates: Per-atom (index, x, y, z) tuples, state 1 only.
        colors: Per-atom (index, color_index) tuples.
    """

    object_names: tuple[str, ...]
    atom_count: int
    chain_a_atom_count: int
    chain_b_atom_count: int
    coordinates: tuple[tuple[int, float, float, float], ...]
    colors: tuple[tuple[int, int], ...]


def capture_session_state(cmd: PyMOLCmd) -> SessionSnapshot:
    """Capture a comparable snapshot of the current real PyMOL session.

    Args:
        cmd: The real PyMOL cmd module.

    Returns:
        A snapshot of the observable state compared by this test module.
    """
    coordinates: list[tuple[int, float, float, float]] = []
    cmd.iterate_state(
        1,
        "all",
        "coordinates.append((index, x, y, z))",
        space={"coordinates": coordinates},
    )
    colors: list[tuple[int, int]] = []
    cmd.iterate(
        "all",
        "colors.append((index, color))",
        space={"colors": colors},
    )
    return SessionSnapshot(
        object_names=tuple(sorted(cmd.get_names())),
        atom_count=cmd.count_atoms("all"),
        chain_a_atom_count=cmd.count_atoms("chain A"),
        chain_b_atom_count=cmd.count_atoms("chain B"),
        coordinates=tuple(coordinates),
        colors=tuple(colors),
    )


def assert_session_unchanged(
    before: SessionSnapshot, after: SessionSnapshot
) -> None:
    """Assert that no observable session state changed between snapshots.

    Args:
        before: Snapshot captured immediately before the invocation.
        after: Snapshot captured immediately after the invocation.

    Raises:
        AssertionError: If any compared field differs.
    """
    assert before == after


def always_deny(_plan: ActionPlan) -> PlanDecision:
    """Deny every plan regardless of its shape.

    Args:
        _plan: The typed plan that would otherwise be evaluated.

    Returns:
        A PlanDecision that denies the plan with no per-operation detail.
    """
    return PlanDecision(decisions=(), allowed=False)


def _always_ok_executor(_request: ExecutionRequest) -> ExecutionReport:
    """Report success for any request, without spawning a second real PyMOL.

    Args:
        _request: Ignored.

    Returns:
        A minimal `STATUS_OK` report.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:test",
        resulting_fingerprint="sha256:" + "0" * 64,
        selection_counts=(),
        command_outcomes=(),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=0.01,
    )


def _lifecycle(
    *,
    policy_validator: Callable[[ActionPlan], PlanDecision] = evaluate_plan,
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> RequestGraphLifecycle:
    """Build a lifecycle over a fresh session, scripted to render the fixture.

    Args:
        policy_validator: Forwarded to `RequestGraphSession`. Defaults to
            the graph's own real `evaluate_plan`.
        max_repair_attempts: Forwarded to `RequestGraphSession`. Defaults
            to the graph's own real repair budget.

    Returns:
        A lifecycle whose engine renders `_FIXTURE_COMPLETION` for every
        call scripted, and whose graph never spawns a second real sidecar.
    """
    engine = FakeEngine(
        [
            CompletionResult(_FIXTURE_COMPLETION, "m-1", STOP_END)
            for _ in range(3)
        ]
    )
    session = RequestGraphSession(
        engine=engine,
        executor=_always_ok_executor,
        policy_validator=policy_validator,
        max_repair_attempts=max_repair_attempts,
    )
    return RequestGraphLifecycle(session=session)


class _SynchronizingExtension:
    """Wrap a command extension so a test can wait for its callback.

    PyMOL's `cmd.do()` queues the command onto PyMOL's own thread and
    returns as soon as it is queued, not when it has run. That was
    established directly rather than assumed: instrumentation on a real
    windows-2025 run recorded the callback entering on `Thread-1
    (launch)` while the test continued on the main thread, with no
    matching return by the time the assertions ran, and `cmd.sync()` did
    not wait for it either.

    Two consequences, and both bit this module. A test that asserts on
    the callback's effects straight after `do()` races it -- which is why
    `test_unavailable_server_path_reports_bounded_diagnostic` failed two
    Windows runs in eight while passing everywhere else, the dead-port
    connection being slower to refuse there than on Linux or macOS. And a
    test that measures elapsed time across `do()` alone measures how long
    queueing took, not how long the command took, so this module's
    `INVOCATION_DEADLINE_SECONDS` assertions were vacuous on every
    platform until this wrapper existed.

    Setting the event from a `finally` rather than after the call means a
    callback that raises still releases the waiter, so a failure surfaces
    as its own assertion rather than as a deadline timeout.
    """

    def __init__(self, inner: Any, finished: threading.Event) -> None:
        """Store the wrapped extension and the event to signal.

        Args:
            inner: The real extension this delegates registration to.
            finished: Event set once the callback has run to completion.
        """
        self._inner = inner
        self._finished = finished

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register `callback` wrapped so completion signals the event.

        Args:
            name: Command name to register.
            callback: Function invoked for the registered command.
        """

        def synchronized(argument: str) -> None:
            try:
                callback(argument)
            finally:
                self._finished.set()

        self._inner.extend(name, synchronized)

    def __getattr__(self, name: str) -> Any:
        """Forward every other attribute to the wrapped extension.

        `pmc_client.command.CopilotCommandClient.register()` stores
        whatever it is given as its own live session, then queries it on
        every later `copilot()` call -- so this wrapper, which `register()`
        actually receives in this test module, must forward the query
        surface (`get_names`, `get_type`, ...) through to the real `cmd`
        it wraps, not only `extend()`.

        Args:
            name: The attribute name being accessed.

        Returns:
            The wrapped extension's own attribute.
        """
        return getattr(self._inner, name)


def _run_pymol_command(
    cmd: PyMOLCmd, finished: threading.Event, command_line: str
) -> float:
    """Dispatch one PML command line and wait for its callback to finish.

    Args:
        cmd: The real PyMOL cmd module.
        finished: Event the registered wrapper sets on completion.
        command_line: The exact command line to dispatch, e.g.
            "copilot_apply p-<id>".

    Returns:
        Seconds from dispatch until the callback completed.

    Raises:
        AssertionError: If the callback did not complete within the
            invocation deadline.
    """
    finished.clear()
    started = time.monotonic()
    cmd.do(command_line)
    completed = finished.wait(INVOCATION_DEADLINE_SECONDS)
    elapsed = time.monotonic() - started
    assert completed, (
        f"{command_line!r} did not complete within "
        f"{INVOCATION_DEADLINE_SECONDS}s of dispatch"
    )
    return elapsed


def _run_copilot(cmd: PyMOLCmd, finished: threading.Event) -> float:
    """Dispatch the copilot command and wait for it to finish.

    Args:
        cmd: The real PyMOL cmd module.
        finished: Event the registered wrapper sets on completion.

    Returns:
        Seconds from dispatch until the callback completed.

    Raises:
        AssertionError: If the callback did not complete within the
            invocation deadline.
    """
    return _run_pymol_command(cmd, finished, f"copilot {INTENT}")


def _run_copilot_apply(
    cmd: PyMOLCmd, finished: threading.Event, plan_id: str
) -> float:
    """Dispatch copilot_apply for one plan id and wait for it to finish.

    Args:
        cmd: The real PyMOL cmd module.
        finished: Event the registered wrapper sets on completion.
        plan_id: The plan identifier to apply, exactly as `copilot` itself
            printed it (with its display prefix).

    Returns:
        Seconds from dispatch until the callback completed.

    Raises:
        AssertionError: If the callback did not complete within the
            invocation deadline.
    """
    return _run_pymol_command(cmd, finished, f"copilot_apply {plan_id}")


def _run_copilot_rollback(
    cmd: PyMOLCmd, finished: threading.Event, plan_id: str
) -> float:
    """Dispatch one explicit full-session rollback and await its callback."""
    return _run_pymol_command(cmd, finished, f"copilot_rollback {plan_id}")


class RealPyMOLCmdExtension:
    """Adapter registering commands through PyMOL's own command system."""

    def __init__(self, cmd: PyMOLCmd) -> None:
        """Wrap a real PyMOL cmd module for command registration.

        Args:
            cmd: The real PyMOL cmd module.
        """
        self._cmd = cmd

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register a command callback with real PyMOL.

        Args:
            name: Command name to register.
            callback: Function invoked for the registered command.
        """
        self._cmd.extend(name, callback)

    def __getattr__(self, name: str) -> Any:
        """Forward every other attribute to the wrapped real cmd module.

        See `_SynchronizingExtension.__getattr__` for why this matters:
        `register()` stores this adapter as its own live session and
        later queries it directly.

        Args:
            name: The attribute name being accessed.

        Returns:
            The real cmd module's own attribute.
        """
        return getattr(self._cmd, name)


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[PyMOLCmd]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL cmd module.
    """
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


@pytest.fixture
def loaded_fixture(real_pymol: PyMOLCmd) -> Iterator[PyMOLCmd]:
    """Load the two-chain fixture fresh for one test and delete it after.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module with the fixture object loaded.
    """
    real_pymol.load(str(FIXTURE_PATH), OBJECT_NAME)
    try:
        yield real_pymol
    finally:
        real_pymol.delete(OBJECT_NAME)


def test_fixture_loads_with_two_atoms_per_chain(
    loaded_fixture: PyMOLCmd,
) -> None:
    """The controlled fixture loads cleanly with the intended chain split."""
    assert loaded_fixture.count_atoms("all") == 4
    assert loaded_fixture.count_atoms("chain A") == 2
    assert loaded_fixture.count_atoms("chain B") == 2


def test_success_path_applies_then_rolls_back_the_real_session(
    loaded_fixture: PyMOLCmd, tmp_path: Path
) -> None:
    """A real approved plan mutates once and explicit rollback restores it.

    Covers the end-to-end path docs/master_plan.md item 7 requires: a real
    headless PyMOL, the real loopback server, `copilot <intent>` followed
    by `copilot_apply <plan-id>`, with a request carrying a computed
    digest, the console reporting fidelity, one live mutation after approval,
    and complete-session rollback.

    Args:
        loaded_fixture: The real PyMOL cmd module with the two-chain
            fixture loaded.
        tmp_path: Hermetic root for the private recovery-point lifecycle.
    """
    requests: list[PlanRequestV1] = []
    output: list[str] = []
    lifecycle = _lifecycle()

    def record_lifecycle(
        request: PlanRequestV1,
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Record a request and return its lifecycle response.

        Args:
            request: Request to record and handle.

        Returns:
            The typed response produced by the lifecycle.
        """
        requests.append(request)
        return lifecycle(request)

    server = LoopbackPlanServer(
        CREDENTIAL,
        record_lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )
    try:
        server.start()
        finished = threading.Event()
        register_copilot(
            # pyrefly: ignore.  __getattr__ delegates the query surface at
            # runtime, but pyrefly cannot verify that structurally.
            _SynchronizingExtension(
                RealPyMOLCmdExtension(loaded_fixture), finished
            ),
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
            recovery_store=RecoveryStore(tmp_path),
        )
        before = capture_session_state(loaded_fixture)

        assert _run_copilot(loaded_fixture, finished) < (
            INVOCATION_DEADLINE_SECONDS
        )

        after_copilot = capture_session_state(loaded_fixture)

        plan_id = plan_id_from(output)
        assert _run_copilot_apply(loaded_fixture, finished, plan_id) < (
            INVOCATION_DEADLINE_SECONDS
        )

        after_apply = capture_session_state(loaded_fixture)
        assert _run_copilot_rollback(loaded_fixture, finished, plan_id) < (
            INVOCATION_DEADLINE_SECONDS
        )
        after_rollback = capture_session_state(loaded_fixture)
    finally:
        server.close()

    assert len(requests) == 1
    assert requests[0].snapshot.digest.startswith("sha256:")
    assert requests[0].snapshot.digest != "sha256:example-chain-a-digest"
    assert requests[0].snapshot.object_name == OBJECT_NAME

    preview = find_preview(output)
    assert OBJECT_NAME in section(output, "object")
    assert section(output, "fidelity") == "exact on the declared state scope"
    assert "NOT applicable" not in preview
    assert "1 | select copilot_selection, chain A" in section(
        output, "commands"
    )
    assert "2 | color red, copilot_selection" in section(output, "commands")
    assert section(output, "checked").startswith("the plan parses")
    assert section(output, "apply").startswith("copilot_apply ")

    apply_lines = [line for line in output if line.startswith("copilot_apply:")]
    rollback_lines = [
        line for line in output if line.startswith("copilot_rollback:")
    ]
    assert len(apply_lines) == 1
    assert apply_lines[0].startswith(f"copilot_apply: plan {plan_id} applied.")
    assert len(rollback_lines) == 2
    assert rollback_lines[0].startswith(
        "copilot_rollback: replacing the entire session"
    )
    assert rollback_lines[1].endswith(
        "rolled back and its recovery point was removed."
    )
    assert len(output) == 1 + len(apply_lines) + len(rollback_lines), output
    assert_session_unchanged(before, after_copilot)
    assert after_apply != before
    assert_session_unchanged(before, after_rollback)


def test_typed_rejection_path_reports_bounded_diagnostic(
    loaded_fixture: PyMOLCmd,
) -> None:
    """A real server-side policy denial reports a bounded diagnostic only."""
    output: list[str] = []
    server = LoopbackPlanServer(
        CREDENTIAL,
        _lifecycle(policy_validator=always_deny, max_repair_attempts=0),
    )
    try:
        server.start()
        finished = threading.Event()
        register_copilot(
            # pyrefly: ignore.  __getattr__ delegates the query surface at
            # runtime, but pyrefly cannot verify that structurally.
            _SynchronizingExtension(
                RealPyMOLCmdExtension(loaded_fixture), finished
            ),
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
        )
        before = capture_session_state(loaded_fixture)

        assert _run_copilot(loaded_fixture, finished) < (
            INVOCATION_DEADLINE_SECONDS
        )

        after = capture_session_state(loaded_fixture)
    finally:
        server.close()

    assert output == [
        "copilot: the repair budget was spent with no validated plan. "
        "The model could not produce a valid plan after retrying. "
        "Rephrase the intent more specifically and run copilot again."
    ]
    assert_session_unchanged(before, after)


def test_unavailable_server_path_reports_bounded_diagnostic(
    loaded_fixture: PyMOLCmd,
) -> None:
    """An unreachable loopback port reports a bounded diagnostic only."""
    dead_server = LoopbackPlanServer(CREDENTIAL, _lifecycle())
    dead_port = dead_server.port
    dead_server.close()

    output: list[str] = []
    finished = threading.Event()
    register_copilot(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        _SynchronizingExtension(
            RealPyMOLCmdExtension(loaded_fixture), finished
        ),
        LoopbackPlanClient(dead_port, CREDENTIAL, timeout_seconds=2.0),
        output.append,
    )
    before = capture_session_state(loaded_fixture)

    assert _run_copilot(loaded_fixture, finished) < (
        INVOCATION_DEADLINE_SECONDS
    )

    after = capture_session_state(loaded_fixture)

    assert len(output) == 1, (
        f"expected exactly one bounded diagnostic line, got {output!r}"
    )
    assert output[0].startswith("copilot: loopback request failed")
    assert_session_unchanged(before, after)


def test_sabotage_mutation_is_detected_by_state_comparison(
    loaded_fixture: PyMOLCmd,
) -> None:
    """A deliberate mutation between snapshots fails the comparison helper."""
    before = capture_session_state(loaded_fixture)

    loaded_fixture.color("blue", "chain A")

    after = capture_session_state(loaded_fixture)

    assert before != after
    with pytest.raises(AssertionError):
        assert_session_unchanged(before, after)


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (the same defect confirmed empirically
    # and fixed the same way in tests/data/test_gold_case_verifier.py's
    # __main__ block). os._exit bypasses that interpreter-shutdown window
    # entirely, so pytest's real result is what Bazel actually sees.
    # os._exit skips the normal stdio flush, so flush explicitly first --
    # otherwise a real failure's traceback and summary can be silently lost
    # from the captured test log (also confirmed empirically).
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
