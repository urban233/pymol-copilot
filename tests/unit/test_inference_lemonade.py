# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic behavior tests for the streaming Lemonade adapter."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import threading
import time
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
from pmc_agent.inference.base import EngineHealth
from pmc_agent.inference.lemonade import EngineCapabilities
from pmc_agent.inference.lemonade import LemonadeEngine
from pmc_core.protocol import HEALTH_ENGINE_READY
from pmc_core.protocol import HEALTH_ENGINE_UNAVAILABLE

_MODEL = "test-model"
_CHECKPOINT = "test/checkpoint.gguf"
_BASE_URL = "http://127.0.0.1"
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
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        """Yield configured chunks in order.

        Yields:
            One configured byte chunk at a time.
        """
        for index, chunk in enumerate(self._chunks):
            if self._before_chunk is not None:
                self._before_chunk(index)
            yield chunk

    def close(self) -> None:
        """Record that the response stopped consuming this stream."""
        self.closed = True


class _BlockingStream(httpx.SyncByteStream):
    """A stream that remains blocked until another thread closes it."""

    def __init__(self) -> None:
        """Create a stream whose close signal releases its iterator."""
        self._closed = threading.Event()

    def __iter__(self) -> Iterator[bytes]:
        """Yield partial text and then wait for the deadline watchdog.

        Yields:
            One partial SSE event before blocking.
        """
        yield _event(content="partial")
        self._closed.wait(timeout=5.0)

    @property
    def closed(self) -> bool:
        """Return whether the stream was closed.

        Returns:
            True once ``close()`` has released the blocked iterator.
        """
        return self._closed.is_set()

    def close(self) -> None:
        """Release the blocked iterator."""
        self._closed.set()


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
    return f"data: {json.dumps({'model': model, 'choices': [choice]})}\n\n".encode()


def _done() -> bytes:
    """Build the terminal streaming sentinel.

    Returns:
        Lemonade's OpenAI-compatible ``[DONE]`` event.
    """
    return b"data: [DONE]\n\n"


def _request(
    *,
    grammar: str | None = None,
    max_tokens: int = 32,
    deadline_seconds: float = 5.0,
) -> CompletionRequest:
    """Build a small completion request.

    Args:
        grammar: The optional grammar to include.
        max_tokens: The bounded generation limit to send.
        deadline_seconds: The completion's total monotonic time budget.

    Returns:
        A request suitable for adapter tests.
    """
    return CompletionRequest(
        prompt="Reply with a plan.",
        grammar=grammar,
        max_tokens=max_tokens,
        deadline_seconds=deadline_seconds,
    )


def _engine(
    handler: _HANDLER,
    *,
    base_url: str = _BASE_URL,
    connect_timeout_seconds: float = 5.0,
    read_timeout_seconds: float = 30.0,
) -> LemonadeEngine:
    """Build an engine using only ``MockTransport``.

    Args:
        handler: The scripted transport response handler.
        base_url: The loopback origin to give both client and adapter.
        connect_timeout_seconds: The adapter's configured connect budget.
        read_timeout_seconds: The adapter's configured read and write budget.

    Returns:
        A Lemonade engine with no network route.
    """
    client = httpx.Client(
        base_url=base_url, transport=httpx.MockTransport(handler)
    )
    return LemonadeEngine(
        base_url=base_url,
        model_name=_MODEL,
        checkpoint=_CHECKPOINT,
        connect_timeout_seconds=connect_timeout_seconds,
        read_timeout_seconds=read_timeout_seconds,
        client=client,
    )


def _successful_response(
    text: str = "hello", reason: str = "stop"
) -> httpx.Response:
    """Build a successful SSE response.

    Args:
        text: The completion text to stream.
        reason: Lemonade's terminal reason.

    Returns:
        A complete streamed HTTP response.
    """
    return httpx.Response(
        200,
        content=_event(content=text) + _event(finish_reason=reason) + _done(),
    )


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
    engine = _engine(
        lambda _request: _successful_response("hello world", reason)
    )

    result = engine.complete(_request(), cancel=CancelToken())

    assert result == CompletionResult(
        text="hello world",
        model_identity=f"{_MODEL}@{_CHECKPOINT}",
        stop_reason=expected_stop,
    )


def test_every_request_is_streaming_deterministic_and_only_sends_grammar_when_set() -> (
    None
):
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


@pytest.mark.parametrize(
    "base_url", ["http://localhost", "http://127.0.0.1", "http://[::1]"]
)
def test_every_supported_loopback_origin_is_accepted(base_url: str) -> None:
    """The sole engine destination may use any standard loopback spelling.

    Args:
        base_url: The loopback URL to validate and use with MockTransport.
    """
    result = _engine(
        lambda _request: _successful_response(), base_url=base_url
    ).complete(_request(), cancel=CancelToken())

    assert isinstance(result, CompletionResult)
    assert result.text == "hello"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com",
        "https://127.0.0.1",
        "http://localhost/api/v1",
        "http://user@localhost",
        "http://@localhost",
        "http://localhost?",
        "http://localhost#",
        "http://[::1",
    ],
)
def test_nonlocal_or_nonorigin_urls_are_rejected_before_the_transport_is_used(
    base_url: str,
) -> None:
    """A MockTransport cannot create a remote route or base-path escape.

    Args:
        base_url: The invalid configured destination to reject.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record any request that would violate local-only operation.

        Args:
            request: The forbidden outbound request.

        Returns:
            Never returns because adapter construction must reject first.
        """
        requests.append(request)
        return _successful_response()

    client = httpx.Client(
        base_url=_BASE_URL, transport=httpx.MockTransport(handler)
    )

    with pytest.raises(ValueError):
        LemonadeEngine(
            base_url=base_url,
            model_name=_MODEL,
            checkpoint=_CHECKPOINT,
            client=client,
        )

    assert requests == []


def test_a_completion_does_not_follow_a_redirect_to_another_origin() -> None:
    """A caller-injected redirect policy cannot escape the local server."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record the local request and offer a forbidden remote redirect.

        Args:
            request: The completion request sent by the adapter.

        Returns:
            A redirect which must be returned as an unavailable response.
        """
        requests.append(request)
        return httpx.Response(
            302,
            headers={"location": "http://example.com/api/v1/chat/completions"},
        )

    client = httpx.Client(
        base_url=_BASE_URL,
        follow_redirects=True,
        transport=httpx.MockTransport(handler),
    )
    engine = LemonadeEngine(
        base_url=_BASE_URL,
        model_name=_MODEL,
        checkpoint=_CHECKPOINT,
        client=client,
    )

    result = engine.complete(_request(), cancel=CancelToken())

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNAVAILABLE
    assert [str(request.url) for request in requests] == [
        f"{_BASE_URL}/api/v1/chat/completions"
    ]


def test_a_cancelled_token_prevents_network_io() -> None:
    """Cancellation before streaming begins cannot send a completion."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record a request that must not be made.

        Args:
            request: The forbidden outbound completion request.

        Returns:
            Never returns because cancellation is preflight checked.
        """
        requests.append(request)
        return _successful_response()

    cancel = CancelToken()
    cancel.cancel()

    result = _engine(handler).complete(_request(), cancel=cancel)

    assert result == CompletionResult(
        text="",
        model_identity=f"{_MODEL}@{_CHECKPOINT}",
        stop_reason=STOP_CANCELLED,
    )
    assert requests == []


def test_an_expired_deadline_prevents_network_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local deadline is checked before opening a response stream.

    Args:
        monkeypatch: Pytest's controlled patching fixture.
    """
    moments = iter((0.0, 1.0))
    monkeypatch.setattr(lemonade.time, "monotonic", lambda: next(moments))
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record a request that must not be made.

        Args:
            request: The forbidden outbound completion request.

        Returns:
            Never returns because deadline is preflight checked.
        """
        requests.append(request)
        return _successful_response()

    result = _engine(handler).complete(
        _request(deadline_seconds=0.5), cancel=CancelToken()
    )

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_TIMEOUT
    assert requests == []


def test_each_http_phase_timeout_is_bounded_by_the_remaining_deadline() -> None:
    """No transport phase can wait longer than this completion permits."""
    observed: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record the HTTPX per-call timeout extension.

        Args:
            request: The outbound completion request.

        Returns:
            A successful stream after inspecting its timeout configuration.
        """
        timeout = request.extensions["timeout"]
        assert isinstance(timeout, dict)
        observed.append(timeout)
        return _successful_response()

    result = _engine(
        handler, connect_timeout_seconds=5.0, read_timeout_seconds=5.0
    ).complete(_request(deadline_seconds=0.5), cancel=CancelToken())

    assert isinstance(result, CompletionResult)
    assert len(observed) == 1
    assert all(
        value is not None and value <= 0.5 for value in observed[0].values()
    )


def test_a_stalled_stream_is_closed_at_the_absolute_deadline() -> None:
    """Repeated reads cannot reset and overrun the wall-clock budget."""
    stream = _BlockingStream()
    engine = _engine(lambda _request: httpx.Response(200, stream=stream))

    started_at = time.monotonic()
    result = engine.complete(
        _request(deadline_seconds=0.05), cancel=CancelToken()
    )
    elapsed_seconds = time.monotonic() - started_at

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_TIMEOUT
    assert elapsed_seconds < 0.5
    assert stream.closed


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


def test_a_server_error_is_typed_as_unavailable() -> None:
    """A reachable Lemonade server still reports its own 5xx failure."""
    result = _engine(
        lambda _request: httpx.Response(503, content="temporarily unavailable")
    ).complete(_request(), cancel=CancelToken())

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_UNAVAILABLE


def test_deadline_discards_partial_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deadline failure cannot feed a truncated plan to the graph.

    Args:
        monkeypatch: Pytest's controlled patching fixture.
    """
    moments = iter((0.0, 0.1, 1.0, 6.0))
    monkeypatch.setattr(lemonade.time, "monotonic", lambda: next(moments))
    stream = _ChunkStream(
        (_event(content="partial"), _event(finish_reason="stop") + _done())
    )
    engine = _engine(lambda _request: httpx.Response(200, stream=stream))

    result = engine.complete(_request(), cancel=CancelToken())

    assert isinstance(result, EngineFailure)
    assert result.category == ENGINE_TIMEOUT
    assert not hasattr(result, "text")
    assert stream.closed


def test_cancellation_closes_the_stream_and_returns_received_text() -> None:
    """A cancellation turns the partial streamed result into a terminal result."""
    cancel = CancelToken()
    stream = _ChunkStream(
        (
            _event(content="before cancel"),
            _event(finish_reason="stop") + _done(),
        ),
        before_chunk=lambda index: cancel.cancel() if index == 1 else None,
    )
    engine = _engine(lambda _request: httpx.Response(200, stream=stream))

    result = engine.complete(_request(), cancel=cancel)

    assert result == CompletionResult(
        text="before cancel",
        model_identity=f"{_MODEL}@{_CHECKPOINT}",
        stop_reason=STOP_CANCELLED,
    )
    assert stream.closed


def test_a_grammar_rejection_is_not_misreported_as_an_outage() -> None:
    """Lemonade's explicit grammar rejection gets its distinct category."""
    engine = _engine(
        lambda _request: httpx.Response(
            400, json={"error": {"param": "grammar", "message": "bad grammar"}}
        )
    )

    result = engine.complete(
        _request(grammar='root ::= "ok"'), cancel=CancelToken()
    )

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


def test_malformed_sse_framing_is_unknown() -> None:
    """Only OpenAI-compatible ``data:`` events are valid stream frames."""
    result = _engine(
        lambda _request: httpx.Response(200, content=b"event: completion\n\n")
    ).complete(_request(), cancel=CancelToken())

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


def _probed_engine(handler: _HANDLER) -> LemonadeEngine:
    """Build an engine that already has capabilities, without a real probe.

    `health()` only needs `capabilities.device`; a full multi-step probe
    is `test_inference_lemonade_probe.py`'s own scope, not this one's.

    Args:
        handler: The scripted transport response handler `health()` calls.

    Returns:
        An engine whose `capabilities` are already set.
    """
    engine = _engine(handler)
    engine._set_capabilities(
        EngineCapabilities(
            lemonade_version="11.9.0",
            model_name=_MODEL,
            checkpoint=_CHECKPOINT,
            device="cpu",
            recipe="test-recipe",
            context_length=4096,
            grammar_enforced=True,
        )
    )
    return engine


def _loaded_health_body(model_name: str = _MODEL) -> dict[str, object]:
    """Build a healthy body reporting `model_name` as currently loaded.

    Args:
        model_name: The model name to report loaded, defaulting to this
            module's own configured `_MODEL`.

    Returns:
        A JSON-shaped health body `health()` treats as ready.
    """
    return {
        "status": "ok",
        "version": "11.9.0",
        "all_models_loaded": [{"model_name": model_name}],
    }


def test_health_reports_ready_when_the_server_answers_healthy() -> None:
    """A healthy server reports ready, naming the probed device."""
    engine = _probed_engine(
        lambda _request: httpx.Response(200, json=_loaded_health_body())
    )

    health = engine.health()

    assert health == EngineHealth(
        state=HEALTH_ENGINE_READY,
        engine="lemonade",
        engine_version="11.9.0",
        device="cpu",
        model_identity=f"{_MODEL}@{_CHECKPOINT}",
        failure=None,
    )


def test_health_reports_unavailable_when_the_model_is_no_longer_loaded() -> (
    None
):
    """A healthy server that evicted or never (re)loaded the model.

    Reported ready would be worse than reported unavailable: `copilot
    _health` would show "ready" while every real completion this engine
    makes fails with an engine error, since Lemonade itself is up but the
    configured model is not.
    """
    engine = _probed_engine(
        lambda _request: httpx.Response(
            200,
            json={
                "status": "ok",
                "version": "11.9.0",
                "all_models_loaded": [{"model_name": "some-other-model"}],
            },
        )
    )

    health = engine.health()

    assert health.state == HEALTH_ENGINE_UNAVAILABLE
    assert health.failure is not None
    assert _MODEL in health.failure.message


def test_health_reports_unavailable_when_the_server_is_unreachable() -> None:
    """A stopped server reports unavailable, not a raised exception."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    health = _probed_engine(handler).health()

    assert health.state == HEALTH_ENGINE_UNAVAILABLE
    assert health.failure is not None
    assert health.failure.category == ENGINE_UNAVAILABLE
    assert health.engine_version is None
    assert health.device is None
    assert health.model_identity is None


def test_health_reports_unavailable_on_a_non_200_response() -> None:
    """An error status is unavailable, not silently treated as healthy."""
    health = _probed_engine(
        lambda _request: httpx.Response(503, content="overloaded")
    ).health()

    assert health.state == HEALTH_ENGINE_UNAVAILABLE
    assert health.failure is not None
    assert health.failure.category == ENGINE_UNAVAILABLE


def test_health_reports_unavailable_on_a_missing_status_or_version() -> None:
    """A malformed health body is unavailable, not guessed at."""
    missing_status = _probed_engine(
        lambda _request: httpx.Response(200, json={"version": "11.9.0"})
    ).health()
    missing_version = _probed_engine(
        lambda _request: httpx.Response(200, json={"status": "ok"})
    ).health()

    assert missing_status.state == HEALTH_ENGINE_UNAVAILABLE
    assert missing_version.state == HEALTH_ENGINE_UNAVAILABLE


def test_health_reports_unavailable_before_any_probe_has_ever_run() -> None:
    """Calling health() on a never-probed engine never raises."""
    engine = _engine(lambda _request: httpx.Response(200, json={}))

    health = engine.health()

    assert health.state == HEALTH_ENGINE_UNAVAILABLE
    assert health.failure is not None


def test_health_issues_no_load_or_completion_calls() -> None:
    """health() never reloads the model or spends a completion call."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok", "version": "11.9.0"})

    _probed_engine(handler).health()

    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/api/v1/health")
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
