# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for the fake inference engine."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import pytest

from pmc_agent.inference import CompletionRequest as PublicCompletionRequest
from pmc_agent.inference import FakeEngine as PublicFakeEngine
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import ENGINE_TIMEOUT
from pmc_agent.inference.fake import FakeEngine
from pmc_core.errors import normalize_message


def _request(prompt: str = "select chain A") -> CompletionRequest:
    """Build a minimal completion request for a test.

    Args:
        prompt: The prompt text to carry.

    Returns:
        A `CompletionRequest` suitable for driving a `FakeEngine`.
    """
    return CompletionRequest(
        prompt=prompt, grammar=None, max_tokens=64, deadline_seconds=5.0
    )


def test_the_fake_replays_its_script_in_order() -> None:
    """Each call returns the next scripted outcome, not a random one."""
    first = CompletionResult("select copilot_a, chain A", "m-1", STOP_END)
    second = EngineFailure(ENGINE_TIMEOUT, "engine timed out")
    engine = FakeEngine([first, second])

    assert engine.complete(_request(), cancel=CancelToken()) is first
    assert engine.complete(_request(), cancel=CancelToken()) is second


def test_every_request_is_recorded_in_call_order() -> None:
    """`calls` holds exactly what each `complete()` call was given."""
    engine = FakeEngine(
        [CompletionResult("one", "m-1", STOP_END)] * 2, model_identity="m-1"
    )

    engine.complete(_request("first prompt"), cancel=CancelToken())
    engine.complete(_request("second prompt"), cancel=CancelToken())

    assert [call.prompt for call in engine.calls] == [
        "first prompt",
        "second prompt",
    ]


def test_a_call_past_the_end_of_the_script_fails_loudly() -> None:
    """Overrunning the script raises rather than returning a default."""
    engine = FakeEngine([CompletionResult("one", "m-1", STOP_END)])

    engine.complete(_request(), cancel=CancelToken())

    with pytest.raises(AssertionError, match="only 1 outcomes"):
        engine.complete(_request(), cancel=CancelToken())


def test_model_identity_is_the_engines_own_configured_value() -> None:
    """`model_identity` reports the fake's own property, not a result's."""
    engine = FakeEngine(
        [CompletionResult("one", "a-different-model", STOP_END)],
        model_identity="the-real-identity",
    )

    assert engine.model_identity == "the-real-identity"


def test_engine_failure_message_stays_bounded_and_printable() -> None:
    """A hostile raw message normalizes to something safe to display."""
    hostile = ("x" * 10_000) + "\x00\x01control-chars\x1b"

    failure = EngineFailure(ENGINE_TIMEOUT, normalize_message(hostile))

    encoded = failure.message.encode("utf-8")
    assert len(encoded) <= 256
    assert all(0x20 <= ord(char) < 0x7F for char in failure.message)


@pytest.mark.parametrize(
    ("max_tokens", "deadline_seconds"),
    [(0, 1.0), (-1, 1.0), (1, 0.0), (1, -0.1)],
)
def test_invalid_completion_bounds_are_rejected(
    max_tokens: int, deadline_seconds: float
) -> None:
    """A request cannot claim a non-positive resource bound.

    Args:
        max_tokens: The invalid token limit under test.
        deadline_seconds: The invalid deadline under test.
    """
    with pytest.raises(ValueError, match="must be positive"):
        CompletionRequest(
            prompt="select chain A",
            grammar=None,
            max_tokens=max_tokens,
            deadline_seconds=deadline_seconds,
        )


def test_unknown_result_and_failure_states_are_rejected() -> None:
    """The public interface cannot acquire undeclared status strings."""
    with pytest.raises(ValueError, match="unknown completion stop reason"):
        CompletionResult("text", "model", "unexpected")
    with pytest.raises(ValueError, match="unknown engine failure category"):
        EngineFailure("unexpected", "message")


def test_the_package_exports_the_supported_contract() -> None:
    """Callers need not import implementation internals to use the seam."""
    request = PublicCompletionRequest(
        prompt="select chain A", grammar=None, max_tokens=8, deadline_seconds=1.0
    )
    engine = PublicFakeEngine([CompletionResult("text", "model", STOP_END)])
    result = engine.complete(request, cancel=CancelToken())

    assert isinstance(result, CompletionResult)
    assert result.text == "text"
