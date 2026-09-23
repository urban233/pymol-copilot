# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic command-level evidence for explicit recovery rollback."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from pmc_client.command import AppliedPlan
from pmc_client.command import CopilotCommandClient
from pmc_client.command import PlanTransport
from pmc_client.recovery import RecoveryStore
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot

_PLAN_ID = "33333333-3333-4333-8333-333333333333"


def _snapshot() -> ObjectSnapshot:
    """Build the smallest complete pre-apply snapshot for rollback tests."""
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="molecule",
        enabled=True,
        states=(),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )


@dataclass
class _Cmd:
    """Minimal save/load command surface with observable call order."""

    events: list[str]

    def extend(self, _name: str, _callback: Callable[[str], None]) -> None:
        """Accept command registration; this test invokes the method directly."""

    def save(self, filename: str) -> None:
        """Materialize the private recovery file for the store."""
        self.events.append("save")
        Path(filename).write_bytes(b"whole session")

    def load(self, filename: str, *, partial: int) -> None:  # noqa: ARG002
        """Record replacement-session load calls."""
        assert partial == 0
        self.events.append("load")


@dataclass
class _Transport:
    """Record the sole terminal outcome rollback is allowed to send."""

    outcomes: list[ApplyOutcomeRequestV1]

    def report_apply_outcome(
        self, request: ApplyOutcomeRequestV1
    ) -> FailedPlanResponseV1:
        """Record and acknowledge a graph terminal outcome."""
        self.outcomes.append(request)
        return FailedPlanResponseV1(
            request.request_id,
            request.session_id,
            FailureEnvelopeV1("rolled_back", "rolled_back", False),
        )


def _client_with_recovery(
    tmp_path: Path,
) -> tuple[CopilotCommandClient, _Cmd, RecoveryStore, list[str], _Transport]:
    """Build a client with a retained successful-apply recovery point."""
    events: list[str] = []
    cmd = _Cmd(events)
    store = RecoveryStore(tmp_path)
    store.save(cmd, _PLAN_ID)
    output: list[str] = []
    transport = _Transport([])
    client = CopilotCommandClient(
        cast(PlanTransport, transport), output.append, recovery_store=store
    )
    client.register(cmd)  # pyrefly: ignore: only rollback's load is exercised.
    client._applied_plan = AppliedPlan(
        plan_id=_PLAN_ID,
        object_name="molecule",
        before=_snapshot(),
        names_before=("molecule",),
        post_apply_digest="sha256:after",
    )
    return client, cmd, store, output, transport


def test_rollback_warns_then_restores_consumes_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback warns before its load and removes the point only when clean."""
    client, cmd, store, output, transport = _client_with_recovery(tmp_path)
    monkeypatch.setattr(
        "pmc_client.command.extract_live_snapshot",
        lambda *_args: (_snapshot(), "sha256:after"),
    )
    monkeypatch.setattr(
        "pmc_client.command.compare_recovery", lambda *_a, **_k: ()
    )

    client.copilot_rollback(f"p-{_PLAN_ID}")

    assert output[0].startswith(
        "copilot_rollback: replacing the entire session"
    )
    assert cmd.events == ["save", "load"]
    assert store.retained is None
    assert transport.outcomes[0].outcome == "rolled_back"
    assert output[-1].endswith(
        "rolled back and its recovery point was removed."
    )


def test_rollback_refusals_do_not_load_or_consume(tmp_path: Path) -> None:
    """Absent and mismatched identifiers leave the whole session untouched."""
    client, cmd, store, output, transport = _client_with_recovery(tmp_path)

    client.copilot_rollback("p-not-the-plan")

    assert output == [
        "copilot_rollback: plan p-not-the-plan is not the applied plan"
    ]
    assert cmd.events == ["save"]
    assert store.retained is not None
    assert transport.outcomes == []


def test_unclean_rollback_preserves_the_point_and_latches_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dirty restored session is contained instead of being consumed."""
    client, cmd, store, output, transport = _client_with_recovery(tmp_path)
    monkeypatch.setattr(
        "pmc_client.command.extract_live_snapshot",
        lambda *_args: (_snapshot(), "sha256:later-change"),
    )
    monkeypatch.setattr(
        "pmc_client.command.compare_recovery",
        lambda *_args, **_kwargs: ("view differs",),
    )

    client.copilot_rollback(f"p-{_PLAN_ID}")

    assert cmd.events == ["save", "load"]
    assert store.retained is None
    preserved = store.directory / f"plan-{_PLAN_ID}.pse"
    assert preserved.exists()
    assert "later changes will be discarded" in output[1]
    assert "comparison failed" in output[-1]
    assert transport.outcomes == []

    output.clear()
    client.copilot_rollback(f"p-{_PLAN_ID}")
    assert output[0].startswith("copilot_rollback: Copilot is halted")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
