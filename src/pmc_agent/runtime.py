# Copyright 2026 PyMOL Copilot contributors.
"""LangGraph orchestration graph and Lemonade engine client construction."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from typing import TypedDict
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


def build_intent_graph() -> (
    CompiledStateGraph[IntentState]  # pyrefly: ignore[bad-specialization]
):
    """Build a compiled single-node intent orchestration graph.

    A `TypedDict` state satisfies langgraph's runtime contract (it carries
    `__required_keys__`/`__optional_keys__`), but pyrefly's strict preset
    does not yet recognize a `TypedDict` class as matching langgraph's
    structural `StateT` bound. Narrowly ignored rather than loosening the
    project-wide strict preset.

    Returns:
        A compiled `StateGraph` with one pass-through node.
    """
    graph = StateGraph(IntentState)  # pyrefly: ignore[bad-specialization]
    graph.add_node("pass_through", _pass_through)
    graph.set_entry_point("pass_through")
    graph.set_finish_point("pass_through")
    return graph.compile()

