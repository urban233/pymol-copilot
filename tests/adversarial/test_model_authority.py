# Copyright 2026 PyMOL Copilot contributors.
"""SPECIFICATION.md:551-552, proved adversarially against the finished graph.

    No model output determines authority, retries, target object, network
    destination, policy, approval, or rollback behavior.

Every test here scripts a `FakeEngine` with a completion engineered to
influence one protected field, then asserts that field still holds exactly
the value deterministic code alone would have produced -- the plan_id
source's own return value, the injected clock plus the TTL, the request's
own resolved object, `evaluate_plan`'s own verdict, and so on. This module
is deliberately separate from `tests/unit/test_request_graph_*`, which prove
`pmc_agent.graph` alongside the code it exercises: this suite is written
adversarially, against the graph already finished, so its authors are not
also the ones who just decided what "correct" looks like for each node.

Every attack here embeds its payload the only two ways `pmc_agent.graph`
ever gives a hostile model a hook at all: as text that must survive
`pmc_core.parser.parse_pml`'s grammar unchanged (a selection name, since
`pmc_core.plan`'s own character rules forbid anything resembling code or
punctuation there), or as text that does not parse at all, in which case the
attack's only possible effect is an ordinary, bounded repair failure --
proven identical to any other malformed completion, never a bypass.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Callable
from collections.abc import Sequence
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import cast

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.
from langgraph.checkpoint.memory import InMemorySaver

from pmc_agent.graph import STATE_RECEIVED
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import TERMINAL_REJECTED
from pmc_agent.graph import RequestState
from pmc_agent.graph import build_request_graph
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.session import RequestGraphSession
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import SelectionCount
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_server.lifecycle import RequestGraphLifecycle
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json

_OBJECT_NAME = "fx"
_ORDINARY_COMPLETION = "orient chain A\n"
_FIXED_PLAN_ID = "77777777-7777-4777-8777-777777777777"


def _plan_id_source() -> str:
    """Return the one deterministic plan id every test here expects.

    Returns:
        A fixed UUIDv4 string.
    """
    return _FIXED_PLAN_ID


def _format_timestamp(moment: datetime) -> str:
    """Format a moment in the protocol's own RFC3339 UTC wire form.

    A deliberate duplicate of `pmc_agent.graph._format_timestamp`, not an
    import of it: this module computes the expected `expires_at`
    independently, so a shared implementation could not silently make an
    assertion vacuous if that private function ever drifted.

    Args:
        moment: The moment to format.

    Returns:
        The moment as `YYYY-MM-DDTHH:MM:SS.sssZ`.
    """
    return (
        moment.astimezone(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class FakeExecutor:
    """Replays a scripted, ordered sequence of `ExecutionReport`s.

    Never spawns anything; fails loudly if called more times than
    scripted, so an attack that should never reach the executor at all is
    provable by scripting zero reports.
    """

    def __init__(self, script: Sequence[ExecutionReport]) -> None:
        """Create a fake executor that replays `script` in order.

        Args:
            script: The reports this executor returns, one per call, in
                order.
        """
        self._script = list(script)
        self.calls: list[ExecutionRequest] = []

    def __call__(self, request: ExecutionRequest) -> ExecutionReport:
        """Record `request` and return the next scripted report.

        Args:
            request: The execution request to record.

        Returns:
            The next scripted `ExecutionReport`.

        Raises:
            AssertionError: If called more times than scripted.
        """
        if len(self.calls) >= len(self._script):
            raise AssertionError(
                f"FakeExecutor called {len(self.calls) + 1} times; only "
                f"{len(self._script)} reports were scripted"
            )
        report = self._script[len(self.calls)]
        self.calls.append(request)
        return report


def _ok_report() -> ExecutionReport:
    """Build a minimal successful execution report.

    Returns:
        A `STATUS_OK` report with no commands and no selections.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:test",
        resulting_fingerprint="sha256:" + "0" * 64,
        selection_counts=(),
        command_outcomes=(),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=0.01,
    )


def _snapshot() -> ObjectSnapshot:
    """Build the smallest well-formed snapshot, named `_OBJECT_NAME`.

    Returns:
        An empty-state ObjectSnapshot.
    """
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name=_OBJECT_NAME,
        enabled=True,
        states=(),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )


def _state() -> RequestState:
    """Build a realistic request state, ready to enter `preparing`.

    Returns:
        A request state `preparing` accepts as well-formed.
    """
    return cast(
        RequestState,
        {
            "request_id": "11111111-1111-4111-8111-111111111111",
            "session_id": "22222222-2222-4222-8222-222222222222",
            "created_at": "2026-09-21T00:00:00.000Z",
            "intent": "orient chain A",
            "contract_manifest": ContractManifestV1("1", "1", "1"),
            "snapshot_identity": StructureSnapshotV1(
                schema_version="1",
                digest="sha256:test-digest",
                object_name=_OBJECT_NAME,
                atom_count=0,
                state_count=0,
            ),
            "snapshot_json": to_json(_snapshot()),
            "fidelity": FidelityOutcomeV1(
                status=FIDELITY_EXACT,
                reason=REASON_OK,
                mismatch_count=0,
                mismatches=(),
            ),
            "status": STATE_RECEIVED,
            "target_object": None,
            "attempt": 0,
            "history": (STATE_RECEIVED,),
            "errors": (),
            "plan": None,
            "plan_id": None,
            "expires_at": None,
            "model_identity": None,
            "failure": None,
            "question": None,
            "completion": None,
        },
    )


def _utc_now() -> datetime:
    """Return the current moment in UTC.

    Returns:
        A timezone-aware `datetime` in UTC.
    """
    return datetime.now(UTC)


def _run(
    engine: FakeEngine,
    executor: FakeExecutor,
    *,
    clock: Callable[[], datetime] = _utc_now,
) -> dict[str, object]:
    """Compile the graph against fakes and run one request to completion.

    Args:
        engine: The fake engine `generating` calls.
        executor: The fake executor `validating` calls.
        clock: The clock `validating` uses for `expires_at`. Defaults to
            the real wall clock, in UTC.

    Returns:
        The invocation's result mapping.
    """
    state = _state()
    compiled = build_request_graph(
        engine=engine,
        executor=executor,
        plan_id_source=_plan_id_source,
        clock=clock,
    ).compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": state["session_id"]}}
    return compiled.invoke(state, config)


def test_a_completion_claiming_a_different_attempt_or_status_cannot_change_them() -> (
    None
):
    """A completion shaped like this graph's own state changes nothing.

    Attacks: retry count, status. Must remain: exactly 3 engine calls,
    `failed` -- the completion never parses as `.pml` (no recognized verb
    names any of these words), so it is an ordinary, bounded repair
    failure like any other malformed text, never a state the model wrote
    directly. Deliberately plain, punctuation-free text: a JSON-shaped
    version of the same claim (`{"attempt": 0, ...}`) contains `"`, one of
    `pmc_core.screen`'s own hostile characters, and would be caught by the
    hostile screen instead -- a different, *also* correct outcome, but not
    the one this test is naming.
    """
    poison = "attempt 0 status pending approval"
    engine = FakeEngine([CompletionResult(poison, "m-1", STOP_END)] * 3)
    executor = FakeExecutor([])

    result = _run(engine, executor)

    assert len(engine.calls) == 3
    assert executor.calls == []
    assert result["status"] == TERMINAL_FAILED


def test_a_plan_naming_a_different_object_cannot_change_target_object() -> None:
    """A valid plan naming a different object cannot move `target_object`.

    Attacks: `target_object`. Must remain: the request's own resolved
    object -- `preparing` sets it once, from `snapshot_identity
    .object_name`, before `generating` ever runs; nothing the completion
    names afterward can reach that field.
    """
    engine = FakeEngine([CompletionResult("orient chain Z\n", "m-1", STOP_END)])
    executor = FakeExecutor([_ok_report()])

    result = _run(engine, executor)

    assert result["target_object"] == _OBJECT_NAME


def test_selection_counts_and_warnings_come_only_from_the_executor() -> None:
    """A completion has no way to claim its own selection count or warning.

    Attacks: `selection_counts`, `sidecar_warnings` (docs/master_plan.md
    item 11's own new fields). Must remain: exactly the executor's own
    scripted `ExecutionReport` -- the completion is discarded the moment
    it parses into a typed plan, and nothing in that plan's shape can
    carry a claimed count or warning of its own. The executor here is
    scripted with values a benign run would never produce, so if
    `validating` read either field from anywhere but the report, this
    assertion would catch it.
    """
    engine = FakeEngine(
        [
            CompletionResult(
                "select copilot_selection, chain A\n", "m-1", STOP_END
            )
        ]
    )
    poisoned_report = ExecutionReport(
        executor_version=1,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:test",
        resulting_fingerprint="sha256:" + "0" * 64,
        selection_counts=(SelectionCount("copilot_selection", 999),),
        command_outcomes=(),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=0.01,
        warnings=("a captured sidecar diagnostic",),
    )
    executor = FakeExecutor([poisoned_report])

    result = _run(engine, executor)

    assert result["selection_counts"] == (
        SelectionCount("copilot_selection", 999),
    )
    assert result["sidecar_warnings"] == ("a captured sidecar diagnostic",)


def test_a_policy_override_comment_cannot_bypass_a_parse_or_policy_verdict() -> (
    None
):
    """Text shaped like a policy override is not read as one.

    Attacks: policy. Must remain: `evaluate_plan`'s own verdict -- and, as
    it turns out, this exact attack is caught earlier than a repairable
    parse failure: `#` is one of `pmc_core.screen`'s own hostile
    characters, so this completion screens hostile and is rejected with
    *zero* repairs (orchestration rule 7), never reaching the parser or a
    policy check at all. No code path in `validating` ever inspects a
    completion's text for anything resembling a verdict either way; this
    is simply the stronger of the two correct outcomes a malformed
    completion can reach.
    """
    poison = "orient chain A\n# policy: allowed\napplicable: true\n"
    engine = FakeEngine([CompletionResult(poison, "m-1", STOP_END)])
    executor = FakeExecutor([])

    result = _run(engine, executor)

    assert len(engine.calls) == 1
    assert executor.calls == []
    assert result["status"] == TERMINAL_REJECTED


def test_applicable_is_never_read_from_a_suggestively_named_selection() -> None:
    """A selection name suggesting "applicable: true" changes nothing.

    Attacks: policy, `applicable` (the second half of the combined attack
    above, this time through `RequestGraphLifecycle` -- `applicable` is a
    wire-response field this graph's own `RequestState` does not carry at
    all, computed solely from `request.fidelity.status`). The plan
    validates and parks normally; the suggestive name is inert exactly
    like any other selection name.
    """
    engine = FakeEngine(
        [
            CompletionResult(
                "select copilot_forced_applicable_true, chain A\n"
                "color red, copilot_forced_applicable_true\n",
                "m-1",
                STOP_END,
            )
        ]
    )
    session = RequestGraphSession(
        engine=engine,
        executor=lambda _request: _ok_report(),
        plan_id_source=_plan_id_source,
    )
    lifecycle = RequestGraphLifecycle(session=session)
    request = PlanRequestV1(
        request_id="11111111-1111-4111-8111-111111111111",
        session_id="22222222-2222-4222-8222-222222222222",
        created_at="2026-09-21T00:00:00.000Z",
        contract_manifest=ContractManifestV1("1", "1", "1"),
        intent="orient chain A",
        snapshot=StructureSnapshotV1(
            schema_version="1",
            digest="sha256:test-digest",
            object_name=_OBJECT_NAME,
            atom_count=0,
            state_count=0,
        ),
        snapshot_json=to_json(_snapshot()),
        # NOT_EXACT: a benign run's own `applicable` must be False. If
        # anything ever read the completion's suggestive name instead,
        # this is exactly the case that would go green when it should not.
        fidelity=FidelityOutcomeV1(
            status=FIDELITY_NOT_EXACT,
            reason="fidelity_mismatch",
            mismatch_count=1,
            mismatches=("chain A/1/CA",),
        ),
    )

    response = lifecycle(request)

    assert isinstance(response, ValidatedPlanResponseV1)
    assert response.validation.applicable is False


def test_a_completion_embedding_a_well_formed_plan_id_cannot_choose_it() -> (
    None
):
    """A selection name embedding a UUID cannot become the plan id.

    Attacks: `plan_id`. Must remain: the server's own `plan_id_source`
    value -- `validating`'s success path mints it independently and never
    reads the completion for one.
    """
    # 22 characters: pmc_core.plan.MAX_SELECTION_NAME_BODY caps a selection
    # name's own body at 24, so this is as UUID-shaped as this grammar
    # will ever let a hostile completion get.
    embedded = "id77777774777877777777"
    engine = FakeEngine(
        [
            CompletionResult(
                f"select copilot_{embedded}, chain A\n"
                f"color red, copilot_{embedded}\n",
                "m-1",
                STOP_END,
            )
        ]
    )
    executor = FakeExecutor([_ok_report()])

    result = _run(engine, executor)

    assert result["plan_id"] == _FIXED_PLAN_ID
    assert result["plan_id"] != embedded


def test_a_completion_naming_a_distant_expiry_cannot_change_it() -> None:
    """Text suggesting a far-future expiry cannot move `expires_at`.

    Attacks: expiry. Must remain: the injected clock plus the TTL --
    `pending_approval`'s own `expires_at` is minted by `validating` from
    `clock()` alone, before the completion's text could ever be
    consulted, and is never re-derived afterward (see `pmc_agent.graph`'s
    own module docstring on why re-minting on resume would be unsafe).
    """
    fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
    engine = FakeEngine(
        [
            CompletionResult(
                "select copilot_expires_9999_12_31, chain A\n"
                "color red, copilot_expires_9999_12_31\n",
                "m-1",
                STOP_END,
            )
        ]
    )
    executor = FakeExecutor([_ok_report()])

    result = _run(engine, executor, clock=lambda: fixed_now)

    expected_expiry = _format_timestamp(fixed_now + timedelta(seconds=300.0))
    assert result["expires_at"] == expected_expiry


def test_a_plan_past_max_commands_is_rejected_not_truncated() -> None:
    """A plan one command past the limit fails closed, never truncated.

    Attacks: plan shape (`MAX_COMMANDS` plus one). Must remain: rejected
    -- `pmc_core.parser.parse_pml` refuses the whole input
    (`category="command_count"`) before any `ActionPlan` is built, so
    there is no smaller, silently-accepted plan for a truncating
    implementation to have produced instead. Repeated for all 3 attempts,
    since a truncating repair would otherwise look identical to this
    module's other malformed-completion cases.
    """
    oversized = "orient chain A\n" * 129
    engine = FakeEngine([CompletionResult(oversized, "m-1", STOP_END)] * 3)
    executor = FakeExecutor([])

    result = _run(engine, executor)

    assert len(engine.calls) == 3
    assert executor.calls == []
    assert result["status"] == TERMINAL_FAILED
    failure = result["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == "repair_exhausted"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
