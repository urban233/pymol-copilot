# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for `validating` and the bounded repair loop.

Runs the compiled graph against a `FakeEngine` and a fake executor --
never real inference and never a real sidecar. docs/master_plan.md item 8:
"one initial generation plus at most two repair attempts, each fed the
error envelope and each validated in a FRESH sidecar."
"""

import re
from collections.abc import Callable
from collections.abc import Sequence
from typing import cast

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.
from langgraph.checkpoint.memory import InMemorySaver

from pmc_agent.graph import ACCEPTED_CONTRACT_MANIFEST
from pmc_agent.graph import STATE_RECEIVED
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import TERMINAL_REJECTED
from pmc_agent.graph import RequestState
from pmc_agent.graph import build_request_graph
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.fake import FakeEngine
from pmc_core.errors import CATEGORY_UNKNOWN
from pmc_core.errors import ERROR_ENVELOPE_VERSION
from pmc_core.errors import ExecutionErrorV1
from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_OK
from pmc_core.executor import REASON_TIMEOUT
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_core.policy import PolicyDecision
from pmc_core.policy import evaluate_plan
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json

_OBJECT_NAME = "fx"
_VALID_COMPLETION = "orient chain A\n"
_HOSTILE_COMPLETION = "orient /etc/passwd\n"


class FakeExecutor:
    """Replays a scripted, ordered sequence of `ExecutionReport`s.

    The `pmc_agent.inference.fake.FakeEngine` of the executor seam: it
    never spawns anything, records every request it was given, and fails
    loudly if called more times than scripted.
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


def _command_failure_report(*, message: str = "boom") -> ExecutionReport:
    """Build a minimal failed-command execution report.

    Args:
        message: The bounded diagnostic the one failing outcome carries.

    Returns:
        A `STATUS_FAILED`/`REASON_COMMAND_FAILURE` report with one failing
        outcome, carrying a real `ExecutionErrorV1` envelope.
    """
    envelope = ExecutionErrorV1(
        envelope_version=ERROR_ENVELOPE_VERSION,
        command_index=0,
        verb="orient",
        category=CATEGORY_UNKNOWN,
        message=message,
    )
    return ExecutionReport(
        executor_version=1,
        status=STATUS_FAILED,
        reason=REASON_COMMAND_FAILURE,
        input_digest="sha256:test",
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(
            CommandOutcome(0, "orient", OUTCOME_ERROR, message, envelope),
        ),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=0.01,
    )


def _timeout_report() -> ExecutionReport:
    """Build a minimal timed-out execution report.

    Returns:
        A `STATUS_FAILED`/`REASON_TIMEOUT` report -- an infrastructure
        failure, never eligible for repair.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_FAILED,
        reason=REASON_TIMEOUT,
        input_digest="sha256:test",
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=30.0,
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
            "contract_manifest": ACCEPTED_CONTRACT_MANIFEST,
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


def _run(
    engine: FakeEngine,
    executor: FakeExecutor,
    *,
    policy_validator: Callable[[ActionPlan], PlanDecision] = evaluate_plan,
    max_repair_attempts: int = 2,
) -> dict[str, object]:
    """Compile the graph against fakes and run one request to completion.

    Args:
        engine: The fake engine `generating` calls.
        executor: The fake executor `validating` calls.
        policy_validator: The policy validator `validating` calls.
            Defaults to the graph's own real `evaluate_plan`.
        max_repair_attempts: The repair budget to build the graph with.

    Returns:
        The invocation's result mapping.
    """
    state = _state()
    compiled = build_request_graph(
        engine=engine,
        executor=executor,
        policy_validator=policy_validator,
        plan_id_source=lambda: "33333333-3333-4333-8333-333333333333",
        max_repair_attempts=max_repair_attempts,
    ).compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": state["session_id"]}}
    return compiled.invoke(state, config)


def test_a_first_pass_success_makes_one_engine_and_one_executor_call() -> None:
    """A clean completion validates on the first try and parks."""
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    executor = FakeExecutor([_ok_report()])

    result = _run(engine, executor)

    assert len(engine.calls) == 1
    assert len(executor.calls) == 1
    assert "__interrupt__" in result
    assert result["plan"] is not None
    assert isinstance(result["plan"], ActionPlan)
    assert result["plan_id"] == "33333333-3333-4333-8333-333333333333"
    assert result["expires_at"] is not None


def test_fail_fail_succeed_makes_three_calls_and_reaches_pending_approval() -> (
    None
):
    """Two repaired command failures still reach `pending_approval`."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 3
    )
    executor = FakeExecutor(
        [
            _command_failure_report(message="first failure"),
            _command_failure_report(message="second failure"),
            _ok_report(),
        ]
    )

    result = _run(engine, executor)

    assert len(engine.calls) == 3
    assert len(executor.calls) == 3
    assert "__interrupt__" in result
    assert result["plan"] is not None


def test_fail_fail_fail_makes_exactly_three_calls_never_four() -> None:
    """Exhausting the repair budget stops at exactly three attempts."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 3
    )
    executor = FakeExecutor([_command_failure_report()] * 3)

    result = _run(engine, executor)

    assert len(engine.calls) == 3
    assert len(executor.calls) == 3
    assert result["status"] == TERMINAL_FAILED
    failure = result["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == "repair_exhausted"


def test_each_repair_prompt_carries_the_prior_failure_and_no_attempt_count() -> (
    None
):
    """A repair prompt names the prior failure but never how many are left."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    executor = FakeExecutor(
        [
            _command_failure_report(message="distinctive failure text"),
            _ok_report(),
        ]
    )

    _run(engine, executor)

    assert len(engine.calls) == 2
    first_prompt = engine.calls[0].prompt
    repair_prompt = engine.calls[1].prompt
    assert "distinctive failure text" not in first_prompt
    assert CATEGORY_UNKNOWN in repair_prompt
    assert "distinctive failure text" in repair_prompt
    # "the model sees what went wrong, never how many turns it has left":
    # the prompt may say an attempt failed, but never a count or a budget
    # -- no digit near the word "attempt", no "remaining", no "of N".
    assert re.search(r"attempts?\s*\d", repair_prompt.lower()) is None
    assert "remaining" not in repair_prompt.lower()
    assert re.search(r"\bof\s+\d+\b", repair_prompt.lower()) is None


def test_a_hostile_completion_is_rejected_with_zero_repairs() -> None:
    """A hostile completion never reaches the executor at all."""
    engine = FakeEngine(
        [CompletionResult(_HOSTILE_COMPLETION, "m-1", STOP_END)]
    )
    executor = FakeExecutor([])

    result = _run(engine, executor)

    assert len(engine.calls) == 1
    assert executor.calls == []
    assert result["status"] == TERMINAL_REJECTED


def test_an_infrastructure_failure_fails_closed_without_a_repair() -> None:
    """A sidecar timeout ends the request; it never consumes a repair."""
    engine = FakeEngine([CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)])
    executor = FakeExecutor([_timeout_report()])

    result = _run(engine, executor)

    assert len(engine.calls) == 1
    assert len(executor.calls) == 1
    assert result["status"] == TERMINAL_FAILED
    failure = result["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == "execution_timeout"
    assert failure.retryable is True


def test_an_ordinary_policy_denial_does_get_its_repair() -> None:
    """A denied-then-allowed plan is repaired, not rejected outright.

    A plan the total parser itself accepted can never reach a genuine
    policy denial in production -- `pmc_core.parser` and
    `pmc_core.policy` enforce the same allowlist over the same grammar --
    so this test injects a fake `policy_validator` that denies once, to
    prove `validating`'s own denial-handling path treats it as an
    ordinary, repairable failure rather than a hostile one.
    """
    calls: list[ActionPlan] = []

    def _deny_once(plan: ActionPlan) -> PlanDecision:
        calls.append(plan)
        if len(calls) == 1:
            return PlanDecision(
                decisions=(PolicyDecision(0, False, "denied_for_test"),),
                allowed=False,
            )
        return PlanDecision(
            decisions=(PolicyDecision(0, True, "allowed_operation"),),
            allowed=True,
        )

    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    executor = FakeExecutor([_ok_report()])

    result = _run(engine, executor, policy_validator=_deny_once)

    assert len(calls) == 2
    assert len(engine.calls) == 2
    assert len(executor.calls) == 1
    assert "__interrupt__" in result
    assert result["plan"] is not None


def test_every_executor_call_receives_its_own_execution_request() -> None:
    """No attempt's `ExecutionRequest` is reused across a repair."""
    engine = FakeEngine(
        [CompletionResult(_VALID_COMPLETION, "m-1", STOP_END)] * 2
    )
    executor = FakeExecutor([_command_failure_report(), _ok_report()])

    _run(engine, executor)

    assert len(executor.calls) == 2
    assert executor.calls[0] is not executor.calls[1]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
