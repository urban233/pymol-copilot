# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL, real-sidecar evidence for the client-side fidelity gate.

docs/master_plan.md item 7's own required evidence: "Test with modified
coordinates, multiple states, alternate locations and hetero atoms."
tests/integration/testdata/h02_full_v1_fixture.pdb already carries three
of the four -- two `MODEL` states, altlocs A/B on `SER 2 OG` at
occupancies 0.60/0.40, one `ZN` HETATM, and a `3A` insertion code -- so no
new fixture is needed. Modified coordinates are produced live, on top of
the loaded fixture, on purpose: a snapshot that can only be reproduced
from the source file proves nothing about a session a user has actually
edited.

Every `FIDELITY_EXACT` case here spawns a real `pmc_sidecar.fidelity`
subprocess through `pmc_core.executor.probe_fidelity()`:
`pmc_client.session.extract_live_snapshot()` reads the mutated live
session, and `pmc_client.fidelity.check_fidelity()` reconstructs that
snapshot in a genuinely fresh PyMOL process and compares the two. Case 6's
sabotage child is what makes those five cases meaningful: it also
reconstructs for real, then perturbs one field of its own honest
re-extraction before reporting it, proving `check_fidelity()` actually
looks at what comes back rather than trusting `STATUS_OK` alone.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import functools
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_client.fidelity import check_fidelity
from pmc_client.session import extract_live_snapshot
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import REASON_OK
from pmc_core.executor import REASON_TIMEOUT
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.executor import probe_fidelity
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import FIDELITY_UNAVAILABLE
from pmc_core.snapshot import ObjectSnapshot

OBJECT_NAME = "fx"


def _extract_and_assert_exact(
    cmd: Any, object_name: str = OBJECT_NAME
) -> ObjectSnapshot:
    """Extract, probe with a real sidecar, assert exact, and return it.

    Args:
        cmd: The real PyMOL cmd module, with the live session already
            mutated by the caller.
        object_name: The object to extract.

    Returns:
        The live snapshot this check was performed against.
    """
    snapshot, digest = extract_live_snapshot(cmd, object_name)

    outcome = check_fidelity(snapshot)

    assert outcome.status == FIDELITY_EXACT
    assert outcome.is_exact is True
    assert outcome.reason == REASON_OK
    assert outcome.mismatches == ()
    assert outcome.live_digest == digest
    assert outcome.reconstructed_digest == digest
    return snapshot


def test_modified_coordinates_reconstruct_exactly(loaded_fixture: Any) -> None:
    """A live coordinate change absent from the source file reconstructs exactly.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    loaded_fixture.alter_state(1, "fx and name CA", "x = x + 3.5")
    loaded_fixture.sync()

    snapshot = _extract_and_assert_exact(loaded_fixture)

    # Serial 2 is chain A's CA, 12.000 in the source file (see the fixture
    # PDB) -- the sidecar never opens that file, only this JSON, so an
    # exact match here proves it reconstructed the live edit, not the disk
    # value.
    chain_a_ca = next(a for a in snapshot.states[0].atoms if a.serial == 2)
    assert chain_a_ca.coord[0] == pytest.approx(12.0 + 3.5)


def test_multiple_states_reconstruct_exactly(loaded_fixture: Any) -> None:
    """Both coordinate states, including a live edit to the second, reconstruct exactly.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    loaded_fixture.alter_state(2, "fx and name CA", "x = x + 7.0")
    loaded_fixture.sync()

    snapshot = _extract_and_assert_exact(loaded_fixture)

    assert len(snapshot.states) == 2
    state1_ca = next(a for a in snapshot.states[0].atoms if a.serial == 2)
    state2_ca = next(a for a in snapshot.states[1].atoms if a.serial == 2)
    assert state1_ca.coord != state2_ca.coord
    assert state2_ca.coord[0] == pytest.approx(12.0 + 7.0)


def test_alternate_locations_reconstruct_exactly(loaded_fixture: Any) -> None:
    """Both altloc atoms, with their distinct occupancies, reconstruct exactly.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    snapshot = _extract_and_assert_exact(loaded_fixture)

    alt_a = next(a for a in snapshot.states[0].atoms if a.serial == 6)
    alt_b = next(a for a in snapshot.states[0].atoms if a.serial == 7)
    assert alt_a.alt == "A"
    assert alt_a.q == pytest.approx(0.6, abs=1e-6)
    assert alt_b.alt == "B"
    assert alt_b.q == pytest.approx(0.4, abs=1e-6)


def test_hetero_atoms_reconstruct_exactly(loaded_fixture: Any) -> None:
    """The ZN hetero atom, with its own representation, reconstructs exactly.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    loaded_fixture.show("spheres", "fx and resn ZN")
    loaded_fixture.sync()

    snapshot = _extract_and_assert_exact(loaded_fixture)

    zinc = next(a for a in snapshot.states[0].atoms if a.serial == 13)
    assert zinc.resn == "ZN"
    assert zinc.hetatm is True
    assert "spheres" in zinc.reps


def test_all_four_categories_combined_reconstruct_exactly(
    loaded_fixture: Any,
) -> None:
    """Modified coordinates, multiple states, altlocs, and hetero atoms together.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    loaded_fixture.alter_state(1, "fx and name CA", "x = x + 3.5")
    loaded_fixture.alter_state(2, "fx and name CA", "x = x + 7.0")
    loaded_fixture.sync()

    # _extract_and_assert_exact already asserts live_digest ==
    # reconstructed_digest, which is this case's own "structure_digest
    # equal both sides" requirement.
    snapshot = _extract_and_assert_exact(loaded_fixture)

    state1_ca = next(a for a in snapshot.states[0].atoms if a.serial == 2)
    state2_ca = next(a for a in snapshot.states[1].atoms if a.serial == 2)
    assert state1_ca.coord[0] == pytest.approx(12.0 + 3.5)
    assert state2_ca.coord[0] == pytest.approx(12.0 + 7.0)
    alt_a = next(a for a in snapshot.states[0].atoms if a.serial == 6)
    assert alt_a.q == pytest.approx(0.6, abs=1e-6)
    zinc = next(a for a in snapshot.states[0].atoms if a.serial == 13)
    assert zinc.hetatm is True


def test_sabotage_child_produces_a_named_mismatch(loaded_fixture: Any) -> None:
    """A dishonestly perturbed reconstruction is caught by name, not missed.

    Without this case, a `check_fidelity()` hard-wired to always report
    `FIDELITY_EXACT` would pass every one of the five cases above too.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    snapshot, _digest = extract_live_snapshot(loaded_fixture, OBJECT_NAME)
    sabotaged_probe = functools.partial(
        probe_fidelity, runner_module="fidelity_sabotage_child"
    )

    outcome = check_fidelity(snapshot, probe=sabotaged_probe)

    assert outcome.status == FIDELITY_NOT_EXACT
    assert outcome.is_exact is False
    assert len(outcome.mismatches) == 1
    assert "state0.atom0.q" in outcome.mismatches[0]


def test_fake_timeout_probe_becomes_unavailable(loaded_fixture: Any) -> None:
    """A probe reporting REASON_TIMEOUT becomes FIDELITY_UNAVAILABLE, never exact.

    No subprocess is spawned here at all -- the probe itself is a fake, so
    this case proves check_fidelity()'s own mapping, independent of
    whether a real sidecar can time out.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    snapshot, digest = extract_live_snapshot(loaded_fixture, OBJECT_NAME)

    def _timed_out_probe(_request: FidelityRequest) -> FidelityReport:
        """Report a fixed timeout regardless of the request.

        Args:
            _request: Ignored.

        Returns:
            A STATUS_FAILED / REASON_TIMEOUT report.
        """
        return FidelityReport(
            executor_version=EXECUTOR_VERSION,
            status=STATUS_FAILED,
            reason=REASON_TIMEOUT,
            input_digest=digest,
            reconstructed_snapshot_json=None,
            child_pid=9999,
            child_terminated=True,
            elapsed_seconds=30.0,
            warnings=(),
        )

    outcome = check_fidelity(snapshot, probe=_timed_out_probe)

    assert outcome.status == FIDELITY_UNAVAILABLE
    assert outcome.is_exact is False
    assert outcome.reason == REASON_TIMEOUT
    assert outcome.mismatches == ()
    assert outcome.reconstructed_digest is None


if __name__ == "__main__":
    import os
    import sys

    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
