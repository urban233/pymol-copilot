# Copyright 2026 PyMOL Copilot contributors.
"""The copilot command seam: preview, approval, live apply, and recovery.

docs/master_plan.md item 7. `copilot` no longer sends a fixture snapshot:
it resolves the one loaded molecular object
(`pmc_client.session.resolve_target_object`), extracts its canonical
snapshot (`pmc_client.session.extract_live_snapshot`), and reconstructs
that snapshot in a fresh sidecar to check it exactly matches
(`pmc_client.fidelity.check_fidelity`) before ever building a request.
Orchestration rule 9 (SPECIFICATION.md:539) is enforced on both ends: the
server's own `ValidationReportV1.applicable` and this client's locally
observed fidelity outcome are ANDed together, and `copilot_apply` refuses
whenever that AND is false. The only live mutations in this module are an
approved ``copilot_apply`` through the closed dispatcher and an explicit
``copilot_rollback`` that replaces the complete session from its recovery
point. Every other path is refusal-only.

docs/master_plan.md item 8's request graph adds a real `copilot_reject`:
unlike `copilot_apply`, it does reach the server, over the same `/v1/reject`
endpoint `pmc_agent.session.RequestGraphSession.reject` answers. It mirrors
`copilot_apply`'s own local refusal table exactly before ever contacting
anything -- neither side trusts the other's verdict alone, and that does
not change because rejecting, unlike applying, has something real to do.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import uuid
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from dataclasses import dataclass
from typing import Protocol
from typing import cast

from pmc_client.approval import PLAN_ID_DISPLAY_PREFIX
from pmc_client.approval import normalize_plan_id
from pmc_client.approval import verify_approval
from pmc_client.apply import APPLY_APPLIED
from pmc_client.apply import APPLY_REFUSED
from pmc_client.apply import APPLY_RESTORE_FAILED
from pmc_client.apply import APPLY_RESTORED
from pmc_client.apply import ApplyOutcome
from pmc_client.apply import apply_plan
from pmc_client.apply import compare_recovery
from pmc_client.fidelity import FidelityOutcome
from pmc_client.fidelity import check_fidelity
from pmc_client.fidelity import to_wire
from pmc_client.session import PyMOLSession
from pmc_client.session import extract_live_snapshot
from pmc_client.session import resolve_target_object
from pmc_client.transport import LoopbackPlanClient
from pmc_client.transport import TransportError
from pmc_core.executor import DEFAULT_DEADLINE_SECONDS
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.executor import probe_fidelity
from pmc_core.plan import ActionPlan
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_core.protocol import APPLY_OUTCOME_APPLIED
from pmc_core.protocol import APPLY_OUTCOME_RESTORED
from pmc_core.protocol import APPLY_OUTCOME_ROLLED_BACK
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.snapshot import to_json
from pmc_sidecar.child import PlanRunResult
from pmc_sidecar.child import run_plan
from pmc_client.recovery import RecoveryStore
from pmc_client.recovery import RecoveryPointError
from pmc_core.snapshot import ObjectSnapshot

#: The contract versions this client declares on every request --
#: `pmc_core.protocol.CURRENT_CONTRACT_MANIFEST`, the one shared constant
#: `pmc_agent.graph.ACCEPTED_CONTRACT_MANIFEST` also checks a request
#: against, rather than a second, independently-typed literal that could
#: silently drift from it.
CONTRACT_MANIFEST = CURRENT_CONTRACT_MANIFEST


def _display_plan_id(raw_plan_id: str) -> str:
    """Render a raw plan identifier for console display and re-entry.

    Args:
        raw_plan_id: The plan id as the server returned it.

    Returns:
        The plan id prefixed for the exact `copilot_apply` command a user
        should type.
    """
    return f"{PLAN_ID_DISPLAY_PREFIX}{raw_plan_id}"


class CmdExtension(Protocol):
    """Small subset of the PyMOL command API required for registration."""

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register a command callback.

        Args:
            name: Command name to register.
            callback: Function invoked for the registered command.
        """


class RegisteredPyMOLSession(CmdExtension, PyMOLSession, Protocol):
    """The read-only session surface required to install and preview commands."""


class LivePyMOLSession(CmdExtension, PyMOLSession, Protocol):
    """The full live PyMOL surface `register()` needs.

    `register()` is where this client first learns the live session it
    will query on every later `copilot` invocation, so it needs both
    `CmdExtension`'s registration method and `PyMOLSession`'s query
    surface from the one object PyMOL actually is.
    """

    def save(self, filename: str) -> None:
        """Write a complete ``.pse`` recovery point."""

    def load(self, filename: str, *, partial: int) -> None:
        """Replace the complete session from a recovery point."""

    def sync(self) -> None:
        """Synchronize one dispatched PyMOL command."""

    def select(self, name: str, expression: str) -> None:
        """Create an allowlisted named selection."""

    def color(self, color: str, target: str) -> None:
        """Color an allowlisted target."""

    def show(self, representation: str, target: str) -> None:
        """Show an allowlisted representation."""

    def hide(self, representation: str, target: str) -> None:
        """Hide an allowlisted representation."""

    def orient(self, target: str) -> None:
        """Orient the view around an allowlisted target."""


class PlanTransport(Protocol):
    """Transport boundary used by the command client."""

    def submit(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Submit one typed plan request.

        Args:
            request: Typed request to send to the server.

        Returns:
            The validated plan or typed failure returned by the server.
        """

    def reject(self, request: RejectRequestV1) -> FailedPlanResponseV1:
        """Submit one typed reject request.

        Args:
            request: Typed request to send to the server.

        Returns:
            The typed failure response returned by the server.
        """

    def apply(
        self, request: ApplyRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Record approval and return the server's canonical plan."""

    def report_apply_outcome(
        self, request: ApplyOutcomeRequestV1
    ) -> FailedPlanResponseV1:
        """Report a terminal live-apply outcome to the server."""


@dataclass(frozen=True)
class PendingPlan:
    """The one plan a session may have pending approval.

    Attributes:
        plan_id: The server-issued plan identifier.
        session_id: The session identifier the request was made under.
        snapshot_digest: The structure digest the plan was bound to.
        applicable: Whether `copilot_apply` may act on this plan --
            `response.validation.applicable AND` this client's own locally
            observed fidelity outcome. Neither side's word alone is
            trusted.
        fidelity: The full local fidelity outcome, kept for `copilot_apply`
            to report on refusal.
    """

    plan_id: str
    session_id: str
    snapshot_digest: str
    action_plan: ActionPlan
    applicable: bool
    fidelity: FidelityOutcome
    expires_at: str
    model_identity: str
    contract_manifest: ContractManifestV1


@dataclass(frozen=True)
class AppliedPlan:
    """Evidence retained for one explicit full-session rollback."""

    plan_id: str
    object_name: str
    before: ObjectSnapshot
    names_before: tuple[str, ...]
    post_apply_digest: str


def _utc_timestamp() -> str:
    """Return the current time in the protocol's RFC3339 UTC form.

    Returns:
        The current timestamp in the protocol wire format.
    """
    return (
        datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _fidelity_block(
    outcome: FidelityOutcome,
    *,
    object_name: str,
    atom_count: int,
    state_count: int,
) -> str:
    """Render the fidelity summary and, when not exact, its mismatches.

    Args:
        outcome: The fidelity outcome to render.
        object_name: The resolved live object's name.
        atom_count: The live object's first-state atom count.
        state_count: The live object's coordinate state count.

    Returns:
        The multi-line fidelity block.
    """
    if outcome.status == FIDELITY_EXACT:
        atom_plural = "" if atom_count == 1 else "s"
        state_plural = "" if state_count == 1 else "s"
        return (
            "copilot fidelity: exact on the declared state scope "
            f"(object {object_name}, {atom_count} atom{atom_plural}, "
            f"{state_count} state{state_plural})"
        )
    if outcome.status == FIDELITY_NOT_EXACT:
        count = len(outcome.mismatches)
        plural = "" if count == 1 else "es"
        lines = [
            "copilot fidelity: NOT EXACT on the declared state scope "
            f"({count} mismatch{plural})"
        ]
        lines.extend(f"  {mismatch}" for mismatch in outcome.mismatches)
        return "\n".join(lines)
    return (
        "copilot fidelity: unavailable on the declared state scope "
        f"({outcome.reason})"
    )


def _plan_block(action_plan_pml: str, plan_id: str, *, applicable: bool) -> str:
    """Render the plan identifier and its numbered canonical commands.

    Args:
        action_plan_pml: The plan's canonical rendered PML text.
        plan_id: The plan identifier to display.
        applicable: Whether the plan may be applied.

    Returns:
        The multi-line plan block.
    """
    suffix = "" if applicable else "  (inspectable only -- NOT applicable)"
    lines = [f"copilot plan: {_display_plan_id(plan_id)}{suffix}"]
    lines.extend(
        f"  {index} | {command}"
        for index, command in enumerate(action_plan_pml.splitlines(), start=1)
    )
    return "\n".join(lines)


def _checked_block(outcome: FidelityOutcome) -> str:
    """Render what was, and was not, checked about a plan.

    Args:
        outcome: The fidelity outcome the plan was gated on.

    Returns:
        The checked/not-checked sentence.
    """
    if outcome.status == FIDELITY_EXACT:
        return (
            "copilot checked: the plan parses, policy allows it, and a "
            "fresh PyMOL sidecar reconstructed this session's declared "
            "state exactly. Not checked: whether the plan is "
            "scientifically what you meant."
        )
    if outcome.status == FIDELITY_NOT_EXACT:
        return (
            "copilot checked: the plan parses and policy allows it. Not "
            "checked: this session could not be reconstructed exactly, "
            "so the plan was never executed anywhere. It cannot be "
            "applied."
        )
    return (
        "copilot checked: the plan parses and policy allows it. Not "
        f"checked: a fresh PyMOL sidecar could not complete a fidelity "
        f"check ({outcome.reason}), so the plan was never executed "
        "anywhere. It cannot be applied."
    )


class CopilotCommandClient:
    """Preview plans and mutate only through an approved recovery boundary."""

    def __init__(
        self,
        transport: PlanTransport,
        output: Callable[[str], None],
        *,
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
        timestamp_factory: Callable[[], str] = _utc_timestamp,
        probe: Callable[[FidelityRequest], FidelityReport] = probe_fidelity,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
        recovery_store: RecoveryStore | None = None,
        dispatcher: Callable[[object, ActionPlan], PlanRunResult] = run_plan,
        now_factory: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Create a command client with one session identity.

        Args:
            transport: Existing authenticated plan transport.
            output: Callable receiving command-console text.
            uuid_factory: UUID source, injectable for deterministic tests.
            timestamp_factory: RFC3339 UTC timestamp source.
            probe: The fidelity probe to call, defaulted to the real
                `pmc_core.executor.probe_fidelity`. A test injects a fake
                so no process is ever spawned.
            deadline_seconds: The wall-clock deadline given to the probe.
            recovery_store: Per-session private recovery-point lifecycle.
            dispatcher: Closed plan dispatcher, injectable only for tests.
            now_factory: Clock used for local approval expiry checks.
        """
        self._transport = transport
        self._output = output
        self._uuid_factory = uuid_factory
        self._timestamp_factory = timestamp_factory
        self._probe = probe
        self._deadline_seconds = deadline_seconds
        # Preview and every refusal path are read-only.  In particular, they
        # must remain usable in a hermetic environment where a home directory
        # is intentionally unavailable (as on Bazel's Windows test worker).
        # Create the private on-disk store only after local approval checks
        # have succeeded and live application can genuinely begin.
        self._recovery_store = recovery_store
        self._dispatcher = dispatcher
        self._now_factory = now_factory
        self._session_id = str(uuid_factory())
        self._cmd: LivePyMOLSession | None = None
        self._pending_plan: PendingPlan | None = None
        self._applied_plan: AppliedPlan | None = None
        self._halted_recovery: str | None = None
        self._uncertain_approval: str | None = None
        self._unreported_outcomes: list[tuple[str, str]] = []

    @property
    def session_id(self) -> str:
        """Return the UUIDv4 session identity reused by this client.

        Returns:
            The session identifier shared by this client's requests.
        """
        return self._session_id

    def register(self, cmd: RegisteredPyMOLSession) -> None:
        """Register this client's commands with a live PyMOL session.

        Stores `cmd` for later live queries and registers the four user
        commands.

        Args:
            cmd: The live PyMOL session receiving the callbacks.
        """
        # Registration itself only needs preview's query surface. The live
        # PyMOL command module has the stricter recovery and closed-dispatch
        # surface too; retain that internal type so mutation code cannot be
        # called without naming every method it needs.
        self._cmd = cast(LivePyMOLSession, cmd)
        cmd.extend("copilot", self.copilot)
        cmd.extend("copilot_apply", self.copilot_apply)
        cmd.extend("copilot_reject", self.copilot_reject)
        cmd.extend("copilot_rollback", self.copilot_rollback)

    def close(self) -> None:
        """Remove this session's retained recovery point on shutdown."""
        if self._recovery_store is not None:
            self._recovery_store.close()

    def _store_for_apply(self) -> RecoveryStore | None:
        """Create private recovery storage only at the mutation boundary."""
        if self._recovery_store is not None:
            return self._recovery_store
        try:
            self._recovery_store = RecoveryStore()
        except RuntimeError as error:
            detail = str(error).rstrip(".")
            self._output(
                "copilot_apply: could not initialize private recovery storage: "
                f"{detail}. Nothing was applied."
            )
            return None
        return self._recovery_store

    def _halted(self, command: str) -> bool:
        """Report the permanent failed-restore latch, if it is set."""
        if self._halted_recovery is None:
            return False
        self._output(
            f"{command}: Copilot is halted after a failed restore. "
            f"Recovery point preserved at {self._halted_recovery}. Restart "
            "PyMOL and load that file manually."
        )
        return True

    def _halt(self, recovery_path: str | None) -> None:
        """Latch live operations after recovery can no longer be trusted."""
        self._halted_recovery = recovery_path or "an unavailable recovery path"

    def _report_outcome(self, plan_id: str, outcome: str) -> bool:
        """Retry older reports before sending a new local outcome."""
        current = (plan_id, outcome)
        for unresolved in tuple(self._unreported_outcomes):
            if unresolved != current:
                self._send_outcome(*unresolved)
        return self._send_outcome(plan_id, outcome)

    def _send_outcome(self, plan_id: str, outcome: str) -> bool:
        """Send one outcome, retaining only that exact report on failure."""
        current = (plan_id, outcome)
        try:
            response = self._transport.report_apply_outcome(
                ApplyOutcomeRequestV1(
                    request_id=str(self._uuid_factory()),
                    session_id=self._session_id,
                    plan_id=plan_id,
                    outcome=outcome,
                )
            )
        except TransportError as error:
            if current not in self._unreported_outcomes:
                self._unreported_outcomes.append(current)
            self._output(f"copilot recovery status unavailable: {error}")
            return False
        if current in self._unreported_outcomes:
            self._unreported_outcomes.remove(current)
        if (
            outcome == APPLY_OUTCOME_RESTORED
            and self._uncertain_approval == plan_id
        ):
            self._uncertain_approval = None
            self._pending_plan = None
        if response.failure.category == "no_pending_plan":
            self._output(
                "copilot recovery status was not recorded: no active "
                "approved plan on the server"
            )
        return True

    def _settle_uncertain_approval(self, plan_id: str) -> bool:
        """Close a possibly approved request that was never applied locally."""
        if self._uncertain_approval != plan_id:
            return True
        return self._report_outcome(plan_id, APPLY_OUTCOME_RESTORED)

    def _refuse_approved_plan(self, pending: PendingPlan, message: str) -> None:
        """Close an approved server request when local checks refuse it."""
        self._output(f"copilot_apply: {message}. Nothing was applied.")
        self._pending_plan = None
        self._report_outcome(pending.plan_id, APPLY_OUTCOME_RESTORED)

    def copilot(self, intent: str) -> None:
        """Extract the live session, gate it on fidelity, and submit a plan.

        Args:
            intent: Natural-language intent to submit for planning.
        """
        if self._halted("copilot"):
            return
        if self._cmd is None:
            raise RuntimeError("copilot invoked before register()")

        for unresolved in tuple(self._unreported_outcomes):
            if not self._send_outcome(*unresolved):
                self._output(
                    "copilot: previous apply outcome is still unconfirmed; "
                    "retry after the server is available."
                )
                return
        if (
            self._uncertain_approval is not None
            and not self._settle_uncertain_approval(self._uncertain_approval)
        ):
            self._output(
                "copilot: previous approval is still unconfirmed; "
                "retry after the server is available."
            )
            return

        # SPECIFICATION.md:515/524-525: a new request unconditionally
        # supersedes any prior pending plan, whether or not this one goes
        # on to succeed -- cleared here, before anything below can fail,
        # so a failed request never leaves a stale plan (bound to
        # whatever the live session looked like before this invocation)
        # reachable through copilot_apply.
        self._pending_plan = None

        try:
            object_name = resolve_target_object(self._cmd)
            snapshot, digest = extract_live_snapshot(self._cmd, object_name)
        except Exception as error:
            # Both calls reach real PyMOL query APIs this module cannot
            # enumerate every failure mode of (resolve_target_object()'s
            # own TargetResolutionError is one specific, expected case
            # among them); fail closed and report rather than let an
            # unhandled exception propagate into PyMOL's own command
            # dispatch.
            self._output(f"copilot failed: {error}")
            return

        outcome = check_fidelity(
            snapshot,
            live_digest=digest,
            probe=self._probe,
            deadline_seconds=self._deadline_seconds,
        )
        atom_count = len(snapshot.states[0].atoms) if snapshot.states else 0
        state_count = len(snapshot.states)

        request = PlanRequestV1(
            request_id=str(self._uuid_factory()),
            session_id=self._session_id,
            created_at=self._timestamp_factory(),
            contract_manifest=CONTRACT_MANIFEST,
            intent=intent,
            snapshot=StructureSnapshotV1(
                schema_version=str(snapshot.schema_version),
                digest=digest,
                object_name=object_name,
                atom_count=atom_count,
                state_count=state_count,
            ),
            # docs/master_plan.md item 8's request graph lives in the
            # server and needs the full canonical snapshot to validate
            # against, not merely its identity; this call site already had
            # it in hand.
            snapshot_json=to_json(snapshot),
            fidelity=to_wire(outcome),
        )
        try:
            response = self._transport.submit(request)
        except TransportError as error:
            self._output(f"copilot unavailable: {error}")
            return
        match response:
            case FailedPlanResponseV1():
                self._report_failure(response)
            case ValidatedPlanResponseV1():
                self._report_validated(
                    response,
                    outcome,
                    object_name=object_name,
                    atom_count=atom_count,
                    state_count=state_count,
                )

    def copilot_apply(self, plan_id: str) -> None:
        """Approve, re-verify, and apply one immutable pending plan.

        Args:
            plan_id: The plan identifier to apply, as the user typed it.
        """
        if self._halted("copilot_apply"):
            return
        if self._cmd is None:
            raise RuntimeError("copilot_apply invoked before register()")
        pending = self._pending_plan
        # Rows that cannot depend on the current live session are settled
        # first. This keeps a stale id or expired plan from even querying
        # PyMOL, while the second verification below still binds a valid
        # plan to a freshly extracted digest before any network or disk I/O.
        preliminary = verify_approval(
            pending,
            entered_plan_id=plan_id,
            session_id=self._session_id,
            live_digest=(
                pending.snapshot_digest if pending is not None else ""
            ),
            now=self._now_factory(),
            contract_manifest=CONTRACT_MANIFEST,
        )
        if not preliminary.allowed:
            self._output(
                f"copilot_apply: {preliminary.refusal}. Nothing was applied."
            )
            if (
                pending is not None
                and normalize_plan_id(plan_id) == pending.plan_id
            ):
                self._settle_uncertain_approval(pending.plan_id)
            return
        assert pending is not None
        try:
            object_name = resolve_target_object(self._cmd)
            _snapshot, live_digest = extract_live_snapshot(
                self._cmd, object_name
            )
        except Exception as error:
            self._output(
                f"copilot_apply: could not verify the live session: {error}. "
                "Nothing was applied."
            )
            self._settle_uncertain_approval(pending.plan_id)
            return
        verdict = verify_approval(
            pending,
            entered_plan_id=plan_id,
            session_id=self._session_id,
            live_digest=live_digest,
            now=self._now_factory(),
            contract_manifest=CONTRACT_MANIFEST,
        )
        if not verdict.allowed:
            self._output(
                f"copilot_apply: {verdict.refusal}. Nothing was applied."
            )
            self._settle_uncertain_approval(pending.plan_id)
            return
        # Constructing the store performs no filesystem write, but do it
        # before marking the server-side request as `applying`: if a runtime
        # has no usable private home directory, there is no safe way to begin
        # an apply and no server request should be left awaiting an outcome.
        store = self._store_for_apply()
        if store is None:
            self._settle_uncertain_approval(pending.plan_id)
            return
        normalized = normalize_plan_id(plan_id)
        try:
            response = self._transport.apply(
                ApplyRequestV1(
                    request_id=str(self._uuid_factory()),
                    session_id=self._session_id,
                    plan_id=normalized,
                )
            )
        except TransportError as error:
            self._uncertain_approval = pending.plan_id
            self._output(f"copilot_apply unavailable: {error}")
            return
        if isinstance(response, FailedPlanResponseV1):
            self._uncertain_approval = None
            self._output(
                f"copilot_apply refused ({response.failure.category}; "
                f"{'retryable' if response.failure.retryable else 'not retryable'}"
                f"): {response.failure.message}. Nothing was applied."
            )
            return
        self._uncertain_approval = None
        if response.model_identity != pending.model_identity:
            self._refuse_approved_plan(
                pending, "server model identity changed since preview"
            )
            return
        if (
            response.action_plan.render_pml()
            != pending.action_plan.render_pml()
        ):
            self._refuse_approved_plan(
                pending, "server plan differs from the approved preview"
            )
            return
        if (
            response.plan_id != pending.plan_id
            or response.session_id != pending.session_id
            or response.snapshot_digest != pending.snapshot_digest
            or response.expires_at != pending.expires_at
            or not response.validation.applicable
        ):
            self._refuse_approved_plan(
                pending, "server approval facts differ from the preview"
            )
            return
        policy = evaluate_plan(response.action_plan)
        if not policy.allowed:
            self._refuse_approved_plan(
                pending,
                "the canonical plan is no longer allowed by local policy",
            )
            return
        outcome = apply_plan(
            self._cmd,
            object_name=object_name,
            plan_id=pending.plan_id,
            plan=response.action_plan,
            store=store,
            dispatcher=self._dispatcher,
        )
        self._pending_plan = None
        self._report_apply_result(pending, object_name, outcome, store)

    def _report_apply_result(
        self,
        pending: PendingPlan,
        object_name: str,
        outcome: ApplyOutcome,
        store: RecoveryStore,
    ) -> None:
        """Render and record one result from the live apply boundary."""
        display_id = _display_plan_id(pending.plan_id)
        if outcome.status == APPLY_APPLIED:
            assert outcome.before is not None
            assert outcome.post_apply_digest is not None
            try:
                store.commit()
            except RecoveryPointError as error:
                self._output(
                    f"copilot_apply: previous recovery point could not be "
                    f"removed: {error}."
                )
            self._applied_plan = AppliedPlan(
                plan_id=pending.plan_id,
                object_name=object_name,
                before=outcome.before,
                names_before=outcome.names_before,
                post_apply_digest=outcome.post_apply_digest,
            )
            self._output(
                f"copilot_apply: plan {display_id} applied. Recovery point "
                f"retained at {outcome.recovery_path}."
            )
            self._report_outcome(pending.plan_id, APPLY_OUTCOME_APPLIED)
            return
        if outcome.status == APPLY_RESTORED:
            try:
                store.discard()
            except RecoveryPointError as error:
                self._output(
                    f"copilot_apply: plan {display_id} failed and the complete "
                    "session was restored cleanly, but recovery point could not "
                    f"be removed: {error}."
                )
            else:
                self._output(
                    f"copilot_apply: plan {display_id} failed and the complete "
                    "session was restored cleanly."
                )
            self._report_outcome(pending.plan_id, APPLY_OUTCOME_RESTORED)
            return
        if outcome.status == APPLY_RESTORE_FAILED:
            self._halt(
                str(outcome.recovery_path)
                if outcome.recovery_path is not None
                else None
            )
            self._output(
                f"copilot_apply: plan {display_id} failed and recovery could "
                f"not be verified. Recovery point preserved at "
                f"{outcome.recovery_path}. Restart PyMOL and load it manually."
            )
            # The V1 graph has one failure-after-apply terminal. It records
            # that commands did not remain applied; the local halt carries
            # the stricter fact that the restore itself was not trustworthy.
            self._report_outcome(pending.plan_id, APPLY_OUTCOME_RESTORED)
            return
        assert outcome.status == APPLY_REFUSED
        if outcome.failure_message is not None:
            self._output(
                f"copilot_apply: {outcome.failure_message}. "
                "Nothing was applied."
            )
        else:
            self._output(
                f"copilot_apply: could not create a private recovery point "
                f"for plan {display_id}. Nothing was applied."
            )
        self._report_outcome(pending.plan_id, APPLY_OUTCOME_RESTORED)

    def copilot_rollback(self, plan_id: str) -> None:
        """Replace the live session with the one retained pre-apply image."""
        if self._halted("copilot_rollback"):
            return
        if self._cmd is None:
            raise RuntimeError("copilot_rollback invoked before register()")
        applied = self._applied_plan
        store = self._recovery_store
        if applied is None or store is None or store.retained is None:
            self._output("copilot_rollback: no retained recovery point")
            return
        if normalize_plan_id(plan_id) != applied.plan_id:
            self._output(
                f"copilot_rollback: plan {plan_id} is not the applied plan"
            )
            return
        try:
            _snapshot, current_digest = extract_live_snapshot(
                self._cmd, applied.object_name
            )
        except Exception as error:
            self._output(
                "copilot_rollback: could not inspect the live session: "
                f"{error}. The entire session will still be restored."
            )
            current_digest = None
        self._output(
            "copilot_rollback: replacing the entire session with the "
            "pre-apply recovery point; later changes will be discarded."
        )
        if (
            current_digest is not None
            and current_digest != applied.post_apply_digest
        ):
            self._output(
                "copilot_rollback: the session changed after apply; those "
                "later changes will be discarded."
            )
        path = store.retained
        assert path is not None
        try:
            store.restore(self._cmd, path)
            mismatches = compare_recovery(
                self._cmd,
                object_name=applied.object_name,
                before=applied.before,
                names_before=applied.names_before,
            )
        except Exception:
            preserved = store.preserve()
            self._halt(str(preserved))
            self._output(
                "copilot_rollback: recovery could not be verified. Recovery "
                f"point preserved at {preserved}. Restart PyMOL and load it manually."
            )
            return
        if mismatches:
            preserved = store.preserve()
            self._halt(str(preserved))
            self._output(
                "copilot_rollback: recovery comparison failed. Recovery point "
                f"preserved at {preserved}. Restart PyMOL and load it manually."
            )
            return
        try:
            store.consume()
        except RecoveryPointError as error:
            self._output(
                "copilot_rollback: session restored, but recovery point "
                f"could not be removed: {error}."
            )
        else:
            self._output(
                f"copilot_rollback: plan {_display_plan_id(applied.plan_id)} "
                "rolled back and its recovery point was removed."
            )
        self._applied_plan = None
        self._report_outcome(applied.plan_id, APPLY_OUTCOME_ROLLED_BACK)

    def copilot_reject(self, plan_id: str) -> None:
        """Reject the pending plan, if it matches; nothing is ever applied.

        An unknown or mismatched plan is refused locally. A matching plan
        reaches the server; if a lost approval reply left it applying, a
        reject refusal is reconciled as a restored outcome because no
        local mutation has occurred.

        Args:
            plan_id: The plan identifier to reject, as the user typed it.
        """
        if self._halted("copilot_reject"):
            return
        pending = self._pending_plan
        if pending is None:
            self._output("copilot_reject: no pending plan for this session")
            return
        normalized = normalize_plan_id(plan_id)
        if normalized != pending.plan_id:
            self._output(
                f"copilot_reject: plan {plan_id} is not the pending plan"
            )
            return
        request = RejectRequestV1(
            request_id=str(self._uuid_factory()),
            session_id=self._session_id,
            plan_id=normalized,
        )
        try:
            response = self._transport.reject(request)
        except TransportError as error:
            self._output(f"copilot_reject unavailable: {error}")
            return
        if response.failure.category == "rejected":
            self._pending_plan = None
            if self._uncertain_approval == normalized:
                self._uncertain_approval = None
            self._output(
                f"copilot_reject: plan {_display_plan_id(normalized)} "
                "rejected. Nothing was applied."
            )
            return
        if (
            response.failure.category == "no_pending_plan"
            and self._uncertain_approval == normalized
        ):
            if self._settle_uncertain_approval(normalized):
                self._output(
                    f"copilot_reject: plan {_display_plan_id(normalized)} "
                    "closed after approval. Nothing was applied."
                )
            else:
                self._output(
                    "copilot_reject: approval outcome is still unconfirmed; "
                    "retry after the server is available."
                )
            return
        self._pending_plan = None
        self._output(
            f"copilot_reject failed ({response.failure.category}; "
            f"{'retryable' if response.failure.retryable else 'not retryable'}"
            f"): {response.failure.message}"
        )

    def _report_failure(self, response: FailedPlanResponseV1) -> None:
        """Report a typed failure without attempting to render a plan.

        Args:
            response: Typed failure response to report.
        """
        failure = response.failure
        retryability = "retryable" if failure.retryable else "not retryable"
        self._output(
            f"copilot failed ({failure.category}; {retryability}): "
            f"{failure.message}"
        )

    def _report_validated(
        self,
        response: ValidatedPlanResponseV1,
        outcome: FidelityOutcome,
        *,
        object_name: str,
        atom_count: int,
        state_count: int,
    ) -> None:
        """Report a validated plan, gated on fidelity, and store it pending.

        Args:
            response: Typed response containing the validated plan.
            outcome: This request's own locally observed fidelity outcome.
            object_name: The resolved live object's name.
            atom_count: The live object's first-state atom count.
            state_count: The live object's coordinate state count.
        """
        if response.validation.status != "passed":
            self._output(
                "copilot validation failed: "
                f"status={response.validation.status}; "
                f"snapshot={response.validation.snapshot_digest}"
            )
            return

        applicable = response.validation.applicable and outcome.is_exact
        self._pending_plan = PendingPlan(
            plan_id=response.plan_id,
            session_id=response.session_id,
            snapshot_digest=response.snapshot_digest,
            action_plan=response.action_plan,
            applicable=applicable,
            fidelity=outcome,
            expires_at=response.expires_at,
            model_identity=response.model_identity,
            contract_manifest=CONTRACT_MANIFEST,
        )

        self._output(
            _fidelity_block(
                outcome,
                object_name=object_name,
                atom_count=atom_count,
                state_count=state_count,
            )
        )
        self._output(
            _plan_block(
                response.action_plan.render_pml(),
                response.plan_id,
                applicable=applicable,
            )
        )
        self._output(_checked_block(outcome))
        if applicable:
            self._output(
                "copilot apply with: copilot_apply "
                f"{_display_plan_id(response.plan_id)}"
            )


def register_copilot(
    cmd: RegisteredPyMOLSession,
    transport: LoopbackPlanClient,
    output: Callable[[str], None],
    *,
    probe: Callable[[FidelityRequest], FidelityReport] = probe_fidelity,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    recovery_store: RecoveryStore | None = None,
) -> CopilotCommandClient:
    """Register copilot and return its client for the owning session.

    Args:
        cmd: The live PyMOL session receiving the callbacks.
        transport: Authenticated transport used to submit plan requests.
        output: Callable receiving command-console text.
        probe: The fidelity probe to call, defaulted to the real
            `pmc_core.executor.probe_fidelity`. A test injects a fake so
            no process is ever spawned by a test focused on client-server
            wiring rather than real sidecar fidelity.
        deadline_seconds: The wall-clock deadline given to the probe.
        recovery_store: Optional injected per-session recovery lifecycle.

    Returns:
        The registered command client.
    """
    client = CopilotCommandClient(
        transport,
        output,
        probe=probe,
        deadline_seconds=deadline_seconds,
        recovery_store=recovery_store,
    )
    client.register(cmd)
    return client
