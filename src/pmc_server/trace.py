# Copyright 2026 PyMOL Copilot contributors.
"""An opt-in local record of every completion the server asks for.

docs/master_plan.md item 19. The client only ever sees a request's
bounded outcome: a preview, a question, or a failure envelope. When the
integrated measurement's outcome for a sample differs from the offline
evaluation's, explaining why needs what the model actually wrote, on
every attempt, which only the server sees. `TracingEngine` wraps the
server's engine and appends one JSON line per completion call to a
private file.

It is off by default and exists only when `--trace-file` names a file:
raw intents, cards and plans are not retained unless the user asks
(SPECIFICATION.md:448). The file is created with user-only permissions,
and holds the prompt's SHA-256, never the prompt itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
from pathlib import Path
from typing import TextIO

from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import EngineHealth
from pmc_agent.inference.base import InferenceEngine

#: The version of one trace line's shape.
TRACE_VERSION = 1

_FILE_MODE = 0o600


def open_trace(path: Path) -> TextIO:
    """Open a trace file for appending, private to this user.

    Args:
        path: The trace file. Its directory must exist.

    Returns:
        The open file, positioned at its end.

    Raises:
        OSError: If it cannot be opened, is not a regular file, or its
            permissions cannot be made user-only.
    """
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, _FILE_MODE)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(f"{path} is not a regular file")
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, _FILE_MODE)
        return os.fdopen(descriptor, "a", encoding="utf-8")
    except BaseException:
        os.close(descriptor)
        raise


class TracingEngine:
    """An `InferenceEngine` that records every completion call it forwards.

    Everything else -- identity, health, cancellation, closing -- is the
    wrapped engine's own, unchanged.
    """

    def __init__(self, engine: InferenceEngine, sink: TextIO) -> None:
        """Wrap `engine`, appending one line per call to `sink`.

        Args:
            engine: The engine every call is forwarded to.
            sink: The open trace file. Closed by `close`.
        """
        self._engine = engine
        self._sink = sink
        self._lock = threading.Lock()
        self._sequence = 0

    @property
    def model_identity(self) -> str:
        """Return the wrapped engine's identity.

        Returns:
            The wrapped engine's `model_identity`.
        """
        return self._engine.model_identity

    def health(self) -> EngineHealth:
        """Return the wrapped engine's health.

        Returns:
            The wrapped engine's `health()`.
        """
        return self._engine.health()

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Forward one completion call, then record it.

        Args:
            request: The completion request.
            cancel: The request's cancellation token.

        Returns:
            Exactly what the wrapped engine returned.
        """
        started = time.monotonic()
        outcome = self._engine.complete(request, cancel=cancel)
        elapsed = time.monotonic() - started
        record: dict[str, object] = {
            "trace_version": TRACE_VERSION,
            "prompt_sha256": hashlib.sha256(
                request.prompt.encode("utf-8")
            ).hexdigest(),
            "grammar": request.grammar is not None,
            "max_tokens": request.max_tokens,
            "deadline_seconds": request.deadline_seconds,
            "elapsed_seconds": round(elapsed, 6),
        }
        if isinstance(outcome, EngineFailure):
            record |= {
                "outcome": "failure",
                "category": outcome.category,
                "message": outcome.message,
            }
        else:
            record |= {
                "outcome": "completion",
                "text": outcome.text,
                "stop_reason": outcome.stop_reason,
            }
        with self._lock:
            self._sequence += 1
            record["sequence"] = self._sequence
            self._sink.write(json.dumps(record, sort_keys=True) + "\n")
            self._sink.flush()
        return outcome

    def close(self) -> None:
        """Close the trace file and the wrapped engine, if it has one."""
        with self._lock:
            self._sink.close()
        close_engine = getattr(self._engine, "close", None)
        if callable(close_engine):
            close_engine()
