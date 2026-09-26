# Copyright 2026 PyMOL Copilot contributors.
"""The harness runs the runtime's own request graph and reads it back right.

Hermetic: the model is a `FakeEngine` and the sidecar a scripted
executor, but the request graph between them is the real, compiled
`pmc_agent.graph`. Each outcome is reached the way the runtime would
reach it, not by calling the harness's own bookkeeping directly.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses

import pytest

from fakes import ScriptedExecutor
from fakes import command_failure_report
from fakes import completion
from fakes import failed_report
from fakes import ok_report
from pmc_agent.inference.base import ENGINE_TIMEOUT
from pmc_agent.inference.base import STOP_LENGTH
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.prompt import AttemptFailure
from pmc_core.executor import REASON_CHILD_CRASH
from pmc_core.executor import ExecutionReport
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_core.policy import PolicyDecision
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import read_samples
from pmc_eval.prompt import repair_line
from pmc_eval.prompt import snapshot_for
from pmc_eval.record import OUTCOME_ABSTAINED
from pmc_eval.record import OUTCOME_DENIED_HOSTILE
from pmc_eval.record import OUTCOME_DENIED_POLICY
from pmc_eval.record import OUTCOME_EXECUTED_WRONG
from pmc_eval.record import OUTCOME_EXECUTION_FAILED
from pmc_eval.record import OUTCOME_SUCCESS
from pmc_eval.record import OUTCOME_SYNTAX_INVALID
from pmc_eval.record import OUTCOME_TRUNCATED
from pmc_eval.record import InfraFailure
from pmc_eval.record import SampleRecord
from pmc_eval.runner import CONDITION_GRAMMAR
from pmc_eval.runner import CONDITION_NO_GRAMMAR
from pmc_eval.runner import Condition
from pmc_eval.runner import RecordingEngine
from pmc_eval.runner import RecordingExecutor
from pmc_eval.runner import VersionDriftError
from pmc_eval.runner import compile_request_graph
from pmc_eval.runner import grammar_text
from pmc_eval.runner import request_state_for
from pmc_eval.runner import run_sample

#: "make the zinc ions magenta", graded on its resulting fingerprint.
SAMPLE = read_samples(DEFAULT_GOLD_SAMPLES_PATH)[0]
RIGHT = SAMPLE.verification.resulting_fingerprint
WRONG = "sha256:" + "f" * 64

GOOD = "color magenta, resn ZN\n"
UNKNOWN_VERB = "colour magenta, resn ZN\n"

NO_GRAMMAR = Condition(
    name=CONDITION_NO_GRAMMAR,
    grammar=False,
    max_tokens=256,
    deadline_seconds=600.0,
)
GRAMMAR = dataclasses.replace(NO_GRAMMAR, name=CONDITION_GRAMMAR, grammar=True)


def _record(result: SampleRecord | InfraFailure) -> SampleRecord:
    """Narrow a run's result to a scored record.

    Args:
        result: What `run_sample` returned.

    Returns:
        The record.
    """
    assert isinstance(result, SampleRecord), result
    return result


def _deny(_plan: ActionPlan) -> PlanDecision:
    """Deny every plan, as no real policy denies a parsed one.

    Args:
        _plan: Ignored.

    Returns:
        A denial naming the first operation.
    """
    return PlanDecision(
        decisions=(
            PolicyDecision(
                operation_index=0,
                allowed=False,
                reason="unsupported_color_arguments",
            ),
        ),
        allowed=False,
    )


def test_wrappers_are_transparent() -> None:
    """The wrapped graph behaves exactly as the bare one when nothing differs.

    With the grammar off and every completion already ending in a
    newline, neither wrapper has anything to change, so the two graphs
    must end in the same state having made the same engine calls.
    """
    script = [completion(UNKNOWN_VERB), completion(GOOD)]
    snapshot = snapshot_for(SAMPLE)
    bare_engine = FakeEngine(script)
    wrapped_engine = FakeEngine(script)

    bare = compile_request_graph(
        engine=bare_engine,
        executor=ScriptedExecutor([ok_report(fingerprint=RIGHT)]),
        condition=NO_GRAMMAR,
    ).invoke(
        request_state_for(SAMPLE, snapshot),
        {"configurable": {"thread_id": "t"}},
    )
    wrapped = compile_request_graph(
        engine=RecordingEngine(wrapped_engine, grammar=None),
        executor=RecordingExecutor(
            ScriptedExecutor([ok_report(fingerprint=RIGHT)])
        ),
        condition=NO_GRAMMAR,
    ).invoke(
        request_state_for(SAMPLE, snapshot),
        {"configurable": {"thread_id": "t"}},
    )

    del bare["__interrupt__"], wrapped["__interrupt__"]
    assert wrapped == bare
    assert wrapped_engine.calls == bare_engine.calls


def test_a_right_plan_is_a_success() -> None:
    """A plan reaching the stored state is a TaskSuccess on attempt one."""
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(GOOD)]),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([ok_report(fingerprint=RIGHT)]),
        )
    )

    assert record.final_outcome == OUTCOME_SUCCESS
    assert record.task_success
    assert [a.outcome for a in record.attempts] == [OUTCOME_SUCCESS]
    assert record.attempts[0].plan_pml == GOOD
    assert record.empty_selection == "false"


def test_a_plan_reaching_another_state_is_executed_wrong() -> None:
    """A plan that runs cleanly to the wrong state is not repaired."""
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion("color red, resn ZN\n")]),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([ok_report(fingerprint=WRONG)]),
        )
    )

    assert record.final_outcome == OUTCOME_EXECUTED_WRONG
    assert not record.task_success
    assert len(record.attempts) == 1


def test_a_truncated_completion_is_never_parsed() -> None:
    """A completion cut off by the token limit ends the request."""
    executor = ScriptedExecutor([])
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(GOOD, STOP_LENGTH)]),
            condition=NO_GRAMMAR,
            executor=executor,
        )
    )

    assert record.final_outcome == OUTCOME_TRUNCATED
    assert executor.calls == ()


@pytest.mark.parametrize("text", ["ask: which zinc ions?", "", "   \n"])
def test_a_question_or_nothing_is_an_abstention(text: str) -> None:
    """The graph's ask rule is the harness's abstention.

    Args:
        text: A clarification, or an empty completion.
    """
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(text)]),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([]),
        )
    )

    assert record.final_outcome == OUTCOME_ABSTAINED


def test_prose_is_denied_as_hostile_with_its_reasons() -> None:
    """An apostrophe in prose trips the screen, and is never repaired."""
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine(
                [completion("Here's the command: color magenta, resn ZN")]
            ),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([]),
        )
    )

    assert record.final_outcome == OUTCOME_DENIED_HOSTILE
    assert len(record.attempts) == 1
    assert record.attempts[0].hostile_reasons == ("character:'",)


def test_repairs_stop_after_two() -> None:
    """Three unparseable completions exhaust the repair budget."""
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(UNKNOWN_VERB)] * 3),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([]),
        )
    )

    assert [a.outcome for a in record.attempts] == [OUTCOME_SYNTAX_INVALID] * 3
    assert record.final_outcome == OUTCOME_SYNTAX_INVALID
    assert {a.category for a in record.attempts} == {"unknown_verb"}


def test_a_repaired_plan_carries_the_failure_in_its_prompt() -> None:
    """The second attempt's prompt feeds back the first attempt's failure."""
    engine = FakeEngine([completion(UNKNOWN_VERB), completion(GOOD)])

    record = _record(
        run_sample(
            SAMPLE,
            engine=engine,
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([ok_report(fingerprint=RIGHT)]),
        )
    )

    assert [a.outcome for a in record.attempts] == [
        OUTCOME_SYNTAX_INVALID,
        OUTCOME_SUCCESS,
    ]
    first, second = (call.prompt for call in engine.calls)
    assert first == SAMPLE.prompt_text
    assert second.startswith(first)
    assert second[len(first) :].startswith("previous attempt failed (parse, ")


def test_a_policy_denial_is_repaired() -> None:
    """A denial is fed back and repaired, like a parse rejection."""
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(GOOD)] * 3),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([]),
            policy_validator=_deny,
        )
    )

    assert [a.outcome for a in record.attempts] == [OUTCOME_DENIED_POLICY] * 3


def test_a_command_failure_is_repaired_with_its_envelope() -> None:
    """A PyMOL command failure is fed back with its normalized category."""
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(GOOD)] * 3),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([command_failure_report()] * 3),
        )
    )

    assert record.final_outcome == OUTCOME_EXECUTION_FAILED
    assert [a.category for a in record.attempts] == ["unknown_color"] * 3
    assert all(a.execution is not None for a in record.attempts)


@pytest.mark.parametrize(
    ("condition", "expected"),
    [(NO_GRAMMAR, None), (GRAMMAR, grammar_text())],
    ids=[CONDITION_NO_GRAMMAR, CONDITION_GRAMMAR],
)
def test_grammar_is_sent_only_under_the_grammar_condition(
    condition: Condition, expected: str | None
) -> None:
    """The graph sends no grammar; the harness adds it under one condition.

    Args:
        condition: The condition to run under.
        expected: The grammar the engine must have received.
    """
    engine = FakeEngine([completion(GOOD)])

    record = _record(
        run_sample(
            SAMPLE,
            engine=engine,
            condition=condition,
            executor=ScriptedExecutor([ok_report(fingerprint=RIGHT)]),
        )
    )

    assert engine.calls[0].grammar == expected
    assert record.attempts[0].grammar_sent == (expected is not None)


def test_newline_is_appended_only_when_missing_and_raw_is_kept() -> None:
    """A plan missing its final newline still parses; the raw text is kept."""
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(GOOD.rstrip("\n"))]),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([ok_report(fingerprint=RIGHT)]),
        )
    )
    unchanged = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(GOOD)]),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([ok_report(fingerprint=RIGHT)]),
        )
    )

    assert record.final_outcome == OUTCOME_SUCCESS
    assert record.attempts[0].newline_appended
    assert record.attempts[0].completion == GOOD.rstrip("\n")
    assert not unchanged.attempts[0].newline_appended


def test_engine_failure_is_infrastructure() -> None:
    """An engine that fails says nothing about the model and is not scored."""
    result = run_sample(
        SAMPLE,
        engine=FakeEngine([EngineFailure(ENGINE_TIMEOUT, "took too long")]),
        condition=NO_GRAMMAR,
        executor=ScriptedExecutor([]),
    )

    assert isinstance(result, InfraFailure)
    assert result.category == ENGINE_TIMEOUT


def test_control_run_attributes_a_plan_induced_crash_to_the_model() -> None:
    """A crash the model's plan reproduces, and the reference does not."""
    crash = failed_report(REASON_CHILD_CRASH)

    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(GOOD)]),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor(
                [crash, crash, ok_report(fingerprint=RIGHT)]
            ),
        )
    )

    assert record.final_outcome == OUTCOME_EXECUTION_FAILED
    assert record.attempts[-1].category == "execution_child_crash"


@pytest.mark.parametrize(
    "control",
    [
        pytest.param([failed_report(REASON_CHILD_CRASH)] * 2, id="reference"),
        pytest.param([ok_report(fingerprint=RIGHT)], id="not-reproduced"),
    ],
)
def test_a_crash_the_control_does_not_pin_on_the_model_is_infrastructure(
    control: list[ExecutionReport],
) -> None:
    """A crash that does not reproduce, or that hits the reference too.

    Args:
        control: What the control runs report after the first crash.
    """
    result = run_sample(
        SAMPLE,
        engine=FakeEngine([completion(GOOD)]),
        condition=NO_GRAMMAR,
        executor=ScriptedExecutor(
            [failed_report(REASON_CHILD_CRASH), *control]
        ),
    )

    assert isinstance(result, InfraFailure)
    assert result.category == "execution_child_crash"


def test_version_drift_is_refused() -> None:
    """A sample verified under another contract is not evaluated."""
    stale = dataclasses.replace(
        SAMPLE,
        versions=dataclasses.replace(SAMPLE.versions, policy_version=0),
    )

    with pytest.raises(VersionDriftError):
        run_sample(
            stale,
            engine=FakeEngine([]),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([]),
        )


def test_a_record_round_trips_through_its_json_form() -> None:
    """What a run writes is exactly what the report is recomputed from."""
    record = _record(
        run_sample(
            SAMPLE,
            engine=FakeEngine([completion(UNKNOWN_VERB), completion(GOOD)]),
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([ok_report(fingerprint=RIGHT)]),
        )
    )

    assert SampleRecord.from_dict(record.to_dict()) == record
    assert "timings" not in record.to_dict()
    assert len(record.timings) == 2


def test_the_repair_line_names_the_first_failure() -> None:
    """The repair prompt's line is `repair_line` of the recorded failure."""
    engine = FakeEngine([completion(UNKNOWN_VERB), completion(GOOD)])
    record = _record(
        run_sample(
            SAMPLE,
            engine=engine,
            condition=NO_GRAMMAR,
            executor=ScriptedExecutor([ok_report(fingerprint=RIGHT)]),
        )
    )
    first = record.attempts[0]

    tail = engine.calls[1].prompt[len(SAMPLE.prompt_text) :]

    assert tail.startswith("previous attempt failed (parse, command 0): ")
    assert first.category == "unknown_verb"
    assert tail == repair_line(
        AttemptFailure(
            source="parse",
            category="unknown_verb",
            command_index=0,
            message="verb is not in the command allowlist",
        )
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
