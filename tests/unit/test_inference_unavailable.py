# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for `UnavailableEngine`."""

from __future__ import annotations

import pytest

from pmc_agent.inference.base import ENGINE_UNAVAILABLE
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.unavailable import UNAVAILABLE_MODEL_IDENTITY
from pmc_agent.inference.unavailable import UnavailableEngine
from pmc_core.protocol import HEALTH_ENGINE_UNAVAILABLE


def _request() -> CompletionRequest:
    """Build a minimal completion request for a test.

    Returns:
        A `CompletionRequest` suitable for driving an `UnavailableEngine`.
    """
    return CompletionRequest(
        prompt="select chain A",
        grammar=None,
        max_tokens=16,
        deadline_seconds=1.0,
    )


def test_complete_always_returns_the_recorded_failure_unchanged() -> None:
    """Every complete() call returns the same startup failure, verbatim."""
    failure = EngineFailure(ENGINE_UNAVAILABLE, "lemonade could not be reached")
    engine = UnavailableEngine(failure)

    first = engine.complete(_request(), cancel=CancelToken())
    second = engine.complete(_request(), cancel=CancelToken())

    assert first is failure
    assert second is failure


def test_health_reports_the_recorded_failure() -> None:
    """health() reports the same recorded failure, never a live check."""
    failure = EngineFailure(ENGINE_UNAVAILABLE, "lemonade could not be reached")
    engine = UnavailableEngine(failure, engine="lemonade")

    health = engine.health()

    assert health.state == HEALTH_ENGINE_UNAVAILABLE
    assert health.engine == "lemonade"
    assert health.failure is failure
    assert health.engine_version is None
    assert health.device is None
    assert health.model_identity is None


def test_model_identity_is_a_fixed_placeholder() -> None:
    """No model was ever loaded, so identity is a fixed placeholder."""
    engine = UnavailableEngine(EngineFailure(ENGINE_UNAVAILABLE, "unreachable"))

    assert engine.model_identity == UNAVAILABLE_MODEL_IDENTITY


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
