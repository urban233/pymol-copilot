# Copyright 2026 PyMOL Copilot contributors.
"""Pure, local verification of an entered plan approval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pmc_client.fidelity import FidelityOutcome
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import ProtocolDecodeError
from pmc_core.protocol import parse_utc_timestamp


PLAN_ID_DISPLAY_PREFIX = "p-"


class PendingApproval(Protocol):
    """The immutable pending-plan facts that local approval must check."""

    plan_id: str
    session_id: str
    snapshot_digest: str
    applicable: bool
    fidelity: FidelityOutcome
    expires_at: str
    contract_manifest: ContractManifestV1


@dataclass(frozen=True)
class ApprovalVerdict:
    """The result of local approval verification without side effects."""

    refusal: str | None

    @property
    def allowed(self) -> bool:
        """Whether all local approval facts match."""
        return self.refusal is None


def normalize_plan_id(entered_plan_id: str) -> str:
    """Strip the console display prefix from an entered plan identifier."""
    if entered_plan_id.startswith(PLAN_ID_DISPLAY_PREFIX):
        return entered_plan_id[len(PLAN_ID_DISPLAY_PREFIX) :]
    return entered_plan_id


def verify_approval(
    pending: PendingApproval | None,
    *,
    entered_plan_id: str,
    session_id: str,
    live_digest: str,
    now: datetime,
    contract_manifest: ContractManifestV1,
) -> ApprovalVerdict:
    """Verify every locally knowable approval fact without mutation.

    The check order is intentionally stable: it exposes the first reason an
    entered approval cannot proceed and prevents callers from reaching save,
    transport, or dispatch until every local fact agrees.

    Args:
        pending: Current immutable plan, if this session has one.
        entered_plan_id: Identifier entered by the user, with optional prefix.
        session_id: Current client session identifier.
        live_digest: Freshly extracted current-session structure digest.
        now: Current timezone-aware time.
        contract_manifest: Versions supported by this client build.

    Returns:
        A permitted verdict or one precise refusal reason.
    """
    if pending is None:
        return ApprovalVerdict("no pending plan for this session")
    normalized = normalize_plan_id(entered_plan_id)
    if normalized != pending.plan_id:
        return ApprovalVerdict(
            f"plan {entered_plan_id} is not the pending plan"
        )
    if pending.session_id != session_id:
        return ApprovalVerdict(
            f"plan {entered_plan_id} belongs to a different session"
        )
    if not pending.applicable:
        return ApprovalVerdict(
            f"plan {entered_plan_id} is not applicable "
            f"({pending.fidelity.status}: {pending.fidelity.reason})"
        )
    try:
        expires_at = parse_utc_timestamp(pending.expires_at)
    except ProtocolDecodeError:
        return ApprovalVerdict(f"plan {entered_plan_id} has an invalid expiry")
    if now >= expires_at:
        return ApprovalVerdict(
            f"plan {entered_plan_id} expired at {pending.expires_at}"
        )
    if live_digest != pending.snapshot_digest:
        return ApprovalVerdict(
            f"the session changed since plan {entered_plan_id} was made"
        )
    if pending.contract_manifest != contract_manifest:
        return ApprovalVerdict(
            f"plan {entered_plan_id} was made under different contract versions"
        )
    return ApprovalVerdict(None)
