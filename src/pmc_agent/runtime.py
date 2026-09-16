# Copyright 2026 PyMOL Copilot contributors.
"""LangGraph orchestration graph and Lemonade engine client construction."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from typing import TypedDict

import httpx
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph


class IntentState(TypedDict):
    """State threaded through the intent orchestration graph.

    Attributes:
        intent: The user's natural-language intent for the current turn.
    """

    intent: str


def _pass_through(state: IntentState) -> IntentState:
    """Return the state unchanged.

    Args:
        state: The current graph state.

    Returns:
        The unchanged state.
    """
    return state


def build_intent_graph() -> CompiledStateGraph[
    IntentState, None, IntentState, IntentState
]:
    """Build a compiled single-node intent orchestration graph.

    Returns:
        A compiled `StateGraph` with one pass-through node.
    """
    graph = StateGraph(IntentState)
    graph.add_node("pass_through", _pass_through)
    graph.set_entry_point("pass_through")
    graph.set_finish_point("pass_through")
    return graph.compile()


def build_engine_client(base_url: str, timeout: float) -> httpx.Client:
    """Configure an `httpx.Client` for the local Lemonade endpoint.

    Args:
        base_url: The Lemonade engine's local base URL.
        timeout: The finite request timeout, in seconds.

    Returns:
        A configured client. No request is sent.
    """
    return httpx.Client(base_url=base_url, timeout=timeout)
