# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL evidence for pmc_core.snapshot's extract/reconstruct round trip.

Every collaborator here is real: real headless Open-Source PyMOL
(`pymol.finish_launching(['pymol', '-qc'])`) and the production
`pmc_core.snapshot` module -- extraction, reconstruction, the JSON codec,
the structure digest, and the diff. This is the promoted, real-process
evidence for candidate A of H-02's snapshot comparison: extract a
snapshot from one real PyMOL process, reconstruct a fresh object from that
snapshot alone in a genuinely different process (one that never opens the
source fixture file), and diff the two extractions field by field.

`real_pymol`/`loaded_fixture` (pytest fixtures defined in
snapshot_support.py) are not imported here: this directory's conftest.py
re-exports them once so pytest's directory-scoped fixture discovery makes
them available to this module without a same-named import that every test
function's `loaded_fixture` parameter would otherwise shadow (ruff's
F811, confirmed empirically -- see conftest.py's own docstring).
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import BondRecord
from pmc_core.snapshot import diff
from pmc_core.snapshot import extract
from pmc_core.snapshot import from_json
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json

from snapshot_support import run_nested_snapshot_process

#: The environment variable the nested reconstruction test reads its
#: snapshot JSON path from -- the only channel run_nested_snapshot_process
#: uses to tell the fresh child process what to reconstruct.
SNAPSHOT_ENV_VAR = "PMC_SNAPSHOT_JSON"


def test_fixture_loads_with_every_declared_state_category(
    loaded_fixture: Any,
) -> None:
    """The fixture exercises every full-V1 state category H-02 must cover."""
    assert loaded_fixture.count_states("fx") == 2
    assert sorted(loaded_fixture.get_chains("fx")) == ["A", "B"]
    assert loaded_fixture.count_atoms("fx and hetatm") == 1
    assert loaded_fixture.count_atoms("fx and altloc A+B") == 2
    resi_with_icode: list[str] = []
    loaded_fixture.iterate(
        "fx and resn GLY",
        "resi_with_icode.append(resi)",
        space={"resi_with_icode": resi_with_icode},
    )
    assert resi_with_icode == ["3A", "3A"]


def test_extracted_snapshot_has_independent_expected_values_for_each_category(
    loaded_fixture: Any,
) -> None:
    """The real fixture contains meaningful data for every tracked field."""
    snapshot = extract(loaded_fixture, "fx")
    first_state = snapshot.states[0]
    second_state = snapshot.states[1]
    ca = next(atom for atom in first_state.atoms if atom.serial == 2)
    insertion_atom = next(
        atom for atom in first_state.atoms if atom.serial == 8
    )
    alt_a = next(atom for atom in first_state.atoms if atom.serial == 6)
    alt_b = next(atom for atom in first_state.atoms if atom.serial == 7)
    zinc = next(atom for atom in first_state.atoms if atom.serial == 13)
    second_state_ca = next(
        atom for atom in second_state.atoms if atom.serial == 2
    )

    assert snapshot.schema_version == SNAPSHOT_VERSION
    assert snapshot.name == "fx"
    assert snapshot.enabled is False
    assert len(snapshot.states) == 2
    assert ca.coord == (12.0, 13.0, 2.5)
    assert ca.name == "CA"
    assert ca.resn == "ALA"
    assert ca.chain == "A"
    assert ca.resv == 1
    assert ca.ins_code == ""
    assert ca.elem == "C"
    assert ca.hetatm is False
    assert ca.q == 1.0
    assert ca.b == 20.0
    assert ca.color == loaded_fixture.get_color_index("red")
    assert ca.label == "CA"
    assert "sticks" in ca.reps
    assert insertion_atom.resn == "GLY"
    assert insertion_atom.ins_code == "A"
    assert alt_a.alt == "A"
    assert alt_a.q == pytest.approx(0.6, abs=1e-6)
    assert alt_b.alt == "B"
    assert alt_b.q == pytest.approx(0.4, abs=1e-6)
    assert zinc.resn == "ZN"
    assert zinc.hetatm is True
    assert "spheres" in zinc.reps
    assert snapshot.bonds == (
        BondRecord(0, 1, 1),
        BondRecord(1, 2, 1),
        BondRecord(2, 3, 1),
        BondRecord(3, 4, 1),
        BondRecord(4, 5, 1),
        BondRecord(4, 6, 1),
        BondRecord(4, 7, 1),
        BondRecord(4, 8, 1),
        BondRecord(5, 7, 1),
        BondRecord(5, 8, 1),
        BondRecord(6, 7, 1),
        BondRecord(6, 8, 1),
        BondRecord(7, 8, 1),
        BondRecord(10, 11, 1),
        BondRecord(11, 12, 1),
    )
    assert second_state_ca.coord == (12.0, 13.0, 3.0)
    expected_view = (
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        -0.5,
        0.5,
        -20.0,
    )
    assert snapshot.view == pytest.approx(expected_view, abs=1e-6)
    assert snapshot.settings == (
        ("sphere_scale", "0.35000"),
        ("cartoon_transparency", "0.25000"),
    )


def test_object_enabled_state_is_extracted_when_object_is_enabled(
    loaded_fixture: Any,
) -> None:
    """Both disabled and enabled object visibility are extracted."""
    loaded_fixture.enable("fx")
    loaded_fixture.sync()

    assert extract(loaded_fixture, "fx").enabled is True

    loaded_fixture.disable("fx")
    loaded_fixture.sync()


def test_snapshot_round_trips_through_a_fresh_process(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """A snapshot reconstructs exactly in a process that never sees the file.

    Extracts the loaded fixture's snapshot in this process, then spawns a
    genuinely fresh nested pytest process -- one that launches its own real
    PyMOL and never opens h02_full_v1_fixture.pdb -- to reconstruct from the
    snapshot JSON alone and diff the result.

    Args:
        loaded_fixture: The real PyMOL cmd module with the fixture loaded.
        tmp_path: A pytest-provided temporary directory for the snapshot.

    Raises:
        AssertionError: If reconstruction was not byte-for-byte faithful,
            with every field-level mismatch the nested process reported.
    """
    snapshot = extract(loaded_fixture, "fx")
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(to_json(snapshot))

    result = run_nested_snapshot_process(
        __file__,
        "test_reconstruct_from_env_snapshot_matches_original",
        {SNAPSHOT_ENV_VAR: str(snapshot_path)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # The nested process's own summary line is the only evidence, from this
    # process's point of view, that the skip-when-unset guard below did not
    # silently turn this into a no-op: a real invocation reports exactly one
    # passed test.
    assert "1 passed" in result.stdout + result.stderr


def test_reconstruct_from_env_snapshot_matches_original() -> None:
    """Reconstruct from an externally supplied snapshot and diff it.

    Only meaningful when invoked as the nested subprocess spawned by
    test_snapshot_round_trips_through_a_fresh_process, which sets
    SNAPSHOT_ENV_VAR. Skips when run any other way, since it has no
    snapshot to reconstruct from and no assertion to make.

    Raises:
        AssertionError: If the re-extracted snapshot differs from the
            original in any recorded field, or if the two structure
            digests disagree despite an empty diff.
    """
    snapshot_json_path = os.environ.get(SNAPSHOT_ENV_VAR)
    if not snapshot_json_path:
        pytest.skip(f"{SNAPSHOT_ENV_VAR} not set; not the nested invocation")

    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        original = from_json(Path(snapshot_json_path).read_text())
        reconstruct(cmd, original)
        reconstructed = extract(cmd, original.name)
        mismatches = diff(original, reconstructed)
        assert not mismatches, "\n".join(mismatches)
        # A genuine process boundary: `original` and `reconstructed` were
        # never held in the same process's memory at once. Structure-digest
        # equality here is the same claim item 10's apply-time
        # re-verification and item 7's fidelity gate both rest on.
        assert structure_digest(original) == structure_digest(reconstructed)
    finally:
        cmd.do("quit")


def test_measurement_objects_are_not_recoverable_via_query_apis(
    loaded_fixture: Any,
) -> None:
    """Negative result: a measurement object cannot be captured by query.

    Records why, rather than silently omitting measurement objects from
    the schema: cmd.get_session() is the only introspection path found
    that exposes a distance object's defining data, and what it returns is
    a raw baked-in coordinate/color array, not a live reference to the
    atoms it measures. This is why DECLARED_UNSUPPORTED carries that case
    as an explicit marker rather than a silent gap, and this test ties the
    marker to the negative evidence that motivates it.

    Args:
        loaded_fixture: The real PyMOL cmd module with the fixture loaded.
    """
    loaded_fixture.distance(
        "d1",
        "fx and chain A and resi 1 and name CA",
        "fx and chain A and resi 2 and name CA",
    )
    loaded_fixture.sync()

    assert loaded_fixture.get_type("d1") == "object:measurement"
    # get_model/iterate, extract()'s only query APIs, do not recognize a
    # measurement object as a selectable set of atoms at all -- PyMOL
    # raises rather than returning an empty selection.
    with pytest.raises(Exception, match="Invalid selection name"):
        loaded_fixture.count_atoms("d1")

    session = loaded_fixture.get_session("d1")
    # The only data cmd.get_session exposes for a measurement object is a
    # raw, already-baked-in coordinate array -- not the live atom selection
    # extract()'s schema is built around, and not obtainable any other
    # documented way.
    assert "names" in session

    snapshot = extract(loaded_fixture, "fx")
    assert any(
        "measurement-objects" in marker for marker in snapshot.unsupported
    )
    loaded_fixture.delete("d1")


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (the same defect documented and
    # fixed the same way in tests/integration/test_real_pymol_command.py
    # and tests/data/test_gold_case_verifier.py). os._exit bypasses that
    # interpreter-shutdown window entirely, so pytest's real result is what
    # Bazel actually sees. os._exit skips the normal stdio flush, so flush
    # explicitly first -- otherwise a real failure's traceback and summary
    # can be silently lost from the captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
