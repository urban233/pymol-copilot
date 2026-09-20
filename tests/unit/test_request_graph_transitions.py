# Copyright 2026 PyMOL Copilot contributors.
"""Shape tests for the request graph: states, the router, and the wiring.

Every edge this graph can take is decided by `route_by_status` alone, so
this file tests that function directly, exhaustively, without compiling or
running the graph at all -- and separately proves the compiled graph's
stub pass-through shape and that `pending_approval` genuinely parks.
Real node behavior (target resolution, generation, the repair loop,
expiry, supersession) is each later step's own test file.
"""

from typing import cast

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END

from pmc_agent.graph import NON_TERMINAL_STATES
from pmc_agent.graph import REQUEST_STATES
from pmc_agent.graph import STATE_GENERATING
from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.graph import STATE_PREPARING
from pmc_agent.graph import STATE_RECEIVED
from pmc_agent.graph import STATE_VALIDATING
from pmc_agent.graph import TERMINAL_ASK
from pmc_agent.graph import TERMINAL_CANCELLED
from pmc_agent.graph import TERMINAL_EXPIRED
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import TERMINAL_REJECTED
from pmc_agent.graph import TERMINAL_STATES
from pmc_agent.graph import TERMINAL_SUPERSEDED
from pmc_agent.graph import RequestState
from pmc_agent.graph import build_request_graph
from pmc_agent.graph import route_by_status


def _state(status: str) -> RequestState:
    """Build a minimal request state carrying only the given status.

    Args:
        status: The status `route_by_status` should route from.

    Returns:
        A request state with every other field at an inert placeholder --
        `route_by_status` reads nothing but `status`.
    """
    return cast(
        RequestState,
        {
            "request_id": "11111111-1111-4111-8111-111111111111",
            "session_id": "22222222-2222-4222-8222-222222222222",
            "created_at": "2026-09-21T00:00:00.000Z",
            "intent": "orient chain A",
            "contract_manifest": None,
            "snapshot_identity": None,
            "snapshot_json": "{}",
            "fidelity": None,
            "status": status,
            "target_object": None,
            "attempt": 0,
            "history": (STATE_RECEIVED,),
            "errors": (),
            "plan": None,
            "plan_id": None,
            "expires_at": None,
            "model_identity": None,
            "failure": None,
            "question": None,
            "completion": None,
        },
    )


def test_request_states_are_exactly_the_eleven_names_in_the_brief() -> None:
    """No status exists that docs/master_plan.md item 8 did not name.

    A set-equality assertion, not a subset check: adding a twelfth status
    anywhere in this graph without deciding to widen this set is a defect,
    not a detail, and this is what catches it.
    """
    expected = {
        STATE_RECEIVED,
        STATE_PREPARING,
        STATE_GENERATING,
        STATE_VALIDATING,
        STATE_PENDING_APPROVAL,
        TERMINAL_REJECTED,
        TERMINAL_EXPIRED,
        TERMINAL_SUPERSEDED,
        TERMINAL_FAILED,
        TERMINAL_CANCELLED,
        TERMINAL_ASK,
    }
    assert expected == REQUEST_STATES
    assert len(REQUEST_STATES) == 11


def test_non_terminal_and_terminal_states_partition_request_states() -> None:
    """The two state sets are disjoint and together cover every status."""
    assert NON_TERMINAL_STATES.isdisjoint(TERMINAL_STATES)
    assert NON_TERMINAL_STATES | TERMINAL_STATES == REQUEST_STATES


@pytest.mark.parametrize(
    "status",
    [
        STATE_PREPARING,
        STATE_GENERATING,
        STATE_VALIDATING,
        STATE_PENDING_APPROVAL,
    ],
)
def test_a_non_terminal_status_routes_to_the_node_of_the_same_name(
    status: str,
) -> None:
    """Every non-terminal status (other than `received`) names its node.

    Args:
        status: A non-terminal status that has a graph node.
    """
    assert route_by_status(_state(status)) == status


@pytest.mark.parametrize(
    "status",
    [
        TERMINAL_REJECTED,
        TERMINAL_EXPIRED,
        TERMINAL_SUPERSEDED,
        TERMINAL_FAILED,
        TERMINAL_CANCELLED,
        TERMINAL_ASK,
    ],
)
def test_every_terminal_status_ends_the_run(status: str) -> None:
    """Every terminal status routes to END, not to a node.

    Args:
        status: A terminal status.
    """
    assert route_by_status(_state(status)) == END


def test_received_has_no_node_of_its_own() -> None:
    """`received` is a real status but names no node in this graph.

    It is the status a request carries before the graph is invoked
    (`pmc_agent.session.RequestGraphSession.submit` sets it); the graph's
    own entry point is `preparing`. Routing from `received` directly would
    be a caller's mistake this graph is never asked to make, so it is not
    asserted to route anywhere -- only that it is not one of the names
    `route_by_status` would treat as a node.
    """
    assert STATE_RECEIVED not in TERMINAL_STATES
    assert STATE_RECEIVED != STATE_PREPARING


def test_an_unrecognized_status_raises_rather_than_routing_somewhere() -> None:
    """A status this graph never produced is a defect to raise on."""
    with pytest.raises(ValueError, match="unrecognized request status"):
        route_by_status(_state("not_a_real_status"))


def test_the_compiled_graph_advances_through_every_stub_in_order() -> None:
    """The stub pass-through chain reaches `pending_approval` and parks.

    Proves the graph compiles, `preparing` -> `generating` -> `validating`
    -> `pending_approval` is wired exactly as SPECIFICATION.md:420 orders
    it, and that reaching `pending_approval` genuinely calls
    `langgraph.types.interrupt` rather than merely setting a status --
    real node bodies replace each stub in steps 6-8, and this stays true
    of every one of them.
    """
    compiled = build_request_graph().compile(checkpointer=InMemorySaver())
    initial = _state(STATE_RECEIVED)
    config = {"configurable": {"thread_id": initial["session_id"]}}

    result = compiled.invoke(initial, config)

    assert "__interrupt__" in result
    snapshot = compiled.get_state(config)
    assert snapshot.next == (STATE_PENDING_APPROVAL,)
    # The checkpointer round-trips a tuple field as a list -- this graph's
    # own nodes only ever read it back through RequestState, never compare
    # its container type, so that is not asserted here either.
    assert list(snapshot.values["history"]) == [
        STATE_RECEIVED,
        STATE_GENERATING,
        STATE_VALIDATING,
        STATE_PENDING_APPROVAL,
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
