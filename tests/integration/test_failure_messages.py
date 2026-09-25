# Copyright 2026 PyMOL Copilot contributors.
"""Every failure path is bounded, actionable, and free of plan text.

docs/master_plan.md item 11, step 9's own proof test. `tests/unit
/test_client_messages.py` already proves `describe_failure`,
`describe_transport`, and `describe_unexpected` are themselves bounded,
printable, and never echo a raw exception's own text; this file instead
proves that `pmc_client.command`'s real handlers actually *reach* one of
those three functions (or an equally bounded fixed template) on every
failure path this module has, rather than a category or exception
slipping through some other, unguarded `_output()` call. Each row below is
one such path, and every row checks the same things
`_assert_failure_message()` enforces: no `Traceback`, every line bounded
and printable, the failure's own action text present, and no line
containing one of the canonical fixture plan's own rendered command
lines. Every read-only row also confirms the live session recorded no
mutating call at all.

Two refusals the plan calls for are not reachable through the public API
and are intentionally omitted rather than faked: a `copilot_apply`
refusal for "different contract versions" (`PendingPlan.contract_manifest`
and `verify_approval`'s own `contract_manifest` argument are both always
`pmc_client.command.CONTRACT_MANIFEST`, so they can never actually
disagree without reaching into private state), and one for "a different
session" (this client only ever has one `session_id`, generated once at
construction and never exposed to change). `tests/recovery
/test_approval_verification.py` already drives both refusals directly at
the pure `verify_approval()` level.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import cast

import pytest

from pmc_client.command import CopilotCommandClient
from pmc_client.command import PendingPlan
from pmc_client.command import PlanTransport
from pmc_client.messages import ACTIONS
from pmc_client.messages import HTTP_ACTIONS
from pmc_client.messages import MAX_LINE_BYTES
from pmc_client.messages import _DEFAULT_TRANSPORT_ACTION
from pmc_client.messages import describe_failure
from pmc_client.messages import describe_transport
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
from pmc_core.protocol import FAILURE_CATEGORIES
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.snapshot import to_json
from pmc_sidecar.child import PlanRunResult

OBJECT_NAME = "fx"
CREATED_AT = "2026-08-26T14:22:03.123Z"
INTENT = "Select chain A and color it red."

#: The one non-empty plan every successful round trip in this file
#: validates against -- `evaluate_plan()` denies an empty `ActionPlan`
#: outright, so `_validated_response()` below needs a real one, not a
#: placeholder.
_FIXTURE_PLAN = ActionPlan(
    operations=(
        SelectOperation(
            selection_name="copilot_selection",
            expression=SelectionExpression(
                clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
            ),
        ),
        ColorOperation(color="red", target=NamedSelection("copilot_selection")),
    )
)

#: Every line the canonical fixture plan itself renders to. No row's
#: output may contain one of these -- proof that a failure path never
#: reaches into `PendingPlan.action_plan` or a server's own plan text,
#: only ever its own fixed template or a bounded, pre-vetted message.
PLAN_TEXT_LINES: tuple[str, ...] = tuple(
    line for line in _FIXTURE_PLAN.render_pml().splitlines() if line
)


def _assert_failure_message(
    output: list[str],
    *,
    action_substring: str,
    leak_sentinel: str | None = None,
) -> None:
    """Check the properties every failure line in this file must hold.

    Args:
        output: Every line the command under test produced.
        action_substring: Text from that failure's own registered next
            step, expected somewhere in `output`.
        leak_sentinel: A marker planted inside a raised exception's own
            message, for rows proving that message is never echoed.
    """
    assert output, "expected at least one reported line"
    for line in output:
        assert "Traceback" not in line, line
        assert len(line.encode("utf-8")) <= MAX_LINE_BYTES, line
        assert line.isascii() and line.isprintable(), line
        for plan_line in PLAN_TEXT_LINES:
            assert plan_line not in line, (plan_line, line)
        if leak_sentinel is not None:
            assert leak_sentinel not in line, line
    assert any(action_substring in line for line in output), output


@dataclass
class _FakeAtom:
    """One in-memory atom record the fake session can serve."""

    id: int = 1
    name: str = "CA"
    alt: str = ""
    resn: str = "ALA"
    chain: str = "A"
    resi_number: int = 1
    ins_code: str = ""
    symbol: str = "C"
    hetatm: bool = False
    q: float = 1.0
    b: float = 20.0
    coord: tuple[float, float, float] = (1.0, 2.0, 3.0)
    color: int = 0
    label: str | None = None
    reps: tuple[str, ...] = ()


@dataclass
class _FakeModel:
    """A minimal chempy-model stand-in exposing `.atom` and `.bond`."""

    atom: list[_FakeAtom] = field(default_factory=lambda: [_FakeAtom()])
    bond: list[Any] = field(default_factory=list)


@dataclass
class _FakeSession:
    """A fake live PyMOL session, adapted for this file's own failure rows.

    `tests/integration/test_command.py` keeps a similarly-shaped
    `_RecordingSession` of its own; this file cannot import it (one
    `py_test` target's sources are not importable from another), and
    `tests/integration/test_client_server_command.py` already keeps its
    own separate copy for the same reason. `raise_on_get_names`,
    `raise_on_save`, and `view` are this file's own additions, for the
    several-objects, recovery-point, and NaN-view rows.
    """

    object_names: tuple[str, ...] = (OBJECT_NAME,)
    view: tuple[float, ...] = tuple(0.0 for _ in range(18))
    raise_on_get_names: Exception | None = None
    raise_on_save: Exception | None = None
    commands: dict[str, Callable[[str], None]] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    #: Real PyMOL's own `cmd.keyword`, populated by `extend()` exactly as
    #: `pymol.commanding.extend()` does, so `register()`'s own
    #: `cmd.keyword["copilot"][4] = _LITERAL_PARSING_MODE` line has an
    #: entry to rewrite (docs/master_plan.md item 11).
    keyword: dict[str, list[Any]] = field(default_factory=dict)

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Record a registered command."""
        self.commands[name] = callback
        self.keyword[name] = [callback, 0, 0, ",", 11]

    def get_names(
        self,
        kind: str = "objects",  # noqa: ARG002
        *,
        enabled_only: int = 0,
    ) -> list[str]:
        """Return every fake molecule name, or raise a scripted exception."""
        assert enabled_only in (0, 1)
        if self.raise_on_get_names is not None:
            raise self.raise_on_get_names
        return list(self.object_names)

    def get_type(self, name: str) -> str:  # noqa: ARG002
        """Report every fake name as a molecular object."""
        return "object:molecule"

    def count_states(self, selection: str) -> int:  # noqa: ARG002
        """Return the fixed one-state count this fake session serves."""
        return 1

    def get_model(self, selection: str, *, state: int) -> _FakeModel:  # noqa: ARG002
        """Return one fake atom as a chempy-like model."""
        assert state == 1
        return _FakeModel()

    def iterate(
        self,
        selection: str,  # noqa: ARG002
        expression: str,
        *,
        space: dict[str, object],
    ) -> None:
        """Evaluate `expression` once for the fake session's one atom."""
        atom = _FakeAtom()
        local_namespace = {
            "ID": atom.id,
            "color": atom.color,
            "label": atom.label,
        }
        exec(expression, {}, {**space, **local_namespace})

    def get_view(self) -> tuple[float, ...]:
        """Return this fake session's own scripted view."""
        return self.view

    def get(self, setting: str, selection: str) -> str:  # noqa: ARG002
        """Return a fixed placeholder setting value."""
        return "1.00000"

    def save(self, filename: str) -> None:
        """Materialize a recovery point, or raise a scripted exception."""
        if self.raise_on_save is not None:
            raise self.raise_on_save
        Path(filename).write_bytes(b"session")
        self.events.append("save")

    def load(self, filename: str, *, partial: int) -> None:  # noqa: ARG002
        """Record a complete-session recovery load."""
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


def _exact_probe(
    session: _FakeSession, object_name: str
) -> Callable[[FidelityRequest], FidelityReport]:
    """Build a probe reporting the fake session's own snapshot back.

    Every row that calls `copilot()` needs a probe: without one, `check
    _fidelity()` defaults to the real `pmc_core.executor.probe_fidelity`,
    which spawns an actual PyMOL sidecar subprocess. Extraction is
    deferred until the probe is actually called, so a row whose fake
    session cannot be serialized (the NaN-view row) never reaches it --
    `check_fidelity()` itself fails closed on that snapshot's own
    `to_json()` first, exactly as it does in production.
    """

    def _probe(_request: FidelityRequest) -> FidelityReport:
        snapshot, _digest = extract_live_snapshot(session, object_name)
        return FidelityReport(
            executor_version=EXECUTOR_VERSION,
            status=STATUS_OK,
            reason=REASON_OK,
            input_digest=None,
            reconstructed_snapshot_json=to_json(snapshot),
            child_pid=4321,
            child_terminated=True,
            elapsed_seconds=0.1,
            warnings=(),
        )

    return _probe


def _validated_response(request: PlanRequestV1) -> ValidatedPlanResponseV1:
    """Build a successful response correlated to a request."""
    return ValidatedPlanResponseV1(
        request_id=request.request_id,
        session_id=request.session_id,
        received_at=CREATED_AT,
        validated_at=CREATED_AT,
        action_plan=_FIXTURE_PLAN,
        validation=ValidationReportV1(
            "passed", request.snapshot.digest, True, (), (), 0
        ),
        plan_id="55555555-5555-4555-8555-555555555555",
        snapshot_digest=request.snapshot.digest,
        expires_at="2099-01-01T00:00:00.000Z",
        model_identity="test-model@test-checkpoint",
        target_object=request.snapshot.object_name,
    )


def _default_rejected(request: RejectRequestV1) -> FailedPlanResponseV1:
    """Build a correlated `rejected` response for any reject request."""
    return FailedPlanResponseV1(
        request.request_id,
        request.session_id,
        FailureEnvelopeV1("rejected", "rejected", False),
    )


@dataclass
class _Transport:
    """Record requests and return one scripted response for each call."""

    plan_response: (
        Callable[
            [PlanRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1
        ]
        | Exception
    )
    reject_response: Callable[[RejectRequestV1], FailedPlanResponseV1] = (
        _default_rejected
    )
    dispatch_error: Exception | None = None
    outcomes: list[ApplyOutcomeRequestV1] = field(default_factory=list)
    _last_validated: ValidatedPlanResponseV1 | None = field(
        default=None, init=False
    )

    def submit(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Return (or raise) this test's scripted `/v1/plan` response."""
        if isinstance(self.plan_response, Exception):
            raise self.plan_response
        response = self.plan_response(request)
        if isinstance(response, ValidatedPlanResponseV1):
            self._last_validated = response
        return response

    def reject(self, request: RejectRequestV1) -> FailedPlanResponseV1:
        """Return this test's scripted `/v1/reject` response."""
        return self.reject_response(request)

    def apply(
        self, request: ApplyRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Re-send the previewed plan as the server's own approval facts."""
        assert self._last_validated is not None
        return dataclasses.replace(
            self._last_validated,
            request_id=request.request_id,
            session_id=request.session_id,
        )

    def report_apply_outcome(
        self, request: ApplyOutcomeRequestV1
    ) -> FailedPlanResponseV1:
        """Record and acknowledge a graph terminal outcome."""
        self.outcomes.append(request)
        return FailedPlanResponseV1(
            request.request_id,
            request.session_id,
            FailureEnvelopeV1(request.outcome, request.outcome, False),
        )


def _client(
    plan_response: (
        Callable[
            [PlanRequestV1], ValidatedPlanResponseV1 | FailedPlanResponseV1
        ]
        | Exception
    ) = _validated_response,
    *,
    output: Callable[[str], None],
    session: _FakeSession | None = None,
    recovery_store: RecoveryStore | None = None,
    dispatcher: Callable[[object, ActionPlan], PlanRunResult] | None = None,
) -> tuple[CopilotCommandClient, _FakeSession, _Transport]:
    """Build a registered client over a scripted `/v1/plan` response."""
    fake_session = session if session is not None else _FakeSession()
    transport = _Transport(plan_response)
    client = CopilotCommandClient(
        cast(PlanTransport, transport),
        output,
        timestamp_factory=lambda: CREATED_AT,
        probe=_exact_probe(fake_session, OBJECT_NAME),
        recovery_store=recovery_store,
        dispatcher=dispatcher
        if dispatcher is not None
        else _default_dispatcher,
        now_factory=lambda: datetime(2026, 8, 26, 14, 23, tzinfo=UTC),
    )
    client.register(cast(Any, fake_session))
    return client, fake_session, transport


def _default_dispatcher(cmd: Any, plan: ActionPlan) -> PlanRunResult:
    """Run every operation directly against the fake session's own methods."""
    for _operation in plan.operations:
        cmd.sync()
    return PlanRunResult(STATUS_OK, REASON_OK, ())


# --- Row group: every category the server may put on the wire ------------


@pytest.mark.parametrize("category", sorted(FAILURE_CATEGORIES))
def test_every_server_failure_category_reaches_describe_failure(
    category: str,
) -> None:
    """`copilot`'s typed-failure path reaches `describe_failure` unchanged.

    Sabotage: replace this test's own `_report_failure` call site with
    `f"copilot failed: {response.failure.message}"` (the pre-item-11
    wording), and this row goes red for every category at once, because
    the printed line no longer contains that category's own action text.
    """
    envelope = FailureEnvelopeV1(category, f"denied ({category})", False)
    response = FailedPlanResponseV1("r-1", "s-1", envelope)
    output: list[str] = []
    client, session, _transport = _client(
        lambda _r: response, output=output.append
    )

    client.copilot(INTENT)

    assert output == [describe_failure("copilot", envelope)]
    assert session.events == []
    action = ACTIONS.get(category, "")
    _assert_failure_message(output, action_substring=action or envelope.message)


# --- Row group: transport failures ----------------------------------------


@pytest.mark.parametrize("status", sorted(HTTP_ACTIONS))
def test_every_known_http_status_reaches_describe_transport(
    status: int,
) -> None:
    """Each registered HTTP status is described with its own action."""
    error = TransportError(f"server rejected request with HTTP {status}")
    output: list[str] = []
    client, session, _transport = _client(error, output=output.append)

    client.copilot(INTENT)

    assert output == [describe_transport("copilot", error)]
    assert session.events == []
    _assert_failure_message(output, action_substring=HTTP_ACTIONS[status])


@pytest.mark.parametrize(
    "message",
    [
        "loopback request failed",
        "connection refused",
        "request timed out",
        "malformed response body",
    ],
    ids=[
        "refused_connection",
        "connection_refused",
        "timeout",
        "malformed_reply",
    ],
)
def test_a_transport_failure_naming_no_status_gets_the_generic_action(
    message: str,
) -> None:
    """A transport failure naming no HTTP status still reports and acts.

    Every underlying cause -- a refused connection, a timeout, a
    malformed reply, or `pmc_client.transport`'s own broadened `except
    Exception: raise TransportError(...) from error` (docs/master_plan.md
    item 11) for anything else -- reaches this client as a
    `TransportError` carrying no recognizable HTTP status, and all of
    them take the same bounded, generic path.
    """
    error = TransportError(message)
    output: list[str] = []
    client, session, _transport = _client(error, output=output.append)

    client.copilot(INTENT)

    assert output == [describe_transport("copilot", error)]
    assert session.events == []
    _assert_failure_message(output, action_substring=_DEFAULT_TRANSPORT_ACTION)


# --- Row group: target resolution -----------------------------------------


def test_no_molecular_object_sends_nothing() -> None:
    """Zero loaded molecular objects is refused before any request is sent."""
    output: list[str] = []
    session = _FakeSession(object_names=())
    client, session, _transport = _client(output=output.append, session=session)

    client.copilot(INTENT)

    assert output == [
        "copilot: no molecular object is loaded. Nothing was applied."
    ]
    assert session.events == []
    _assert_failure_message(output, action_substring="Nothing was applied")


def test_several_molecular_objects_sends_nothing() -> None:
    """More than one loaded molecular object is refused before any request."""
    output: list[str] = []
    session = _FakeSession(object_names=("fx", "fy", "fz"))
    client, session, _transport = _client(output=output.append, session=session)

    client.copilot(INTENT)

    assert output == [
        "copilot: more than one molecular object is loaded: fx, fy, fz -- "
        "load or delete objects so exactly one remains. Nothing was applied."
    ]
    assert session.events == []
    _assert_failure_message(output, action_substring="Nothing was applied")


def test_an_unexpected_target_resolution_exception_fails_closed() -> None:
    """A non-`TargetResolutionError` exception is reported by type name only.

    The scripted exception carries a `LEAK` sentinel and one of the
    canonical fixture plan's own rendered lines, exactly what a real
    PyMOL query-API exception could carry if it echoed a selection
    expression back; neither may reach the console.
    """
    sentinel = "LEAK-1f2e3d"
    output: list[str] = []
    session = _FakeSession(
        raise_on_get_names=RuntimeError(
            f"{sentinel} while evaluating {PLAN_TEXT_LINES[0]}"
        )
    )
    client, session, _transport = _client(output=output.append, session=session)

    client.copilot(INTENT)

    assert output == [
        "copilot: internal error (RuntimeError). Nothing was applied. "
        "Retry; if it keeps happening, run copilot_health."
    ]
    _assert_failure_message(
        output, action_substring="run copilot_health", leak_sentinel=sentinel
    )


def test_a_nan_view_refuses_before_sending_a_request() -> None:
    """A non-finite camera view cannot be serialized, and is refused closed."""
    output: list[str] = []
    session = _FakeSession(view=(float("nan"), *tuple(0.0 for _ in range(17))))
    client, session, _transport = _client(output=output.append, session=session)

    client.copilot(INTENT)

    assert output == [
        "copilot: the session cannot be serialized (a non-finite "
        "coordinate or view value). Nothing was applied."
    ]
    assert session.events == []
    _assert_failure_message(output, action_substring="Nothing was applied")


# --- Row group: approval refusals (copilot_apply, copilot_reject) --------


def _pending(client: CopilotCommandClient) -> PendingPlan:
    """Return the plan a real `copilot()` round trip just parked."""
    pending = client._pending_plan
    assert pending is not None
    return pending


def test_copilot_apply_with_no_pending_plan() -> None:
    """`copilot_apply` refuses locally when nothing has been submitted."""
    output: list[str] = []
    client, _session, _transport = _client(output=output.append)

    client.copilot_apply("p-55555555-5555-4555-8555-555555555555")

    assert output == [
        "copilot_apply: no pending plan for this session. Nothing was applied."
    ]
    _assert_failure_message(output, action_substring="Nothing was applied")


def test_copilot_apply_with_a_mismatched_id() -> None:
    """`copilot_apply` names the actual pending plan when refusing a mismatch."""
    output: list[str] = []
    client, _session, _transport = _client(output=output.append)
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    output.clear()

    client.copilot_apply("p-not-the-pending-plan")

    assert output == [
        "copilot_apply: plan p-not-the-pending-plan is not the pending "
        f"plan (pending: p-{plan_id}); apply that, or run copilot again. "
        "Nothing was applied."
    ]
    _assert_failure_message(output, action_substring="run copilot again")


def test_copilot_apply_on_a_not_applicable_plan() -> None:
    """`copilot_apply` refuses a plan fidelity marked as not applicable."""
    output: list[str] = []
    client, _session, _transport = _client(output=output.append)
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    client._pending_plan = dataclasses.replace(
        _pending(client), applicable=False
    )
    status, reason = (
        _pending(client).fidelity.status,
        _pending(client).fidelity.reason,
    )
    output.clear()

    client.copilot_apply(f"p-{plan_id}")

    assert output == [
        f"copilot_apply: plan p-{plan_id} is not applicable "
        f"({status}: {reason}). Nothing was applied."
    ]
    _assert_failure_message(output, action_substring="Nothing was applied")


def test_copilot_apply_on_an_expired_plan() -> None:
    """`copilot_apply` refuses once the plan's own expiry has passed."""
    output: list[str] = []
    client, _session, _transport = _client(output=output.append)
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    client._pending_plan = dataclasses.replace(
        _pending(client), expires_at="2020-01-01T00:00:00.000Z"
    )
    output.clear()

    client.copilot_apply(f"p-{plan_id}")

    assert output == [
        f"copilot_apply: plan p-{plan_id} expired at "
        "2020-01-01T00:00:00.000Z. Nothing was applied."
    ]
    _assert_failure_message(output, action_substring="Nothing was applied")


def test_copilot_apply_after_the_session_changed() -> None:
    """`copilot_apply` refuses once the live session no longer matches."""
    output: list[str] = []
    client, _session, _transport = _client(output=output.append)
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    client._pending_plan = dataclasses.replace(
        _pending(client), snapshot_digest="sha256:stale"
    )
    output.clear()

    client.copilot_apply(f"p-{plan_id}")

    assert output == [
        f"copilot_apply: the session changed since plan p-{plan_id} was "
        "made. Nothing was applied."
    ]
    _assert_failure_message(output, action_substring="Nothing was applied")


def test_copilot_reject_with_no_pending_plan() -> None:
    """`copilot_reject` refuses locally when nothing has been submitted."""
    output: list[str] = []
    client, _session, _transport = _client(output=output.append)

    client.copilot_reject("p-55555555-5555-4555-8555-555555555555")

    assert output == ["copilot_reject: no pending plan for this session"]
    _assert_failure_message(output, action_substring="no pending plan")


def test_copilot_reject_with_a_mismatched_id() -> None:
    """`copilot_reject` names the actual pending plan when refusing a mismatch."""
    output: list[str] = []
    client, _session, _transport = _client(output=output.append)
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    output.clear()

    client.copilot_reject("p-not-the-pending-plan")

    assert output == [
        "copilot_reject: plan p-not-the-pending-plan is not the pending "
        f"plan (pending: p-{plan_id}); reject that, or run copilot again"
    ]
    _assert_failure_message(output, action_substring="run copilot again")


# --- Row group: recovery-store errors --------------------------------------


def test_apply_refuses_when_a_recovery_point_cannot_be_saved(
    tmp_path: Path,
) -> None:
    """A `RecoveryStore.save()` failure refuses apply; nothing is dispatched."""
    output: list[str] = []
    session = _FakeSession()
    client, session, _transport = _client(
        output=output.append,
        session=session,
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    output.clear()
    session.raise_on_save = OSError("disk full")

    client.copilot_apply(f"p-{plan_id}")

    assert output == [
        f"copilot_apply: could not create a private recovery point for "
        f"plan p-{plan_id}. Nothing was applied."
    ]
    assert "select" not in session.events and "color" not in session.events
    _assert_failure_message(output, action_substring="Nothing was applied")


def test_apply_reports_when_private_recovery_storage_cannot_be_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A home-directory-less runtime refuses apply before any I/O begins."""

    class _RaisingRecoveryStore:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("Could not determine home directory")

    output: list[str] = []
    client, session, _transport = _client(output=output.append)
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    output.clear()
    monkeypatch.setattr(
        "pmc_client.command.RecoveryStore", _RaisingRecoveryStore
    )

    client.copilot_apply(f"p-{plan_id}")

    assert output == [
        "copilot_apply: could not initialize private recovery storage: "
        "Could not determine home directory. Nothing was applied."
    ]
    assert session.events == []
    _assert_failure_message(output, action_substring="Nothing was applied")


def test_apply_reports_a_dispatcher_exception_by_type_name_only(
    tmp_path: Path,
) -> None:
    """A dispatcher exception is reported without its own raw text.

    The scripted exception embeds a `LEAK` sentinel and one of the
    canonical plan's own rendered lines, exactly what a real dispatched
    PyMOL command's own exception could carry.
    """
    sentinel = "LEAK-4d5e6f"

    def _raising_dispatcher(cmd: Any, plan: ActionPlan) -> PlanRunResult:  # noqa: ARG001
        raise RuntimeError(f"{sentinel} in {PLAN_TEXT_LINES[0]}")

    output: list[str] = []
    session = _FakeSession()
    client, session, _transport = _client(
        output=output.append,
        session=session,
        recovery_store=RecoveryStore(tmp_path),
        dispatcher=_raising_dispatcher,
    )
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    output.clear()

    client.copilot_apply(f"p-{plan_id}")

    assert output[0] == (
        f"copilot_apply: plan p-{plan_id} failed and the complete session "
        "was restored cleanly."
    )
    _assert_failure_message(
        output, action_substring="restored", leak_sentinel=sentinel
    )


# --- Row group: rollback's own inspection failure --------------------------


def test_rollback_continues_after_a_failed_pre_restore_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An inspection exception before restore does not cancel the restore.

    Unlike every other row in this file, this path continues rather than
    refusing: `pmc_client.command.copilot_rollback`'s own docstring notes
    the shared "nothing was applied" wording would be actively misleading
    here, since the whole-session restore proceeds regardless.
    """
    sentinel = "LEAK-9a8b7c"
    output: list[str] = []
    session = _FakeSession()
    client, session, _transport = _client(
        output=output.append,
        session=session,
        recovery_store=RecoveryStore(tmp_path),
    )
    client.copilot(INTENT)
    plan_id = _pending(client).plan_id
    output.clear()
    client.copilot_apply(f"p-{plan_id}")
    output.clear()

    monkeypatch.setattr(
        "pmc_client.command.extract_live_snapshot",
        lambda *_a: (_ for _ in ()).throw(
            RuntimeError(f"{sentinel} in {PLAN_TEXT_LINES[0]}")
        ),
    )
    monkeypatch.setattr(
        "pmc_client.command.compare_recovery", lambda *_a, **_k: ()
    )

    client.copilot_rollback(f"p-{plan_id}")

    assert output[0] == (
        "copilot_rollback: internal error (RuntimeError) while inspecting "
        "the live session. The entire session will still be restored."
    )
    assert output[-1].endswith(
        "rolled back and its recovery point was removed."
    )
    _assert_failure_message(
        output, action_substring="restored", leak_sentinel=sentinel
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
