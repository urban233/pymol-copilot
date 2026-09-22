# Copyright 2026 PyMOL Copilot contributors.
"""Bounded local-inference engines and their supported public contract."""

from pmc_agent.inference.base import ENGINE_FAILURE_CATEGORIES
from pmc_agent.inference.base import ENGINE_REFUSED_GRAMMAR
from pmc_agent.inference.base import ENGINE_TIMEOUT
from pmc_agent.inference.base import ENGINE_UNAVAILABLE
from pmc_agent.inference.base import ENGINE_UNKNOWN
from pmc_agent.inference.base import STOP_CANCELLED
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import STOP_LENGTH
from pmc_agent.inference.base import STOP_REASONS
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.inference.fake import FakeEngine

__all__ = [
    "ENGINE_FAILURE_CATEGORIES",
    "ENGINE_REFUSED_GRAMMAR",
    "ENGINE_TIMEOUT",
    "ENGINE_UNAVAILABLE",
    "ENGINE_UNKNOWN",
    "STOP_CANCELLED",
    "STOP_END",
    "STOP_LENGTH",
    "STOP_REASONS",
    "CancelToken",
    "CompletionRequest",
    "CompletionResult",
    "EngineFailure",
    "FakeEngine",
    "InferenceEngine",
]
