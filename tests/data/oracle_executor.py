# Copyright 2026 PyMOL Copilot contributors.
"""Fake execution seams for the data tests: a child that agrees, or not.

`oracle_report` answers an execution request with exactly what
`pmc_data.oracle` predicts, standing in for a real PyMOL child that
agrees with the oracle. `mismatch_report` answers as one that
disagreed. Both let the gold set and the split be exercised end to end
without spawning PyMOL; real execution is covered by the real-PyMOL
suites.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib

from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import REASON_FIDELITY_MISMATCH
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import SelectionCount
from pmc_core.snapshot import from_json
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.oracle import apply_plan


def oracle_report(request: ExecutionRequest) -> ExecutionReport:
    """Answer a request with exactly what the oracle predicts.

    Stands in for a real PyMOL child that agrees with the oracle, so the
    gold path's own decisions are tested without spawning anything.

    Args:
        request: The execution request.

    Returns:
        A clean report carrying the oracle's prediction.
    """
    snapshot = from_json(request.snapshot_json)
    expected = apply_plan(snapshot, request.plan)
    resulting = expected.snapshot or snapshot
    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest=structure_digest(snapshot),
        resulting_fingerprint="sha256:"
        + hashlib.sha256(to_json(resulting).encode("utf-8")).hexdigest(),
        selection_counts=tuple(
            SelectionCount(name=name, atom_count=count)
            for name, count in expected.selection_counts
        ),
        command_outcomes=tuple(
            CommandOutcome(
                index=index,
                verb=line.split(" ", 1)[0],
                status=OUTCOME_OK,
                error=None,
            )
            for index, line in enumerate(request.plan.render_pml().splitlines())
        ),
        child_pid=4242,
        child_terminated=True,
        elapsed_seconds=0.1,
    )


def mismatch_report(request: ExecutionRequest) -> ExecutionReport:
    """Answer a request as a child that disagreed with the oracle.

    Args:
        request: The execution request.

    Returns:
        A fidelity-mismatch report.
    """
    clean = oracle_report(request)
    return ExecutionReport(
        executor_version=clean.executor_version,
        status=STATUS_FAILED,
        reason=REASON_FIDELITY_MISMATCH,
        input_digest=clean.input_digest,
        resulting_fingerprint="sha256:" + "0" * 64,
        selection_counts=clean.selection_counts,
        command_outcomes=clean.command_outcomes,
        child_pid=clean.child_pid,
        child_terminated=True,
        elapsed_seconds=0.1,
    )
