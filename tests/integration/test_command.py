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
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_client.command import FIXTURE_INTENT
from pmc_client.command import PLAN_ID_DISPLAY_PREFIX
from pmc_client.command import CopilotCommandClient
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
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json

SESSION_ID = "22222222-2222-4222-8222-222222222222"
CREATED_AT = "2026-08-26T14:22:03.123Z"
OBJECT_NAME = "fx"


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
    commands: dict[str, Callable[[str], None]] = field(default_factory=dict)

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
        """
        assert enabled_only in (0, 1)
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


@dataclass
class RecordingTransport:
    """Record requests and return a supplied typed response."""

    response_factory: Callable[
        [PlanRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1
    ]
    requests: list[PlanRequestV1]

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
        return self.response_factory(request)


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
        )
    )
    return lambda: next(values)


def _client(
    transport: RecordingTransport,
    output: Callable[[str], None],
    *,
    probe: Callable[[FidelityRequest], FidelityReport],
) -> tuple[CopilotCommandClient, _RecordingSession]:
    """Build a registered client and the fake session it is bound to.

    Args:
        transport: The transport the client submits requests through.
        output: Callable receiving command-console text.
        probe: The fidelity probe the client is injected with.

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

    client.copilot(FIXTURE_INTENT)

    request = requests[0]
    assert request.request_id == "33333333-3333-4333-8333-333333333333"
    assert request.session_id == SESSION_ID
    assert request.created_at == CREATED_AT
    assert request.intent == FIXTURE_INTENT
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

    client.copilot(FIXTURE_INTENT)

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

    client.copilot(FIXTURE_INTENT)

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

    client.copilot(FIXTURE_INTENT)

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

    client.copilot(FIXTURE_INTENT)
    client.copilot(FIXTURE_INTENT)

    assert requests[0].session_id == requests[1].session_id == client.session_id
    assert requests[0].request_id != requests[1].request_id
    assert all(
        uuid.UUID(request.request_id).version == 4 for request in requests
    )


def test_registers_both_copilot_commands() -> None:
    """Registration exposes both commands, bound to the same client."""
    session = _RecordingSession()
    client = CopilotCommandClient(
        RecordingTransport(validated_response, []), lambda _text: None
    )

    client.register(session)

    assert session.commands["copilot"] == client.copilot
    assert session.commands["copilot_apply"] == client.copilot_apply


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

    client.copilot(FIXTURE_INTENT)

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

    client.copilot(FIXTURE_INTENT)

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
        )

    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(failed_validation, []),
        output.append,
        probe=_exact_probe(session),
    )

    client.copilot(FIXTURE_INTENT)

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

    client.copilot(FIXTURE_INTENT)

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

    client.copilot(FIXTURE_INTENT)
    client.copilot(FIXTURE_INTENT)
    output.clear()
    client.copilot_apply(f"{PLAN_ID_DISPLAY_PREFIX}{first_id}")

    assert output == [
        f"copilot_apply: plan {PLAN_ID_DISPLAY_PREFIX}{first_id} is not "
        "the pending plan"
    ]


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

    assert output == ["copilot_apply: no pending plan for this session"]


def test_copilot_apply_with_a_mismatched_id() -> None:
    """copilot_apply refuses an id that is not the pending plan's own."""
    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_exact_probe(session),
    )
    client.copilot(FIXTURE_INTENT)
    output.clear()

    client.copilot_apply(f"{PLAN_ID_DISPLAY_PREFIX}not-the-pending-plan")

    assert output == [
        f"copilot_apply: plan {PLAN_ID_DISPLAY_PREFIX}not-the-pending-plan "
        "is not the pending plan"
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
    client.copilot(FIXTURE_INTENT)
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


def test_copilot_apply_refuses_an_applicable_pending_plan_too() -> None:
    """copilot_apply still refuses an applicable plan: apply is item 10's."""
    output: list[str] = []
    session = _RecordingSession()
    client, _session = _client(
        RecordingTransport(validated_response, []),
        output.append,
        probe=_exact_probe(session),
    )
    client.copilot(FIXTURE_INTENT)
    output.clear()

    client.copilot_apply(
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555"
    )

    assert output == [
        "copilot_apply: plan "
        f"{PLAN_ID_DISPLAY_PREFIX}55555555-5555-4555-8555-555555555555 "
        "is applicable, but apply is not implemented yet (master plan "
        "item 10). Nothing was applied."
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
