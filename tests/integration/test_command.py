# Copyright 2026 PyMOL Copilot contributors.
"""Integration tests for the copilot command seam: no PyMOL, no subprocess.

Drives `pmc_client.command.CopilotCommandClient` against a fake live
session (`_RecordingSession`, implementing `pmc_client.command
.LivePyMOLSession`) and a fake fidelity probe, so every branch -- a real
computed snapshot identity, an exact or non-exact fidelity outcome, the
server's own `applicable` AND'd with the client's, and every
`copilot_apply` refusal -- is provable without spawning anything. The
real-PyMOL, real-server end-to-end evidence lives in
tests/integration/test_real_pymol_command.py.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_client.command import PLAN_ID_DISPLAY_PREFIX
from pmc_client.command import CopilotCommandClient
from pmc_client.recovery import RecoveryPointError
from pmc_client.command import PlanTransport
from pmc_client.recovery import RecoveryStore
from pmc_client.session import extract_live_snapshot
from pmc_client.transport import TransportError
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import NamedSelection
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_sidecar.child import PlanRunResult
from pmc_sidecar.child import run_plan

SESSION_ID = "22222222-2222-4222-8222-222222222222"
CREATED_AT = "2026-08-26T14:22:03.123Z"
OBJECT_NAME = "fx"
INTENT = "Select chain A and color it red."


@dataclass(frozen=True)
class _FakeAtom:
    """One in-memory atom record a `_RecordingSession` can serve."""

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
class _RecordingSession:
    """A fake live PyMOL session: registers commands and serves one atom.

    Implements `pmc_client.command.LivePyMOLSession` in full, so
    `CopilotCommandClient.register()` accepts it and `copilot()` can
    resolve and extract from it exactly as it would a real session.
    """

    object_name: str = OBJECT_NAME
    atoms: tuple[_FakeAtom, ...] = (_DEFAULT_ATOM,)
    has_molecule: bool = True
    #: When set, get_names() raises this instead of returning names --
    #: simulating a real PyMOL-internal query failure distinct from
    #: TargetResolutionError's own "zero or more than one candidate"
    #: business-logic condition.
    raise_on_get_names: Exception | None = None
    commands: dict[str, Callable[[str], None]] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Record a registered command.

        Args:
            name: Command name to record.
            callback: Command callback to record.
        """
        self.commands[name] = callback

    def get_names(
        self,
        kind: str = "objects",  # noqa: ARG002
        *,
        enabled_only: int = 0,
    ) -> list[str]:
        """Return this session's one molecule name, or none at all.

        `kind` and `enabled_only` keep `PyMOLSession`'s own parameter
        names, not underscore-prefixed stand-ins: pyrefly's structural
        Protocol check requires a matching name for a parameter callable
        by keyword, and `extract()` genuinely calls this one by keyword
        (`cmd.get_names("objects", enabled_only=1)`).

        Args:
            kind: Ignored; this fake carries at most one object.
            enabled_only: Every fake object counts as enabled regardless
                of this value, so 0 and 1 return the same list; PyMOL
                itself accepts no other value here.

        Returns:
            The one molecule name, or an empty list when `has_molecule`
            is False.

        Raises:
            Exception: `raise_on_get_names`, when set.
        """
        assert enabled_only in (0, 1)
        if self.raise_on_get_names is not None:
            raise self.raise_on_get_names
        return [self.object_name] if self.has_molecule else []

    def get_type(self, name: str) -> str:
        """Return "object:molecule" for the fake object's own name.

        Args:
            name: The object name to look up.

        Returns:
            "object:molecule".
        """
        assert name == self.object_name
        return "object:molecule"

    def count_states(self, selection: str) -> int:  # noqa: ARG002
        """Return the fixed one-state count this fake session serves.

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

    def save(self, filename: str) -> None:
        """Record and materialize a complete recovery point."""
        Path(filename).write_bytes(b"session")
        self.events.append("save")

    def load(self, filename: str, *, partial: int) -> None:  # noqa: ARG002
        """Record a complete-session recovery load."""
        assert partial == 0
        self.events.append("load")

    def sync(self) -> None:
        """Record the closed dispatcher's synchronization boundary."""
        self.events.append("sync")

    def select(self, name: str, expression: str) -> None:  # noqa: ARG002
        """Record a closed-dispatch selection mutation."""
        self.events.append("select")

    def color(self, color: str, target: str) -> None:  # noqa: ARG002
        """Record a closed-dispatch color mutation."""
        self.events.append("color")

    def show(self, representation: str, target: str) -> None:  # noqa: ARG002
        """Record a closed-dispatch show mutation."""
        self.events.append("show")

    def hide(self, representation: str, target: str) -> None:  # noqa: ARG002
        """Record a closed-dispatch hide mutation."""
        self.events.append("hide")

    def orient(self, target: str) -> None:  # noqa: ARG002
        """Record a closed-dispatch orient mutation."""
        self.events.append("orient")


def _report_for(
    snapshot: ObjectSnapshot,
) -> FidelityReport:
    """Build a successful FidelityReport carrying a given reconstruction.

    Args:
        snapshot: The snapshot the fake child claims to have reconstructed.

    Returns:
        A STATUS_OK report carrying that snapshot's JSON.
    """
    return FidelityReport(
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


def _exact_probe(
    session: _RecordingSession,
) -> Callable[[FidelityRequest], FidelityReport]:
    """Build a probe that reports the live session's own snapshot back.

    Args:
        session: The fake session `copilot()` will independently extract
            from too -- this probe reports exactly what that extraction
            produces, so `check_fidelity()` finds an empty diff.

    Returns:
        A probe reporting an exact match.
    """
    snapshot, _digest = extract_live_snapshot(session, session.object_name)
    report = _report_for(snapshot)
    return lambda _request: report


def _mismatched_probe(
    session: _RecordingSession,
) -> Callable[[FidelityRequest], FidelityReport]:
    """Build a probe that reports one atom's occupancy perturbed.

    Args:
        session: The fake session to extract the base snapshot from.

    Returns:
        A probe reporting a not-exact reconstruction.
    """
    snapshot, _digest = extract_live_snapshot(session, session.object_name)
    perturbed_atom = dataclasses.replace(snapshot.states[0].atoms[0], q=0.5)
    perturbed = dataclasses.replace(
        snapshot, states=(StateSnapshot(atoms=(perturbed_atom,)),)
    )
    report = _report_for(perturbed)
    return lambda _request: report


def _default_rejected(request: RejectRequestV1) -> FailedPlanResponseV1:
    """Build a correlated `rejected` response for any reject request.

    Args:
        request: Request whose correlation values are copied.

    Returns:
        A `rejected`, non-retryable typed failure response.
    """
    return FailedPlanResponseV1(
        request_id=request.request_id,
        session_id=request.session_id,
        failure=FailureEnvelopeV1("rejected", "rejected", False),
    )


@dataclass
class RecordingTransport:
    """Record requests and return a supplied typed response."""

    response_factory: Callable[
        [PlanRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1
    ]
    requests: list[PlanRequestV1]
    reject_response_factory: Callable[
        [RejectRequestV1], FailedPlanResponseV1
    ] = _default_rejected
    reject_requests: list[RejectRequestV1] = field(default_factory=list)
    apply_requests: list[ApplyRequestV1] = field(default_factory=list)
    outcome_requests: list[ApplyOutcomeRequestV1] = field(default_factory=list)
    apply_response_factory: (
        Callable[
            [ApplyRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1
        ]
        | None
    ) = None
    _last_validated: ValidatedPlanResponseV1 | None = field(
        default=None, init=False
    )

    def submit(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Record and handle one request.

        Args:
            request: Request to record and handle.

        Returns:
            The typed response produced by the response factory.
        """
        self.requests.append(request)
        response = self.response_factory(request)
        if isinstance(response, ValidatedPlanResponseV1):
            self._last_validated = response
        return response

    def reject(self, request: RejectRequestV1) -> FailedPlanResponseV1:
        """Record and handle one reject request.

        Args:
            request: Request to record and handle.

        Returns:
            The typed response produced by the reject response factory.
        """
        self.reject_requests.append(request)
        return self.reject_response_factory(request)

    def apply(
        self, request: ApplyRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Record approval and return the preview's canonical plan by default."""
        self.apply_requests.append(request)
        if self.apply_response_factory is not None:
            return self.apply_response_factory(request)
        if self._last_validated is None:
            return FailedPlanResponseV1(
                request.request_id,
                request.session_id,
                FailureEnvelopeV1("no_pending_plan", "no pending plan", False),
            )
        return dataclasses.replace(
            self._last_validated,
            request_id=request.request_id,
            session_id=request.session_id,
        )

    def report_apply_outcome(
        self, request: ApplyOutcomeRequestV1
    ) -> FailedPlanResponseV1:
        """Record the local outcome and acknowledge its graph terminal."""
        self.outcome_requests.append(request)
        return FailedPlanResponseV1(
            request.request_id,
            request.session_id,
            FailureEnvelopeV1(request.outcome, request.outcome, False),
        )


def fixture_plan() -> ActionPlan:
    """Build the two-command plan these protocol fixtures carry.

    pmc_core no longer ships a fixture plan of its own, and this module
    must not reach into pmc_data or pmc_server for one, so it builds the
    plan from the typed values directly.

    Returns:
        select copilot_selection, chain A followed by
        color red, copilot_selection.
    """
    return ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_selection",
                expression=SelectionExpression(
                    clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
                ),
            ),
            ColorOperation(
                color="red", target=NamedSelection("copilot_selection")
            ),
        )
    )


def validated_response(
    request: PlanRequestV1, *, applicable: bool = True
) -> ValidatedPlanResponseV1:
    """Build a successful response correlated to a request.

    Args:
        request: Request whose correlation and snapshot values are copied.
        applicable: The server's own applicable verdict to report.

    Returns:
        A successful typed response.
    """
    return ValidatedPlanResponseV1(
        request_id=request.request_id,
        session_id=request.session_id,
        received_at=CREATED_AT,
        validated_at=CREATED_AT,
        action_plan=fixture_plan(),
        validation=ValidationReportV1(
            "passed", request.snapshot.digest, applicable, ()
        ),
        plan_id="55555555-5555-4555-8555-555555555555",
        snapshot_digest=request.snapshot.digest,
        expires_at="2026-08-26T14:27:03.220Z",
        model_identity="test-model@test-checkpoint",
    )


def uuid_factory() -> Callable[[], uuid.UUID]:
    """Return a deterministic sequence of UUIDv4 values.

    Returns:
        A callable that returns the next deterministic UUIDv4 value.
    """
    values = iter(
        (
            uuid.UUID(SESSION_ID),
            uuid.UUID("33333333-3333-4333-8333-333333333333"),
            uuid.UUID("44444444-4444-4444-8444-444444444444"),
            uuid.UUID("55555555-5555-4555-8555-555555555556"),
            uuid.UUID("66666666-6666-4666-8666-666666666667"),
            uuid.UUID("77777777-7777-4777-8777-777777777778"),
        )
    )
    return lambda: next(values)


def _client(
    transport: PlanTransport,
    output: Callable[[str], None],
    *,
    probe: Callable[[FidelityRequest], FidelityReport],
    recovery_store: RecoveryStore | None = None,
    dispatcher: Callable[[object, ActionPlan], PlanRunResult] | None = None,
) -> tuple[CopilotCommandClient, _RecordingSession]:
    """Build a registered client and the fake session it is bound to.

    Args:
        transport: The transport the client submits requests through.
        output: Callable receiving command-console text.
        probe: The fidelity probe the client is injected with.
        recovery_store: Optional hermetic recovery-point lifecycle.
        dispatcher: Optional scripted closed dispatcher.

    Returns:
        The registered client and its fake session.
    """
    session = _RecordingSession()
    client = CopilotCommandClient(
        transport,
        output,
        uuid_factory=uuid_factory(),
        timestamp_factory=lambda: CREATED_AT,
        probe=probe,
        recovery_store=recovery_store,
        dispatcher=run_plan if dispatcher is None else dispatcher,
        now_factory=lambda: datetime(2026, 8, 26, 14, 23, tzinfo=UTC),
    )
    client.register(session)
    return client, session


def test_copilot_builds_request_from_the_live_session_not_a_literal() -> None:
    """The submitted request carries the live session's own real values."""
    requests: list[PlanRequestV1] = []
    transport = RecordingTransport(validated_response, requests)
    session = _RecordingSession()
    expected_snapshot, expected_digest = extract_live_snapshot(
        session, session.object_name
    )
    client, _session = _client(
        transport, lambda _text: None, probe=_exact_probe(session)
    )

    client.copilot(INTENT)

    request = requests[0]
    assert request.request_id == "33333333-3333-4333-8333-333333333333"
    assert request.session_id == SESSION_ID
    assert request.created_at == CREATED_AT
    assert request.intent == INTENT
    assert request.snapshot.digest == expected_digest
    assert request.snapshot.digest != "sha256:example-chain-a-digest"
    assert request.snapshot.object_name == OBJECT_NAME
    assert request.snapshot.atom_count == len(expected_snapshot.states[0].atoms)
    assert request.snapshot.state_count == len(expected_snapshot.states)
    assert request.fidelity.status == "exact"
    assert request.fidelity.mismatch_count == 0


def test_exact_outcome_is_applicable_and_prints_the_approval_line() -> None:
    """An exact fidelity outcome produces an applicable pending plan."""
    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_exact_probe(session),
    )

    client.copilot(INTENT)

    assert output[0].startswith("copilot fidelity: exact")
    assert f"object {OBJECT_NAME}" in output[0]
    assert output[1].startswith(
        f"copilot plan: {PLAN_ID_DISPLAY_PREFIX}"
        "55555555-5555-4555-8555-555555555555"
    )
    assert "NOT applicable" not in output[1]
    assert "1 | select copilot_selection, chain A" in output[1]
    assert "2 | color red, copilot_selection" in output[1]
    assert output[2].startswith("copilot checked:")
    assert output[3] == (
        "copilot apply with: copilot_apply "
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )


def test_non_exact_outcome_prints_the_plan_but_marks_it_non_applicable() -> (
    None
):
    """A non-exact fidelity outcome still shows the plan, marked refused."""
    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_mismatched_probe(session),
    )

    client.copilot(INTENT)

    assert output[0].startswith("copilot fidelity: NOT EXACT")
    assert "1 | select copilot_selection, chain A" in output[1]
    assert "(inspectable only -- NOT applicable)" in output[1]
    assert "cannot be applied" in output[2]
    assert not any(line.startswith("copilot apply with:") for line in output)


def test_server_inapplicable_overrides_an_exact_local_outcome() -> None:
    """response.validation.applicable=False still refuses, even if exact.

    Neither side's word alone is trusted: applicable is the AND of the
    server's own verdict and the client's locally observed fidelity.
    """
    output: list[str] = []
    session = _RecordingSession()

    def inapplicable_response(
        request: PlanRequestV1,
    ) -> ValidatedPlanResponseV1:
        """Build a response the server itself marks non-applicable.

        Args:
            request: Request whose correlation and snapshot values are
                copied.

        Returns:
            A validated response with applicable=False.
        """
        return validated_response(request, applicable=False)

    client, _session = _client(
        RecordingTransport(inapplicable_response, []),
        output.append,
        probe=_exact_probe(session),
    )

    client.copilot(INTENT)

    assert output[0].startswith("copilot fidelity: exact")
    assert "(inspectable only -- NOT applicable)" in output[1]
    assert not any(line.startswith("copilot apply with:") for line in output)


def test_client_reuses_session_and_generates_unique_request_ids() -> None:
    """One client reuses its session while requests receive new IDs."""
    requests: list[PlanRequestV1] = []
    transport = RecordingTransport(validated_response, requests)
    session = _RecordingSession()
    client, _session = _client(
        transport, lambda _text: None, probe=_exact_probe(session)
    )

    client.copilot(INTENT)
    client.copilot(INTENT)

    assert requests[0].session_id == requests[1].session_id == client.session_id
    assert requests[0].request_id != requests[1].request_id
    assert all(
        uuid.UUID(request.request_id).version == 4 for request in requests
    )


def test_registers_all_four_copilot_commands() -> None:
    """Registration exposes all four commands, bound to the same client."""
    session = _RecordingSession()
    client = CopilotCommandClient(
        RecordingTransport(validated_response, []), lambda _text: None
    )

    client.register(session)

    assert session.commands["copilot"] == client.copilot
    assert session.commands["copilot_apply"] == client.copilot_apply
    assert session.commands["copilot_reject"] == client.copilot_reject
    assert session.commands["copilot_rollback"] == client.copilot_rollback


def test_preview_does_not_require_a_home_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read-only preview remains available in a hermetic Windows sandbox."""
    requests: list[PlanRequestV1] = []

    def unavailable_store() -> RecoveryStore:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr("pmc_client.command.RecoveryStore", unavailable_store)
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(validated_response, requests),
        lambda _text: None,
        probe=_exact_probe(session),
    )

    client.copilot(INTENT)

    assert len(requests) == 1


def test_apply_refuses_before_server_handshake_without_private_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing home directory cannot leave the server awaiting an outcome."""
    output: list[str] = []
    session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(session),
    )
    client.copilot(INTENT)
    output.clear()

    def unavailable_store() -> RecoveryStore:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr("pmc_client.command.RecoveryStore", unavailable_store)

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: could not initialize private recovery storage: "
        "Could not determine home directory. Nothing was applied."
    ]
    assert transport.apply_requests == []
    assert transport.outcome_requests == []
    assert live.events == []


def test_typed_failure_reports_diagnostic_without_plan_text() -> None:
    """A typed failure reports a diagnostic without a plan."""

    def failed_response(request: PlanRequestV1) -> FailedPlanResponseV1:
        """Build a correlated typed policy failure.

        Args:
            request: Request whose correlation values are copied.

        Returns:
            A typed policy failure response.
        """
        return FailedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            failure=FailureEnvelopeV1("policy", "command denied", False),
        )

    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(failed_response, []),
        output.append,
        probe=_exact_probe(session),
    )

    client.copilot(INTENT)

    assert output == ["copilot failed (policy; not retryable): command denied"]


def test_transport_failure_reports_bounded_diagnostic() -> None:
    """A raised TransportError is caught and reported without a traceback."""

    @dataclass
    class RaisingTransport:
        """Transport double that always raises a known transport failure."""

        def submit(
            self, request: PlanRequestV1
        ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
            """Raise a bounded transport failure for any request.

            Args:
                request: Request that would have been submitted.

            Raises:
                TransportError: Always, to simulate an unavailable server.
            """
            raise TransportError(
                f"loopback request failed: {request.request_id}"
            )

        def reject(self, request: RejectRequestV1) -> FailedPlanResponseV1:
            """Raise a bounded transport failure for any reject request.

            Args:
                request: Request that would have been submitted.

            Raises:
                TransportError: Always, to simulate an unavailable server.
            """
            raise TransportError(
                f"loopback request failed: {request.request_id}"
            )

        def apply(
            self, request: ApplyRequestV1
        ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
            """Raise the same bounded outage if approval were reached."""
            raise TransportError(
                f"loopback request failed: {request.request_id}"
            )

        def report_apply_outcome(
            self, request: ApplyOutcomeRequestV1
        ) -> FailedPlanResponseV1:
            """Raise the same bounded outage if an outcome were reached."""
            raise TransportError(
                f"loopback request failed: {request.request_id}"
            )

    output: list[str] = []
    session = _RecordingSession()
    client = CopilotCommandClient(
        RaisingTransport(),
        output.append,
        uuid_factory=uuid_factory(),
        timestamp_factory=lambda: CREATED_AT,
        probe=_exact_probe(session),
    )
    client.register(session)

    client.copilot(INTENT)

    assert output == [
        "copilot unavailable: loopback request failed: "
        "33333333-3333-4333-8333-333333333333"
    ]


def test_failed_validation_reports_status_without_rendering_plan() -> None:
    """A non-passing validation status prevents plan rendering."""

    def failed_validation(
        request: PlanRequestV1,
    ) -> ValidatedPlanResponseV1:
        """Build a correlated response with failed validation.

        Args:
            request: Request whose response should be modified.

        Returns:
            A response with a failed validation status.
        """
        response = validated_response(request)
        return ValidatedPlanResponseV1(
            request_id=response.request_id,
            session_id=response.session_id,
            received_at=response.received_at,
            validated_at=response.validated_at,
            action_plan=response.action_plan,
            validation=ValidationReportV1(
                "failed", request.snapshot.digest, False, ()
            ),
            plan_id=response.plan_id,
            snapshot_digest=response.snapshot_digest,
            expires_at=response.expires_at,
            model_identity=response.model_identity,
        )

    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(failed_validation, []),
        output.append,
        probe=_exact_probe(session),
    )

    client.copilot(INTENT)

    assert len(output) == 1
    assert output[0].startswith("copilot validation failed: status=failed;")


def test_a_target_resolution_failure_sends_nothing() -> None:
    """Zero molecular objects means no request is ever built or sent."""
    requests: list[PlanRequestV1] = []
    transport = RecordingTransport(validated_response, requests)
    output: list[str] = []
    empty_session = _RecordingSession(atoms=(), has_molecule=False)
    client = CopilotCommandClient(
        transport,
        output.append,
        uuid_factory=uuid_factory(),
        timestamp_factory=lambda: CREATED_AT,
    )
    client.register(empty_session)

    client.copilot(INTENT)

    assert requests == []
    assert len(output) == 1
    assert output[0].startswith("copilot failed: no molecular object")


def test_a_second_copilot_call_replaces_the_pending_plan() -> None:
    """A new request supersedes the previous pending plan.

    SPECIFICATION.md:515: "A new request supersedes the old pending plan."
    Once replaced, the first plan's own id is refused by copilot_apply.
    """
    output: list[str] = []
    session = _RecordingSession()
    first_id = "55555555-5555-4555-8555-555555555555"
    second_id = "66666666-6666-4666-8666-666666666666"
    ids = iter((first_id, second_id))

    def _next_response(request: PlanRequestV1) -> ValidatedPlanResponseV1:
        """Build a response with the next deterministic plan id.

        Args:
            request: Request whose correlation and snapshot values are
                copied.

        Returns:
            A successful typed response with the next plan id.
        """
        response = validated_response(request)
        return dataclasses.replace(response, plan_id=next(ids))

    client, _session = _client(
        RecordingTransport(_next_response, []),
        output.append,
        probe=_exact_probe(session),
    )

    client.copilot(INTENT)
    client.copilot(INTENT)
    output.clear()
    client.copilot_apply(f"{PLAN_ID_DISPLAY_PREFIX}{first_id}")

    assert output == [
        f"copilot_apply: plan {PLAN_ID_DISPLAY_PREFIX}{first_id} is not "
        "the pending plan. Nothing was applied."
    ]


def test_a_failed_second_copilot_call_still_clears_the_pending_plan() -> None:
    """A new request supersedes the pending plan even when it fails too.

    SPECIFICATION.md:515/524-525 require this unconditionally, not only
    when the new request happens to succeed: a stale applicable plan,
    bound to whatever the live session looked like one request ago, must
    never remain reachable through copilot_apply just because the
    request that was meant to replace it failed.
    """
    output: list[str] = []
    probe_session = _RecordingSession()
    client, session = _client(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_exact_probe(probe_session),
    )
    client.copilot(INTENT)
    first_plan_id = output[1].splitlines()[0].removeprefix("copilot plan: ")
    output.clear()

    # Simulate the live session becoming unresolvable before the second
    # request -- any failure mode would do; this one needs no new fake.
    # Mutates the client's own registered session (_client()'s second
    # return value), not the separate one the probe was built from above.
    session.has_molecule = False
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(first_plan_id)

    # The failed second request cleared the pending plan entirely
    # (nothing replaced it), so this is refused as having no pending
    # plan at all -- not as an id mismatch against a stale one.
    assert output == [
        "copilot_apply: no pending plan for this session. Nothing was applied."
    ]


def test_a_broad_exception_from_resolve_target_object_fails_closed() -> None:
    """An exception other than TargetResolutionError is still caught.

    resolve_target_object() itself can reach real PyMOL query APIs
    (get_names/get_type) this module cannot enumerate every failure mode
    of; copilot() must fail closed the same way it already does for a
    failure in extract_live_snapshot(), not let an unrelated exception
    escape uncaught.
    """
    requests: list[PlanRequestV1] = []
    transport = RecordingTransport(validated_response, requests)
    output: list[str] = []
    session = _RecordingSession(
        raise_on_get_names=RuntimeError(
            "simulated PyMOL-internal query failure"
        )
    )
    client = CopilotCommandClient(
        transport,
        output.append,
        uuid_factory=uuid_factory(),
        timestamp_factory=lambda: CREATED_AT,
    )
    client.register(session)

    client.copilot(INTENT)

    assert requests == []
    assert len(output) == 1
    assert output[0].startswith("copilot failed: ")
    assert "simulated PyMOL-internal query failure" in output[0]


def test_copilot_apply_with_no_pending_plan() -> None:
    """copilot_apply refuses when no plan has ever been submitted."""
    output: list[str] = []
    session = _RecordingSession()
    client = CopilotCommandClient(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_exact_probe(session),
    )
    client.register(session)

    client.copilot_apply(f"{PLAN_ID_DISPLAY_PREFIX}not-a-real-id")

    assert output == [
        "copilot_apply: no pending plan for this session. Nothing was applied."
    ]


def test_copilot_apply_with_a_mismatched_id() -> None:
    """copilot_apply refuses an id that is not the pending plan's own."""
    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_exact_probe(session),
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(f"{PLAN_ID_DISPLAY_PREFIX}not-the-pending-plan")

    assert output == [
        f"copilot_apply: plan {PLAN_ID_DISPLAY_PREFIX}not-the-pending-plan "
        "is not the pending plan. Nothing was applied."
    ]


def test_copilot_apply_refuses_a_non_applicable_pending_plan() -> None:
    """copilot_apply refuses a pending plan the fidelity gate marked non-applicable."""
    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_mismatched_probe(session),
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: plan "
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555 "
        "is not applicable (not_exact: fidelity_mismatch). "
        "Nothing was applied."
    ]


def test_copilot_apply_applies_the_approved_canonical_plan(
    tmp_path: Path,
) -> None:
    """A valid approved plan saves first, applies once, and is reported."""
    output: list[str] = []
    session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    store = RecoveryStore(tmp_path)
    client, applied_session = _client(
        transport,
        output.append,
        probe=_exact_probe(session),
        recovery_store=store,
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: plan "
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555 "
        "applied. Recovery point retained at "
        f"{store.directory / 'plan-55555555-5555-4555-8555-555555555555.pse'}."
    ]
    assert applied_session.events == ["save", "select", "sync", "color", "sync"]
    assert len(transport.apply_requests) == 1
    assert len(transport.outcome_requests) == 1
    assert transport.outcome_requests[0].outcome == "applied"


def test_copilot_apply_can_retry_after_lost_approval_response(
    tmp_path: Path,
) -> None:
    """A transport loss before any local mutation leaves a usable pending plan."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    attempts = 0

    def lost_once(request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TransportError("approval response lost")
        assert transport._last_validated is not None
        return dataclasses.replace(
            transport._last_validated,
            request_id=request.request_id,
            session_id=request.session_id,
        )

    transport.apply_response_factory = lost_once
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    output.clear()

    plan_id = f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    client.copilot_apply(plan_id)

    assert output == ["copilot_apply unavailable: approval response lost"]
    assert live.events == []
    assert transport.outcome_requests == []
    assert client._pending_plan is not None

    client.copilot_apply(plan_id)

    assert len(transport.apply_requests) == 2
    assert [request.outcome for request in transport.outcome_requests] == [
        "applied"
    ]
    assert live.events == ["save", "select", "sync", "color", "sync"]


def test_new_preview_settles_a_lost_approval_before_submitting(
    tmp_path: Path,
) -> None:
    """A lost apply reply cannot strand or overwrite the approved request."""
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])

    def lost_apply(_request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        raise TransportError("approval response lost")

    transport.apply_response_factory = lost_apply
    client, live = _client(
        transport,
        lambda _text: None,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert live.events == []
    assert transport.outcome_requests == []
    client.copilot("Another preview")

    assert len(transport.requests) == 2
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert client._uncertain_approval is None


@pytest.mark.parametrize("outcome_report_lost", [False, True])
def test_close_settles_a_lost_approval_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome_report_lost: bool,
) -> None:
    """Shutdown reports no local mutation after an uncertain approval."""
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])

    def lost_apply(_request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        raise TransportError("approval response lost")

    transport.apply_response_factory = lost_apply
    client, live = _client(
        transport,
        lambda _text: None,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )
    assert client._uncertain_approval is not None

    if outcome_report_lost:
        original_report = transport.report_apply_outcome
        attempts = 0

        def report_after_outage(
            request: ApplyOutcomeRequestV1,
        ) -> FailedPlanResponseV1:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TransportError("outcome response lost")
            return original_report(request)

        monkeypatch.setattr(
            transport, "report_apply_outcome", report_after_outage
        )
        client.copilot("Another preview")
        assert client._unreported_outcomes == [
            ("55555555-5555-4555-8555-555555555555", "restored")
        ]
        assert len(transport.requests) == 1

    client.close()

    assert live.events == []
    assert len(transport.requests) == 1
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert client._uncertain_approval is None
    assert client._unreported_outcomes == []


def test_expired_local_retry_settles_a_lost_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A locally refused retry still reports that nothing was applied."""
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])

    def lost_apply(_request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        raise TransportError("approval response lost")

    transport.apply_response_factory = lost_apply
    client, live = _client(
        transport,
        lambda _text: None,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    plan_id = f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    client.copilot_apply(plan_id)
    monkeypatch.setattr(
        client,
        "_now_factory",
        lambda: datetime(2026, 8, 26, 14, 28, tzinfo=UTC),
    )

    client.copilot_apply(plan_id)

    assert len(transport.apply_requests) == 1
    assert live.events == []
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert client._uncertain_approval is None
    assert client._pending_plan is None


def test_reject_after_lost_approval_reports_no_local_mutation(
    tmp_path: Path,
) -> None:
    """Rejecting an already approved plan closes its applying state."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])

    def lost_apply(_request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        raise TransportError("approval response lost")

    def already_approved(request: RejectRequestV1) -> FailedPlanResponseV1:
        return FailedPlanResponseV1(
            request.request_id,
            request.session_id,
            FailureEnvelopeV1("no_pending_plan", "already approved", False),
        )

    transport.apply_response_factory = lost_apply
    transport.reject_response_factory = already_approved
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    plan_id = f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    client.copilot_apply(plan_id)

    client.copilot_reject(plan_id)

    assert live.events == []
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert client._uncertain_approval is None
    assert client._pending_plan is None
    assert output[-1].endswith("closed after approval. Nothing was applied.")


def test_new_preview_waits_and_retries_when_lost_approval_cannot_be_settled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unavailable outcome endpoint prevents an unsafe new submit."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])

    def lost_apply(_request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        raise TransportError("approval response lost")

    transport.apply_response_factory = lost_apply
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )
    original_report = transport.report_apply_outcome
    attempts = 0

    def report_after_outage(
        request: ApplyOutcomeRequestV1,
    ) -> FailedPlanResponseV1:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TransportError("outcome endpoint unavailable")
        return original_report(request)

    monkeypatch.setattr(transport, "report_apply_outcome", report_after_outage)
    client.copilot("Another preview")

    assert len(transport.requests) == 1
    assert live.events == []
    assert client._unreported_outcomes == [
        ("55555555-5555-4555-8555-555555555555", "restored")
    ]
    assert any(
        "previous approval is still unconfirmed" in line for line in output
    )

    client.copilot("Another preview")

    assert len(transport.requests) == 2
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert client._uncertain_approval is None
    assert client._unreported_outcomes == []


def test_new_preview_retries_lost_applied_outcome_before_submitting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A completed live apply is reported before the next graph request."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    original_report = transport.report_apply_outcome
    attempts = 0

    def report_after_outage(
        request: ApplyOutcomeRequestV1,
    ) -> FailedPlanResponseV1:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TransportError("outcome response lost")
        return original_report(request)

    monkeypatch.setattr(transport, "report_apply_outcome", report_after_outage)
    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert live.events == ["save", "select", "sync", "color", "sync"]
    assert client._unreported_outcomes == [
        ("55555555-5555-4555-8555-555555555555", "applied")
    ]
    assert transport.outcome_requests == []

    client.copilot("Another preview")

    assert len(transport.requests) == 2
    assert [request.outcome for request in transport.outcome_requests] == [
        "applied"
    ]
    assert client._unreported_outcomes == []


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_failed_second_apply_keeps_first_plan_rollback_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_fails: bool
) -> None:
    """A remains rollbackable after B restores, even with a locked B file."""
    first_id = "55555555-5555-4555-8555-555555555555"
    second_id = "66666666-6666-4666-8666-666666666666"
    previews = 0

    def preview(request: PlanRequestV1) -> ValidatedPlanResponseV1:
        nonlocal previews
        previews += 1
        plan_id = first_id if previews == 1 else second_id
        return dataclasses.replace(validated_response(request), plan_id=plan_id)

    dispatches = 0

    def dispatch(cmd: object, plan: ActionPlan) -> PlanRunResult:
        nonlocal dispatches
        dispatches += 1
        if dispatches == 1:
            return run_plan(cmd, plan)
        return PlanRunResult("failed", "test", ())

    live = _RecordingSession()
    output: list[str] = []
    transport = RecordingTransport(preview, [])
    store = RecoveryStore(tmp_path)
    client = CopilotCommandClient(
        transport,
        output.append,
        timestamp_factory=lambda: CREATED_AT,
        probe=_exact_probe(live),
        recovery_store=store,
        dispatcher=dispatch,
        now_factory=lambda: datetime(2026, 8, 26, 14, 23, tzinfo=UTC),
    )
    client.register(live)

    client.copilot(INTENT)
    client.copilot_apply(f"p-{first_id}")
    first_path = store.retained
    assert first_path is not None and first_path.exists()

    client.copilot(INTENT)
    second_path = store.directory / f"plan-{second_id}.pse"
    if cleanup_fails:
        real_unlink = Path.unlink

        def locked_second(self: Path, *, missing_ok: bool = False) -> None:
            if self == second_path:
                raise OSError("locked")
            real_unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", locked_second)
    client.copilot_apply(f"p-{second_id}")

    assert store.retained == first_path
    assert first_path.exists()
    assert second_path.exists() is cleanup_fails
    assert client._applied_plan is not None
    assert client._applied_plan.plan_id == first_id
    assert [request.outcome for request in transport.outcome_requests] == [
        "applied",
        "restored",
    ]

    client.copilot_rollback(f"p-{first_id}")

    assert client._applied_plan is None
    assert store.retained is None
    assert [request.outcome for request in transport.outcome_requests] == [
        "applied",
        "restored",
        "rolled_back",
    ]


@pytest.mark.parametrize("lose_rollback", [False, True])
def test_rollback_report_does_not_erase_another_plans_unreported_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lose_rollback: bool
) -> None:
    """A's rollback cannot discard B's failed restored-outcome report."""
    first_id = "55555555-5555-4555-8555-555555555555"
    second_id = "66666666-6666-4666-8666-666666666666"
    third_id = "77777777-7777-4777-8777-777777777777"
    previews = 0

    def preview(request: PlanRequestV1) -> ValidatedPlanResponseV1:
        nonlocal previews
        previews += 1
        plan_id = (first_id, second_id, third_id)[previews - 1]
        return dataclasses.replace(validated_response(request), plan_id=plan_id)

    dispatches = 0

    def dispatch(cmd: object, plan: ActionPlan) -> PlanRunResult:
        nonlocal dispatches
        dispatches += 1
        if dispatches == 1:
            return run_plan(cmd, plan)
        return PlanRunResult("failed", "test", ())

    live = _RecordingSession()
    transport = RecordingTransport(preview, [])
    client = CopilotCommandClient(
        transport,
        lambda _text: None,
        probe=_exact_probe(live),
        recovery_store=RecoveryStore(tmp_path),
        dispatcher=dispatch,
        now_factory=lambda: datetime(2026, 8, 26, 14, 23, tzinfo=UTC),
    )
    client.register(live)
    client.copilot(INTENT)
    client.copilot_apply(f"p-{first_id}")
    client.copilot(INTENT)

    original_report = transport.report_apply_outcome
    restored_attempts = 0
    rollback_attempts = 0

    def lose_two_restored_reports(
        request: ApplyOutcomeRequestV1,
    ) -> FailedPlanResponseV1:
        nonlocal restored_attempts, rollback_attempts
        if request.plan_id == second_id and request.outcome == "restored":
            restored_attempts += 1
            if restored_attempts <= 2:
                raise TransportError("B outcome response lost")
        if request.plan_id == first_id and request.outcome == "rolled_back":
            rollback_attempts += 1
            if lose_rollback and rollback_attempts == 1:
                raise TransportError("A rollback response lost")
        return original_report(request)

    monkeypatch.setattr(
        transport, "report_apply_outcome", lose_two_restored_reports
    )
    client.copilot_apply(f"p-{second_id}")
    assert client._unreported_outcomes == [(second_id, "restored")]

    client.copilot_rollback(f"p-{first_id}")

    assert restored_attempts == 2
    expected_pending = [(second_id, "restored")]
    if lose_rollback:
        expected_pending.append((first_id, "rolled_back"))
    assert client._unreported_outcomes == expected_pending
    assert [request.outcome for request in transport.outcome_requests] == (
        ["applied"] if lose_rollback else ["applied", "rolled_back"]
    )

    client.copilot("Preview C")

    assert restored_attempts == 3
    assert client._unreported_outcomes == []
    assert len(transport.requests) == 3
    expected_reports = ["applied"]
    if not lose_rollback:
        expected_reports.append("rolled_back")
    expected_reports.append("restored")
    if lose_rollback:
        expected_reports.append("rolled_back")
    assert [request.outcome for request in transport.outcome_requests] == (
        expected_reports
    )


def test_copilot_apply_refuses_changed_server_identity_before_save(
    tmp_path: Path,
) -> None:
    """A canonical reply from a different model cannot reach disk or PyMOL."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])

    def changed_identity(
        request: ApplyRequestV1,
    ) -> ValidatedPlanResponseV1:
        """Return the preview response with only model identity changed."""
        assert transport._last_validated is not None
        return dataclasses.replace(
            transport._last_validated,
            request_id=request.request_id,
            session_id=request.session_id,
            model_identity="different-model@checkpoint",
        )

    transport.apply_response_factory = changed_identity
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: server model identity changed since preview. "
        "Nothing was applied."
    ]
    assert live.events == []
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert not RecoveryStore(tmp_path).directory.exists()


def test_copilot_apply_reports_restored_when_recovery_save_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-approval save failure still closes the server apply state."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    store = RecoveryStore(tmp_path)

    def fail_save(_cmd: object, _plan_id: str) -> Path:
        raise RecoveryPointError("save failed")

    monkeypatch.setattr(store, "save", fail_save)
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=store,
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: could not create a private recovery point for plan "
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555. "
        "Nothing was applied."
    ]
    assert live.events == []
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]


def test_copilot_apply_reports_restored_when_recovery_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cleanup trouble after a verified restore cannot strand the server."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    store = RecoveryStore(tmp_path)

    def fail_discard() -> None:
        raise RecoveryPointError("locked")

    monkeypatch.setattr(store, "discard", fail_discard)
    client, _live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=store,
        dispatcher=lambda _cmd, _plan: PlanRunResult("failed", "test", ()),
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert (
        "session was restored cleanly, but recovery point could not be removed"
        in output[0]
    )
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]


def test_halted_client_retries_failed_outcome_without_live_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed restore stays halted but can still settle its server thread."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
        dispatcher=lambda _cmd, _plan: PlanRunResult("failed", "test", ()),
    )

    def failed_load(_filename: str, *, partial: int) -> None:
        assert partial == 0
        live.events.append("load")
        raise RuntimeError("restore failed")

    monkeypatch.setattr(live, "load", failed_load)
    original_report = transport.report_apply_outcome
    attempts = 0

    def report_after_outage(
        request: ApplyOutcomeRequestV1,
    ) -> FailedPlanResponseV1:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise TransportError("outcome endpoint unavailable")
        return original_report(request)

    monkeypatch.setattr(transport, "report_apply_outcome", report_after_outage)
    client.copilot(INTENT)
    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert client._halted_recovery is not None
    assert client._unreported_outcomes == [
        ("55555555-5555-4555-8555-555555555555", "restored")
    ]
    events_after_failure = list(live.events)
    assert events_after_failure == ["save", "load"]

    client.copilot("Another preview")

    assert attempts == 2
    assert len(transport.requests) == 1
    assert live.events == events_after_failure
    assert client._unreported_outcomes == [
        ("55555555-5555-4555-8555-555555555555", "restored")
    ]

    client.copilot("Another preview")

    assert attempts == 3
    assert len(transport.requests) == 1
    assert live.events == events_after_failure
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert client._unreported_outcomes == []
    assert output[-1].startswith("copilot: Copilot is halted")


def test_close_retries_an_unconfirmed_outcome(tmp_path: Path) -> None:
    """Shutdown makes one final status attempt without touching PyMOL."""
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    client, live = _client(
        transport,
        lambda _text: None,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client._unreported_outcomes.append(
        ("55555555-5555-4555-8555-555555555555", "restored")
    )

    client.close()

    assert client._unreported_outcomes == []
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert live.events == []


def test_copilot_apply_refuses_changed_server_text_before_save(
    tmp_path: Path,
) -> None:
    """The response must exactly match the immutable preview the user saw."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])

    def changed_text(request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        """Return a valid but shorter canonical plan for the same approval."""
        assert transport._last_validated is not None
        return dataclasses.replace(
            transport._last_validated,
            request_id=request.request_id,
            session_id=request.session_id,
            action_plan=ActionPlan(operations=(fixture_plan().operations[0],)),
        )

    transport.apply_response_factory = changed_text
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: server plan differs from the approved preview. "
        "Nothing was applied."
    ]
    assert live.events == []
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert not RecoveryStore(tmp_path).directory.exists()


def test_copilot_apply_reports_restored_for_changed_approval_facts(
    tmp_path: Path,
) -> None:
    """Changed server facts refuse mutation and close the approved request."""
    output: list[str] = []
    probe_session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])

    def changed_facts(request: ApplyRequestV1) -> ValidatedPlanResponseV1:
        assert transport._last_validated is not None
        return dataclasses.replace(
            transport._last_validated,
            request_id=request.request_id,
            session_id=request.session_id,
            snapshot_digest="sha256:changed",
        )

    transport.apply_response_factory = changed_facts
    client, live = _client(
        transport,
        output.append,
        probe=_exact_probe(probe_session),
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: server approval facts differ from the preview. "
        "Nothing was applied."
    ]
    assert live.events == []
    assert [request.outcome for request in transport.outcome_requests] == [
        "restored"
    ]
    assert not RecoveryStore(tmp_path).directory.exists()


def test_copilot_reject_with_no_pending_plan() -> None:
    """copilot_reject refuses when no plan has ever been submitted."""
    output: list[str] = []
    session = _RecordingSession()
    client = CopilotCommandClient(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_exact_probe(session),
    )
    client.register(session)

    client.copilot_reject(f"{PLAN_ID_DISPLAY_PREFIX}not-a-real-id")

    assert output == ["copilot_reject: no pending plan for this session"]


def test_copilot_reject_with_a_mismatched_id() -> None:
    """copilot_reject refuses an id that is not the pending plan's own."""
    output: list[str] = []
    session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    client, _session = _client(
        transport, output.append, probe=_exact_probe(session)
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_reject(f"{PLAN_ID_DISPLAY_PREFIX}not-the-pending-plan")

    assert output == [
        f"copilot_reject: plan {PLAN_ID_DISPLAY_PREFIX}not-the-pending-plan "
        "is not the pending plan"
    ]
    assert transport.reject_requests == []


def test_copilot_reject_round_trip_clears_the_pending_plan() -> None:
    """A matching copilot_reject reaches the server and clears the plan."""
    output: list[str] = []
    session = _RecordingSession()
    transport = RecordingTransport(validated_response, [])
    client, _session = _client(
        transport, output.append, probe=_exact_probe(session)
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_reject(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_reject: plan "
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555 "
        "rejected. Nothing was applied."
    ]
    assert len(transport.reject_requests) == 1
    reject_request = transport.reject_requests[0]
    assert reject_request.session_id == client.session_id
    assert reject_request.plan_id == "55555555-5555-4555-8555-555555555555"

    output.clear()
    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: no pending plan for this session. Nothing was applied."
    ]


def test_copilot_reject_transport_failure_reports_bounded_diagnostic() -> None:
    """A raised TransportError from reject is caught and reported."""

    @dataclass
    class RaisingRejectTransport:
        """Transport double that raises only when rejecting."""

        def submit(
            self, request: PlanRequestV1
        ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
            """Answer submit normally, so a plan can become pending.

            Args:
                request: Request to record and handle.

            Returns:
                A successful typed response.
            """
            return validated_response(request)

        def reject(self, request: RejectRequestV1) -> FailedPlanResponseV1:
            """Raise a bounded transport failure for any reject request.

            Args:
                request: Request that would have been submitted.

            Raises:
                TransportError: Always, to simulate an unavailable server.
            """
            raise TransportError(
                f"loopback request failed: {request.request_id}"
            )

        def apply(
            self, request: ApplyRequestV1
        ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
            """Refuse an unexpected approval in this reject-only test."""
            return FailedPlanResponseV1(
                request.request_id,
                request.session_id,
                FailureEnvelopeV1("no_pending_plan", "no pending plan", False),
            )

        def report_apply_outcome(
            self, request: ApplyOutcomeRequestV1
        ) -> FailedPlanResponseV1:
            """Raise if an outcome is unexpectedly reached in this test."""
            raise TransportError(
                f"loopback request failed: {request.request_id}"
            )

    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RaisingRejectTransport(), output.append, probe=_exact_probe(session)
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_reject(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_reject unavailable: loopback request failed: "
        "44444444-4444-4444-8444-444444444444"
    ]


def test_copilot_reject_reports_a_non_rejected_terminal() -> None:
    """A terminal other than `rejected` is reported, not silently accepted.

    `pending_approval`'s own expiry check can win over a reject that
    arrives too late (docs/master_plan.md item 8); this proves the client
    reports whatever the server actually decided rather than assuming its
    own request was honored.
    """

    def expired_response(request: RejectRequestV1) -> FailedPlanResponseV1:
        """Build a correlated `expired` response for any reject request.

        Args:
            request: Request whose correlation values are copied.

        Returns:
            An `expired`, retryable typed failure response.
        """
        return FailedPlanResponseV1(
            request_id=request.request_id,
            session_id=request.session_id,
            failure=FailureEnvelopeV1(
                "expired", "the plan's TTL had already passed", True
            ),
        )

    output: list[str] = []
    session = _RecordingSession()
    transport = RecordingTransport(
        validated_response, [], reject_response_factory=expired_response
    )
    client, _session = _client(
        transport, output.append, probe=_exact_probe(session)
    )
    client.copilot(INTENT)
    output.clear()

    client.copilot_reject(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_reject failed (expired; retryable): "
        "the plan's TTL had already passed"
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
