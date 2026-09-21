# Copyright 2026 PyMOL Copilot contributors.
"""The bounded streaming adapter for a local Lemonade server.

This is deliberately one module, rather than an ``inference.lemonade``
subpackage. ``tools/bazel/check_dependency_boundaries.py`` matches the
forbidden name ``lemonade`` against Bazel package identities, and a directory
would make the otherwise-safe inference package look like a runtime boundary
violation.

Every completion uses Lemonade's streaming endpoint. The capability spike in
``tests/discovery/lemonade/FINDINGS.md`` found that closing a non-streaming
request does not stop its compute, while closing a stream does. A deadline
therefore drops partial text and returns a typed failure; cancellation closes
the stream and returns the text received so far with ``STOP_CANCELLED``.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import time
from typing import Any

import httpx

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
from pmc_core.errors import normalize_message

# Item 17 replaces this base checkpoint with the fine-tuned artifact. Keep
# both values explicit so the identity and the server-side model selection
# cannot silently drift apart.
DEFAULT_BASE_URL = "http://localhost:13305"
DEFAULT_MODEL_NAME = "Llama-3.2-1B-Instruct-GGUF"
DEFAULT_CHECKPOINT = (
    "unsloth/Llama-3.2-1B-Instruct-GGUF:"
    "Llama-3.2-1B-Instruct-UD-Q4_K_XL.gguf"
)
DEFAULT_BACKEND = "cpu"
DEFAULT_CONTEXT_SIZE = 4096
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_READ_TIMEOUT_SECONDS = 30.0

_CHAT_COMPLETIONS_PATH = "/api/v1/chat/completions"


def _failure(category: str, message: str | None) -> EngineFailure:
    """Build one normalized typed engine failure.

    Args:
        category: The stable engine-failure category.
        message: A possibly hostile server or transport diagnostic.

    Returns:
        A failure whose message is safe to retain in request history.
    """
    return EngineFailure(category=category, message=normalize_message(message))


def _response_message(response: httpx.Response) -> str:
    """Return a bounded-source diagnostic from an HTTP response.

    Args:
        response: The HTTP response that rejected a request.

    Returns:
        The response body when it is readable, or its status otherwise.
    """
    try:
        body = response.text
    except (httpx.ResponseNotRead, UnicodeDecodeError):
        body = ""
    return body or f"HTTP {response.status_code}"


def _has_grammar_error(response: httpx.Response) -> bool:
    """Report whether a rejected response specifically names ``grammar``.

    Args:
        response: A 4xx response to a completion carrying a grammar.

    Returns:
        True when Lemonade's response identifies the grammar parameter.
    """
    return "grammar" in _response_message(response).lower()


class LemonadeEngine:
    """A local, deterministic, streaming Lemonade inference engine.

    The constructor accepts every deployment value explicitly because item 9
    intentionally does not introduce a configuration schema. ``client`` is
    a narrow test seam; production construction leaves it as ``None`` and
    receives a client pinned to the supplied local ``base_url`` and finite
    timeouts.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model_name: str = DEFAULT_MODEL_NAME,
        checkpoint: str = DEFAULT_CHECKPOINT,
        backend: str = DEFAULT_BACKEND,
        context_size: int = DEFAULT_CONTEXT_SIZE,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        """Configure a Lemonade engine without issuing a request.

        Args:
            base_url: The local Lemonade HTTP origin.
            model_name: Lemonade's exact model identifier.
            checkpoint: The exact checkpoint this engine is pinned to.
            backend: The requested Lemonade backend, used by the probe.
            context_size: The requested llama.cpp context size, used by the
                probe.
            connect_timeout_seconds: Finite socket connection budget.
            read_timeout_seconds: Finite per-read HTTP budget.
            client: An optional preconfigured client for hermetic tests.
        """
        self.base_url = base_url
        self.model_name = model_name
        self.checkpoint = checkpoint
        self.backend = backend
        self.context_size = context_size
        self.connect_timeout_seconds = connect_timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
                write=read_timeout_seconds,
                pool=connect_timeout_seconds,
            ),
        )

    @property
    def model_identity(self) -> str:
        """Return the configured model and immutable checkpoint identity.

        Returns:
            The identity that every successful completion reports.
        """
        return f"{self.model_name}@{self.checkpoint}"

    def _request_body(self, request: CompletionRequest) -> dict[str, object]:
        """Build the only completion request shape this adapter can send.

        Args:
            request: The bounded completion request to serialize.

        Returns:
            Lemonade's streaming chat-completion body.
        """
        body: dict[str, object] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": 0,
            "stream": True,
        }
        if request.grammar is not None:
            body["grammar"] = request.grammar
        return body

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Run one bounded streaming completion and return a typed outcome.

        Args:
            request: The prompt, grammar, and budgets to send to Lemonade.
            cancel: The cooperative signal checked between streamed chunks.

        Returns:
            The full completion, a cancellation result, or a typed failure.
        """
        started_at = time.monotonic()
        text_parts: list[str] = []
        finish_reason: str | None = None
        try:
            with self._client.stream(
                "POST", _CHAT_COMPLETIONS_PATH, json=self._request_body(request)
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if time.monotonic() - started_at > request.deadline_seconds:
                        return _failure(
                            ENGINE_TIMEOUT,
                            "Lemonade completion exceeded its deadline",
                        )
                    if cancel.is_cancelled():
                        return CompletionResult(
                            text="".join(text_parts),
                            model_identity=self.model_identity,
                            stop_reason=STOP_CANCELLED,
                        )
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line.removeprefix("data:").strip()
                    if payload == "[DONE]":
                        break
                    event = json.loads(payload)
                    if not isinstance(event, dict):
                        return _failure(ENGINE_UNKNOWN, "malformed SSE event")
                    response_model = event.get("model")
                    if response_model != self.model_name:
                        return _failure(
                            ENGINE_UNKNOWN,
                            "Lemonade completion returned an unexpected model",
                        )
                    choices = event.get("choices")
                    if not isinstance(choices, list) or len(choices) != 1:
                        return _failure(ENGINE_UNKNOWN, "malformed SSE choices")
                    choice: Any = choices[0]
                    if not isinstance(choice, dict):
                        return _failure(ENGINE_UNKNOWN, "malformed SSE choice")
                    delta = choice.get("delta", {})
                    if not isinstance(delta, dict):
                        return _failure(ENGINE_UNKNOWN, "malformed SSE delta")
                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str):
                            return _failure(
                                ENGINE_UNKNOWN, "malformed SSE content"
                            )
                        text_parts.append(content)
                    event_finish_reason = choice.get("finish_reason")
                    if event_finish_reason is not None:
                        if not isinstance(event_finish_reason, str):
                            return _failure(
                                ENGINE_UNKNOWN, "malformed SSE finish reason"
                            )
                        finish_reason = event_finish_reason
        except httpx.HTTPStatusError as error:
            response = error.response
            if (
                request.grammar is not None
                and 400 <= response.status_code < 500
                and _has_grammar_error(response)
            ):
                return _failure(ENGINE_REFUSED_GRAMMAR, _response_message(response))
            return _failure(ENGINE_UNAVAILABLE, _response_message(response))
        except httpx.RequestError as error:
            return _failure(ENGINE_UNAVAILABLE, str(error))
        except Exception as error:  # The interface is total by contract.
            return _failure(ENGINE_UNKNOWN, str(error))

        if cancel.is_cancelled():
            return CompletionResult(
                text="".join(text_parts),
                model_identity=self.model_identity,
                stop_reason=STOP_CANCELLED,
            )
        if time.monotonic() - started_at > request.deadline_seconds:
            return _failure(
                ENGINE_TIMEOUT, "Lemonade completion exceeded its deadline"
            )
        if finish_reason == "stop":
            return CompletionResult(
                text="".join(text_parts),
                model_identity=self.model_identity,
                stop_reason=STOP_END,
            )
        if finish_reason == "length":
            return CompletionResult(
                text="".join(text_parts),
                model_identity=self.model_identity,
                stop_reason=STOP_LENGTH,
            )
        return _failure(ENGINE_UNKNOWN, "missing or unknown SSE finish reason")
