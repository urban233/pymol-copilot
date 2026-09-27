# Copyright 2026 PyMOL Copilot contributors.
"""Shared real-PyMOL harness for docs/master_plan.md item 12's scenarios.

Every real-PyMOL end-to-end module in this directory launches PyMOL once
(module-scoped `real_pymol`) and reuses this file's `ConsoleDriver`,
`SessionFingerprint`, and `build_lifecycle` rather than re-deriving them,
the same way `tests/integration/test_real_pymol_command.py` built its own
harness in one place.

`SessionFingerprint` is deliberately independent of `pmc_core.snapshot`; see
this package's own README for why that separation matters. It reads only
PyMOL's own query surface: `get_names`, `iterate`, `iterate_state`,
`count_atoms`, and `get_view`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import threading
import time
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pmc_agent.graph import MAX_REPAIR_ATTEMPTS
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.session import RequestGraphSession
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import execute
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_core.policy import evaluate_plan
from pmc_server.lifecycle import RequestGraphLifecycle

import winstage

#: The credential every scenario's own loopback server expects. Not a real
#: secret: it never leaves this process, and step 6's production entrypoint
#: mints one with `secrets.token_urlsafe` instead.
CREDENTIAL = "e2e-scenario-secret"

#: The fixture also used by tests/integration -- shared through a Bazel
#: filegroup so the two real-PyMOL suites cannot disagree about what "the
#: fixture" is.
OBJECT_NAME = "two_chain_fixture"
FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "integration"
    / "testdata"
    / "two_chain_fixture.pdb"
)

#: How long one console invocation may take before a test concludes PyMOL's
#: callback never returned. Raised well above
#: tests/integration/test_real_pymol_command.py's own 15.0: that module's
#: `copilot` fakes the sidecar executor and spawns only one real process
#: (the fidelity probe). This directory's own scenarios 1 and 2
#: deliberately leave both the fidelity probe and the executor at their
#: real defaults, so a single `copilot` call chains two real headless
#: PyMOL launches -- confirmed empirically to exceed 15.0s under this
#: sandbox's own scheduling.
INVOCATION_DEADLINE_SECONDS = 45.0


def fake_exact_probe(request: FidelityRequest) -> FidelityReport:
    """Report the exact reconstruction, without spawning a second sidecar.

    Used only by scenarios that fake fidelity on purpose (the stale-plan,
    denied-command, and server-unavailable scenarios never reach the
    fidelity comparison's own subject). Scenarios 1 and 2 pass the real
    `pmc_core.executor.probe_fidelity` instead.

    Args:
        request: The candidate snapshot to "reconstruct".

    Returns:
        A `STATUS_OK` report whose reconstruction is the request's own
        input, verbatim -- an exact match by construction.
    """
    return FidelityReport(
        executor_version=request.executor_version,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:" + "0" * 64,
        reconstructed_snapshot_json=request.snapshot_json,
        child_pid=None,
        child_terminated=True,
        elapsed_seconds=0.0,
    )


def fake_ok_executor(_request: ExecutionRequest) -> ExecutionReport:
    """Report success for any request, without spawning a second real PyMOL.

    Used only by scenarios whose subject is not the sidecar itself (the
    stale-plan scenario): the server's own `_validating` node calls the
    executor on every successful parse, regardless of client-side
    fidelity, so a scenario that fakes the client's probe must fake this
    too or it still spawns a real sidecar per preview.

    Args:
        _request: Ignored.

    Returns:
        A minimal `STATUS_OK` report.
    """
    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:" + "0" * 64,
        resulting_fingerprint="sha256:" + "0" * 64,
        selection_counts=(),
        command_outcomes=(),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=0.01,
    )


def counting(
    delegate: Callable[[Any], Any],
) -> tuple[Callable[[Any], Any], list[Any]]:
    """Wrap a callable so a test can assert it was never (or only) called.

    Args:
        delegate: The real callable to wrap -- never a fake, so a count of
            zero is evidence about the real spawn path, not about a
            double's own behavior.

    Returns:
        A `(wrapped, calls)` pair. `wrapped` forwards every call to
        `delegate` and appends its argument to `calls` first.
    """
    calls: list[Any] = []

    def wrapped(argument: Any) -> Any:
        calls.append(argument)
        return delegate(argument)

    return wrapped, calls


@dataclass(frozen=True)
class SessionFingerprint:
    """A comparable slice of live PyMOL state, captured PyMOL-natively.

    Attributes:
        object_names: The complete sorted name list from
            `get_names("all")`, so a plan-created selection a partial
            restore left behind is caught.
        chain_a_atom_count: Atom count for `chain A`.
        chain_b_atom_count: Atom count for `chain B`.
        coordinates: Per-atom `(index, x, y, z)` tuples, state 1.
        colors: Per-atom `(index, color)` tuples.
        representations: Per-atom `(index, reps)` tuples.
        labels: Per-atom `(index, label)` tuples.
        view: The 18-float camera view `get_view()` returns. Included
            even though `pmc_core.snapshot.structure_digest` deliberately
            excludes it: a refusal path that silently re-oriented the
            camera is still an unapproved mutation of the user's session.
    """

    object_names: tuple[str, ...]
    chain_a_atom_count: int
    chain_b_atom_count: int
    coordinates: tuple[tuple[int, float, float, float], ...]
    colors: tuple[tuple[int, int], ...]
    representations: tuple[tuple[int, int], ...]
    labels: tuple[tuple[int, str], ...]
    view: tuple[float, ...]


def capture_fingerprint(cmd: Any) -> SessionFingerprint:
    """Capture the complete real-PyMOL fingerprint this directory compares.

    Args:
        cmd: The real PyMOL `cmd` module.

    Returns:
        The current fingerprint.
    """
    coordinates: list[tuple[int, float, float, float]] = []
    cmd.iterate_state(
        1,
        "all",
        "coordinates.append((index, x, y, z))",
        space={"coordinates": coordinates},
    )
    colors: list[tuple[int, int]] = []
    representations: list[tuple[int, int]] = []
    labels: list[tuple[int, str]] = []
    cmd.iterate(
        "all",
        "colors.append((index, color));"
        "representations.append((index, reps));"
        "labels.append((index, label))",
        space={
            "colors": colors,
            "representations": representations,
            "labels": labels,
        },
    )
    return SessionFingerprint(
        object_names=tuple(sorted(cmd.get_names("all"))),
        chain_a_atom_count=cmd.count_atoms("chain A"),
        chain_b_atom_count=cmd.count_atoms("chain B"),
        coordinates=tuple(coordinates),
        colors=tuple(colors),
        representations=tuple(representations),
        labels=tuple(labels),
        view=tuple(cmd.get_view()),
    )


def assert_unchanged(
    before: SessionFingerprint, after: SessionFingerprint
) -> None:
    """Fail when a supposedly read-only path changed observable state.

    Args:
        before: Fingerprint captured immediately before the invocation.
        after: Fingerprint captured immediately after it.
    """
    assert before == after


def assert_changed(
    before: SessionFingerprint, after: SessionFingerprint
) -> None:
    """Fail when an approved apply left the session observably untouched.

    Args:
        before: Fingerprint captured immediately before the apply.
        after: Fingerprint captured immediately after it.
    """
    assert before != after


class ConsoleDriver:
    """Drive `copilot*` commands through PyMOL's own dispatch, synchronously.

    `cmd.do()` queues a command onto PyMOL's own thread and returns as soon
    as it is queued, not when it has run -- established directly in
    `tests/integration/test_real_pymol_command.py`'s own
    `_SynchronizingExtension` docstring, and reused here unchanged: a
    `threading.Event` set from a `finally` around the registered callback,
    so a raising callback still releases the waiter and surfaces as its
    own assertion rather than a deadline timeout.
    """

    def __init__(self, cmd: Any) -> None:
        """Wrap a real PyMOL `cmd` module for synchronized dispatch.

        Args:
            cmd: The real PyMOL `cmd` module.
        """
        self._cmd = cmd
        self._finished = threading.Event()

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register one command, wrapped to signal completion.

        `pmc_client.command.CopilotCommandClient.register()` calls this
        once per registered command and stores this driver as its own live
        session, so `__getattr__` below must forward the query surface
        (`get_names`, `iterate`, ...) through to the real `cmd` it wraps.

        Args:
            name: Command name to register.
            callback: Function invoked for the registered command.
        """

        def synchronized(argument: str = "") -> None:
            try:
                callback(argument)
            finally:
                self._finished.set()

        self._cmd.extend(name, synchronized)

    def __getattr__(self, name: str) -> Any:
        """Forward every other attribute to the wrapped real `cmd` module.

        Args:
            name: The attribute name being accessed.

        Returns:
            The real `cmd` module's own attribute.
        """
        return getattr(self._cmd, name)

    def run(self, command_line: str) -> float:
        """Dispatch one PML command line and wait for its callback.

        Args:
            command_line: The exact command line to dispatch, e.g.
                `"copilot_apply p-<id>"`.

        Returns:
            Seconds from dispatch until the callback completed.

        Raises:
            AssertionError: If the callback did not complete within
                `INVOCATION_DEADLINE_SECONDS`.
        """
        self._finished.clear()
        started = time.monotonic()
        self._cmd.do(command_line)
        completed = self._finished.wait(INVOCATION_DEADLINE_SECONDS)
        elapsed = time.monotonic() - started
        assert completed, (
            f"{command_line!r} did not complete within "
            f"{INVOCATION_DEADLINE_SECONDS}s of dispatch"
        )
        return elapsed


def build_lifecycle(
    *,
    completions: Sequence[CompletionResult] | None = None,
    executor: Callable[[ExecutionRequest], ExecutionReport] = execute,
    policy_validator: Callable[[ActionPlan], PlanDecision] = evaluate_plan,
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> RequestGraphLifecycle:
    """Build a request-graph lifecycle over one fresh session.

    Args:
        completions: Completions the scripted `FakeEngine` renders, in
            order, one per attempt. Defaults to a fixed two-command plan
            (select, color) repeated for every repair attempt.
        executor: Forwarded to `RequestGraphSession`; defaults to the real
            `pmc_core.executor.execute`.
        policy_validator: Forwarded to `RequestGraphSession`; defaults to
            the real `pmc_core.policy.evaluate_plan`.
        max_repair_attempts: Forwarded to `RequestGraphSession`.

    Returns:
        A lifecycle ready to hand to `LoopbackPlanServer`.
    """
    if completions is None:
        # `show spheres`, not `show sticks`: confirmed empirically that
        # `two_chain_fixture.pdb`'s atoms already carry `sticks` (PyMOL's
        # `cRepCyl`) in their default per-atom `reps` bitmask, alongside
        # `cRepNonbondedSphere` and `cRepCartoon` -- an unbonded few-atom
        # fixture's own default display, not a bug in this harness. A
        # `show sticks` there is a genuine no-op, which would make
        # scenario 1's own "representations changed" assertion vacuous.
        # `spheres` (`cRepSphere`) is not in that default set.
        completions = [
            CompletionResult(
                "select copilot_selection, chain A\n"
                "color red, copilot_selection\n"
                "show spheres, copilot_selection\n"
                "orient copilot_selection\n",
                "m-1",
                STOP_END,
            )
            for _ in range(max_repair_attempts + 1)
        ]
    engine = FakeEngine(list(completions))
    session = RequestGraphSession(
        engine=engine,
        executor=executor,
        policy_validator=policy_validator,
        max_repair_attempts=max_repair_attempts,
    )
    return RequestGraphLifecycle(session=session)


def utc_now() -> datetime:
    """Return the current UTC moment, matching the client's own default.

    Returns:
        The current timezone-aware UTC time.
    """
    return datetime.now(UTC)


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[Any]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL `cmd` module.
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
def loaded_fixture(real_pymol: Any) -> Iterator[Any]:
    """Load the two-chain fixture fresh for one test and clear it after.

    `real_pymol` is module-scoped -- one real PyMOL process is shared by
    every test in a module -- so this clears the *entire* session, not
    only the fixture object, on both ends. A scenario that leaves an
    applied plan's own selection in place on purpose (scenario 1 never
    rolls back, to prove approval mutated something durable) would
    otherwise leak that selection into the next test's own "before"
    fingerprint, exactly as this module's own tests are the record of
    (docs/master_plan.md item 12).

    Args:
        real_pymol: The real PyMOL `cmd` module.

    Yields:
        The real PyMOL `cmd` module with only the fixture object loaded.
    """
    real_pymol.delete("all")
    real_pymol.load(str(FIXTURE_PATH), OBJECT_NAME)
    try:
        yield real_pymol
    finally:
        real_pymol.delete("all")
