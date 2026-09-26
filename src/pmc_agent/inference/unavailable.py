# Copyright 2026 PyMOL Copilot contributors.
"""An `InferenceEngine` that was never reachable at startup.

docs/master_plan.md item 11. SPECIFICATION.md:609: when Lemonade is
unavailable or incompatible, *"Server remains available for diagnostics; no
unconstrained fallback."* Today nothing in `src/` builds a real server
entrypoint (that lands with a later item), but this is the engine such an
entrypoint constructs when `pmc_agent.inference.lemonade.connect_lemonade`
returns an `EngineFailure` instead of a connected engine: every
`complete()` call returns that same recorded failure unchanged, and
`copilot_health` can still report why, instead of the server refusing to
start at all.
"""

from __future__ import annotations

from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import EngineHealth
from pmc_core.protocol import HEALTH_ENGINE_UNAVAILABLE

#: `UnavailableEngine.model_identity`'s fixed placeholder: no model was
#: ever loaded, so there is no real identity to report.
UNAVAILABLE_MODEL_IDENTITY = "unavailable"


class UnavailableEngine:
    """An `InferenceEngine` whose startup capability probe already failed.

    Every method is total and returns the one recorded failure; nothing
    here ever opens a connection or blocks.
    """

    def __init__(
        self, failure: EngineFailure, *, engine: str = "lemonade"
    ) -> None:
        """Record the startup probe failure this engine always returns.

        Args:
            failure: The typed failure a startup capability probe produced.
            engine: A stable engine name for health reporting, matching
                whichever real adapter's probe actually failed.
        """
        self._failure = failure
        self._engine = engine

    @property
    def model_identity(self) -> str:
        """Return a fixed placeholder identity: no model was ever loaded.

        Returns:
            `UNAVAILABLE_MODEL_IDENTITY`.
        """
        return UNAVAILABLE_MODEL_IDENTITY

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult | EngineFailure:
        """Return the recorded startup failure, unconditionally.

        Args:
            request: Accepted for interface conformance; never inspected.
            cancel: Accepted for interface conformance; never inspected.

        Returns:
            The startup probe failure this engine was constructed with.
        """
        del request, cancel
        return self._failure

    def health(self) -> EngineHealth:
        """Report the recorded startup failure as this engine's health.

        Returns:
            Unavailable health carrying the recorded startup failure.
        """
        return EngineHealth(
            state=HEALTH_ENGINE_UNAVAILABLE,
            engine=self._engine,
            engine_version=None,
            device=None,
            model_identity=None,
            failure=self._failure,
        )
