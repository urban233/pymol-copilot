# Copyright 2026 PyMOL Copilot contributors.
"""The narrow, total, bounded local-inference engine interface.

docs/master_plan.md item 9 names the shape: "a narrow engine interface --
bounded completion taking prompt, optional grammar, token limit, time
limit, cancellation and model identity". This module defines that
interface and its typed values; item 9 adds the one production
implementation (`lemonade.py`), against a local Lemonade server, plus
startup capability probing. `fake.py`, alongside this module, is the other
implementation and is what the request graph (`pmc_agent.graph`) is tested
against.

Every outcome is a typed value, never an exception. `InferenceEngine.
complete()` cannot raise on the engine's own behalf -- a timeout, an
unreachable server, or a refused grammar all become an `EngineFailure`, in
the same total-boundary style as `pmc_core.parser.parse_pml` and
`pmc_core.executor.execute`. SPECIFICATION.md:551-552 forbids model output
from ever determining retry count, target object, policy or approval; a raw
exception surfacing from an engine into the request graph's control flow
would be exactly that kind of influence, uncontrolled.

`CancelToken` is deliberately advisory rather than a hard guarantee.
tests/discovery/lemonade/FINDINGS.md found that only streaming Lemonade
requests can be cancelled mid-generation; a non-streaming request cannot.
The request graph's actual bound on how long a call can run is
`CompletionRequest.deadline_seconds`, enforced by the engine implementation
itself, not by this token.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import threading
from dataclasses import dataclass
from typing import Protocol

#: `CompletionResult.stop_reason`: generation ran to a natural stop.
STOP_END = "end"

#: `CompletionResult.stop_reason`: generation stopped at `max_tokens`.
STOP_LENGTH = "length"

#: `CompletionResult.stop_reason`: generation stopped at
#: `deadline_seconds` before finishing.
STOP_DEADLINE = "deadline"

#: `CompletionResult.stop_reason`: generation stopped because its
#: `CancelToken` was set. Not guaranteed to be honored -- see the module
#: docstring.
STOP_CANCELLED = "cancelled"

#: Every value `CompletionResult.stop_reason` may carry.
STOP_REASONS: frozenset[str] = frozenset(
    {STOP_END, STOP_LENGTH, STOP_DEADLINE, STOP_CANCELLED}
)

#: `EngineFailure.category`: the engine process or server could not be
#: reached at all.
ENGINE_UNAVAILABLE = "engine_unavailable"

#: `EngineFailure.category`: the call did not complete within
#: `deadline_seconds`.
ENGINE_TIMEOUT = "engine_timeout"

#: `EngineFailure.category`: a grammar was supplied and the engine either
#: rejected it outright or silently ignored it. docs/master_plan.md item 9:
#: "treat silently-ignored grammar as a hard engine failure, not a
#: warning."
ENGINE_REFUSED_GRAMMAR = "engine_refused_grammar"

#: `EngineFailure.category`: a catch-all for a failure this module does not
#: otherwise name, in the same spirit as `pmc_core.errors.CATEGORY_UNKNOWN`
#: -- bounded text is preserved rather than dropped.
ENGINE_UNKNOWN = "engine_unknown"

#: Every category `EngineFailure.category` may carry.
ENGINE_FAILURE_CATEGORIES: frozenset[str] = frozenset(
    {
        ENGINE_UNAVAILABLE,
        ENGINE_TIMEOUT,
        ENGINE_REFUSED_GRAMMAR,
        ENGINE_UNKNOWN,
    }
)


class CancelToken:
    """A cooperative, best-effort cancellation signal for one completion.

    Backed by `threading.Event`. Setting it asks an in-flight `complete()`
    call to stop; whether the underlying engine actually can is that
    engine's own property, not this token's.
    """

    def __init__(self) -> None:
        """Create an unset token."""
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation of the call this token was given to."""
        self._event.set()

    def is_cancelled(self) -> bool:
        """Report whether cancellation has been requested.

        Returns:
            True once `cancel()` has been called on this token.
        """
        return self._event.is_set()


@dataclass(frozen=True)
class CompletionRequest:
    """One bounded request for a single local-model completion.

    Attributes:
        prompt: The complete prompt text to complete. Built once per
            request by `pmc_agent.prompt`'s `PROMPT_BUILDER` and never
            rewritten by anything this dataclass's own consumer does with
            the result.
        grammar: A grammar the engine should constrain generation to, or
            None when no grammar is supplied yet. docs/master_plan.md item
            13 is what will eventually populate this.
        max_tokens: The greatest number of tokens the engine may generate
            for this call.
        deadline_seconds: The wall-clock budget for this call. An engine
            implementation that cannot finish within it must return
            `EngineFailure(category=ENGINE_TIMEOUT, ...)`, never raise.
    """

    prompt: str
    grammar: str | None
    max_tokens: int
    deadline_seconds: float

    def __post_init__(self) -> None:
        """Reject locally invalid completion bounds.

        Raises:
            ValueError: The token limit or deadline is not positive.
        """
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")


@dataclass(frozen=True)
class CompletionResult:
    """One successful local-model completion.

    Attributes:
        text: The model's raw completion text, exactly as the engine
            returned it. The request graph classifies and parses this text;
            this module makes no claim about its shape.
        model_identity: A string identifying the exact model and revision
            that produced this text. SPECIFICATION.md:541 requires this be
            re-verified at approval time (item 10's territory); this module
            only carries it.
        stop_reason: Why generation stopped. One of STOP_REASONS.
    """

    text: str
    model_identity: str
    stop_reason: str

    def __post_init__(self) -> None:
        """Reject an unrecognized successful completion state.

        Raises:
            ValueError: The stop reason is outside the stable interface.
        """
        if self.stop_reason not in STOP_REASONS:
            raise ValueError(f"unknown completion stop reason: {self.stop_reason}")


@dataclass(frozen=True)
class EngineFailure:
    """A bounded, typed engine failure.

    Attributes:
        category: A stable, machine-readable category. One of
            ENGINE_FAILURE_CATEGORIES.
        message: A bounded, printable, single-line explanation. Built with
            `pmc_core.errors.normalize_message` so failures from this
            module and from `pmc_core.errors` are bounded the same way and
            neither can leak unbounded or unprintable text into a request's
            history.
    """

    category: str
    message: str

    def __post_init__(self) -> None:
        """Reject an unrecognized typed engine-failure category.

        Raises:
            ValueError: The category is outside the stable interface.
        """
        if self.category not in ENGINE_FAILURE_CATEGORIES:
            raise ValueError(f"unknown engine failure category: {self.category}")


class InferenceEngine(Protocol):
    """The narrow, engine-neutral local-inference interface.

    An implementation may vary freely in how it talks to its model or
    server; the request graph depends on nothing beyond this surface, so a
    fake and a real adapter are interchangeable to it.
    """

    @property
    def model_identity(self) -> str:
        """Return this engine's model identity.

        Returns:
            A string identifying the exact model and revision this engine
            will report on every `complete()` call. Constant for the
            engine's lifetime.
        """
        ...

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Run one bounded completion.

        Must never raise on the engine's own behalf; every failure this
        engine can encounter -- unreachable, timed out, refused grammar, or
        anything else -- is returned as a typed `EngineFailure`.

        Args:
            request: The bounded completion request to run.
            cancel: A cooperative cancellation signal for this call. An
                implementation that cannot honor it may ignore it; it must
                still return within `request.deadline_seconds`.

        Returns:
            The completion, or a typed failure.
        """
        ...
