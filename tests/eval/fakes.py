# Copyright 2026 PyMOL Copilot contributors.
"""Scripted executors and completions for the hermetic harness tests.

A scripted executor replays a fixed sequence of reports, one per call,
and records every request it was given, so a test controls exactly what
the request graph sees from the sidecar -- the same discipline
`pmc_agent.inference.fake.FakeEngine` applies to the model.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Sequence

from pmc_agent.inference.base import ENGINE_UNAVAILABLE
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import EngineHealth
from pmc_core.errors import CATEGORY_UNKNOWN_COLOR
from pmc_core.errors import ERROR_ENVELOPE_VERSION
from pmc_core.errors import ExecutionErrorV1
from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import SelectionCount
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.protocol import HEALTH_ENGINE_READY
from pmc_data.sample import Sample


def completion(text: str, stop_reason: str = STOP_END) -> CompletionResult:
    """Build one scripted model completion.

    Args:
        text: The completion text.
        stop_reason: Why generation stopped.

    Returns:
        The completion.
    """
    return CompletionResult(
        text=text, model_identity="fake-engine-v1", stop_reason=stop_reason
    )


def ok_report(
    *,
    fingerprint: str | None,
    counts: Sequence[tuple[str, int]] = (),
    commands: int = 1,
) -> ExecutionReport:
    """Build a successful sidecar report.

    Args:
        fingerprint: The resulting-state fingerprint.
        counts: Each named selection and its atom count.
        commands: How many commands ran, all successfully.

    Returns:
        The report.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:test",
        resulting_fingerprint=fingerprint,
        selection_counts=tuple(
            SelectionCount(name=name, atom_count=count)
            for name, count in counts
        ),
        command_outcomes=tuple(
            CommandOutcome(index=i, verb="color", status=OUTCOME_OK, error=None)
            for i in range(commands)
        ),
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=1.25,
    )


def command_failure_report(
    *, index: int = 0, category: str = CATEGORY_UNKNOWN_COLOR
) -> ExecutionReport:
    """Build a sidecar report of one PyMOL command failing.

    Args:
        index: The failing command's index.
        category: Its normalized error category.

    Returns:
        The report, carrying the command's error envelope.
    """
    envelope = ExecutionErrorV1(
        envelope_version=ERROR_ENVELOPE_VERSION,
        command_index=index,
        verb="color",
        category=category,
        message="unknown color",
    )
    return ExecutionReport(
        executor_version=1,
        status=STATUS_FAILED,
        reason=REASON_COMMAND_FAILURE,
        input_digest="sha256:test",
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(
            CommandOutcome(
                index=index,
                verb="color",
                status=OUTCOME_ERROR,
                error="unknown color",
                error_envelope=envelope,
            ),
        ),
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=1.25,
    )


def failed_report(reason: str) -> ExecutionReport:
    """Build a sidecar report failing for a reason other than a command.

    Args:
        reason: The executor reason, such as a timeout or a crash.

    Returns:
        The report.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_FAILED,
        reason=reason,
        input_digest="sha256:test",
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(),
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=30.0,
    )


class ScriptedExecutor:
    """An executor that replays a fixed sequence of reports."""

    def __init__(self, reports: Sequence[ExecutionReport]) -> None:
        """Create an executor that returns `reports` in order.

        Args:
            reports: One report per expected call.
        """
        self._reports = list(reports)
        self._calls: list[ExecutionRequest] = []

    @property
    def calls(self) -> tuple[ExecutionRequest, ...]:
        """Return every request received so far.

        Returns:
            The requests, in call order.
        """
        return tuple(self._calls)

    def __call__(self, request: ExecutionRequest) -> ExecutionReport:
        """Record `request` and return the next scripted report.

        Args:
            request: The execution request.

        Returns:
            The next report.

        Raises:
            AssertionError: If called more often than scripted.
        """
        if len(self._calls) >= len(self._reports):
            raise AssertionError(
                f"executor called {len(self._calls) + 1} times; only "
                f"{len(self._reports)} reports were scripted"
            )
        report = self._reports[len(self._calls)]
        self._calls.append(request)
        return report


class ReferenceEngine:
    """A model that answers every sample's prompt with its reference plan.

    It stands in for a perfect model in the CLI tests, which are about
    what the CLI writes and refuses rather than about any model. A
    one-token request is the CLI's context preflight, answered with an
    empty, length-stopped completion.
    """

    def __init__(
        self,
        samples: Sequence[Sample],
        *,
        model_identity: str,
        unavailable_for: frozenset[str] = frozenset(),
        preflight_failure: EngineFailure | None = None,
    ) -> None:
        """Create a reference model for `samples`.

        Args:
            samples: The samples it will be prompted with.
            model_identity: The identity it reports.
            unavailable_for: Sample ids whose prompt it fails as an
                unavailable engine would.
            preflight_failure: The failure to return for the context
                preflight, or None to pass it.
        """
        self._answers = {s.prompt_text: s.plan_pml for s in samples}
        self._unavailable = {
            s.prompt_text for s in samples if s.sample_id in unavailable_for
        }
        self._model_identity = model_identity
        self._preflight_failure = preflight_failure
        self._calls: list[CompletionRequest] = []

    @property
    def model_identity(self) -> str:
        """Return the configured identity.

        Returns:
            The identity this engine reports.
        """
        return self._model_identity

    def health(self) -> EngineHealth:
        """Report a ready engine.

        Returns:
            A ready health carrying this engine's identity.
        """
        return EngineHealth(
            state=HEALTH_ENGINE_READY,
            engine="reference",
            engine_version="test",
            device="cpu",
            model_identity=self._model_identity,
            failure=None,
        )

    @property
    def calls(self) -> tuple[CompletionRequest, ...]:
        """Return every request received so far.

        Returns:
            The requests, in call order.
        """
        return tuple(self._calls)

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Answer one request.

        Args:
            request: The completion request.
            cancel: Ignored.

        Returns:
            The reference plan, the preflight's answer, or a failure.
        """
        del cancel
        self._calls.append(request)
        if request.max_tokens == 1:
            if self._preflight_failure is not None:
                return self._preflight_failure
            return CompletionResult(
                text="",
                model_identity=self._model_identity,
                stop_reason="length",
            )
        if request.prompt in self._unavailable:
            return EngineFailure(ENGINE_UNAVAILABLE, "connection refused")
        return CompletionResult(
            text=self._answers[request.prompt],
            model_identity=self._model_identity,
            stop_reason=STOP_END,
        )


class ReferenceExecutor:
    """A sidecar that reproduces each sample's own verification.

    Keyed by plan and structure, so it answers a sample's reference plan
    on that sample's structure with the report the sample was verified
    with, and refuses anything else.
    """

    def __init__(self, samples: Sequence[Sample]) -> None:
        """Create a reference sidecar for `samples`.

        Args:
            samples: The samples whose verifications to reproduce.
        """
        self._reports: dict[tuple[str, str], ExecutionReport] = {}
        for sample in samples:
            plan = parse_pml(sample.plan_pml)
            assert isinstance(plan, ActionPlan)
            self._reports[
                (sample.plan_pml, sample.structure.structure_digest)
            ] = ok_report(
                fingerprint=sample.verification.resulting_fingerprint,
                counts=sample.verification.selection_counts,
                commands=len(plan.operations),
            )

    def __call__(self, request: ExecutionRequest) -> ExecutionReport:
        """Reproduce one sample's verification.

        Args:
            request: The execution request.

        Returns:
            The sample's verified report.
        """
        key = (
            request.plan.render_pml(),
            request.expected_snapshot_digest or "",
        )
        return self._reports[key]
