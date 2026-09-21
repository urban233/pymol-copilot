# Copyright 2026 PyMOL Copilot contributors.
"""The promotion guard, proved without PyMOL.

Only a clean run may become a sample. Everything else -- a fidelity
mismatch, a command failure, a policy denial, or a clean run whose
selection counts contradict the oracle -- has to come back as a
rejection carrying its own reason, because the per-category rejection
rate is only honest if every attempt is accounted for under the reason
it actually had.

The execution seam is injected here rather than spawned. What is under
test is the grading decision, not PyMOL; driving a real child would
make these cases slow and, for a policy denial against a plan the
generator only emits when policy allows it, impossible to reach at all.
Real execution is covered in test_generate_sample_real_pymol.py.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib

import pytest

from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_FIDELITY_MISMATCH
from pmc_core.executor import REASON_OK
from pmc_core.executor import REASON_POLICY_DENIED
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.executor import STATUS_REJECTED
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import SelectionCount
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.sample import REASON_NOT_GRADABLE
from pmc_data.generate import REASON_SELECTION_COUNT_MISMATCH
from pmc_data.sample import STATUS_UNSUPPORTED
from pmc_data.sample import Rejection
from pmc_data.generate import verify_sample
from pmc_data.oracle import apply_plan
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import Sample
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures
from pmc_data.taxonomy import PlanCandidate
from pmc_data.taxonomy import enumerate_plans

SEED = 20260921

SPEC = next(
    spec
    for spec in enumerate_structures(SEED)
    if spec.spec_id == "everything_small"
)
SNAPSHOT = build_structure(SPEC)
CANDIDATES = enumerate_plans(SNAPSHOT, seed=SPEC.seed)


def _candidate(predicate: str) -> PlanCandidate:
    """Find the first enumerated candidate whose category matches.

    Args:
        predicate: A substring of the wanted category.

    Returns:
        The first matching plan candidate.
    """
    return next(c for c in CANDIDATES if predicate in c.category)


#: A plan whose whole result the oracle can predict.
PREDICTABLE = _candidate("color+select/chain/single")
#: A plan that orients, so the resulting view cannot be predicted.
ORIENTING = _candidate("orient+select/chain/single")
#: A plan naming the polymer flag, which has no ground truth at all.
POLYMER = _candidate("polymer")


def _report(
    candidate: PlanCandidate,
    *,
    reason: str = REASON_OK,
    status: str = STATUS_OK,
    counts: tuple[tuple[str, int], ...] | None = None,
    outcomes: tuple[CommandOutcome, ...] = (),
) -> ExecutionReport:
    """Build an ExecutionReport a fake executor can return.

    Args:
        candidate: The plan candidate being graded.
        reason: The reason code to report.
        status: The status to report.
        counts: Observed selection counts; the oracle's own by default.
        outcomes: Per-command outcomes to report.

    Returns:
        The assembled report.
    """
    expected = apply_plan(SNAPSHOT, candidate.plan)
    observed = expected.selection_counts if counts is None else counts
    fingerprint = (
        None
        if expected.snapshot is None
        else "sha256:"
        + hashlib.sha256(to_json(expected.snapshot).encode("utf-8")).hexdigest()
    )
    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status=status,
        reason=reason,
        input_digest=structure_digest(SNAPSHOT),
        resulting_fingerprint=fingerprint if reason == REASON_OK else None,
        selection_counts=tuple(
            SelectionCount(name=name, atom_count=count)
            for name, count in observed
        ),
        command_outcomes=outcomes
        or tuple(
            CommandOutcome(
                index=index,
                verb=line.split(" ", 1)[0],
                status=OUTCOME_OK,
                error=None,
            )
            for index, line in enumerate(
                candidate.plan.render_pml().splitlines()
            )
        ),
        child_pid=4242,
        child_terminated=True,
        elapsed_seconds=0.1,
    )


def test_a_clean_run_is_promoted_to_a_sample() -> None:
    """The one outcome that may become a sample."""
    result = verify_sample(
        SNAPSHOT,
        SPEC,
        PREDICTABLE,
        sample_id="probe_0001",
        executor=lambda _request: _report(PREDICTABLE),
    )

    assert isinstance(result, Sample)
    assert result.verification.reason == REASON_OK
    assert ASSERTION_RESULTING_SNAPSHOT in {a.kind for a in result.assertions}
    assert result.unsupported_assertions == ()


def test_the_oracle_prediction_is_what_the_executor_is_asked_to_match() -> None:
    """The verdict must be the boundary's, against an expectation it did not make.

    If the request did not carry the oracle's fingerprint, every run
    would pass on the executor's own say-so and the oracle would be
    decorative.
    """
    seen: list[ExecutionRequest] = []

    def capture(request: ExecutionRequest) -> ExecutionReport:
        """Record the request and return a clean report.

        Args:
            request: The execution request under inspection.

        Returns:
            A clean execution report.
        """
        seen.append(request)
        return _report(PREDICTABLE)

    verify_sample(
        SNAPSHOT, SPEC, PREDICTABLE, sample_id="probe", executor=capture
    )

    expected = apply_plan(SNAPSHOT, PREDICTABLE.plan)
    assert expected.snapshot is not None
    assert seen[0].expected_resulting_fingerprint == (
        "sha256:"
        + hashlib.sha256(to_json(expected.snapshot).encode("utf-8")).hexdigest()
    )
    assert seen[0].expected_snapshot_digest == structure_digest(SNAPSHOT)
    assert seen[0].snapshot_json == to_json(SNAPSHOT)


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (STATUS_FAILED, REASON_FIDELITY_MISMATCH),
        (STATUS_FAILED, REASON_COMMAND_FAILURE),
        (STATUS_REJECTED, REASON_POLICY_DENIED),
    ],
)
def test_every_unclean_run_is_rejected_under_its_own_reason(
    status: str, reason: str
) -> None:
    """A rejection must carry the reason it actually had.

    Collapsing these into one bucket would make the per-category
    report unable to distinguish an oracle disagreement from a plan
    PyMOL refused to run.

    Args:
        status: The executor status to simulate.
        reason: The executor reason to simulate.
    """
    result = verify_sample(
        SNAPSHOT,
        SPEC,
        PREDICTABLE,
        sample_id="probe",
        executor=lambda _r: _report(PREDICTABLE, status=status, reason=reason),
    )

    assert isinstance(result, Rejection)
    assert result.reason == reason
    assert result.category == PREDICTABLE.category


def test_a_fidelity_mismatch_is_never_repaired() -> None:
    """Real PyMOL disagreeing with the oracle is the finding, not a nuisance."""
    result = verify_sample(
        SNAPSHOT,
        SPEC,
        PREDICTABLE,
        sample_id="probe",
        executor=lambda _r: _report(
            PREDICTABLE, status=STATUS_FAILED, reason=REASON_FIDELITY_MISMATCH
        ),
    )

    assert isinstance(result, Rejection)


def test_a_command_failure_records_which_command_failed() -> None:
    """A rejection with no detail cannot be acted on."""
    result = verify_sample(
        SNAPSHOT,
        SPEC,
        PREDICTABLE,
        sample_id="probe",
        executor=lambda _r: _report(
            PREDICTABLE,
            status=STATUS_FAILED,
            reason=REASON_COMMAND_FAILURE,
            outcomes=(
                CommandOutcome(
                    index=1,
                    verb="color",
                    status=OUTCOME_ERROR,
                    error="unknown color",
                ),
            ),
        ),
    )

    assert isinstance(result, Rejection)
    assert "unknown color" in result.detail


def test_selection_count_disagreement_is_rejected() -> None:
    """A clean status is not enough if the counts contradict the oracle.

    This is the one case the executor itself cannot catch: the
    fingerprint covers the object's state, not how many atoms a named
    selection held.
    """
    result = verify_sample(
        SNAPSHOT,
        SPEC,
        PREDICTABLE,
        sample_id="probe",
        executor=lambda _r: _report(
            PREDICTABLE, counts=(("copilot_wrong", 999),)
        ),
    )

    assert isinstance(result, Rejection)
    assert result.reason == REASON_SELECTION_COUNT_MISMATCH


def test_an_orienting_plan_is_graded_and_marks_the_camera_unsupported() -> None:
    """Orient is kept, with the assertion it cannot make named outright."""
    result = verify_sample(
        SNAPSHOT,
        SPEC,
        ORIENTING,
        sample_id="probe",
        executor=lambda _r: _report(ORIENTING),
    )

    assert isinstance(result, Sample)
    assert result.unsupported_assertions == ("camera_view",)
    assert result.verification.expected_fingerprint is None
    assert ASSERTION_RESULTING_SNAPSHOT not in {
        a.kind for a in result.assertions
    }


def test_an_ungradable_plan_never_reaches_the_executor() -> None:
    """A category with no ground truth is reported, not run and not kept."""
    calls: list[ExecutionRequest] = []

    def never_called(request: ExecutionRequest) -> ExecutionReport:
        """Record that the executor was reached at all.

        Args:
            request: The unexpected execution request.

        Returns:
            Never returns; the recorded call fails the test.
        """
        calls.append(request)
        return _report(POLYMER)

    result = verify_sample(
        SNAPSHOT, SPEC, POLYMER, sample_id="probe", executor=never_called
    )

    assert isinstance(result, Rejection)
    assert result.status == STATUS_UNSUPPORTED
    assert result.reason == REASON_NOT_GRADABLE
    assert "polymer_classification" in result.detail
    assert calls == []


def test_a_promoted_sample_records_the_versions_its_prompt_declared() -> None:
    """A sample that cannot say which contracts made it is not auditable."""
    result = verify_sample(
        SNAPSHOT,
        SPEC,
        PREDICTABLE,
        sample_id="probe",
        executor=lambda _r: _report(PREDICTABLE),
    )

    assert isinstance(result, Sample)
    assert f"card-version={result.versions.card_version}" in result.prompt_text
    assert result.structure.spec_id == SPEC.spec_id
    assert result.structure.seed == SPEC.seed


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
