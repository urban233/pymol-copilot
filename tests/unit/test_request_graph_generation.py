# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for `preparing` and `generating`.

Runs the compiled graph against a `FakeEngine`, never a real one --
docs/master_plan.md item 8: "Test every transition and terminal state
against a fake inference adapter." `validating` is real as of step 7, so
every test here that reaches it also injects a fake executor that always
succeeds -- this file's own scope stays `preparing` and `generating`;
`validating`'s own behavior is tests/unit/test_request_graph_repair.py's.
"""

from typing import cast

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.
from langgraph.checkpoint.memory import InMemorySaver

from pmc_agent.graph import ACCEPTED_CONTRACT_MANIFEST
from pmc_agent.graph import FAILURE_ENGINE_INCOMPLETE
from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.graph import STATE_RECEIVED
from pmc_agent.graph import TERMINAL_ASK
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import RequestState
from pmc_agent.graph import build_request_graph
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import STOP_DEADLINE
from pmc_agent.inference.base import STOP_LENGTH
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import ENGINE_REFUSED_GRAMMAR
from pmc_agent.inference.base import ENGINE_TIMEOUT
from pmc_agent.inference.base import ENGINE_UNAVAILABLE
from pmc_agent.inference.base import ENGINE_UNKNOWN
from pmc_agent.inference.fake import FakeEngine
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json


def _always_ok_executor(_request: ExecutionRequest) -> ExecutionReport:
    """Report success for any request, without ever spawning anything.

    This file's own tests never inspect `validating`'s behavior -- only
    that it is real, and that a well-formed request can reach past it --
    so a single scripted success is all `_run` below needs.

    Args:
        _request: Ignored.

    Returns:
        A minimal `STATUS_OK` report.
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


_OBJECT_NAME = "fx"


def _snapshot() -> ObjectSnapshot:
    """Build the smallest well-formed snapshot, named `_OBJECT_NAME`.

    Returns:
        An empty-state ObjectSnapshot, sufficient for every test below --
        `_run` always injects `_always_ok_executor`, so nothing here ever
        reaches a real sidecar spawn.
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


def _state(
    *,
    contract_manifest: ContractManifestV1 = ACCEPTED_CONTRACT_MANIFEST,
    snapshot_json: str | None = None,
) -> RequestState:
    """Build a realistic request state, ready to enter `preparing`.

    Args:
        contract_manifest: The manifest this request declares.
        snapshot_json: The canonical snapshot JSON to carry. Defaults to
            `_snapshot()`'s own encoding.

    Returns:
        A request state `preparing` accepts as well-formed by default.
    """
    return cast(
        RequestState,
        {
            "request_id": "11111111-1111-4111-8111-111111111111",
            "session_id": "22222222-2222-4222-8222-222222222222",
            "created_at": "2026-09-21T00:00:00.000Z",
            "intent": "orient chain A",
            "contract_manifest": contract_manifest,
            "snapshot_identity": StructureSnapshotV1(
                schema_version="1",
                digest="sha256:test-digest",
                object_name=_OBJECT_NAME,
                atom_count=0,
                state_count=0,
            ),
            "snapshot_json": (
                snapshot_json
                if snapshot_json is not None
                else to_json(_snapshot())
            ),
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


def _run(engine: FakeEngine, state: RequestState) -> dict[str, object]:
    """Compile the graph against `engine` and run `state` to completion.

    `validating` runs for real for any request that reaches it, always
    against `_always_ok_executor` -- never the real
    `pmc_core.executor.execute` default, which would try to spawn a real
    sidecar process against this file's placeholder snapshot identity.

    Args:
        engine: The fake engine `generating` will call.
        state: The request state to invoke the graph with.

    Returns:
        The invocation's result mapping.
    """
    compiled = build_request_graph(
        engine=engine, executor=_always_ok_executor
    ).compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": state["session_id"]}}
    return compiled.invoke(state, config)


def test_a_first_pass_success_calls_the_engine_exactly_once() -> None:
    """A well-formed request calls the engine once and reaches `validating`.

    A single `invoke()` call runs straight through `validating` (real as
    of step 7, here against `_always_ok_executor`) to `pending_approval`
    and parks there -- the assertion that matters in this file is the
    engine call count and what `generating` itself wrote, both already
    final by the time `validating` runs.
    """
    engine = FakeEngine([CompletionResult("orient chain A\n", "m-1", STOP_END)])

    result = _run(engine, _state())

    assert len(engine.calls) == 1
    assert "__interrupt__" in result
    assert result["status"] == STATE_PENDING_APPROVAL
    assert result["completion"] == "orient chain A\n"
    assert result["model_identity"] == engine.model_identity
    assert result["attempt"] == 1


def test_the_engine_identity_wins_over_a_completion_claim() -> None:
    """Approval provenance comes from the engine, not response metadata."""
    engine = FakeEngine(
        [CompletionResult("orient chain A\n", "claimed-model", STOP_END)],
        model_identity="verified-engine-model",
    )

    result = _run(engine, _state())

    assert result["status"] == STATE_PENDING_APPROVAL
    assert result["model_identity"] == "verified-engine-model"


def test_a_contract_manifest_mismatch_never_calls_the_engine() -> None:
    """A rejected manifest fails closed before generation is ever tried."""
    engine = FakeEngine([])
    mismatched = ContractManifestV1(
        plan_version="2", policy_version="1", snapshot_version="1"
    )

    result = _run(engine, _state(contract_manifest=mismatched))

    assert engine.calls == ()
    assert result["status"] == TERMINAL_FAILED
    failure = result["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == "contract_mismatch"
    assert failure.retryable is False


def test_a_malformed_snapshot_never_calls_the_engine() -> None:
    """Undecodable snapshot JSON fails closed before generation."""
    engine = FakeEngine([])

    result = _run(engine, _state(snapshot_json="{not valid json"))

    assert engine.calls == ()
    assert result["status"] == TERMINAL_FAILED
    failure = result["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == "malformed_snapshot"


@pytest.mark.parametrize(
    "completion",
    ["", "   ", "\n\n"],
    ids=["empty", "whitespace", "blank_lines"],
)
def test_an_empty_completion_reaches_ask_with_a_fixed_question(
    completion: str,
) -> None:
    """Empty or whitespace-only output is a clarification, not a plan.

    Args:
        completion: An empty-in-substance completion.
    """
    engine = FakeEngine([CompletionResult(completion, "m-1", STOP_END)])

    result = _run(engine, _state())

    assert result["status"] == TERMINAL_ASK
    assert result["plan"] is None
    question = result["question"]
    assert isinstance(question, str)
    assert question
    assert all(0x20 <= ord(char) < 0x7F for char in question)


def test_an_explicit_ask_line_reaches_ask_with_its_bounded_question() -> None:
    """An `ask: <question>` completion carries its question through."""
    engine = FakeEngine(
        [CompletionResult("ask: which chain do you mean?", "m-1", STOP_END)]
    )

    result = _run(engine, _state())

    assert result["status"] == TERMINAL_ASK
    assert result["plan"] is None
    assert result["question"] == "which chain do you mean?"


def test_an_ask_questions_case_and_quoted_names_survive_bounding() -> None:
    """A realistic question is bounded, not mangled like a PyMOL exception.

    Regression: the question path used to run through
    `pmc_core.errors.normalize_message`, built to sanitize a raw PyMOL
    exception -- it lowercases its input and replaces every quoted span
    with a fixed redaction marker, destroying exactly the chain names a
    clarifying question needs to read back.
    """
    engine = FakeEngine(
        [
            CompletionResult(
                'ask: Did you mean chain "A" or "B"?', "m-1", STOP_END
            )
        ]
    )

    result = _run(engine, _state())

    assert result["status"] == TERMINAL_ASK
    assert result["question"] == 'Did you mean chain "A" or "B"?'


@pytest.mark.parametrize(
    "category",
    [
        ENGINE_UNAVAILABLE,
        ENGINE_TIMEOUT,
        ENGINE_REFUSED_GRAMMAR,
        ENGINE_UNKNOWN,
    ],
)
def test_every_engine_failure_category_reaches_failed(category: str) -> None:
    """Every engine failure category ends the request, typed, no traceback.

    Args:
        category: An `EngineFailure` category `generating` must handle.
    """
    engine = FakeEngine([EngineFailure(category, "engine says no")])

    result = _run(engine, _state())

    assert result["status"] == TERMINAL_FAILED
    failure = result["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == category
    assert failure.message == "engine says no"


def test_an_engine_failure_message_is_bounded_before_reaching_the_wire() -> (
    None
):
    """An adapter cannot turn its diagnostic into an oversized response."""
    engine = FakeEngine([EngineFailure(ENGINE_UNKNOWN, "x" * 500)])

    result = _run(engine, _state())

    failure = result["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert len(failure.message) == 200
    assert failure.message.endswith("...")


@pytest.mark.parametrize(
    "stop_reason", [STOP_LENGTH, STOP_DEADLINE], ids=["length", "deadline"]
)
def test_a_partial_completion_never_reaches_validation(
    stop_reason: str,
) -> None:
    """A clean line-boundary truncation is still not an approvable plan.

    Args:
        stop_reason: The non-natural completion stop the engine reports.
    """
    engine = FakeEngine(
        [CompletionResult("orient chain A\n", "m-1", stop_reason)]
    )

    result = _run(engine, _state())

    assert result["status"] == TERMINAL_FAILED
    failure = result["failure"]
    assert isinstance(failure, FailureEnvelopeV1)
    assert failure.category == FAILURE_ENGINE_INCOMPLETE
    assert result["attempt"] == 1


@pytest.mark.parametrize(
    "completion",
    [
        "orient chain A\n",
        "select copilot_x, chain B\ncolor red, copilot_x\n",
        "orient chain Z\n",
    ],
    ids=["same_object_implied", "different_selection", "different_chain"],
)
def test_target_object_is_fixed_by_preparing_never_by_the_completion(
    completion: str,
) -> None:
    """`target_object` always equals the client's resolved object.

    Nothing about the completion's own text -- even one that reads as
    though it names a different chain or object -- ever changes it:
    `preparing` sets it once, from `snapshot_identity.object_name`, and no
    node after it, including `generating`, rewrites the field.

    Args:
        completion: A completion whose text is irrelevant to this
            assertion by construction.
    """
    engine = FakeEngine([CompletionResult(completion, "m-1", STOP_END)])

    result = _run(engine, _state())

    assert result["target_object"] == _OBJECT_NAME


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
