# Copyright 2026 PyMOL Copilot contributors.
"""The request graph's checkpoint names every type it holds.

LangGraph's default checkpoint serializer rebuilds any class it finds and
only logs "Deserializing unregistered type"; a later LangGraph refuses
them (docs/master_plan.md item 18's hand-over note). These tests run real
requests through `pmc_agent.session.RequestGraphSession` -- every plan
node type, a repair, a failure, approval and its outcome -- and listen to
LangGraph's own serde events, so a type missing from
`pmc_agent.graph.CHECKPOINT_TYPES` fails here rather than in a later
LangGraph.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import inspect
from collections.abc import Iterator
from collections.abc import Sequence
from datetime import UTC
from datetime import datetime
from typing import Any
from typing import cast

import pytest
from langgraph.checkpoint.serde.event_hooks import register_serde_event_listener

import pmc_core.plan
from pmc_agent.graph import ACCEPTED_CONTRACT_MANIFEST
from pmc_agent.graph import CHECKPOINT_TYPES
from pmc_agent.graph import STATE_APPLYING
from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.graph import TERMINAL_APPLIED
from pmc_agent.graph import TERMINAL_FAILED
from pmc_agent.graph import new_checkpointer
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.prompt import AttemptFailure
from pmc_agent.session import RequestGraphSession
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import SelectionCount
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json

_OBJECT_NAME = "fx"
_SESSION_ID = "33333333-3333-4333-8333-333333333333"

#: Plans that between them use every operation and every term the
#: command language has, so every plan node type is checkpointed.
_PLANS = (
    "select copilot_a, chain A\n"
    "select copilot_b_waters, chain B and resn HOH\n"
    "color forest, copilot_a\n"
    "show sticks, copilot_b_waters\n",
    "select copilot_site, chain A and resn ZN or chain B and resn HOH\n"
    "color purple, copilot_site\n",
    "select copilot_cb, resn SER and name CB or resn ALA and name CB\n"
    "color firebrick, copilot_cb\n",
    "select copilot_ends, chain A and resi 1-3 or chain B and resi 6\n"
    "color yellow, copilot_ends\n",
    "select copilot_het_a, chain A and hetatm\nhide spheres, copilot_het_a\n",
    "select copilot_p, polymer and chain A\norient copilot_p\n",
    "color red, chain B\n",
)


@pytest.fixture
def serde_events() -> Iterator[list[dict[str, Any]]]:
    """Record every serde allowlist event LangGraph emits during a test.

    Yields:
        The events, appended as they happen.
    """
    events: list[dict[str, Any]] = []
    unregister = register_serde_event_listener(
        lambda event: events.append(dict(event))
    )
    try:
        yield events
    finally:
        unregister()


def _ok_executor(_request: ExecutionRequest) -> ExecutionReport:
    """Report success with one selection count, spawning nothing.

    Args:
        _request: Ignored.

    Returns:
        A `STATUS_OK` report.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:test",
        resulting_fingerprint="sha256:" + "0" * 64,
        selection_counts=(SelectionCount("copilot_a", 3),),
        command_outcomes=(),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=0.01,
        warnings=("captured stderr",),
    )


def _session(*completions: str) -> RequestGraphSession:
    """Build a session whose engine replies with `completions` in order.

    Args:
        *completions: The scripted completion texts.

    Returns:
        The session.
    """
    engine = FakeEngine(
        [CompletionResult(text, "m-1", STOP_END) for text in completions]
    )
    return RequestGraphSession(
        engine=engine,
        executor=_ok_executor,
        clock=lambda: datetime(2026, 9, 30, tzinfo=UTC),
        ttl_seconds=60.0,
    )


def _submit(session: RequestGraphSession, request_id: str) -> dict[str, Any]:
    """Submit one well-formed request.

    Args:
        session: The session to submit against.
        request_id: The request's identifier.

    Returns:
        The session's result mapping.
    """
    snapshot = ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name=_OBJECT_NAME,
        enabled=True,
        states=(),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )
    return cast(
        dict[str, Any],
        session.submit(
            request_id=request_id,
            session_id=_SESSION_ID,
            created_at="2026-09-30T00:00:00.000Z",
            intent="colour chain A",
            contract_manifest=ACCEPTED_CONTRACT_MANIFEST,
            snapshot_identity=StructureSnapshotV1(
                schema_version="1",
                digest="sha256:test-digest",
                object_name=_OBJECT_NAME,
                atom_count=0,
                state_count=0,
            ),
            snapshot_json=to_json(snapshot),
            fidelity=FidelityOutcomeV1(
                status=FIDELITY_EXACT,
                reason=REASON_OK,
                mismatch_count=0,
                mismatches=(),
            ),
        ),
    )


@pytest.mark.parametrize("plan", _PLANS)
def test_a_plan_round_trips_through_approval_and_apply(
    plan: str, serde_events: list[dict[str, Any]]
) -> None:
    """Every plan node type survives the checkpoint with no serde event."""
    session = _session(plan)
    pending = _submit(session, "r-1")
    assert pending["status"] == STATE_PENDING_APPROVAL
    plan_id = cast(str, pending["plan_id"])

    applying = session.approve(session_id=_SESSION_ID, plan_id=plan_id)
    assert applying is not None
    assert applying["status"] == STATE_APPLYING
    assert applying["plan"] == pending["plan"]
    assert applying["selection_counts"] == pending["selection_counts"]
    applied = session.report_apply_outcome(
        session_id=_SESSION_ID, plan_id=plan_id, outcome="applied"
    )
    assert applied is not None
    assert applied["status"] == TERMINAL_APPLIED

    assert serde_events == []


def test_a_repair_round_trips_its_attempt_failures(
    serde_events: list[dict[str, Any]],
) -> None:
    """A repaired request checkpoints its earlier failure cleanly."""
    session = _session("colour red, chain A\n", "color red, chain A\n")
    pending = _submit(session, "r-1")
    assert pending["status"] == STATE_PENDING_APPROVAL
    assert len(pending["errors"]) == 1
    applying = session.approve(
        session_id=_SESSION_ID, plan_id=cast(str, pending["plan_id"])
    )
    assert applying is not None
    # msgpack has no tuple, so the checkpoint hands a list back; that was
    # already so under LangGraph's default serializer. What must survive
    # is each typed `AttemptFailure`.
    restored = cast(Sequence[AttemptFailure], applying["errors"])
    assert tuple(restored) == tuple(pending["errors"])

    assert serde_events == []


def test_a_failed_request_round_trips_its_failure_envelope(
    serde_events: list[dict[str, Any]],
) -> None:
    """A request that exhausts its repairs checkpoints its envelope cleanly."""
    session = _session(*["colour red, chain A\n"] * 3)
    failed = _submit(session, "r-1")
    assert failed["status"] == TERMINAL_FAILED
    assert failed["failure"] is not None

    assert serde_events == []


def test_the_allowlist_covers_every_plan_node_type() -> None:
    """Walking the state's annotations finds the whole plan vocabulary."""
    plan_classes = {
        kind
        for _, kind in inspect.getmembers(pmc_core.plan, inspect.isclass)
        if kind.__module__ == pmc_core.plan.__name__
        and dataclasses.is_dataclass(kind)
        and kind.__name__.endswith(("Term", "Operation", "Clause"))
    }
    assert plan_classes
    assert plan_classes <= CHECKPOINT_TYPES


@dataclasses.dataclass(frozen=True)
class _Foreign:
    """A class that is not the graph's own."""

    value: int


def test_a_foreign_type_is_refused_not_merely_warned_about(
    serde_events: list[dict[str, Any]],
) -> None:
    """The allowlist is explicit: a class outside it is blocked."""
    serde = new_checkpointer().serde
    restored = serde.loads_typed(serde.dumps_typed(_Foreign(1)))

    assert restored != _Foreign(1)
    assert [event["kind"] for event in serde_events] == ["msgpack_blocked"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
