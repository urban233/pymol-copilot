# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL proof that every approval refusal leaves state untouched."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pmc_client.command import CopilotCommandClient
from pmc_client.command import PendingPlan
from pmc_client.fidelity import FidelityOutcome
from pmc_client.recovery import RecoveryStore
from pmc_client.session import extract_live_snapshot
from pmc_client.transport import TransportError
from pmc_core.executor import REASON_OK
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import NamedSelection
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.policy import PlanDecision
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_UNAVAILABLE
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1

from session_fingerprint import assert_session_unchanged
from session_fingerprint import capture_session_fingerprint

import winstage


_OBJECT = "refusal_fixture"
_PLAN_ID = "33333333-3333-4333-8333-333333333333"
_EXPIRY = "2026-08-26T14:27:03.220Z"
_NOW = datetime(2026, 8, 26, 14, 23, tzinfo=UTC)


@dataclass
class _Transport:
    """Configurable in-process server edge; it never touches PyMOL."""

    apply_factory: Callable[
        [ApplyRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1
    ]
    reject_factory: Callable[[RejectRequestV1], FailedPlanResponseV1]

    def submit(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Refuse unexpected preview requests in this apply-focused matrix."""
        raise AssertionError(
            f"unexpected preview request: {request.request_id}"
        )

    def apply(
        self, request: ApplyRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Return this case's preselected apply handshake response."""
        return self.apply_factory(request)

    def reject(self, request: RejectRequestV1) -> FailedPlanResponseV1:
        """Return this case's preselected rejection response."""
        return self.reject_factory(request)

    def report_apply_outcome(
        self, request: ApplyOutcomeRequestV1
    ) -> FailedPlanResponseV1:
        """Fail if a refusal reaches a terminal mutation outcome."""
        raise AssertionError(f"unexpected apply outcome: {request.outcome}")


def _plan() -> ActionPlan:
    """Return the normal, policy-allowed two-command fixture plan."""
    return ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_selection",
                expression=SelectionExpression(
                    clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
                ),
            ),
            ColorOperation("red", NamedSelection("copilot_selection")),
        )
    )


def _failed_apply(request: ApplyRequestV1) -> FailedPlanResponseV1:
    """Return the server-side expiry case after client re-verification."""
    return FailedPlanResponseV1(
        request.request_id,
        request.session_id,
        FailureEnvelopeV1("expired", "the plan's TTL had already passed", True),
    )


def _rejected(request: RejectRequestV1) -> FailedPlanResponseV1:
    """Acknowledge an explicit rejection without altering the session."""
    return FailedPlanResponseV1(
        request.request_id,
        request.session_id,
        FailureEnvelopeV1("rejected", "rejected", False),
    )


def _client(
    cmd: Any,
    root: Path,
    *,
    apply_factory: Callable[
        [ApplyRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1
    ] = _failed_apply,
) -> tuple[CopilotCommandClient, RecoveryStore]:
    """Create a registered client with an empty, hermetic recovery root."""
    store = RecoveryStore(root)
    client = CopilotCommandClient(
        _Transport(apply_factory, _rejected),
        lambda _line: None,
        recovery_store=store,
        now_factory=lambda: _NOW,
    )
    client.register(cmd)
    return client, store


def _pending(
    client: CopilotCommandClient,
    cmd: Any,
    *,
    session_id: str | None = None,
    digest: str | None = None,
    applicable: bool = True,
    fidelity: FidelityOutcome | None = None,
    expires_at: str = _EXPIRY,
) -> PendingPlan:
    """Build pending facts bound to the current real PyMOL session."""
    _snapshot, current_digest = extract_live_snapshot(cmd, _OBJECT)
    resolved_digest = current_digest if digest is None else digest
    resolved_fidelity = fidelity or FidelityOutcome(
        FIDELITY_EXACT,
        REASON_OK,
        (),
        resolved_digest,
        resolved_digest,
    )
    return PendingPlan(
        plan_id=_PLAN_ID,
        session_id=client.session_id if session_id is None else session_id,
        snapshot_digest=resolved_digest,
        action_plan=_plan(),
        applicable=applicable,
        fidelity=resolved_fidelity,
        expires_at=expires_at,
        model_identity="test-model@checkpoint",
        contract_manifest=CURRENT_CONTRACT_MANIFEST,
    )


def _validated_for(
    pending: PendingPlan,
) -> Callable[[ApplyRequestV1], ValidatedPlanResponseV1]:
    """Build an authenticated response that matches `pending` exactly."""

    def response(request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        return ValidatedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            received_at="2026-08-26T14:22:03.123Z",
            validated_at="2026-08-26T14:22:03.123Z",
            action_plan=pending.action_plan,
            validation=ValidationReportV1(
                "passed", pending.snapshot_digest, True, ()
            ),
            plan_id=pending.plan_id,
            snapshot_digest=pending.snapshot_digest,
            expires_at=pending.expires_at,
            model_identity=pending.model_identity,
        )

    return response


@pytest.fixture(scope="module")
def real_pymol() -> Any:
    """Launch one actual headless PyMOL interpreter for this evidence."""
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


def _reset(cmd: Any) -> None:
    """Make a fresh two-chain object before each refusal case."""
    cmd.delete("all")
    cmd.pseudoatom(
        _OBJECT,
        name="CA",
        resn="ALA",
        resi="1",
        chain="A",
        pos=(0.0, 0.0, 0.0),
    )
    cmd.pseudoatom(
        _OBJECT,
        name="CA",
        resn="GLY",
        resi="1",
        chain="B",
        pos=(1.0, 0.0, 0.0),
    )


def _assert_read_only(
    cmd: Any, store: RecoveryStore, action: Callable[[], None]
) -> None:
    """Run one refusal and prove it changed neither PyMOL nor disk state."""
    before = capture_session_fingerprint(cmd, _OBJECT)
    action()
    assert_session_unchanged(before, capture_session_fingerprint(cmd, _OBJECT))
    assert store.retained is None
    assert not store.directory.exists()


def test_every_refusal_path_has_zero_live_or_recovery_mutation(
    real_pymol: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the V1 refusal matrix against real PyMOL, not a fake cmd."""
    cases = 0

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "no-pending")
    _assert_read_only(real_pymol, store, lambda: client.copilot_apply("p-nope"))
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "wrong-id")
    client._pending_plan = _pending(client, real_pymol)
    _assert_read_only(real_pymol, store, lambda: client.copilot_apply("p-nope"))
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "wrong-session")
    client._pending_plan = _pending(
        client, real_pymol, session_id="other-session"
    )
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "not-applicable")
    client._pending_plan = _pending(client, real_pymol, applicable=False)
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "fidelity-unavailable")
    client._pending_plan = _pending(
        client,
        real_pymol,
        applicable=False,
        fidelity=FidelityOutcome(
            FIDELITY_UNAVAILABLE, "probe_failed", (), "sha256:before", None
        ),
    )
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "expired")
    client._pending_plan = _pending(
        client, real_pymol, expires_at="2026-08-26T14:22:59.000Z"
    )
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "stale")
    client._pending_plan = _pending(client, real_pymol)
    real_pymol.color("blue", "chain A")
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "server-expired")
    client._pending_plan = _pending(client, real_pymol)
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "rejected")
    client._pending_plan = _pending(client, real_pymol)
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_reject(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "policy")
    pending = _pending(client, real_pymol)
    client._pending_plan = pending
    client._transport = _Transport(_validated_for(pending), _rejected)
    monkeypatch.setattr(
        "pmc_client.command.evaluate_plan",
        lambda _plan: PlanDecision((), False),
    )
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    monkeypatch.undo()
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "model-mismatch")
    pending = _pending(client, real_pymol)
    client._pending_plan = pending

    def changed_model(request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        return ValidatedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            received_at="2026-08-26T14:22:03.123Z",
            validated_at="2026-08-26T14:22:03.123Z",
            action_plan=pending.action_plan,
            validation=ValidationReportV1(
                "passed", pending.snapshot_digest, True, ()
            ),
            plan_id=pending.plan_id,
            snapshot_digest=pending.snapshot_digest,
            expires_at=pending.expires_at,
            model_identity="different-model@checkpoint",
        )

    client._transport = _Transport(changed_model, _rejected)
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "text-mismatch")
    pending = _pending(client, real_pymol)
    client._pending_plan = pending

    def changed_text(request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        response = _validated_for(pending)(request)
        return ValidatedPlanResponseV1(
            request_id=response.request_id,
            session_id=response.session_id,
            received_at=response.received_at,
            validated_at=response.validated_at,
            action_plan=ActionPlan(
                operations=(pending.action_plan.operations[0],)
            ),
            validation=response.validation,
            plan_id=response.plan_id,
            snapshot_digest=response.snapshot_digest,
            expires_at=response.expires_at,
            model_identity=response.model_identity,
        )

    client._transport = _Transport(changed_text, _rejected)
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "transport")
    client._pending_plan = _pending(client, real_pymol)

    def unavailable(_request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        raise TransportError("loopback unavailable")

    client._transport = _Transport(unavailable, _rejected)
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "halted")
    client._halted_recovery = "preserved.pse"
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_apply(f"p-{_PLAN_ID}")
    )
    cases += 1

    _reset(real_pymol)
    client, store = _client(real_pymol, tmp_path / "no-rollback")
    _assert_read_only(
        real_pymol, store, lambda: client.copilot_rollback(f"p-{_PLAN_ID}")
    )
    cases += 1

    assert cases == 15


if __name__ == "__main__":
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
