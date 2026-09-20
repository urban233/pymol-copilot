# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the client-side fidelity gate: no PyMOL.

Covers every branch of `pmc_client.fidelity.check_fidelity()` against a
fake probe -- never a real sidecar -- so the adjudication logic (exact,
not-exact, and every unavailable reason) is provable without spawning
anything, plus `to_wire()`'s truncation. The real-sidecar evidence that a
faithfully reconstructed live session actually reaches `FIDELITY_EXACT`
lives in tests/integration/test_client_fidelity_real_pymol.py.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
from collections.abc import Callable

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_client.fidelity import FidelityOutcome
from pmc_client.fidelity import check_fidelity
from pmc_client.fidelity import to_wire
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_CHILD_CRASH
from pmc_core.executor import REASON_FIDELITY_MISMATCH
from pmc_core.executor import REASON_MALFORMED_INPUT
from pmc_core.executor import REASON_OK
from pmc_core.executor import REASON_RECONSTRUCTION_FAILURE
from pmc_core.executor import REASON_SPAWN_OR_LOAD_FAILURE
from pmc_core.executor import REASON_TIMEOUT
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.executor import STATUS_REJECTED
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import FIDELITY_UNAVAILABLE
from pmc_core.protocol import MAX_FIDELITY_MISMATCH_BYTES
from pmc_core.protocol import MAX_FIDELITY_MISMATCHES
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot
from pmc_core.snapshot import diff
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json


def _one_atom_snapshot(*, name: str = "fx") -> ObjectSnapshot:
    """Build a one-atom, one-state snapshot.

    Args:
        name: The object name.

    Returns:
        The constructed snapshot.
    """
    atom = AtomRecord(
        serial=1,
        name="CA",
        alt="",
        resn="ALA",
        chain="A",
        resv=1,
        ins_code="",
        elem="C",
        hetatm=False,
        q=1.0,
        b=20.0,
        color=0,
        reps=(),
        label=None,
        coord=(1.0, 2.0, 3.0),
    )
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name=name,
        enabled=True,
        states=(StateSnapshot(atoms=(atom,)),),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )


def _ok_report(reconstructed: ObjectSnapshot) -> FidelityReport:
    """Build a successful FidelityReport carrying a given reconstruction.

    Args:
        reconstructed: The snapshot the fake child claims to have
            reconstructed and re-extracted.

    Returns:
        A STATUS_OK report carrying that snapshot's JSON.
    """
    return FidelityReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest=structure_digest(reconstructed),
        reconstructed_snapshot_json=to_json(reconstructed),
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=0.5,
        warnings=(),
    )


def _fake_probe(
    report: FidelityReport,
) -> Callable[[FidelityRequest], FidelityReport]:
    """Build a probe callable that returns a fixed report for any request.

    Args:
        report: The report to return.

    Returns:
        The fake probe.
    """

    def _probe(_request: FidelityRequest) -> FidelityReport:
        """Return the fixed report regardless of the request.

        Args:
            _request: Ignored.

        Returns:
            The fixed report.
        """
        return report

    return _probe


def test_identical_reextraction_is_exact() -> None:
    """A reconstruction identical to the live snapshot is exact."""
    live = _one_atom_snapshot()

    outcome = check_fidelity(live, probe=_fake_probe(_ok_report(live)))

    assert outcome.status == FIDELITY_EXACT
    assert outcome.is_exact is True
    assert outcome.reason == REASON_OK
    assert outcome.mismatches == ()
    assert outcome.live_digest == structure_digest(live)
    assert outcome.reconstructed_digest == outcome.live_digest


def test_perturbed_reextraction_is_not_exact_with_diffs_module_own_strings() -> (
    None
):
    """A perturbed reconstruction's mismatches equal an independent diff().

    Perturbs one atom's q, that same atom's coordinate, and adds an extra
    coordinate state -- exactly the three categories this item's own
    step 9 covers with real PyMOL. The assertion is equality against an
    independently computed `diff()` call, not a hand-predicted message
    list, since `diff()`'s own n_states short-circuit means which
    messages appear depends on its internal comparison order, not on
    this test.
    """
    live = _one_atom_snapshot()
    perturbed_atom = dataclasses.replace(
        live.states[0].atoms[0], q=0.5, coord=(9.0, 9.0, 9.0)
    )
    perturbed = dataclasses.replace(
        live,
        states=(
            StateSnapshot(atoms=(perturbed_atom,)),
            StateSnapshot(atoms=(perturbed_atom,)),
        ),
    )

    outcome = check_fidelity(live, probe=_fake_probe(_ok_report(perturbed)))

    assert outcome.status == FIDELITY_NOT_EXACT
    assert outcome.is_exact is False
    assert outcome.reason == REASON_FIDELITY_MISMATCH
    assert outcome.mismatches == tuple(diff(live, perturbed))
    assert outcome.mismatches != ()


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (STATUS_REJECTED, REASON_MALFORMED_INPUT),
        (STATUS_FAILED, REASON_TIMEOUT),
        (STATUS_FAILED, REASON_CHILD_CRASH),
        (STATUS_FAILED, REASON_SPAWN_OR_LOAD_FAILURE),
        (STATUS_FAILED, REASON_RECONSTRUCTION_FAILURE),
    ],
)
def test_every_non_ok_report_becomes_unavailable(
    status: str, reason: str
) -> None:
    """A report that never reached STATUS_OK becomes FIDELITY_UNAVAILABLE.

    Args:
        status: The report status under test.
        reason: The report reason under test.
    """
    live = _one_atom_snapshot()
    report = FidelityReport(
        executor_version=EXECUTOR_VERSION,
        status=status,
        reason=reason,
        input_digest=None,
        reconstructed_snapshot_json=None,
        child_pid=None if status == STATUS_REJECTED else 4321,
        child_terminated=None if status == STATUS_REJECTED else True,
        elapsed_seconds=0.1,
        warnings=(),
    )

    outcome = check_fidelity(live, probe=_fake_probe(report))

    assert outcome.status == FIDELITY_UNAVAILABLE
    assert outcome.is_exact is False
    assert outcome.reason == reason
    assert outcome.mismatches == ()
    assert outcome.reconstructed_digest is None
    assert outcome.live_digest == structure_digest(live)


def test_undecodable_reconstructed_json_becomes_unavailable() -> None:
    """STATUS_OK carrying JSON that will not decode fails closed too."""
    live = _one_atom_snapshot()
    report = FidelityReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest=structure_digest(live),
        reconstructed_snapshot_json="{not valid json",
        child_pid=4321,
        child_terminated=True,
        elapsed_seconds=0.5,
        warnings=(),
    )

    outcome = check_fidelity(live, probe=_fake_probe(report))

    assert outcome.status == FIDELITY_UNAVAILABLE
    assert outcome.reason == REASON_MALFORMED_INPUT
    assert outcome.reconstructed_digest is None


def test_empty_diff_but_digest_disagreement_is_not_exact() -> None:
    """A coordinate within diff()'s tolerance but not bit-identical is caught.

    `diff()` allows coordinates to differ by up to 1e-3 without flagging a
    mismatch; `structure_digest()` hashes the exact float value with no
    tolerance. A coordinate nudged by less than 1e-3 produces an empty
    diff but a different digest -- exactly the disagreement
    `check_fidelity()` must not silently trust.
    """
    live = _one_atom_snapshot()
    live_atom = live.states[0].atoms[0]
    nudged_atom = dataclasses.replace(
        live_atom,
        coord=(
            live_atom.coord[0] + 0.0005,
            live_atom.coord[1],
            live_atom.coord[2],
        ),
    )
    nudged = dataclasses.replace(
        live, states=(StateSnapshot(atoms=(nudged_atom,)),)
    )
    assert diff(live, nudged) == []
    assert structure_digest(live) != structure_digest(nudged)

    outcome = check_fidelity(live, probe=_fake_probe(_ok_report(nudged)))

    assert outcome.status == FIDELITY_NOT_EXACT
    assert outcome.is_exact is False
    assert outcome.reason == REASON_FIDELITY_MISMATCH
    assert len(outcome.mismatches) == 1
    assert "digest disagreement" in outcome.mismatches[0]


def test_to_wire_truncates_but_keeps_the_true_count() -> None:
    """to_wire() bounds the sample but never the reported total."""
    outcome = FidelityOutcome(
        status=FIDELITY_NOT_EXACT,
        reason=REASON_FIDELITY_MISMATCH,
        mismatches=tuple(f"mismatch {i}: {'x' * 500}" for i in range(50)),
        live_digest="sha256:live",
        reconstructed_digest="sha256:reconstructed",
    )

    wire = to_wire(outcome)

    assert wire.status == FIDELITY_NOT_EXACT
    assert wire.reason == REASON_FIDELITY_MISMATCH
    assert wire.mismatch_count == 50
    assert len(wire.mismatches) == MAX_FIDELITY_MISMATCHES
    assert all(
        len(mismatch.encode("utf-8")) <= MAX_FIDELITY_MISMATCH_BYTES
        for mismatch in wire.mismatches
    )


def test_to_wire_on_an_exact_outcome_carries_no_mismatches() -> None:
    """An exact outcome's wire form has zero mismatches and count."""
    outcome = FidelityOutcome(
        status=FIDELITY_EXACT,
        reason=REASON_OK,
        mismatches=(),
        live_digest="sha256:live",
        reconstructed_digest="sha256:live",
    )

    wire = to_wire(outcome)

    assert wire.mismatch_count == 0
    assert wire.mismatches == ()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
