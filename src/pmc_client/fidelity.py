# Copyright 2026 PyMOL Copilot contributors.
"""The fidelity gate: reconstruct-and-compare, adjudicated in this process.

docs/master_plan.md item 7's second half. `check_fidelity()` serializes a
live snapshot, hands it to `pmc_core.executor.probe_fidelity()`, and
adjudicates the result against the live snapshot it started from --
`probe_fidelity()` itself never sees the live session, only the candidate
this module gives it and its own child's re-extraction of what it
reconstructed. This module holds both sides of the comparison and is the
only place that does.

`check_fidelity()` never raises for a documented failure mode; every one
becomes a `FIDELITY_UNAVAILABLE` outcome carrying the reason a caller can
report. Orchestration rule 9 (SPECIFICATION.md:539) treats "the check
could not be performed" the same as "the check found a mismatch": neither
produces an applicable plan.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Callable
from dataclasses import dataclass

from pmc_core.executor import DEFAULT_DEADLINE_SECONDS
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_FIDELITY_MISMATCH
from pmc_core.executor import REASON_MALFORMED_INPUT
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.executor import bounded_diagnostic
from pmc_core.executor import probe_fidelity
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import FIDELITY_UNAVAILABLE
from pmc_core.protocol import MAX_FIDELITY_MISMATCH_BYTES
from pmc_core.protocol import MAX_FIDELITY_MISMATCHES
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import SnapshotDecodeError
from pmc_core.snapshot import diff
from pmc_core.snapshot import from_json
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json


@dataclass(frozen=True)
class FidelityOutcome:
    """The adjudicated result of one fidelity check.

    Attributes:
        status: `FIDELITY_EXACT`, `FIDELITY_NOT_EXACT`, or
            `FIDELITY_UNAVAILABLE`.
        reason: A `pmc_core.executor` `REASON_*` constant explaining
            `status`. `REASON_OK` iff status is `FIDELITY_EXACT`.
        mismatches: The complete, unbounded set of field-level mismatches
            `pmc_core.snapshot.diff` found, for the console to show in
            full. Empty iff status is `FIDELITY_EXACT`. `to_wire()`, not
            this dataclass, is where truncation happens.
        live_digest: `pmc_core.snapshot.structure_digest` of the live
            snapshot this check started from.
        reconstructed_digest: The same digest over the sidecar's own
            re-extraction, or None when status is `FIDELITY_UNAVAILABLE`
            (the check never produced a reconstruction to digest).
    """

    status: str
    reason: str
    mismatches: tuple[str, ...]
    live_digest: str
    reconstructed_digest: str | None

    @property
    def is_exact(self) -> bool:
        """Whether this outcome is `FIDELITY_EXACT`.

        Returns:
            True iff status is `FIDELITY_EXACT`.
        """
        return self.status == FIDELITY_EXACT


def check_fidelity(
    live: ObjectSnapshot,
    *,
    probe: Callable[[FidelityRequest], FidelityReport] = probe_fidelity,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
) -> FidelityOutcome:
    """Reconstruct a live snapshot in a fresh sidecar and compare it.

    Args:
        live: The snapshot extracted from the live session
            (`pmc_client.session.extract_live_snapshot`).
        probe: The fidelity probe to call, defaulted to the real
            `pmc_core.executor.probe_fidelity`. A test injects a fake so
            every branch below is provable without spawning anything --
            the same seam shape `pmc_server.validation.PlanValidationService`
            gives its own `executor`.
        deadline_seconds: The wall-clock deadline given to the probe.

    Returns:
        The adjudicated fidelity outcome. Never raises for any documented
        failure mode.
    """
    live_digest = structure_digest(live)
    report = probe(
        FidelityRequest(
            executor_version=EXECUTOR_VERSION,
            snapshot_json=to_json(live),
            deadline_seconds=deadline_seconds,
        )
    )

    if report.status != STATUS_OK:
        # A timeout, a crash, a spawn failure, or a reconstruction failure
        # all mean the same thing here: the check itself could not be
        # performed, which orchestration rule 9 treats identically to a
        # check that found a mismatch.
        return FidelityOutcome(
            status=FIDELITY_UNAVAILABLE,
            reason=report.reason,
            mismatches=(),
            live_digest=live_digest,
            reconstructed_digest=None,
        )

    assert report.reconstructed_snapshot_json is not None
    try:
        reconstructed = from_json(report.reconstructed_snapshot_json)
    except (
        json.JSONDecodeError,
        SnapshotDecodeError,
        KeyError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        # A conforming child never produces this; a caller injecting a
        # fake probe for testing might, and this module must fail closed
        # rather than propagate a raw decode exception.
        return FidelityOutcome(
            status=FIDELITY_UNAVAILABLE,
            reason=REASON_MALFORMED_INPUT,
            mismatches=(),
            live_digest=live_digest,
            reconstructed_digest=None,
        )

    reconstructed_digest = structure_digest(reconstructed)
    mismatches = list(diff(live, reconstructed))
    if not mismatches and reconstructed_digest != live_digest:
        # The two comparisons are computed by different code over
        # different field sets (structure_digest excludes view/settings/
        # enabled; diff covers every declared field). Agreement between
        # them is the cross-process claim
        # tests/integration/test_snapshot_round_trip.py's own round-trip
        # test rests on; a disagreement despite an empty diff is a
        # fidelity failure in its own right, never silently trusted.
        mismatches.append(
            "digest disagreement despite empty diff: live="
            f"{live_digest} reconstructed={reconstructed_digest}"
        )

    if mismatches:
        return FidelityOutcome(
            status=FIDELITY_NOT_EXACT,
            reason=REASON_FIDELITY_MISMATCH,
            mismatches=tuple(mismatches),
            live_digest=live_digest,
            reconstructed_digest=reconstructed_digest,
        )
    return FidelityOutcome(
        status=FIDELITY_EXACT,
        reason=REASON_OK,
        mismatches=(),
        live_digest=live_digest,
        reconstructed_digest=reconstructed_digest,
    )


def to_wire(outcome: FidelityOutcome) -> FidelityOutcomeV1:
    """Bound a fidelity outcome for the wire, without losing its total count.

    The console gets `FidelityOutcome.mismatches` in full; the wire gets at
    most `MAX_FIDELITY_MISMATCHES` of them, each bounded to
    `MAX_FIDELITY_MISMATCH_BYTES`, with `mismatch_count` carrying the true,
    untruncated total regardless.

    Args:
        outcome: The fidelity outcome to encode.

    Returns:
        The bounded wire representation.
    """
    return FidelityOutcomeV1(
        status=outcome.status,
        reason=outcome.reason,
        mismatch_count=len(outcome.mismatches),
        mismatches=tuple(
            bounded_diagnostic(
                mismatch, maximum_bytes=MAX_FIDELITY_MISMATCH_BYTES
            )
            for mismatch in outcome.mismatches[:MAX_FIDELITY_MISMATCHES]
        ),
    )
