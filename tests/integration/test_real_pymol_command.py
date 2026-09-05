# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL, real-server evidence for the non-mutating copilot command.

Every collaborator here is a real production component: real headless
Open-Source PyMOL (`pymol.finish_launching(['pymol', '-qc'])`), PyMOL's own
command registry (`cmd.extend`/`cmd.do`), the real authenticated loopback
server (`pmc_server.transport.LoopbackPlanServer`) driven by the real
`pmc_server.lifecycle.PlanRequestLifecycle`, and the real
`pmc_client.transport.LoopbackPlanClient` and
`pmc_client.command.register_copilot`. Nothing here is a transport, server,
policy, or PyMOL test double.

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
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import time
from collections.abc import Callable
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pytest

from pmc_client.command import FIXTURE_INTENT
from pmc_client.command import register_copilot
from pmc_client.transport import LoopbackPlanClient
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_server.lifecycle import PlanRequestLifecycle
from pmc_server.transport import LoopbackPlanServer

CREDENTIAL = "real-pymol-integration-secret"
OBJECT_NAME = "two_chain_fixture"
FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "two_chain_fixture.pdb"
)
INVOCATION_DEADLINE_SECONDS = 5.0
FIXTURE_PML = (
    "select copilot_selection, chain A\ncolor red, copilot_selection\n"
)
PREVIEW_DISCLAIMER = (
    "copilot preview: this is a fixed, policy-checked plan preview. "
    "Loaded-state fidelity, execution, and scientific intent were "
    "not validated, and nothing was applied to this session. The "
    "snapshot value above is a fixture placeholder, not a computed "
    "structure checksum."
)


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

    def get_names(self) -> list[str]:
        """Return the names of every loaded object.

        Returns:
            The list of loaded object names.
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


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[PyMOLCmd]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL cmd module.
    """
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


def test_success_path_previews_without_mutating_session(
    loaded_fixture: PyMOLCmd,
) -> None:
    """A real, policy-allowed plan reports an honest preview and no mutation."""
    output: list[str] = []
    server = LoopbackPlanServer(CREDENTIAL, PlanRequestLifecycle())
    try:
        server.start()
        register_copilot(
            RealPyMOLCmdExtension(loaded_fixture),
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
        )
        before = capture_session_state(loaded_fixture)

        started = time.monotonic()
        loaded_fixture.do(f"copilot {FIXTURE_INTENT}")
        assert time.monotonic() - started < INVOCATION_DEADLINE_SECONDS

        after = capture_session_state(loaded_fixture)
    finally:
        server.close()

    assert output == [
        "copilot validation: passed",
        FIXTURE_PML,
        PREVIEW_DISCLAIMER,
    ]
    assert_session_unchanged(before, after)


def test_typed_rejection_path_reports_bounded_diagnostic(
    loaded_fixture: PyMOLCmd,
) -> None:
    """A real server-side policy denial reports a bounded diagnostic only."""
    output: list[str] = []
    server = LoopbackPlanServer(
        CREDENTIAL, PlanRequestLifecycle(policy_validator=always_deny)
    )
    try:
        server.start()
        register_copilot(
            RealPyMOLCmdExtension(loaded_fixture),
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
        )
        before = capture_session_state(loaded_fixture)

        started = time.monotonic()
        loaded_fixture.do(f"copilot {FIXTURE_INTENT}")
        assert time.monotonic() - started < INVOCATION_DEADLINE_SECONDS

        after = capture_session_state(loaded_fixture)
    finally:
        server.close()

    assert output == [
        "copilot failed (policy_denied; not retryable): "
        "plan was denied by server policy"
    ]
    assert_session_unchanged(before, after)


def test_unavailable_server_path_reports_bounded_diagnostic(
    loaded_fixture: PyMOLCmd,
) -> None:
    """An unreachable loopback port reports a bounded diagnostic only."""
    dead_server = LoopbackPlanServer(CREDENTIAL, PlanRequestLifecycle())
    dead_port = dead_server.port
    dead_server.close()

    output: list[str] = []
    register_copilot(
        RealPyMOLCmdExtension(loaded_fixture),
        LoopbackPlanClient(dead_port, CREDENTIAL, timeout_seconds=2.0),
        output.append,
    )
    before = capture_session_state(loaded_fixture)

    started = time.monotonic()
    loaded_fixture.do(f"copilot {FIXTURE_INTENT}")
    assert time.monotonic() - started < INVOCATION_DEADLINE_SECONDS

    after = capture_session_state(loaded_fixture)

    assert len(output) == 1
    assert output[0].startswith("copilot unavailable: ")
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
    raise SystemExit(pytest.main([__file__]))
