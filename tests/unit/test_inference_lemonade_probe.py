# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic startup capability tests for the Lemonade adapter."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Callable

import httpx
import pytest

from pmc_agent.inference.base import ENGINE_REFUSED_GRAMMAR
from pmc_agent.inference.base import ENGINE_UNAVAILABLE
from pmc_agent.inference.base import ENGINE_UNKNOWN
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.lemonade import EngineCapabilities
from pmc_agent.inference.lemonade import LemonadeEngine
from pmc_agent.inference.lemonade import connect_lemonade

_MODEL = "test-model"
_CHECKPOINT = "test/checkpoint.gguf"
_RECIPE = "llamacpp"
_HANDLER = Callable[[httpx.Request], httpx.Response]


def _event(content: str, *, finish_reason: str | None = None) -> bytes:
    """Build one valid Lemonade completion SSE event.

    Args:
        content: The delta text to emit.
        finish_reason: The optional terminal reason.

    Returns:
        One JSON ``data:`` SSE event.
    """
    choice = {"delta": {"content": content}, "finish_reason": finish_reason}
    return f"data: {json.dumps({'model': _MODEL, 'choices': [choice]})}\n\n".encode()


def _canary_response(text: str = "pmc-grammar-probe-ok") -> httpx.Response:
    """Build a successful grammar-canary response.

    Args:
        text: The text the canary should produce.

    Returns:
        A stopped SSE response with the requested text.
    """
    return httpx.Response(
        200,
        content=_event(text) + _event("", finish_reason="stop") + b"data: [DONE]\n\n",
    )


def _health(*, device: str = "cpu") -> dict[str, object]:
    """Build a loaded health response.

    Args:
        device: The reported device value.

    Returns:
        A health object with the selected model loaded.
    """
    return {
        "status": "ok",
        "version": "11.9.0",
        "all_models_loaded": [
            {
                "model_name": _MODEL,
                "checkpoint": _CHECKPOINT,
                "device": device,
                "recipe": _RECIPE,
                "recipe_options": {"ctx_size": 4096},
            }
        ],
    }


def _catalog(*, checkpoint: str = _CHECKPOINT) -> dict[str, object]:
    """Build a catalog entry for the selected model.

    Args:
        checkpoint: The catalog checkpoint to report.

    Returns:
        The catalog model object.
    """
    return {
        "checkpoint": checkpoint,
        "recipe": _RECIPE,
        "context_length": 4096,
    }


def _client(handler: _HANDLER) -> httpx.Client:
    """Build a no-network test client.

    Args:
        handler: The scripted response handler.

    Returns:
        A MockTransport-backed local client.
    """
    return httpx.Client(
        base_url="http://lemonade.test", transport=httpx.MockTransport(handler)
    )


def _happy_handler(*, device: str = "cpu", canary: httpx.Response | None = None) -> _HANDLER:
    """Build the ordered response script for a successful probe.

    Args:
        device: The device reported after loading.
        canary: An optional canary response override.

    Returns:
        A handler for health, catalog, load, health, then completion.
    """
    responses = iter(
        (
            httpx.Response(200, json={"status": "ok", "version": "11.9.0"}),
            httpx.Response(200, json=_catalog()),
            httpx.Response(200, json={"status": "success"}),
            httpx.Response(200, json=_health(device=device)),
            canary or _canary_response(),
        )
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        """Return the next probe response after checking its endpoint.

        Args:
            request: The outbound probe request.

        Returns:
            The next scripted response.
        """
        return next(responses)

    return handler


def _connect(handler: _HANDLER, *, backend: str = "cpu") -> LemonadeEngine | EngineFailure:
    """Connect through a hermetic scripted transport.

    Args:
        handler: The capability probe's scripted responses.
        backend: The backend requested at load time.

    Returns:
        The connected engine or its first typed failure.
    """
    return connect_lemonade(
        base_url="http://lemonade.test",
        model_name=_MODEL,
        checkpoint=_CHECKPOINT,
        backend=backend,
        client=_client(handler),
    )


def test_the_full_probe_returns_an_engine_with_immutable_capabilities() -> None:
    """Health, identity, loaded state, and grammar canary all must succeed."""
    engine = _connect(_happy_handler())

    assert isinstance(engine, LemonadeEngine)
    assert engine.capabilities == EngineCapabilities(
        lemonade_version="11.9.0",
        model_name=_MODEL,
        checkpoint=_CHECKPOINT,
        device="cpu",
        recipe=_RECIPE,
        context_length=4096,
        grammar_enforced=True,
    )
    assert engine.model_identity == f"{_MODEL}@{_CHECKPOINT}"


def test_an_unreachable_health_check_stops_before_load_or_completion() -> None:
    """No later probe may touch an absent or wrong server."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record and reject the first health request.

        Args:
            request: The health request that cannot connect.

        Returns:
            Never returns.

        Raises:
            httpx.ConnectError: Always, for an unavailable server.
        """
        requests.append(request)
        raise httpx.ConnectError("not listening", request=request)

    result = _connect(handler)

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNAVAILABLE
    assert [request.url.path for request in requests] == ["/api/v1/health"]


def test_a_missing_model_fails_before_load() -> None:
    """The cheap exact-model lookup is the first identity assertion."""
    requests: list[httpx.Request] = []
    responses = iter(
        (
            httpx.Response(200, json={"status": "ok", "version": "11.9.0"}),
            httpx.Response(404, json={"error": {"code": "model_not_found"}}),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        """Record each request and return the next script item.

        Args:
            request: The outgoing probe request.

        Returns:
            The next scripted response.
        """
        requests.append(request)
        return next(responses)

    result = _connect(handler)

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNKNOWN
    assert [request.url.path for request in requests] == [
        "/api/v1/health",
        f"/api/v1/models/{_MODEL}",
    ]


def test_a_one_character_checkpoint_difference_is_an_identity_failure() -> None:
    """Checkpoint equality is byte-for-byte, never a friendly-name match."""
    responses = iter(
        (
            httpx.Response(200, json={"status": "ok", "version": "11.9.0"}),
            httpx.Response(200, json=_catalog(checkpoint=_CHECKPOINT + "x")),
        )
    )

    result = _connect(lambda _request: next(responses))

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNKNOWN


def test_a_backend_fallback_visible_in_health_is_an_identity_failure() -> None:
    """A load response alone cannot prove Lemonade used the requested device."""
    result = _connect(_happy_handler(device="cpu"), backend="vulkan")

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNKNOWN


@pytest.mark.parametrize(
    "canary",
    [
        httpx.Response(400, json={"error": {"param": "grammar"}}),
        _canary_response("an unconstrained answer"),
        _canary_response("pmc-grammar-probe-ok!"),
    ],
    ids=["explicit-rejection", "silently-ignored", "near-miss"],
)
def test_every_failed_grammar_canary_refuses_to_return_an_engine(
    canary: httpx.Response,
) -> None:
    """Grammar must be proven rather than assumed from a 200 response.

    Args:
        canary: The explicit, ignored, or near-miss canary response.
    """
    result = _connect(_happy_handler(canary=canary))

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_REFUSED_GRAMMAR
