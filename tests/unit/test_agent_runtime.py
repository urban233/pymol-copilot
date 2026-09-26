# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for the LangGraph and httpx runtime wiring."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import pytest

from pmc_agent.runtime import build_engine_client
from pmc_agent.runtime import build_intent_graph


def test_intent_graph_passes_the_intent_through() -> None:
    """The compiled graph returns the intent it was given, unchanged."""
    graph = build_intent_graph()

    result = graph.invoke({"intent": "Select chain A and color it red."})

    assert result == {"intent": "Select chain A and color it red."}


def test_engine_client_is_configured_but_sends_nothing() -> None:
    """The engine client carries the given base URL and timeout."""
    client = build_engine_client("http://127.0.0.1:8000", timeout=5.0)

    assert str(client.base_url) == "http://127.0.0.1:8000"
    assert client.timeout.connect == 5.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
