# Copyright 2026 PyMOL Copilot contributors.
"""Opt-in evidence against a real, local Lemonade server.

This suite only exercises positive grammar enforcement against the live
server. Lemonade currently enforces the grammar parameter, so the negative
evidence for a silently ignored grammar is deliberately hermetic in
``tests/unit/test_inference_lemonade_probe.py``.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import threading
import time

import httpx
import pytest

from lemonade_support import lemonade_base_url as _lemonade_base_url  # noqa: F401
from pmc_agent.inference.base import ENGINE_TIMEOUT
from pmc_agent.inference.base import STOP_CANCELLED
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import STOP_LENGTH
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.lemonade import DEFAULT_MODEL_NAME
from pmc_agent.inference.lemonade import LemonadeEngine
from pmc_agent.inference.lemonade import connect_lemonade

_GRAMMAR_SENTINEL = "pmc-real-grammar-sentinel"
_GRAMMAR = f'root ::= "{_GRAMMAR_SENTINEL}"'
_GRAMMAR_PROMPT = "What is the capital of France? Answer with one word."
_DEADLINE_GRACE_SECONDS = 1.0
_IDLE_WAIT_SECONDS = 10.0


@pytest.fixture(scope="session")
def lemonade_engine(lemonade_base_url: str) -> LemonadeEngine:
    """Connect once to the explicitly configured local Lemonade server.

    Args:
        lemonade_base_url: The production-validated loopback origin.

    Returns:
        A startup-probed Lemonade engine.
    """
    connected = connect_lemonade(base_url=lemonade_base_url)
    if isinstance(connected, EngineFailure):
        pytest.fail(
            "Lemonade startup probe failed: "
            f"{connected.category}: {connected.message}"
        )
    return connected


def _request(
    *,
    prompt: str,
    grammar: str | None = None,
    max_tokens: int = 64,
    deadline_seconds: float = 15.0,
) -> CompletionRequest:
    """Build one bounded real-server completion request.

    Args:
        prompt: The exact user prompt to send to Lemonade.
        grammar: An optional grammar to enforce at generation time.
        max_tokens: The generation limit for this evidence call.
        deadline_seconds: The total completion deadline.

    Returns:
        The engine request to execute.
    """
    return CompletionRequest(
        prompt=prompt,
        grammar=grammar,
        max_tokens=max_tokens,
        deadline_seconds=deadline_seconds,
    )


def _wait_until_model_is_idle(base_url: str) -> None:
    """Require the just-cancelled local model to leave Lemonade's busy state.

    Args:
        base_url: The production-validated loopback Lemonade origin.

    Raises:
        pytest.fail: Lemonade remains busy beyond the measured grace window.
    """
    deadline = time.monotonic() + _IDLE_WAIT_SECONDS
    with httpx.Client(base_url=base_url, timeout=1.0) as client:
        while time.monotonic() < deadline:
            response = client.get("/api/v1/health")
            if response.status_code == 200:
                body = response.json()
                if isinstance(body, dict):
                    models = body.get("all_models_loaded")
                    if isinstance(models, list) and any(
                        isinstance(model, dict)
                        and model.get("model_name") == DEFAULT_MODEL_NAME
                        and model.get("is_busy") is False
                        for model in models
                    ):
                        return
            time.sleep(0.1)
    pytest.fail("Lemonade remained busy after the cancelled streaming request")


def test_startup_probe_returns_the_pinned_local_engine(
    lemonade_engine: LemonadeEngine,
) -> None:
    """The real server satisfies the same startup contract as its mock."""
    assert lemonade_engine.capabilities.grammar_enforced
    assert lemonade_engine.model_identity.endswith(
        f"@{lemonade_engine.capabilities.checkpoint}"
    )


def test_a_real_grammar_forces_its_sentinel_and_is_not_implicit(
    lemonade_engine: LemonadeEngine,
) -> None:
    """The live grammar route differs observably from the ordinary prompt."""
    constrained = lemonade_engine.complete(
        _request(prompt=_GRAMMAR_PROMPT, grammar=_GRAMMAR), cancel=CancelToken()
    )
    unconstrained = lemonade_engine.complete(
        _request(prompt=_GRAMMAR_PROMPT), cancel=CancelToken()
    )

    assert constrained == CompletionResult(
        text=_GRAMMAR_SENTINEL,
        model_identity=lemonade_engine.model_identity,
        stop_reason=STOP_END,
    )
    assert isinstance(unconstrained, CompletionResult)
    assert unconstrained.text != _GRAMMAR_SENTINEL


def test_the_real_server_reports_token_limit_exhaustion(
    lemonade_engine: LemonadeEngine,
) -> None:
    """A one-token budget must surface the standard length stop reason."""
    result = lemonade_engine.complete(
        _request(
            prompt="Explain the history of structural biology in detail.",
            max_tokens=1,
        ),
        cancel=CancelToken(),
    )

    assert isinstance(result, CompletionResult)
    assert result.stop_reason == STOP_LENGTH


def test_a_short_real_deadline_returns_timeout_within_its_grace_window(
    lemonade_engine: LemonadeEngine,
) -> None:
    """A deadline failure is bounded even if the server has already loaded."""
    started_at = time.monotonic()
    result = lemonade_engine.complete(
        _request(
            prompt="Write a detailed 2,000-token essay about protein folding.",
            max_tokens=2_000,
            deadline_seconds=1e-9,
        ),
        cancel=CancelToken(),
    )
    elapsed_seconds = time.monotonic() - started_at

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_TIMEOUT
    assert elapsed_seconds <= _DEADLINE_GRACE_SECONDS


def test_cancelling_a_real_stream_leaves_lemonade_idle(
    lemonade_engine: LemonadeEngine, lemonade_base_url: str
) -> None:
    """Closing a live stream on cancellation makes Lemonade stop computing.

    Args:
        lemonade_engine: The startup-probed local engine under test.
        lemonade_base_url: The same production-validated loopback origin.
    """
    cancel = CancelToken()
    timer = threading.Timer(0.1, cancel.cancel)
    timer.start()
    try:
        result = lemonade_engine.complete(
            _request(
                prompt="Write a detailed 2,000-token essay about protein folding.",
                max_tokens=2_000,
                deadline_seconds=15.0,
            ),
            cancel=cancel,
        )
    finally:
        timer.cancel()
        timer.join()

    assert isinstance(result, CompletionResult)
    assert result.stop_reason == STOP_CANCELLED
    _wait_until_model_is_idle(lemonade_base_url)
