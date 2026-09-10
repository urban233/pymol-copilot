# Copyright 2026 PyMOL Copilot contributors.
"""H-02 discovery: candidate A (canonical structured data) differential.

Candidate A extracts and reconstructs full-V1 relevant state entirely
through PyMOL's own object-construction API (get_model/iterate for reads;
pseudoatom/bond/alter/alter_state/color/show/hide/set/set_view for writes)
-- never a standard molecular file format (candidate B) and never PyMOL's
native session serialization (candidate C). This module proves the
round trip fixture-freeze evidence needs: extract a snapshot from one real
headless Open-Source PyMOL process, reconstruct a fresh object from that
snapshot alone in a genuinely different process (one that never opens the
source fixture file), and diff the two extractions field by field.

The extraction format, the extraction query itself, the JSON round trip,
the diff, the shared fixture, and the nested-subprocess-via-environment-
variable technique all live in `harness.py` now (slice 2) -- shared
unchanged with candidates B and C. Only what is genuinely specific to this
candidate stays here: `reconstruct()` (the object-construction technique
itself), this candidate's own snapshot env-var name, and this module's own
tests.

Real, empirically confirmed API facts this candidate depends on, each of
which cost a wrong first attempt to discover:

- `cmd.load_coords` shares the same NumPy 2.x ABI break already documented
  for `cmd.get_coords` in
  tests/integration/test_real_pymol_command.py -- this pinned
  pymol-open-source-whl==3.2.0.2 build's compiled `_cmd` extension cannot
  call into a NumPy-2.x-linked coordinate array. `cmd.alter_state`'s
  per-atom Python expression avoids NumPy entirely and is used here for
  every multi-state coordinate write.
- The per-atom serial number lives in the iterate/alter namespace as
  uppercase `ID`; lowercase `id` is a different name that `cmd.alter`
  accepts syntactically but never applies.
- An insertion code has no independent alter()-able property. PyMOL only
  derives it by parsing an icode suffix out of `resi` (e.g. `"3A"`), the
  same folded string `get_model().atom[i].resi` already returns -- so
  reconstruction must fold resv+ins_code back into that one string at
  creation time rather than trying to set ins_code separately afterward.
- `pseudoatom` silently renames an atom on a same-residue
  (chain, resi, resn, name) collision at creation time, regardless of
  alt -- both atoms still have alt='' at their own creation moment. `name`
  is an ordinary alterable property, so the practical fix is to always
  set every atom's true name back explicitly after creation rather than
  try to avoid the collision.
- Addressing an atom by `index N` is not stable across the rest of one
  reconstruct() run: a later pseudoatom() call can silently reassign what
  `index N` points to for an earlier atom (confirmed empirically -- a
  same-residue altloc pair's name, alt, q, and coordinates ended up
  swapped across two positions after only later atoms were added, with no
  edit ever addressed at the earlier position by number). A stable
  per-atom tag -- this module uses the otherwise-unused `segi` field --
  makes every post-creation edit safe regardless of internal reordering.
- The per-atom `reps` integer has no documented Python-level bit layout.
  Querying membership by name through the `rep <name>` selection keyword
  (harness.REP_NAMES) is the robust, stable alternative.

Confirmed unsupported case, recorded rather than silently dropped per the
structure-context design's requirement: measurement objects (`cmd.distance`
and siblings) are not covered by this candidate. `cmd.get_session(name)` is
the only introspection path found that exposes a measurement object's
defining data, and it returns raw baked-in coordinate/color arrays rather
than a live reference to the atoms it measures -- structurally candidate
C's mechanism (session serialization), not a live-query read this candidate
can reuse. See test_measurement_objects_are_not_recoverable_via_query_apis
below for the negative evidence.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from harness import SNAPSHOT_SCHEMA_VERSION
from harness import BondRecord
from harness import ObjectSnapshot
from harness import _diff
from harness import extract
from harness import from_json
from harness import run_nested_snapshot_process
from harness import to_json

# real_pymol/loaded_fixture (pytest fixtures defined in harness.py) are not
# imported here: this directory's conftest.py re-exports them once so
# pytest's directory-scoped fixture discovery makes them available to every
# test below without a same-named import that every test function's
# loaded_fixture parameter would otherwise shadow (ruff's F811, confirmed
# empirically -- see conftest.py's own docstring).

SNAPSHOT_ENV_VAR = "H02_CANDIDATE_A_SNAPSHOT_JSON"


def reconstruct(cmd: Any, snapshot: ObjectSnapshot) -> None:
    """Rebuild a live PyMOL object from a canonical structured snapshot.

    Uses only PyMOL's object-construction API (pseudoatom/bond/alter/
    alter_state/color/show/hide/set/set_view) -- never a molecular file
    format and never session serialization.

    Args:
        cmd: The real PyMOL cmd module, in a fresh process with no
            conflicting object of the same name.
        snapshot: The canonical snapshot to reconstruct.
    """
    name = snapshot.name
    first_state = snapshot.states[0]

    def tag(i: int) -> str:
        """A per-atom selection stable across internal reordering.

        Args:
            i: The atom's zero-based position in the first state.

        Returns:
            A selection clause matching only that one atom's segi tag.
        """
        return f"tag{i:04d}"

    for i, atom in enumerate(first_state.atoms):
        folded_resi = f"{atom.resv}{atom.ins_code}"
        cmd.pseudoatom(
            name,
            pos=list(atom.coord),
            chain=atom.chain,
            resi=folded_resi,
            resn=atom.resn,
            name=atom.name,
            elem=atom.elem,
            b=atom.b,
            q=atom.q,
            hetatm=int(atom.hetatm),
            segi=tag(i),
            state=1,
        )
    cmd.sync()

    for i, atom in enumerate(first_state.atoms):
        edits = [f"name={atom.name!r}", f"ID={atom.serial}"]
        if atom.alt:
            edits.append(f"alt={atom.alt!r}")
        cmd.alter(f"{name} and segi {tag(i)}", "; ".join(edits))
    cmd.sync()

    for bond in snapshot.bonds:
        cmd.bond(
            f"{name} and segi {tag(bond.atom_index_a)}",
            f"{name} and segi {tag(bond.atom_index_b)}",
            order=bond.order,
        )
    cmd.sync()

    for i, atom in enumerate(first_state.atoms):
        sel = f"{name} and segi {tag(i)}"
        cmd.color(str(atom.color), sel)
        cmd.hide("everything", sel)
        for rep_name in atom.reps:
            cmd.show(rep_name, sel)
        if atom.label is not None:
            cmd.label(sel, repr(atom.label))
    cmd.sync()

    # segi was only a reconstruction-time addressing aid, never part of the
    # declared schema; clear it so the reconstructed object doesn't carry a
    # field the original never had.
    cmd.alter(name, "segi=''")
    cmd.sync()

    for state_number, state in enumerate(snapshot.states[1:], start=2):
        cmd.create(name, name, 1, state_number)
        cmd.sync()
        coords = [list(atom.coord) for atom in state.atoms]
        cmd.alter_state(
            state_number,
            name,
            "x,y,z = coords.pop(0)",
            space={"coords": coords},
        )
    cmd.sync()

    cmd.set_view(snapshot.view)

    for setting_name, value in snapshot.settings:
        cmd.set(setting_name, value, name)
    if snapshot.enabled:
        cmd.enable(name)
    else:
        cmd.disable(name)
    cmd.sync()


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
    """The real fixture contains meaningful data for every candidate field."""
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

    assert snapshot.schema_version == SNAPSHOT_SCHEMA_VERSION
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


def test_json_rejects_an_unsupported_candidate_schema_version(
    loaded_fixture: Any,
) -> None:
    """Candidate A rejects JSON from an unknown shared schema version."""
    payload = json.loads(to_json(extract(loaded_fixture, "fx")))
    payload["schema_version"] = SNAPSHOT_SCHEMA_VERSION + 1

    with pytest.raises(ValueError, match="unsupported snapshot schema version"):
        from_json(json.dumps(payload))


def test_object_enabled_state_is_extracted_when_object_is_enabled(
    loaded_fixture: Any,
) -> None:
    """Candidate A records both disabled and enabled object visibility."""
    loaded_fixture.enable("fx")
    loaded_fixture.sync()

    assert extract(loaded_fixture, "fx").enabled is True

    loaded_fixture.disable("fx")
    loaded_fixture.sync()


def test_diff_reports_identity_and_state_mutations(
    loaded_fixture: Any,
) -> None:
    """Diff reports independent mutations instead of trusting equal extracts."""
    snapshot = extract(loaded_fixture, "fx")
    atom = snapshot.states[0].atoms[0]
    mutated_atom = dataclasses.replace(
        atom,
        coord=(atom.coord[0] + 1.0, atom.coord[1], atom.coord[2]),
        color=atom.color + 1,
        label="mutated label",
        reps=atom.reps[1:],
    )
    mutated = dataclasses.replace(
        snapshot,
        name="other-object",
        enabled=not snapshot.enabled,
        schema_version=SNAPSHOT_SCHEMA_VERSION + 1,
        states=(
            dataclasses.replace(
                snapshot.states[0],
                atoms=(mutated_atom, *snapshot.states[0].atoms[1:]),
            ),
            *snapshot.states[1:],
        ),
    )

    mismatches = _diff(snapshot, mutated)

    assert any("object.name" in mismatch for mismatch in mismatches)
    assert any("object.enabled" in mismatch for mismatch in mismatches)
    assert any("schema_version" in mismatch for mismatch in mismatches)
    assert any("state0.atom0.coord" in mismatch for mismatch in mismatches)
    assert any("state0.atom0.color" in mismatch for mismatch in mismatches)
    assert any("state0.atom0.label" in mismatch for mismatch in mismatches)
    assert any("state0.atom0.reps" in mismatch for mismatch in mismatches)


def test_candidate_a_round_trips_through_a_fresh_process(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Candidate A reconstructs exactly in a process that never sees the file.

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


def test_reconstruct_from_env_snapshot_matches_original() -> None:
    """Reconstruct from an externally supplied snapshot and diff it.

    Only meaningful when invoked as the nested subprocess spawned by
    test_candidate_a_round_trips_through_a_fresh_process, which sets
    SNAPSHOT_ENV_VAR. Skips when run any other way, since it has no
    snapshot to reconstruct from and no assertion to make.

    Raises:
        AssertionError: If the re-extracted snapshot differs from the
            original in any recorded field.
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
        mismatches = _diff(original, reconstructed)
        assert not mismatches, "\n".join(mismatches)
    finally:
        cmd.do("quit")


def test_measurement_objects_are_not_recoverable_via_query_apis(
    loaded_fixture: Any,
) -> None:
    """Negative result: candidate A cannot capture a measurement object.

    Records why, rather than silently omitting measurement objects from
    the schema above: cmd.get_session() is the only introspection path
    found that exposes a distance object's defining data, and what it
    returns is a raw baked-in coordinate/color array, not a live reference
    to the atoms it measures -- the same mechanism candidate C (session
    serialization) uses, not something this candidate's ordinary query
    APIs (iterate/get_model) can reuse. This is recorded as an explicit
    unsupported case for the differential report, not a gap to silently
    drop from the eventual contract.

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
    # get_model/iterate, this candidate's only extraction APIs, do not
    # recognize a measurement object as a selectable set of atoms at all --
    # PyMOL raises rather than returning an empty selection (confirmed
    # empirically), so there is no atom-based query to fall back on.
    with pytest.raises(Exception, match="Invalid selection name"):
        loaded_fixture.count_atoms("d1")

    session = loaded_fixture.get_session("d1")
    # The only data cmd.get_session exposes for a measurement object is a
    # raw, already-baked-in coordinate array -- not the live atom selection
    # candidate A's schema is built around, and not obtainable any other
    # documented way.
    assert "names" in session


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
