# Copyright 2026 PyMOL Copilot contributors.
"""Headless client-server test for the public non-mutating command path."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
import uuid

from pmc_client.command import FIXTURE_INTENT
from pmc_client.command import register_copilot
from pmc_client.transport import LoopbackPlanClient
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_server.lifecycle import PlanRequestLifecycle
from pmc_server.transport import LoopbackPlanServer

FIXTURE_PML = (
    "select copilot_selection, chain A\ncolor red, copilot_selection\n"
)


@dataclass
class DisposablePyMOLAdapter:
    """Register commands while recording every supported session mutation."""

    commands: dict[str, Callable[[str], None]] = field(default_factory=dict)
    mutations: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    selections: dict[str, str] = field(
        default_factory=lambda: {"existing_selection": "chain B"}
    )
    colors: dict[str, str] = field(
        default_factory=lambda: {"existing_selection": "blue"}
    )

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register a command callback without changing molecular state."""
        self.commands[name] = callback

    def select(self, name: str, expression: str) -> None:
        """Record a selection mutation if the client attempts one."""
        self.mutations.append(("select", (name, expression)))
        self.selections[name] = expression

    def color(self, color: str, target: str) -> None:
        """Record a color mutation if the client attempts one."""
        self.mutations.append(("color", (color, target)))
        self.colors[target] = color

    def do(self, command: str) -> None:
        """Record rendered PML execution if the client attempts it."""
        self.mutations.append(("do", (command,)))


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
    assert output == ["copilot validation: passed", FIXTURE_PML]
    assert adapter.mutations == []
    assert adapter.selections == original_selections
    assert adapter.colors == original_colors


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__]))
