# Copyright 2026 PyMOL Copilot contributors.
"""Headless client-server test for the public non-mutating command path."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import pytest
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from pmc_client.command import FIXTURE_INTENT
from pmc_client.command import register_copilot
from pmc_client.session import extract_live_snapshot
from pmc_client.transport import LoopbackPlanClient
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_server.lifecycle import PlanRequestLifecycle
from pmc_server.transport import LoopbackPlanServer

OBJECT_NAME = "fx"


@dataclass(frozen=True)
class _FakeAtom:
    """One in-memory atom record the fake adapter can serve."""

    id: int
    name: str
    alt: str
    resn: str
    chain: str
    resi_number: int
    ins_code: str
    symbol: str
    hetatm: bool
    q: float
    b: float
    coord: tuple[float, float, float]
    color: int
    label: str | None
    reps: tuple[str, ...]


@dataclass(frozen=True)
class _FakeModel:
    """A minimal chempy-model stand-in exposing `.atom` and `.bond`."""

    atom: list[_FakeAtom] = field(default_factory=list)
    bond: list[Any] = field(default_factory=list)


_DEFAULT_ATOM = _FakeAtom(
    id=1,
    name="CA",
    alt="",
    resn="ALA",
    chain="A",
    resi_number=1,
    ins_code="",
    symbol="C",
    hetatm=False,
    q=1.0,
    b=20.0,
    coord=(1.0, 2.0, 3.0),
    color=0,
    label=None,
    reps=(),
)


@dataclass
class DisposablePyMOLAdapter:
    """Register commands while recording every supported session mutation.

    Also implements `pmc_client.command.LivePyMOLSession`'s query surface,
    backed by one fixed fake object and atom, so `copilot()` can resolve
    and extract from it -- distinct from `select`/`color`/`do` below,
    which record only genuine mutation *attempts*, proving `copilot`
    never makes one.
    """

    commands: dict[str, Callable[[str], None]] = field(default_factory=dict)
    mutations: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    selections: dict[str, str] = field(
        default_factory=lambda: {"existing_selection": "chain B"}
    )
    colors: dict[str, str] = field(
        default_factory=lambda: {"existing_selection": "blue"}
    )
    atoms: tuple[_FakeAtom, ...] = (_DEFAULT_ATOM,)

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register a command callback without changing molecular state.

        Args:
            name: Command name to register.
            callback: Function invoked for the registered command.
        """
        self.commands[name] = callback

    def select(self, name: str, expression: str) -> None:
        """Record a selection mutation if the client attempts one.

        Args:
            name: Selection name supplied by the attempted command.
            expression: Selection expression supplied by the attempted command.
        """
        self.mutations.append(("select", (name, expression)))
        self.selections[name] = expression

    def color(self, color: str, target: str) -> None:
        """Record a color mutation if the client attempts one.

        Args:
            color: Color supplied by the attempted command.
            target: Selection target supplied by the attempted command.
        """
        self.mutations.append(("color", (color, target)))
        self.colors[target] = color

    def do(self, command: str) -> None:
        """Record rendered PML execution if the client attempts it.

        Args:
            command: Rendered command text supplied for execution.
        """
        self.mutations.append(("do", (command,)))

    def get_names(
        self,
        kind: str = "objects",  # noqa: ARG002
        *,
        enabled_only: int = 0,
    ) -> list[str]:
        """Return this adapter's one fake molecule name.

        `kind` and `enabled_only` keep `PyMOLSession`'s own parameter
        names, not underscore-prefixed stand-ins: pyrefly's structural
        Protocol check requires a matching name for a parameter callable
        by keyword, and `extract()` genuinely calls this one by keyword
        (`cmd.get_names("objects", enabled_only=1)`).

        Args:
            kind: Ignored; this fake carries only one object.
            enabled_only: Every fake object counts as enabled regardless
                of this value, so 0 and 1 return the same list; PyMOL
                itself accepts no other value here.

        Returns:
            The one molecule name.
        """
        assert enabled_only in (0, 1)
        return [OBJECT_NAME]

    def get_type(self, name: str) -> str:
        """Return "object:molecule" for the fake object's own name.

        Args:
            name: The object name to look up.

        Returns:
            "object:molecule".
        """
        assert name == OBJECT_NAME
        return "object:molecule"

    def count_states(self, selection: str) -> int:  # noqa: ARG002
        """Return the fixed one-state count this fake adapter serves.

        Args:
            selection: Ignored; this fake has exactly one state.

        Returns:
            1.
        """
        return 1

    def get_model(self, selection: str, *, state: int) -> _FakeModel:  # noqa: ARG002
        """Return every fake atom as one chempy-like model.

        `selection` and `state` keep `PyMOLSession`'s own parameter names
        for the same reason `get_names()` above does.

        Args:
            selection: Ignored; this fake has one object's worth of atoms.
            state: Must be 1, the only state `count_states()` reports.

        Returns:
            The fake model.
        """
        assert state == 1
        return _FakeModel(atom=list(self.atoms))

    def iterate(
        self, selection: str, expression: str, *, space: dict[str, object]
    ) -> None:
        """Evaluate `expression` once per atom matching `selection`.

        Args:
            selection: An object name, optionally followed by
                " and rep <name>" -- the only two selection shapes
                pmc_core.snapshot.extract() builds.
            expression: The Python statement to evaluate per atom.
            space: The namespace mutated by `expression`.
        """
        rep_filter = None
        if " and rep " in selection:
            rep_filter = selection.rsplit(" and rep ", 1)[1]
        for atom in self.atoms:
            if rep_filter is not None and rep_filter not in atom.reps:
                continue
            local_namespace = {
                "ID": atom.id,
                "color": atom.color,
                "label": atom.label,
            }
            exec(expression, {}, {**space, **local_namespace})

    def get_view(self) -> tuple[float, ...]:
        """Return a fixed 18-float view.

        Returns:
            18 zeros.
        """
        return tuple(0.0 for _ in range(18))

    def get(self, setting: str, selection: str) -> str:  # noqa: ARG002
        """Return a fixed setting value.

        `setting` and `selection` keep `PyMOLSession`'s own parameter
        names for the same reason `get_names()` above does.

        Args:
            setting: Ignored.
            selection: Ignored.

        Returns:
            A fixed placeholder value.
        """
        return "1.00000"


def _exact_probe(
    adapter: DisposablePyMOLAdapter,
) -> Callable[[FidelityRequest], FidelityReport]:
    """Build a probe that reports the adapter's own snapshot back.

    A fake probe, not the real `pmc_core.executor.probe_fidelity`: this
    test is about client-server wiring, not real sidecar fidelity, which
    tests/integration/test_client_fidelity_real_pymol.py owns.

    Args:
        adapter: The fake adapter `copilot()` will independently extract
            from too -- this probe reports exactly what that extraction
            produces, so `check_fidelity()` finds an empty diff.

    Returns:
        A probe reporting an exact match.
    """
    snapshot, _digest = extract_live_snapshot(adapter, OBJECT_NAME)
    report = FidelityReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest=structure_digest(snapshot),
        reconstructed_snapshot_json=to_json(snapshot),
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=0.5,
        warnings=(),
    )
    return lambda _request: report


def test_public_command_round_trip_renders_without_session_mutation() -> None:
    """The public command preserves correlation and never mutates PyMOL."""
    requests: list[PlanRequestV1] = []
    responses: list[ValidatedPlanResponseV1 | FailedPlanResponseV1] = []
    lifecycle = PlanRequestLifecycle(
        plan_id_source=lambda: "33333333-3333-4333-8333-333333333333",
        timestamp_source=iter(
            ("2026-08-26T14:22:03.124Z", "2026-08-26T14:22:03.220Z")
        ).__next__,
    )

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
        response = lifecycle(request)
        responses.append(response)
        return response

    adapter = DisposablePyMOLAdapter()
    original_selections = adapter.selections.copy()
    original_colors = adapter.colors.copy()
    output: list[str] = []
    with LoopbackPlanServer("secret", record_lifecycle) as server:
        client = register_copilot(
            adapter,
            LoopbackPlanClient(server.port, "secret"),
            output.append,
            probe=_exact_probe(adapter),
        )
        adapter.commands["copilot"](FIXTURE_INTENT)

    request = requests[0]
    response = responses[0]
    assert isinstance(response, ValidatedPlanResponseV1)
    assert uuid.UUID(request.request_id).version == 4
    assert uuid.UUID(request.session_id).version == 4
    assert request.session_id == client.session_id
    assert response.request_id == request.request_id
    assert response.session_id == request.session_id
    assert request.snapshot.object_name == OBJECT_NAME
    assert request.snapshot.digest != "sha256:example-chain-a-digest"
    assert output[0].startswith("copilot fidelity: exact")
    assert output[1].startswith("copilot plan:")
    assert "1 | select copilot_selection, chain A" in output[1]
    assert output[2].startswith("copilot checked:")
    assert output[3].startswith("copilot apply with: copilot_apply ")
    assert adapter.mutations == []
    assert adapter.selections == original_selections
    assert adapter.colors == original_colors


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
