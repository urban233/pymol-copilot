# Copyright 2026 PyMOL Copilot contributors.
"""Side-effect-free approval verification tests."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from pathlib import Path

import pytest

from pmc_client.approval import ApprovalVerdict
from pmc_client.approval import verify_approval
from pmc_client.fidelity import FidelityOutcome
from pmc_client.recovery import RecoveryStore
from pmc_core.executor import REASON_OK
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FIDELITY_EXACT


PLAN_ID = "33333333-3333-4333-8333-333333333333"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 26, 14, 25, tzinfo=UTC)
EXPIRY = "2026-08-26T14:27:03.220Z"
DIGEST = "sha256:example-chain-a-digest"


@dataclass(frozen=True)
class _Pending:
    """Minimal structural value satisfying the verifier's pending contract."""

    plan_id: str = PLAN_ID
    session_id: str = SESSION_ID
    snapshot_digest: str = DIGEST
    applicable: bool = True
    fidelity: FidelityOutcome = field(
        default_factory=lambda: FidelityOutcome(
            FIDELITY_EXACT, REASON_OK, (), DIGEST, DIGEST
        )
    )
    expires_at: str = EXPIRY
    contract_manifest: ContractManifestV1 = CURRENT_CONTRACT_MANIFEST


_DEFAULT_PENDING = _Pending()


def _verify(
    pending: _Pending | None = _DEFAULT_PENDING, **changes: object
) -> ApprovalVerdict:
    """Call the verifier with one valid fact set and optional substitutions."""
    arguments: dict[str, object] = {
        "entered_plan_id": f"p-{PLAN_ID}",
        "session_id": SESSION_ID,
        "live_digest": DIGEST,
        "now": NOW,
        "contract_manifest": CURRENT_CONTRACT_MANIFEST,
    }
    arguments.update(changes)
    return verify_approval(pending, **arguments)  # type: ignore[arg-type]


def test_valid_pending_plan_is_approved_locally() -> None:
    """All seven local facts agreeing produces a permitted verdict."""
    assert _verify().allowed
    assert _verify().refusal is None


@pytest.mark.parametrize(
    ("pending", "changes", "reason"),
    [
        (None, {}, "no pending plan"),
        (_Pending(), {"entered_plan_id": "p-other"}, "not the pending plan"),
        (_Pending(session_id="other-session"), {}, "different session"),
        (
            _Pending(
                applicable=False,
                fidelity=FidelityOutcome(
                    "not_exact", "different", (), DIGEST, "sha256:other"
                ),
            ),
            {},
            "not applicable",
        ),
        (_Pending(expires_at="2026-08-26T14:24:59.000Z"), {}, "expired at"),
        (_Pending(), {"live_digest": "sha256:changed"}, "session changed"),
        (
            _Pending(
                contract_manifest=ContractManifestV1(
                    plan_version="2", policy_version="1", snapshot_version="1"
                )
            ),
            {},
            "different contract versions",
        ),
    ],
)
def test_each_local_approval_fact_has_one_refusal(
    pending: _Pending | None, changes: dict[str, object], reason: str
) -> None:
    """Each independently invalid fact fails closed with its own reason."""
    verdict = _verify(pending, **changes)
    assert not verdict.allowed
    assert verdict.refusal is not None
    assert reason in verdict.refusal


def test_identity_mismatch_precedes_expiry() -> None:
    """The fixed refusal order reports identity before a later failed fact."""
    verdict = _verify(
        _Pending(expires_at="2026-08-26T14:24:59.000Z"),
        entered_plan_id="p-not-the-plan",
    )

    assert verdict.refusal == "plan p-not-the-plan is not the pending plan"


def test_refusals_do_not_create_recovery_data_or_call_transport(
    tmp_path: Path,
) -> None:
    """Pure verification cannot write a recovery point or send a request."""
    store = RecoveryStore(tmp_path)
    transport_calls: list[object] = []

    verdict = _verify(None)

    assert not verdict.allowed
    assert store.retained is None
    assert not store.directory.exists()
    assert transport_calls == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
