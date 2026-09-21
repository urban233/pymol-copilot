# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for the LangGraph and httpx runtime wiring."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_agent.runtime import build_intent_graph


def test_intent_graph_passes_the_intent_through() -> None:
    """The compiled graph returns the intent it was given, unchanged."""
    graph = build_intent_graph()

    result = graph.invoke({"intent": "Select chain A and color it red."})

    assert result == {"intent": "Select chain A and color it red."}
