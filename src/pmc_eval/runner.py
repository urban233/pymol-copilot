# Copyright 2026 PyMOL Copilot contributors.
"""Run one stored sample through the runtime's own request graph.

The harness does not reimplement the generate, screen, parse, policy,
sidecar and repair loop. It compiles `pmc_agent.graph`'s request graph,
exactly as the unit tests do, and wraps three of its seams:

- the engine, so the grammar can be sent under the `grammar` condition
  (the graph is built without its own `grammar`), so a missing final
  newline can be appended before the graph sees a completion, and so
  every request and raw completion is kept;
- the executor, so every sidecar report is kept;
- the plan-id source and clock, so a run is deterministic.

The prompt builder is `pmc_eval.prompt.contract_prompt`. Everything
else -- the ask rule, the hostile screen, the repair budget, how a
failure is bounded and fed back -- is the graph's own, so the harness
measures the loop the runtime runs rather than a copy that could drift
from it.

Each attempt's outcome is read back from the graph's own state, never
re-derived: every repairable failure is one entry in `errors`, and the
terminal status says how the last attempt ended.

The newline normalization is a declared deviation from the runtime,
settled with Martin: `pmc_core.parser.parse_pml` rejects a completion
that does not end in a newline, and a chat model's completion usually
does not, so without it the ungrammared condition would measure that
formatting rule rather than the model. It is a no-op under the grammar,
which forces every command to end in a newline.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import functools
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import cast

from langgraph.graph.state import CompiledStateGraph

from pmc_agent.graph import FAILURE_ENGINE_INCOMPLETE
from pmc_agent.graph import FAILURE_EXECUTION_PREFIX
from pmc_agent.graph import FAILURE_REPAIR_EXHAUSTED
from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.graph import STATE_RECEIVED
from pmc_agent.graph import TERMINAL_ASK
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import TERMINAL_REJECTED
from pmc_agent.graph import RequestState
from pmc_agent.graph import build_request_graph
from pmc_agent.graph import new_checkpointer
from pmc_agent.inference.base import ENGINE_FAILURE_CATEGORIES
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import EngineHealth
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.prompt import AttemptFailure
from pmc_core.card import CARD_VERSION
from pmc_core.executor import DEFAULT_DEADLINE_SECONDS
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import execute
from pmc_core.grammar import build_grammar
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.policy import PlanDecision
from pmc_core.policy import evaluate_plan
from pmc_core.prompt import PROMPT_VERSION
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.sample import Sample
from pmc_data.sample import current_versions
from pmc_eval.grade import AssertionResult
from pmc_eval.grade import grade
from pmc_eval.grade import grading_complete
from pmc_eval.grade import is_vacuous
from pmc_eval.prompt import contract_prompt
from pmc_eval.prompt import snapshot_for
from pmc_eval.record import OUTCOME_ABSTAINED
from pmc_eval.record import OUTCOME_DENIED_HOSTILE
from pmc_eval.record import OUTCOME_DENIED_POLICY
from pmc_eval.record import OUTCOME_EXECUTED_WRONG
from pmc_eval.record import OUTCOME_EXECUTION_FAILED
from pmc_eval.record import OUTCOME_SUCCESS
from pmc_eval.record import OUTCOME_SYNTAX_INVALID
from pmc_eval.record import OUTCOME_TRUNCATED
from pmc_eval.record import AttemptRecord
from pmc_eval.record import AttemptTiming
from pmc_eval.record import ExecutionSummary
from pmc_eval.record import InfraFailure
from pmc_eval.record import SampleRecord
from pmc_eval.screen_reasons import hostile_reasons

#: The names of the two conditions every run is made under.
CONDITION_NO_GRAMMAR = "no-grammar"
CONDITION_GRAMMAR = "grammar"

#: The one normalization the harness applies to a completion, named so a
#: run records exactly what it did. See the module docstring.
NORMALIZATION = "append-missing-final-newline"

#: The version of how this module drives the graph: which seams it wraps,
#: what it sends, and how it reads each attempt's outcome back. Any change
#: to any of those is a bump, and a new baseline.
HARNESS_VERSION = 1

#: What each `AttemptFailure.source` the graph records means as an
#: attempt outcome.
_SOURCE_OUTCOMES = {
    "parse": OUTCOME_SYNTAX_INVALID,
    "policy": OUTCOME_DENIED_POLICY,
    "execution": OUTCOME_EXECUTION_FAILED,
}

#: The fixed identities and moment a harness request carries. Nothing in
#: the graph's decisions depends on them; fixing them makes a run
#: reproducible.
_FIXED_MOMENT = datetime(2026, 1, 1, tzinfo=UTC)
_FIXED_PLAN_ID = "00000000-0000-4000-8000-000000000000"


class VersionDriftError(ValueError):
    """A stored sample was verified under contracts no longer in force."""


class HarnessDefectError(RuntimeError):
    """The graph ended in a state the harness never produces a request for."""


@dataclass(frozen=True)
class Condition:
    """How every generation in a run is bounded and constrained.

    Attributes:
        name: `CONDITION_NO_GRAMMAR` or `CONDITION_GRAMMAR`.
        grammar: Whether `pmc_core.grammar.build_grammar()` is sent with
            every generation.
        max_tokens: The token budget of every generation.
        deadline_seconds: The wall-clock budget of every generation. Set
            far above what the slowest host needs, so it never binds on
            a slow CPU and an engine timeout really is an infrastructure
            failure.
    """

    name: str
    grammar: bool
    max_tokens: int
    deadline_seconds: float


@functools.cache
def grammar_text() -> str:
    """Return the engine grammar, built once.

    Returns:
        `pmc_core.grammar.build_grammar()`'s GBNF document.
    """
    return build_grammar()


@dataclass(frozen=True)
class CompletionCall:
    """One engine call as the recording wrapper saw it.

    Attributes:
        request: The request actually sent, with the grammar set.
        outcome: What the engine returned, before normalization.
        newline_appended: Whether the harness appended a final newline.
        elapsed_seconds: Wall-clock seconds the call took.
    """

    request: CompletionRequest
    outcome: CompletionResult | EngineFailure
    newline_appended: bool
    elapsed_seconds: float


class RecordingEngine:
    """An `InferenceEngine` wrapper: grammar in, newline fixed, all kept."""

    def __init__(
        self,
        inner: InferenceEngine,
        *,
        grammar: str | None,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        """Wrap an engine.

        Args:
            inner: The engine every call is forwarded to.
            grammar: The grammar to send with every request, or None to
                send none.
            timer: A monotonic clock, for the call timings.
        """
        self._inner = inner
        self._grammar = grammar
        self._timer = timer
        self._calls: list[CompletionCall] = []

    @property
    def model_identity(self) -> str:
        """Return the wrapped engine's identity.

        Returns:
            The inner engine's `model_identity`.
        """
        return self._inner.model_identity

    def health(self) -> EngineHealth:
        """Return the wrapped engine's health.

        Returns:
            The inner engine's `health()`.
        """
        return self._inner.health()

    @property
    def calls(self) -> tuple[CompletionCall, ...]:
        """Return every call so far, in order.

        Returns:
            The recorded calls.
        """
        return tuple(self._calls)

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Forward one request with the grammar set; fix a final newline.

        Args:
            request: The graph's request.
            cancel: The graph's cancellation token, forwarded.

        Returns:
            The inner engine's outcome, with a newline appended to a
            completion's text when it did not end in one.
        """
        sent = dataclasses.replace(request, grammar=self._grammar)
        started = self._timer()
        outcome = self._inner.complete(sent, cancel=cancel)
        elapsed = self._timer() - started
        appended = isinstance(
            outcome, CompletionResult
        ) and not outcome.text.endswith("\n")
        self._calls.append(
            CompletionCall(
                request=sent,
                outcome=outcome,
                newline_appended=appended,
                elapsed_seconds=elapsed,
            )
        )
        if appended and isinstance(outcome, CompletionResult):
            return dataclasses.replace(outcome, text=outcome.text + "\n")
        return outcome


class RecordingExecutor:
    """An executor wrapper that keeps every request and report."""

    def __init__(
        self, inner: Callable[[ExecutionRequest], ExecutionReport]
    ) -> None:
        """Wrap an executor.

        Args:
            inner: The executor every call is forwarded to.
        """
        self._inner = inner
        self._calls: list[tuple[ExecutionRequest, ExecutionReport]] = []

    @property
    def calls(self) -> tuple[tuple[ExecutionRequest, ExecutionReport], ...]:
        """Return every call so far, in order.

        Returns:
            Each request with the report it produced.
        """
        return tuple(self._calls)

    def __call__(self, request: ExecutionRequest) -> ExecutionReport:
        """Forward one request and keep its report.

        Args:
            request: The graph's execution request.

        Returns:
            The inner executor's report.
        """
        report = self._inner(request)
        self._calls.append((request, report))
        return report


def request_state_for(sample: Sample, snapshot: ObjectSnapshot) -> RequestState:
    """Build the request state a client would send for this sample.

    The structure is synthetic and its snapshot canonical by
    construction, so its fidelity is exact: there is no live session for
    it to disagree with.

    Args:
        sample: The stored sample.
        snapshot: Its rebuilt structure.

    Returns:
        A request state the graph's `preparing` node accepts.
    """
    identity = f"eval-{sample.sample_id}"
    return cast(
        RequestState,
        {
            "request_id": identity,
            "session_id": identity,
            "created_at": "2026-01-01T00:00:00.000Z",
            "intent": sample.intent,
            "contract_manifest": CURRENT_CONTRACT_MANIFEST,
            "snapshot_identity": StructureSnapshotV1(
                schema_version=str(snapshot.schema_version),
                digest=structure_digest(snapshot),
                object_name=snapshot.name,
                atom_count=(
                    len(snapshot.states[0].atoms) if snapshot.states else 0
                ),
                state_count=len(snapshot.states),
            ),
            "snapshot_json": to_json(snapshot),
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


def compile_request_graph(
    *,
    engine: InferenceEngine,
    executor: Callable[[ExecutionRequest], ExecutionReport],
    condition: Condition,
    validation_deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    policy_validator: Callable[[ActionPlan], PlanDecision] = evaluate_plan,
) -> CompiledStateGraph:
    """Compile the runtime's request graph with the harness's seams.

    Args:
        engine: The engine `generating` calls.
        executor: The executor `validating` calls.
        condition: The generation bounds.
        validation_deadline_seconds: The sidecar's own deadline.
        policy_validator: The policy re-check. Always the real one in a
            run; injectable only so a test can reach the graph's denial
            path, which a parsed plan cannot reach for real.

    Returns:
        The compiled graph, with an in-memory checkpointer.
    """
    return build_request_graph(
        engine=engine,
        prompt_builder=contract_prompt,
        max_tokens=condition.max_tokens,
        deadline_seconds=condition.deadline_seconds,
        executor=executor,
        policy_validator=policy_validator,
        plan_id_source=lambda: _FIXED_PLAN_ID,
        clock=lambda: _FIXED_MOMENT,
        validation_deadline_seconds=validation_deadline_seconds,
    ).compile(checkpointer=new_checkpointer())


def _summary(report: ExecutionReport) -> ExecutionSummary:
    """Keep what a report says about the model, not about the process.

    Args:
        report: A sidecar report.

    Returns:
        Its summary, without PIDs, timings or warnings.
    """
    failing = next(
        (o for o in report.command_outcomes if o.status == OUTCOME_ERROR),
        None,
    )
    envelope = failing.error_envelope if failing is not None else None
    return ExecutionSummary(
        status=report.status,
        reason=report.reason,
        resulting_fingerprint=report.resulting_fingerprint,
        selection_counts=tuple(
            (count.name, count.atom_count) for count in report.selection_counts
        ),
        failed_command_index=failing.index if failing is not None else None,
        failed_category=envelope.category if envelope is not None else None,
    )


def _parsed(text: str) -> ActionPlan | None:
    """Parse a normalized completion, or report that it does not parse.

    Args:
        text: The completion as the graph saw it.

    Returns:
        The plan, or None.
    """
    parsed = parse_pml(text)
    return parsed if isinstance(parsed, ActionPlan) else None


@dataclass(frozen=True)
class _Terminal:
    """How the last attempt ended, read off the graph's final state.

    Attributes:
        outcome: The last attempt's outcome, or None for an executed plan
            the grade has yet to decide.
        category: Its failure category, if any.
        command_index: The command its failure names, if any.
        executed: Whether the last attempt's plan reached the sidecar.
        infra: The failure category, when infrastructure failed.
    """

    outcome: str | None
    category: str | None
    command_index: int | None
    executed: bool
    infra: str | None


def _terminal(
    result: dict[str, object], errors: tuple[AttemptFailure, ...]
) -> _Terminal:
    """Read how the last attempt ended off the graph's final state.

    Args:
        result: The graph invocation's final state.
        errors: The failures the graph recorded, oldest first.

    Returns:
        The last attempt's ending.

    Raises:
        HarnessDefectError: For an ending the harness never requests: a
            contract, snapshot or target failure, a cancellation, or an
            unrecognized failure category.
    """
    status = result["status"]
    if status == STATE_PENDING_APPROVAL:
        return _Terminal(None, None, None, executed=True, infra=None)
    if status == TERMINAL_ASK:
        return _Terminal(OUTCOME_ABSTAINED, None, None, False, None)
    if status == TERMINAL_REJECTED:
        return _Terminal(OUTCOME_DENIED_HOSTILE, None, None, False, None)
    if status != TERMINAL_FAILED:
        raise HarnessDefectError(f"graph ended at unexpected {status!r}")
    failure = result["failure"]
    category = getattr(failure, "category", None)
    if category == FAILURE_REPAIR_EXHAUSTED:
        last = errors[-1]
        return _Terminal(
            _SOURCE_OUTCOMES[last.source],
            last.category,
            last.command_index,
            executed=last.source == "execution",
            infra=None,
        )
    if category == FAILURE_ENGINE_INCOMPLETE:
        return _Terminal(
            OUTCOME_TRUNCATED, FAILURE_ENGINE_INCOMPLETE, None, False, None
        )
    if category in ENGINE_FAILURE_CATEGORIES:
        return _Terminal(None, None, None, executed=False, infra=category)
    if isinstance(category, str) and category.startswith(
        FAILURE_EXECUTION_PREFIX
    ):
        return _Terminal(None, None, None, executed=True, infra=category)
    raise HarnessDefectError(f"graph failed with unexpected {category!r}")


def _control_attributes_to_model(
    *,
    plan: ActionPlan | None,
    sample: Sample,
    snapshot_json: str,
    digest: str,
    reason: str,
    executor: Callable[[ExecutionRequest], ExecutionReport],
    validation_deadline_seconds: float,
) -> bool:
    """Decide whether a non-command sidecar failure is the model's doing.

    The graph ends a request, unrepaired, on any sidecar failure other
    than a command failure -- a timeout, a crash, a spawn failure. Most
    are infrastructure. One the model's own plan reliably causes is not.
    It counts as the model's only when the model's plan fails again, the
    same way, in a fresh sidecar, and the sample's own reference plan
    succeeds against the same structure.

    Args:
        plan: The model's plan, if its completion parsed.
        sample: The stored sample, whose reference plan is the control.
        snapshot_json: The structure the plan ran against.
        digest: Its structure digest.
        reason: The executor reason the graph's run failed with.
        executor: The unwrapped executor.
        validation_deadline_seconds: The sidecar's own deadline.

    Returns:
        True when the failure reproduces for the model's plan and not for
        the reference plan.
    """
    reference = _parsed(sample.plan_pml)
    if plan is None or reference is None:
        return False

    def _run(candidate: ActionPlan) -> ExecutionReport:
        return executor(
            ExecutionRequest(
                executor_version=EXECUTOR_VERSION,
                plan=candidate,
                snapshot_json=snapshot_json,
                expected_snapshot_digest=digest,
                deadline_seconds=validation_deadline_seconds,
            )
        )

    again = _run(plan)
    if again.status == STATUS_OK or again.reason != reason:
        return False
    return _run(reference).status == STATUS_OK


def check_versions(sample: Sample) -> None:
    """Refuse a sample verified under contracts no longer in force.

    Args:
        sample: The stored sample.

    Raises:
        VersionDriftError: If any version it recorded differs from this
            process's own.
    """
    current = current_versions(
        card_version=CARD_VERSION, prompt_version=PROMPT_VERSION
    )
    if sample.versions != current:
        raise VersionDriftError(
            f"{sample.sample_id}: verified under {sample.versions}, "
            f"but this process runs {current}"
        )


def run_sample(
    sample: Sample,
    *,
    engine: InferenceEngine,
    condition: Condition,
    executor: Callable[[ExecutionRequest], ExecutionReport] = execute,
    validation_deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    policy_validator: Callable[[ActionPlan], PlanDecision] = evaluate_plan,
    timer: Callable[[], float] = time.monotonic,
) -> SampleRecord | InfraFailure:
    """Evaluate one stored sample under one condition.

    Args:
        sample: The stored sample.
        engine: The model under evaluation.
        condition: The generation bounds and grammar setting.
        executor: The sidecar executor.
        validation_deadline_seconds: The sidecar's own deadline.
        policy_validator: The policy re-check; see
            `compile_request_graph`.
        timer: A monotonic clock, for the engine-call timings.

    Returns:
        The sample's record, or the infrastructure failure that kept it
        from being scored.

    Raises:
        VersionDriftError: If the sample's recorded versions are stale.
        pmc_eval.prompt.BrokenLineageError: If its structure no longer
            rebuilds to what it was verified on.
        HarnessDefectError: If the graph ends in a state the harness
            never requests.
    """
    check_versions(sample)
    snapshot = snapshot_for(sample)
    recording_engine = RecordingEngine(
        engine,
        grammar=grammar_text() if condition.grammar else None,
        timer=timer,
    )
    recording_executor = RecordingExecutor(executor)
    state = request_state_for(sample, snapshot)
    compiled = compile_request_graph(
        engine=recording_engine,
        executor=recording_executor,
        condition=condition,
        validation_deadline_seconds=validation_deadline_seconds,
        policy_validator=policy_validator,
    )
    result = compiled.invoke(
        state, {"configurable": {"thread_id": state["session_id"]}}
    )
    errors = cast(tuple[AttemptFailure, ...], result["errors"])
    calls = recording_engine.calls
    ending = _terminal(result, errors)

    if ending.infra is not None and not ending.executed:
        last = calls[-1].outcome
        message = last.message if isinstance(last, EngineFailure) else ""
        return InfraFailure(
            sample_id=sample.sample_id,
            condition=condition.name,
            category=ending.infra,
            message=message,
        )

    # Every attempt whose plan reached the sidecar ran it exactly once,
    # in attempt order: each execution failure the graph recorded, and
    # the last attempt when it ended in the sidecar without one.
    last_index = len(calls) - 1
    executed_attempts = [
        index
        for index, error in enumerate(errors)
        if error.source == "execution"
    ]
    if ending.executed and ending.outcome is None:
        executed_attempts.append(last_index)
    reports = [report for _, report in recording_executor.calls]
    if len(executed_attempts) != len(reports):
        raise HarnessDefectError(
            f"{len(reports)} sidecar runs for attempts {executed_attempts}"
        )
    report_of = dict(zip(executed_attempts, reports, strict=True))

    final_outcome = ending.outcome
    final_category = ending.category
    final_command = ending.command_index
    assertions: tuple[AssertionResult, ...] = ()
    empty: str | None = None
    if ending.infra is not None:
        final_plan = _parsed(_normalized(calls[last_index]))
        reason = ending.infra[len(FAILURE_EXECUTION_PREFIX) :]
        if not _control_attributes_to_model(
            plan=final_plan,
            sample=sample,
            snapshot_json=state["snapshot_json"],
            digest=state["snapshot_identity"].digest,
            reason=reason,
            executor=executor,
            validation_deadline_seconds=validation_deadline_seconds,
        ):
            return InfraFailure(
                sample_id=sample.sample_id,
                condition=condition.name,
                category=ending.infra,
                message=f"sidecar execution failed: {reason}",
            )
        final_outcome = OUTCOME_EXECUTION_FAILED
        final_category = ending.infra
    elif final_outcome is None:
        final_report = report_of[last_index]
        final_plan = cast(ActionPlan, result["plan"])
        graded = grade(sample, final_report, final_plan, snapshot)
        assertions = graded.assertions
        empty = graded.empty_selection
        final_outcome = (
            OUTCOME_SUCCESS if graded.task_success else OUTCOME_EXECUTED_WRONG
        )

    attempts: list[AttemptRecord] = []
    timings: list[AttemptTiming] = []
    for index, call in enumerate(calls):
        # Each repairable failure is one entry in `errors`, in attempt
        # order; an attempt past the last of them is the one the
        # terminal status describes.
        if index < len(errors):
            error = errors[index]
            outcome = _SOURCE_OUTCOMES[error.source]
            category: str | None = error.category
            command_index = error.command_index
        else:
            outcome = cast(str, final_outcome)
            category = final_category
            command_index = final_command
        completion = cast(CompletionResult, call.outcome)
        normalized = _normalized(call)
        plan = _parsed(normalized)
        report = report_of.get(index)
        attempts.append(
            AttemptRecord(
                attempt=index + 1,
                prompt_sha256=hashlib.sha256(
                    call.request.prompt.encode("utf-8")
                ).hexdigest(),
                grammar_sent=call.request.grammar is not None,
                completion=completion.text,
                stop_reason=completion.stop_reason,
                newline_appended=call.newline_appended,
                outcome=outcome,
                category=category,
                command_index=command_index,
                hostile_reasons=(
                    hostile_reasons(normalized)
                    if outcome == OUTCOME_DENIED_HOSTILE
                    else ()
                ),
                syntax_valid=plan is not None,
                plan_pml=plan.render_pml() if plan is not None else None,
                execution=_summary(report) if report is not None else None,
            )
        )
        timings.append(
            AttemptTiming(
                engine_seconds=call.elapsed_seconds,
                executor_seconds=(
                    report.elapsed_seconds if report is not None else None
                ),
            )
        )

    return SampleRecord(
        sample_id=sample.sample_id,
        category=sample.category,
        difficulty=sample.difficulty,
        spec_id=sample.structure.spec_id,
        condition=condition.name,
        attempts=tuple(attempts),
        final_outcome=cast(str, final_outcome),
        assertions=assertions,
        task_success=final_outcome == OUTCOME_SUCCESS,
        empty_selection=empty,
        grading_complete=grading_complete(sample),
        vacuous=is_vacuous(sample),
        timings=tuple(timings),
    )


def _normalized(call: CompletionCall) -> str:
    """Return a completion as the graph saw it, after normalization.

    Args:
        call: The recorded engine call.

    Returns:
        The completion text, with the final newline the harness added.
    """
    outcome = cast(CompletionResult, call.outcome)
    return outcome.text + ("\n" if call.newline_appended else "")
