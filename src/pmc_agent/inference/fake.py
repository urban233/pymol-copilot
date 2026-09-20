# Copyright 2026 PyMOL Copilot contributors.
"""A scripted `InferenceEngine` test double.

Every test of `pmc_agent.graph` runs against this module, never against a
real engine (docs/master_plan.md item 8: "Test every transition and
terminal state against a fake inference adapter."). item 9 adds the one
real implementation, `lemonade.py`, against this same `InferenceEngine`
interface.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Sequence

from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure


class FakeEngine:
    """An `InferenceEngine` that replays a fixed, ordered script.

    Each `complete()` call consumes the next scripted outcome and returns
    it unchanged -- this fake never inspects `request.prompt`, so a test
    controls exactly what the request graph sees from the model and
    nothing more. Every request this fake receives is recorded, in order,
    so a test can assert not only what the graph did with each result but
    how many calls it made and what each prompt contained.
    """

    def __init__(
        self,
        script: Sequence[CompletionResult | EngineFailure],
        *,
        model_identity: str = "fake-engine-v1",
    ) -> None:
        """Create a fake engine that replays `script` in order.

        Args:
            script: The outcomes this engine returns, one per call, in
                order. A test scripts exactly as many outcomes as the path
                under test is expected to call `complete()`.
            model_identity: The identity this engine reports. Independent
                of any `CompletionResult.model_identity` already present in
                `script` -- this property is what `InferenceEngine` itself
                promises, and a scripted result may deliberately disagree
                with it to test that the graph never trusts the result's
                own claim over the engine's.
        """
        self._script = list(script)
        self._model_identity = model_identity
        self._calls: list[CompletionRequest] = []

    @property
    def model_identity(self) -> str:
        """Return this fake's configured model identity.

        Returns:
            The `model_identity` this engine was constructed with.
        """
        return self._model_identity

    @property
    def calls(self) -> tuple[CompletionRequest, ...]:
        """Return every request this fake has received, in call order.

        Returns:
            Each `CompletionRequest` passed to `complete()` so far.
        """
        return tuple(self._calls)

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Record `request` and return the next scripted outcome.

        Args:
            request: The completion request to record.
            cancel: Accepted for interface conformance and otherwise
                ignored -- this fake never runs long enough to need it.

        Returns:
            The next `CompletionResult` or `EngineFailure` in this
            engine's script.

        Raises:
            AssertionError: If called more times than `script` has
                entries. A test overrunning its own script is a test
                asserting the wrong number of attempts, and that must fail
                loudly rather than fall back to a plausible-looking
                default that would mask the miscount.
        """
        del cancel
        if len(self._calls) >= len(self._script):
            raise AssertionError(
                f"FakeEngine.complete() called {len(self._calls) + 1} "
                f"times; only {len(self._script)} outcomes were scripted"
            )
        outcome = self._script[len(self._calls)]
        self._calls.append(request)
        return outcome
