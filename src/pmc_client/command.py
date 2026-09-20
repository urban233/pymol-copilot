# Copyright 2026 PyMOL Copilot contributors.
"""The copilot command seam: live extraction, the fidelity gate, and apply.

docs/master_plan.md item 7. `copilot` no longer sends a fixture snapshot:
it resolves the one loaded molecular object
(`pmc_client.session.resolve_target_object`), extracts its canonical
snapshot (`pmc_client.session.extract_live_snapshot`), and reconstructs
that snapshot in a fresh sidecar to check it exactly matches
(`pmc_client.fidelity.check_fidelity`) before ever building a request.
Orchestration rule 9 (SPECIFICATION.md:539) is enforced on both ends: the
server's own `ValidationReportV1.applicable` and this client's locally
observed fidelity outcome are ANDed together, and `copilot_apply` refuses
whenever that AND is false. Nothing on any path in this module mutates the
live PyMOL session; `copilot_apply` is refusal-only here, since applying is
master_plan item 10's own work.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import uuid
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from dataclasses import dataclass
from typing import Protocol

from pmc_client.fidelity import FidelityOutcome
from pmc_client.fidelity import check_fidelity
from pmc_client.fidelity import to_wire
from pmc_client.session import PyMOLSession
from pmc_client.session import TargetResolutionError
from pmc_client.session import extract_live_snapshot
from pmc_client.session import resolve_target_object
from pmc_client.transport import LoopbackPlanClient
from pmc_client.transport import TransportError
from pmc_core.executor import DEFAULT_DEADLINE_SECONDS
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.executor import probe_fidelity
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1

FIXTURE_INTENT = "Select chain A and color it red."
FIXTURE_MANIFEST = ContractManifestV1("1", "1", "1")

#: The literal a plan id is displayed and re-entered with, so a console
#: user can copy the exact `copilot_apply <id>` line `copilot` prints.
PLAN_ID_DISPLAY_PREFIX = "p-"


def _display_plan_id(raw_plan_id: str) -> str:
    """Render a raw plan identifier for console display and re-entry.

    Args:
        raw_plan_id: The plan id as the server returned it.

    Returns:
        The plan id prefixed for the exact `copilot_apply` command a user
        should type.
    """
    return f"{PLAN_ID_DISPLAY_PREFIX}{raw_plan_id}"


def _normalize_plan_id(entered_plan_id: str) -> str:
    """Strip the console display prefix from a user-entered plan id.

    Args:
        entered_plan_id: The argument a user passed to `copilot_apply`,
            with or without the display prefix.

    Returns:
        The bare plan id, comparable against a stored `PendingPlan.plan_id`.
    """
    if entered_plan_id.startswith(PLAN_ID_DISPLAY_PREFIX):
        return entered_plan_id[len(PLAN_ID_DISPLAY_PREFIX) :]
    return entered_plan_id


class CmdExtension(Protocol):
    """Small subset of the PyMOL command API required for registration."""

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register a command callback.

        Args:
            name: Command name to register.
            callback: Function invoked for the registered command.
        """


class LivePyMOLSession(CmdExtension, PyMOLSession, Protocol):
    """The full live PyMOL surface `register()` needs.

    `register()` is where this client first learns the live session it
    will query on every later `copilot` invocation, so it needs both
    `CmdExtension`'s registration method and `PyMOLSession`'s query
    surface from the one object PyMOL actually is.
    """


class PlanTransport(Protocol):
    """Transport boundary used by the non-mutating command client."""

    def submit(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Submit one typed plan request.

        Args:
            request: Typed request to send to the server.

        Returns:
            The validated plan or typed failure returned by the server.
        """


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
    applicable: bool
    fidelity: FidelityOutcome


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
    """Submit real plan requests, gate them on fidelity, and refuse apply."""

    def __init__(
        self,
        transport: PlanTransport,
        output: Callable[[str], None],
        *,
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
        timestamp_factory: Callable[[], str] = _utc_timestamp,
        probe: Callable[[FidelityRequest], FidelityReport] = probe_fidelity,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
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
        """
        self._transport = transport
        self._output = output
        self._uuid_factory = uuid_factory
        self._timestamp_factory = timestamp_factory
        self._probe = probe
        self._deadline_seconds = deadline_seconds
        self._session_id = str(uuid_factory())
        self._cmd: PyMOLSession | None = None
        self._pending_plan: PendingPlan | None = None

    @property
    def session_id(self) -> str:
        """Return the UUIDv4 session identity reused by this client.

        Returns:
            The session identifier shared by this client's requests.
        """
        return self._session_id

    def register(self, cmd: LivePyMOLSession) -> None:
        """Register this client's commands with a live PyMOL session.

        Stores `cmd` for `copilot()` to query on every later invocation,
        in addition to registering both commands.

        Args:
            cmd: The live PyMOL session receiving the callbacks.
        """
        self._cmd = cmd
        cmd.extend("copilot", self.copilot)
        cmd.extend("copilot_apply", self.copilot_apply)

    def copilot(self, intent: str) -> None:
        """Extract the live session, gate it on fidelity, and submit a plan.

        Args:
            intent: Natural-language intent to submit for planning.
        """
        if self._cmd is None:
            raise RuntimeError("copilot invoked before register()")

        try:
            object_name = resolve_target_object(self._cmd)
        except TargetResolutionError as error:
            self._output(f"copilot failed: {error}")
            return

        try:
            snapshot, digest = extract_live_snapshot(self._cmd, object_name)
        except Exception as error:
            # extract_live_snapshot() reaches real PyMOL query APIs this
            # module cannot enumerate every failure mode of; fail closed
            # and report rather than let an unhandled exception propagate
            # into PyMOL's own command dispatch.
            self._output(f"copilot failed: {error}")
            return

        outcome = check_fidelity(
            snapshot, probe=self._probe, deadline_seconds=self._deadline_seconds
        )
        atom_count = len(snapshot.states[0].atoms) if snapshot.states else 0
        state_count = len(snapshot.states)

        request = PlanRequestV1(
            request_id=str(self._uuid_factory()),
            session_id=self._session_id,
            created_at=self._timestamp_factory(),
            contract_manifest=FIXTURE_MANIFEST,
            intent=intent,
            snapshot=StructureSnapshotV1(
                schema_version=str(snapshot.schema_version),
                digest=digest,
                object_name=object_name,
                atom_count=atom_count,
                state_count=state_count,
            ),
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
        """Refuse to apply a plan; applying is master_plan item 10's work.

        Args:
            plan_id: The plan identifier to apply, as the user typed it.
        """
        pending = self._pending_plan
        if pending is None:
            self._output("copilot_apply: no pending plan for this session")
            return
        if _normalize_plan_id(plan_id) != pending.plan_id:
            self._output(
                f"copilot_apply: plan {plan_id} is not the pending plan"
            )
            return
        display_id = _display_plan_id(pending.plan_id)
        if not pending.applicable:
            self._output(
                f"copilot_apply: plan {display_id} is not applicable "
                f"({pending.fidelity.status}: {pending.fidelity.reason}). "
                "Nothing was applied."
            )
            return
        self._output(
            f"copilot_apply: plan {display_id} is applicable, but apply is "
            "not implemented yet (master plan item 10). Nothing was "
            "applied."
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
            applicable=applicable,
            fidelity=outcome,
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
    cmd: LivePyMOLSession,
    transport: LoopbackPlanClient,
    output: Callable[[str], None],
    *,
    probe: Callable[[FidelityRequest], FidelityReport] = probe_fidelity,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
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

    Returns:
        The registered command client.
    """
    client = CopilotCommandClient(
        transport, output, probe=probe, deadline_seconds=deadline_seconds
    )
    client.register(cmd)
    return client
