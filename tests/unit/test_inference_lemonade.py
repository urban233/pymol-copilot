# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic behavior tests for the streaming Lemonade adapter."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Callable
from collections.abc import Iterator

import httpx
import pytest

from pmc_agent.inference import lemonade
from pmc_agent.inference.base import ENGINE_REFUSED_GRAMMAR
from pmc_agent.inference.base import ENGINE_TIMEOUT
from pmc_agent.inference.base import ENGINE_UNAVAILABLE
from pmc_agent.inference.base import ENGINE_UNKNOWN
from pmc_agent.inference.base import STOP_CANCELLED
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import STOP_LENGTH
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.lemonade import LemonadeEngine

_MODEL = "test-model"
_CHECKPOINT = "test/checkpoint.gguf"
_HANDLER = Callable[[httpx.Request], httpx.Response]


class _ChunkStream(httpx.SyncByteStream):
    """A deterministic byte stream that may run a callback between chunks."""

    def __init__(
        self,
        chunks: tuple[bytes, ...],
        *,
        before_chunk: Callable[[int], None] | None = None,
    ) -> None:
        """Store the chunks and optional callback.

        Args:
            chunks: The byte chunks yielded to httpx in order.
            before_chunk: Called immediately before each chunk is yielded.
        """
        self._chunks = chunks
        self._before_chunk = before_chunk

    def __iter__(self) -> Iterator[bytes]:
        """Yield configured chunks in order.

        Yields:
            One configured byte chunk at a time.
        """
        for index, chunk in enumerate(self._chunks):
            if self._before_chunk is not None:
                self._before_chunk(index)
            yield chunk


def _event(
    *,
    content: str | None = None,
    finish_reason: str | None = None,
    model: str = _MODEL,
) -> bytes:
    """Build one OpenAI-compatible SSE event.

    Args:
        content: Optional delta content for the event.
        finish_reason: Optional terminal completion reason.
        model: The response model identity to include.

    Returns:
        UTF-8 bytes carrying one ``data:`` event and its blank separator.
    """
    delta: dict[str, object] = {}
    if content is not None:
        delta["content"] = content
    choice: dict[str, object] = {"delta": delta, "finish_reason": finish_reason}
    return (
        f"data: {json.dumps({'model': model, 'choices': [choice]})}\n\n".encode()
    )


def _done() -> bytes:
    """Build the terminal streaming sentinel.

    Returns:
        Lemonade's OpenAI-compatible ``[DONE]`` event.
    """
    return b"data: [DONE]\n\n"


def _request(*, grammar: str | None = None) -> CompletionRequest:
    """Build a small completion request.

    Args:
        grammar: The optional grammar to include.

    Returns:
        A request suitable for adapter tests.
    """
    return CompletionRequest(
        prompt="Reply with a plan.",
        grammar=grammar,
        max_tokens=32,
        deadline_seconds=5.0,
    )


def _engine(handler: _HANDLER) -> LemonadeEngine:
    """Build an engine using only ``MockTransport``.

    Args:
        handler: The scripted transport response handler.

    Returns:
        A Lemonade engine with no network route.
    """
    client = httpx.Client(
        base_url="http://lemonade.test", transport=httpx.MockTransport(handler)
    )
    return LemonadeEngine(
        base_url="http://lemonade.test",
        model_name=_MODEL,
        checkpoint=_CHECKPOINT,
        client=client,
    )


def _successful_response(text: str = "hello", reason: str = "stop") -> httpx.Response:
    """Build a successful SSE response.

    Args:
        text: The completion text to stream.
        reason: Lemonade's terminal reason.

    Returns:
        A complete streamed HTTP response.
    """
    return httpx.Response(200, content=_event(content=text) + _event(finish_reason=reason) + _done())


@pytest.mark.parametrize(
    ("reason", "expected_stop"),
    [("stop", STOP_END), ("length", STOP_LENGTH)],
)
def test_a_streamed_completion_accumulates_text_and_maps_its_stop_reason(
    reason: str, expected_stop: str
) -> None:
    """A normal Lemonade stream yields a typed completion.

    Args:
        reason: The server's terminal SSE reason.
        expected_stop: The interface stop reason expected for it.
    """
    engine = _engine(lambda _request: _successful_response("hello world", reason))

    result = engine.complete(_request(), cancel=CancelToken())

    assert result == CompletionResult(
        text="hello world",
        model_identity=f"{_MODEL}@{_CHECKPOINT}",
        stop_reason=expected_stop,
    )


def test_every_request_is_streaming_deterministic_and_only_sends_grammar_when_set() -> None:
    """No adapter path can accidentally issue an uncancellable request."""
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record each request and return a valid stream.

        Args:
            request: The outbound request from the adapter.

        Returns:
            A successful stream.
        """
        body = json.loads(request.content)
        assert isinstance(body, dict)
        bodies.append(body)
        return _successful_response()

    engine = _engine(handler)

    engine.complete(_request(grammar='root ::= "ok"'), cancel=CancelToken())
    engine.complete(_request(), cancel=CancelToken())

    assert [body["stream"] for body in bodies] == [True, True]
    assert [body["temperature"] for body in bodies] == [0, 0]
    assert bodies[0]["grammar"] == 'root ::= "ok"'
    assert "grammar" not in bodies[1]


def test_connect_errors_are_typed_as_unavailable() -> None:
    """A transport failure never escapes the total adapter boundary."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Raise the scripted connection failure.

        Args:
            request: The outbound request that failed to connect.

        Returns:
            Never returns.

        Raises:
            httpx.ConnectError: Always, to emulate an absent Lemonade server.
        """
        raise httpx.ConnectError("server refused connection", request=request)

    result = _engine(handler).complete(_request(), cancel=CancelToken())

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNAVAILABLE


def test_deadline_discards_partial_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deadline failure cannot feed a truncated plan to the graph.

    Args:
        monkeypatch: Pytest's controlled patching fixture.
    """
    moments = iter((0.0, 0.1, 5.1))
    monkeypatch.setattr(lemonade.time, "monotonic", lambda: next(moments))
    stream = _ChunkStream(
        (_event(content="partial"), _event(finish_reason="stop") + _done())
    )
    engine = _engine(lambda _request: httpx.Response(200, stream=stream))

    result = engine.complete(_request(), cancel=CancelToken())

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_TIMEOUT
    assert not hasattr(result, "text")


def test_cancellation_closes_the_stream_and_returns_received_text() -> None:
    """A cancellation turns the partial streamed result into a terminal result."""
    cancel = CancelToken()
    stream = _ChunkStream(
        (_event(content="before cancel"), _event(finish_reason="stop") + _done()),
        before_chunk=lambda index: cancel.cancel() if index == 1 else None,
    )
    engine = _engine(lambda _request: httpx.Response(200, stream=stream))

    result = engine.complete(_request(), cancel=cancel)

    assert result == CompletionResult(
        text="before cancel",
        model_identity=f"{_MODEL}@{_CHECKPOINT}",
        stop_reason=STOP_CANCELLED,
    )


def test_a_grammar_rejection_is_not_misreported_as_an_outage() -> None:
    """Lemonade's explicit grammar rejection gets its distinct category."""
    engine = _engine(
        lambda _request: httpx.Response(
            400, json={"error": {"param": "grammar", "message": "bad grammar"}}
        )
    )

    result = engine.complete(_request(grammar='root ::= "ok"'), cancel=CancelToken())

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_REFUSED_GRAMMAR


def test_a_completion_from_another_model_is_unknown() -> None:
    """A server-side model swap never silently changes request provenance."""
    response = httpx.Response(
        200, content=_event(content="wrong", model="other-model") + _done()
    )

    result = _engine(lambda _request: response).complete(
        _request(), cancel=CancelToken()
    )

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNKNOWN


def test_hostile_server_errors_are_normalized_before_reaching_history() -> None:
    """An error body is bounded, printable, and cannot preserve control bytes."""
    hostile = ("x" * 900) + "\x00\x01\n\x1b"
    engine = _engine(lambda _request: httpx.Response(500, content=hostile))

    result = engine.complete(_request(), cancel=CancelToken())

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNAVAILABLE
    assert len(result.message.encode("ascii")) <= 256
    assert all(0x20 <= ord(char) < 0x7F for char in result.message)
