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

import ipaddress
import json
import math
import time
from dataclasses import dataclass
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
_HEALTH_PATH = "/api/v1/health"
_LOAD_PATH = "/api/v1/load"
_GRAMMAR_CANARY = 'root ::= "pmc-grammar-probe-ok"'
_GRAMMAR_CANARY_OUTPUT = "pmc-grammar-probe-ok"
_GRAMMAR_CANARY_PROMPT = "Reply with the capital of France in one word."


def _local_origin(base_url: str) -> tuple[str, str, int]:
    """Validate and canonicalize one loopback-only HTTP origin.

    Args:
        base_url: The configured Lemonade origin.

    Returns:
        Its lowercase scheme, normalized host, and effective port.

    Raises:
        ValueError: The value is not a bare HTTP origin on a loopback host.
    """
    try:
        url = httpx.URL(base_url)
        host = url.host.lower()
        port = url.port if url.port is not None else 80
    except (TypeError, ValueError) as error:
        raise ValueError("Lemonade base_url must be a valid local HTTP origin") from error

    if (
        url.scheme != "http"
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or not _is_loopback_host(host)
    ):
        raise ValueError("Lemonade base_url must be a bare loopback HTTP origin")
    return url.scheme, host, port


def _is_loopback_host(host: str) -> bool:
    """Return whether one URL host names the local machine.

    Args:
        host: The hostname as normalized by ``httpx.URL``.

    Returns:
        True for localhost and literal IPv4 or IPv6 loopback addresses.
    """
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _finite_positive_timeout(value: float, name: str) -> float:
    """Validate one configured HTTP timeout.

    Args:
        value: The configured timeout in seconds.
        name: Its public configuration name for the exception.

    Returns:
        The unchanged, valid timeout.

    Raises:
        ValueError: The timeout is not finite and positive.
    """
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


@dataclass(frozen=True)
class EngineCapabilities:
    """The immutable capabilities proved when a Lemonade engine connects.

    ``grammar_enforced`` deliberately has no false state. A server either
    proves it honors a grammar at startup or no engine is returned, which
    makes an unconstrained fallback structurally unavailable.

    Attributes:
        lemonade_version: The running Lemonade version from health.
        model_name: The exact Lemonade model id selected for this engine.
        checkpoint: The exact loaded checkpoint selected for this engine.
        device: The device Lemonade reports after loading.
        recipe: The loaded model recipe Lemonade reports.
        context_length: The catalog context length for the selected model.
        grammar_enforced: Always True for a connected engine.
    """

    lemonade_version: str
    model_name: str
    checkpoint: str
    device: str
    recipe: str
    context_length: int
    grammar_enforced: bool


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
        origin = _local_origin(base_url)
        if client is not None and _local_origin(str(client.base_url)) != origin:
            raise ValueError("Lemonade client origin must match base_url")
        self.base_url = base_url
        self.model_name = model_name
        self.checkpoint = checkpoint
        self.backend = backend
        self.context_size = context_size
        self.connect_timeout_seconds = _finite_positive_timeout(
            connect_timeout_seconds, "connect_timeout_seconds"
        )
        self.read_timeout_seconds = _finite_positive_timeout(
            read_timeout_seconds, "read_timeout_seconds"
        )
        self._capabilities: EngineCapabilities | None = None
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
        checkpoint = (
            self._capabilities.checkpoint
            if self._capabilities is not None
            else self.checkpoint
        )
        return f"{self.model_name}@{checkpoint}"

    @property
    def capabilities(self) -> EngineCapabilities:
        """Return capabilities proved before this engine was handed to a server.

        Returns:
            The immutable startup capability record.

        Raises:
            RuntimeError: The engine was constructed directly rather than by
                ``connect_lemonade()`` and has not been probed.
        """
        if self._capabilities is None:
            raise RuntimeError("Lemonade capabilities have not been probed")
        return self._capabilities

    def _set_capabilities(self, capabilities: EngineCapabilities) -> None:
        """Store the one startup capability record.

        Args:
            capabilities: The successfully verified immutable capability set.
        """
        self._capabilities = capabilities

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

    def _timeout_for_remaining_deadline(
        self, remaining_seconds: float
    ) -> httpx.Timeout:
        """Build HTTP timeouts that cannot outlive one completion deadline.

        Args:
            remaining_seconds: The monotonic budget still available to call.

        Returns:
            A finite timeout for every HTTP phase.
        """
        return httpx.Timeout(
            connect=min(self.connect_timeout_seconds, remaining_seconds),
            read=min(self.read_timeout_seconds, remaining_seconds),
            write=min(self.read_timeout_seconds, remaining_seconds),
            pool=min(self.connect_timeout_seconds, remaining_seconds),
        )

    @staticmethod
    def _remaining_deadline(
        started_at: float, deadline_seconds: float
    ) -> float:
        """Return the monotonic budget left for a completion.

        Args:
            started_at: The monotonic time immediately before the call began.
            deadline_seconds: The call's requested total time budget.

        Returns:
            Remaining positive seconds, or zero once the deadline elapsed.
        """
        return max(0.0, deadline_seconds - (time.monotonic() - started_at))

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
        if cancel.is_cancelled():
            return CompletionResult(
                text="",
                model_identity=self.model_identity,
                stop_reason=STOP_CANCELLED,
            )
        remaining_seconds = self._remaining_deadline(
            started_at, request.deadline_seconds
        )
        if remaining_seconds <= 0:
            return _failure(
                ENGINE_TIMEOUT, "Lemonade completion exceeded its deadline"
            )
        try:
            with self._client.stream(
                "POST",
                _CHAT_COMPLETIONS_PATH,
                json=self._request_body(request),
                timeout=self._timeout_for_remaining_deadline(remaining_seconds),
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    if (
                        request.grammar is not None
                        and response.status_code < 500
                        and _has_grammar_error(response)
                    ):
                        return _failure(
                            ENGINE_REFUSED_GRAMMAR, _response_message(response)
                        )
                    return _failure(ENGINE_UNAVAILABLE, _response_message(response))
                response.raise_for_status()
                for line in response.iter_lines():
                    if cancel.is_cancelled():
                        return CompletionResult(
                            text="".join(text_parts),
                            model_identity=self.model_identity,
                            stop_reason=STOP_CANCELLED,
                        )
                    if self._remaining_deadline(
                        started_at, request.deadline_seconds
                    ) <= 0:
                        return _failure(
                            ENGINE_TIMEOUT,
                            "Lemonade completion exceeded its deadline",
                        )
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        return _failure(ENGINE_UNKNOWN, "malformed SSE framing")
                    payload = line.removeprefix("data:").strip()
                    if not payload:
                        return _failure(ENGINE_UNKNOWN, "malformed SSE event")
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
        except httpx.TimeoutException as error:
            return _failure(ENGINE_TIMEOUT, str(error))
        except httpx.HTTPStatusError as error:
            return _failure(ENGINE_UNAVAILABLE, _response_message(error.response))
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
        if self._remaining_deadline(started_at, request.deadline_seconds) <= 0:
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


def _json_object(response: httpx.Response) -> dict[str, object] | None:
    """Decode one JSON-object response without leaking a parser exception.

    Args:
        response: The response whose body should be a JSON object.

    Returns:
        The JSON object, or None when the body has another shape.
    """
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def _request(
    engine: LemonadeEngine,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
) -> tuple[httpx.Response, dict[str, object] | None] | EngineFailure:
    """Issue one probe request and decode its optional object body.

    Args:
        engine: The local engine whose client sends the request.
        method: The HTTP method to send.
        path: The relative Lemonade API path.
        body: An optional JSON request body.

    Returns:
        The raw response and decoded object, or an unavailable transport
        failure. HTTP status is intentionally left to each ordered probe
        check, since a model 404 has distinct identity semantics.
    """
    try:
        response = engine._client.request(method, path, json=body)
    except httpx.RequestError as error:
        return _failure(ENGINE_UNAVAILABLE, str(error))
    except Exception as error:  # The capability boundary is total too.
        return _failure(ENGINE_UNKNOWN, str(error))
    return response, _json_object(response)


def _unknown(message: str) -> EngineFailure:
    """Build one bounded incompatibility failure.

    Args:
        message: The incompatibility diagnostic.

    Returns:
        An ``ENGINE_UNKNOWN`` capability failure.
    """
    return _failure(ENGINE_UNKNOWN, message)


def _loaded_model(
    health: dict[str, object], model_name: str
) -> dict[str, object] | None:
    """Find the selected model's loaded-health block.

    Args:
        health: The decoded Lemonade health object.
        model_name: The exact selected model id.

    Returns:
        Its loaded model object, or None when health does not report it.
    """
    models = health.get("all_models_loaded")
    if not isinstance(models, list):
        return None
    for model in models:
        if isinstance(model, dict) and model.get("model_name") == model_name:
            return model
    return None


def probe_capabilities(
    engine: LemonadeEngine,
) -> EngineCapabilities | EngineFailure:
    """Prove this local Lemonade server has the required capabilities.

    Checks are deliberately ordered by cost: reachable health, exact catalog
    identity, requested loaded state, then one grammar-constrained completion.
    No failure is retried or degraded into an unconstrained engine.

    Args:
        engine: The local engine whose configured server is probed.

    Returns:
        Immutable capabilities when every check succeeds, otherwise the first
        typed failure observed.
    """
    health_result = _request(engine, "GET", _HEALTH_PATH)
    if isinstance(health_result, EngineFailure):
        return health_result
    health_response, health = health_result
    if health_response.status_code != 200:
        return _failure(ENGINE_UNAVAILABLE, _response_message(health_response))
    if health is None or health.get("status") != "ok":
        return _unknown("Lemonade health did not report status ok")
    version = health.get("version")
    if not isinstance(version, str):
        return _unknown("Lemonade health did not report a version")

    model_result = _request(
        engine, "GET", f"/api/v1/models/{engine.model_name}"
    )
    if isinstance(model_result, EngineFailure):
        return model_result
    model_response, model = model_result
    if model_response.status_code == 404:
        return _unknown(f"Lemonade model not found: {engine.model_name}")
    if model_response.status_code != 200:
        return _failure(ENGINE_UNAVAILABLE, _response_message(model_response))
    if model is None:
        return _unknown("Lemonade model response was not a JSON object")
    actual_checkpoint = model.get("checkpoint")
    if actual_checkpoint != engine.checkpoint:
        return _unknown(
            "Lemonade checkpoint mismatch: "
            f"expected {engine.checkpoint}, got {actual_checkpoint}"
        )
    recipe = model.get("recipe")
    context_length = model.get("context_length")
    if not isinstance(recipe, str) or not isinstance(context_length, int):
        return _unknown("Lemonade model response omitted recipe or context length")

    load_result = _request(
        engine,
        "POST",
        _LOAD_PATH,
        body={
            "model_name": engine.model_name,
            "llamacpp_backend": engine.backend,
            "ctx_size": engine.context_size,
        },
    )
    if isinstance(load_result, EngineFailure):
        return load_result
    load_response, _load = load_result
    if load_response.status_code != 200:
        return _failure(ENGINE_UNAVAILABLE, _response_message(load_response))

    loaded_health_result = _request(engine, "GET", _HEALTH_PATH)
    if isinstance(loaded_health_result, EngineFailure):
        return loaded_health_result
    loaded_health_response, loaded_health = loaded_health_result
    if loaded_health_response.status_code != 200:
        return _failure(
            ENGINE_UNAVAILABLE, _response_message(loaded_health_response)
        )
    if loaded_health is None or loaded_health.get("status") != "ok":
        return _unknown("Lemonade health became invalid after loading")
    loaded_model = _loaded_model(loaded_health, engine.model_name)
    if loaded_model is None:
        return _unknown("Lemonade health did not report the loaded model")
    if loaded_model.get("checkpoint") != engine.checkpoint:
        return _unknown("Lemonade loaded an unexpected checkpoint")
    if loaded_model.get("device") != engine.backend:
        return _unknown("Lemonade loaded an unexpected device")
    if loaded_model.get("recipe") != recipe:
        return _unknown("Lemonade loaded an unexpected recipe")
    recipe_options = loaded_model.get("recipe_options")
    if (
        not isinstance(recipe_options, dict)
        or recipe_options.get("ctx_size") != engine.context_size
    ):
        return _unknown("Lemonade loaded an unexpected context size")

    canary = engine.complete(
        CompletionRequest(
            prompt=_GRAMMAR_CANARY_PROMPT,
            grammar=_GRAMMAR_CANARY,
            max_tokens=16,
            deadline_seconds=engine.read_timeout_seconds,
        ),
        cancel=CancelToken(),
    )
    if (
        isinstance(canary, EngineFailure)
        or canary.text != _GRAMMAR_CANARY_OUTPUT
        or canary.stop_reason != STOP_END
    ):
        detail = canary.message if isinstance(canary, EngineFailure) else canary.text
        return _failure(
            ENGINE_REFUSED_GRAMMAR,
            f"Lemonade grammar canary did not return its sentinel: {detail}",
        )

    return EngineCapabilities(
        lemonade_version=version,
        model_name=engine.model_name,
        checkpoint=engine.checkpoint,
        device=engine.backend,
        recipe=recipe,
        context_length=context_length,
        grammar_enforced=True,
    )


def connect_lemonade(
    *,
    base_url: str = DEFAULT_BASE_URL,
    model_name: str = DEFAULT_MODEL_NAME,
    checkpoint: str = DEFAULT_CHECKPOINT,
    backend: str = DEFAULT_BACKEND,
    context_size: int = DEFAULT_CONTEXT_SIZE,
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> LemonadeEngine | EngineFailure:
    """Connect to, prove, and return one local Lemonade engine.

    Args:
        base_url: The local Lemonade HTTP origin.
        model_name: The exact Lemonade model identifier.
        checkpoint: The expected exact model checkpoint.
        backend: The requested backend device.
        context_size: The requested context size.
        connect_timeout_seconds: The finite connection timeout.
        read_timeout_seconds: The finite HTTP read timeout.
        client: An optional hermetic transport client for tests.

    Returns:
        A proven engine, or the first typed capability failure. There is no
        fallback server, retry loop, or unconstrained mode.
    """
    engine = LemonadeEngine(
        base_url=base_url,
        model_name=model_name,
        checkpoint=checkpoint,
        backend=backend,
        context_size=context_size,
        connect_timeout_seconds=connect_timeout_seconds,
        read_timeout_seconds=read_timeout_seconds,
        client=client,
    )
    capabilities = probe_capabilities(engine)
    if isinstance(capabilities, EngineFailure):
        return capabilities
    engine._set_capabilities(capabilities)
    return engine
