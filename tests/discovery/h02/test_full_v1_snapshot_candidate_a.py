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
  (REP_NAMES below) is the robust, stable alternative.

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

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "h02_full_v1_fixture.pdb"
)
SNAPSHOT_ENV_VAR = "H02_CANDIDATE_A_SNAPSHOT_JSON"

#: PyMOL's named representations, in the order `cmd.count_atoms(f"rep {x}")`
#: is queried -- there is no documented Python-level bit layout for the raw
#: per-atom `reps` integer, so candidate A records membership by name instead.
REP_NAMES = (
    "lines",
    "sticks",
    "spheres",
    "dots",
    "surface",
    "mesh",
    "nonbonded",
    "nb_spheres",
    "cartoon",
    "ribbon",
    "labels",
    "slice",
    "ellipsoids",
    "volume",
)

#: The bounded set of "safe" display settings this prototype exercises at
#: object scope. Not exhaustive -- H-02's contract-freeze checkpoint decides
#: the real accepted set; this proves the get/set/reconstruct path for a
#: representative non-view, non-atom-level setting.
SAFE_SETTINGS = ("sphere_scale", "cartoon_transparency")
CANDIDATE_A_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AtomRecord:
    """One atom's full-V1 relevant state, as candidate A represents it.

    Attributes:
        serial: The atom's stable serial number (PyMOL's uppercase `ID`).
        name: The atom name.
        alt: The alternate location indicator, or "" when not altloc-bearing.
        resn: The residue name.
        chain: The chain identifier.
        resv: The integer residue number, with any insertion code excluded.
        ins_code: The insertion code, or "" when absent.
        elem: The element symbol.
        hetatm: Whether PyMOL classifies this atom as HETATM.
        q: The occupancy.
        b: The temperature factor.
        color: The PyMOL color index.
        reps: The names of every representation this atom is shown in.
        label: The atom label text, or None when it is not labeled.
        coord: The (x, y, z) coordinate for this state.
    """

    serial: int
    name: str
    alt: str
    resn: str
    chain: str
    resv: int
    ins_code: str
    elem: str
    hetatm: bool
    q: float
    b: float
    color: int
    reps: tuple[str, ...]
    label: str | None
    coord: tuple[float, float, float]


@dataclass(frozen=True)
class BondRecord:
    """One bond between two atoms, addressed by their position in a state.

    Attributes:
        atom_index_a: The zero-based position of the bond's first atom.
        atom_index_b: The zero-based position of the bond's second atom.
        order: The bond order.
    """

    atom_index_a: int
    atom_index_b: int
    order: int


@dataclass(frozen=True)
class StateSnapshot:
    """The atoms present in one coordinate state.

    Attributes:
        atoms: The atoms in this state, in a fixed, comparable order.
    """

    atoms: tuple[AtomRecord, ...]


@dataclass(frozen=True)
class ObjectSnapshot:
    """A canonical structured snapshot of one live PyMOL object.

    Attributes:
        schema_version: Candidate A's private schema version; not a production
            StructureSnapshotV1 contract.
        name: The object's name.
        enabled: Whether the object is enabled in the PyMOL session.
        states: Every coordinate state, in order.
        bonds: Every bond, addressed by first-state atom position.
        view: The camera view, as `cmd.get_view()` returns it.
        settings: The (setting name, value) pairs this candidate tracks.
    """

    schema_version: int
    name: str
    enabled: bool
    states: tuple[StateSnapshot, ...]
    bonds: tuple[BondRecord, ...]
    view: tuple[float, ...]
    settings: tuple[tuple[str, str], ...]


def extract(cmd: Any, object_name: str) -> ObjectSnapshot:
    """Extract a canonical structured snapshot of one live PyMOL object.

    Args:
        cmd: The real PyMOL cmd module.
        object_name: Name of the loaded object to extract.

    Returns:
        The extracted canonical snapshot.
    """
    n_states = cmd.count_states(object_name)
    states: list[StateSnapshot] = []
    for state in range(1, n_states + 1):
        model = cmd.get_model(object_name, state=state)
        colors: list[int] = []
        labels: list[str | None] = []
        cmd.iterate(
            object_name,
            "colors.append(color); labels.append(label)",
            space={"colors": colors, "labels": labels},
        )
        # Per-atom membership in each named representation, keyed by ID
        # (stable regardless of atom-array order) rather than position.
        reps_by_id: dict[int, list[str]] = {}
        for rep_name in REP_NAMES:
            ids: list[int] = []
            cmd.iterate(
                f"{object_name} and rep {rep_name}",
                "ids.append(ID)",
                space={"ids": ids},
            )
            for atom_id in ids:
                reps_by_id.setdefault(atom_id, []).append(rep_name)

        atoms: list[AtomRecord] = []
        for index, atom in enumerate(model.atom):
            atoms.append(
                AtomRecord(
                    serial=atom.id,
                    name=atom.name,
                    alt=atom.alt,
                    resn=atom.resn,
                    chain=atom.chain,
                    resv=atom.resi_number,
                    ins_code=atom.ins_code,
                    elem=atom.symbol,
                    hetatm=bool(atom.hetatm),
                    q=atom.q,
                    b=atom.b,
                    color=colors[index],
                    reps=tuple(reps_by_id.get(atom.id, [])),
                    label=labels[index] or None,
                    coord=tuple(atom.coord),
                )
            )
        states.append(StateSnapshot(atoms=tuple(atoms)))

    model = cmd.get_model(object_name, state=1)
    bonds = tuple(
        BondRecord(
            atom_index_a=bond.index[0],
            atom_index_b=bond.index[1],
            order=bond.order,
        )
        for bond in model.bond
    )
    view = tuple(cmd.get_view())
    settings = tuple(
        (setting, cmd.get(setting, object_name)) for setting in SAFE_SETTINGS
    )

    return ObjectSnapshot(
        schema_version=CANDIDATE_A_SCHEMA_VERSION,
        name=object_name,
        enabled=object_name in cmd.get_names("objects", enabled_only=1),
        states=tuple(states),
        bonds=bonds,
        view=view,
        settings=settings,
    )


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


def to_json(snapshot: ObjectSnapshot) -> str:
    """Serialize a canonical snapshot to JSON for cross-process comparison.

    Args:
        snapshot: The snapshot to serialize.

    Returns:
        The compact JSON text.
    """
    return json.dumps(asdict(snapshot))


def _atom_record_from_json(data: dict[str, Any]) -> AtomRecord:
    """Deserialize one atom record from its JSON object.

    Args:
        data: The JSON object for one atom, as to_json wrote it.

    Returns:
        The reconstructed AtomRecord.
    """
    return AtomRecord(
        serial=data["serial"],
        name=data["name"],
        alt=data["alt"],
        resn=data["resn"],
        chain=data["chain"],
        resv=data["resv"],
        ins_code=data["ins_code"],
        elem=data["elem"],
        hetatm=data["hetatm"],
        q=data["q"],
        b=data["b"],
        color=data["color"],
        reps=tuple(data["reps"]),
        label=data["label"],
        coord=tuple(data["coord"]),
    )


def from_json(text: str) -> ObjectSnapshot:
    """Deserialize a canonical snapshot from JSON.

    Args:
        text: JSON text produced by to_json.

    Returns:
        The reconstructed ObjectSnapshot dataclass tree.
    """
    data = json.loads(text)
    if data.get("schema_version") != CANDIDATE_A_SCHEMA_VERSION:
        raise ValueError(
            "unsupported candidate-A schema version: "
            f"{data.get('schema_version')!r}; "
            f"expected {CANDIDATE_A_SCHEMA_VERSION}"
        )
    return ObjectSnapshot(
        schema_version=data["schema_version"],
        name=data["name"],
        enabled=data["enabled"],
        states=tuple(
            StateSnapshot(
                atoms=tuple(_atom_record_from_json(a) for a in state["atoms"])
            )
            for state in data["states"]
        ),
        bonds=tuple(
            BondRecord(
                atom_index_a=b["atom_index_a"],
                atom_index_b=b["atom_index_b"],
                order=b["order"],
            )
            for b in data["bonds"]
        ),
        view=tuple(data["view"]),
        settings=tuple((s, v) for s, v in data["settings"]),
    )


def _diff(expected: ObjectSnapshot, actual: ObjectSnapshot) -> list[str]:
    """Compare two snapshots field by field.

    Args:
        expected: The snapshot taken before reconstruction.
        actual: The snapshot re-extracted after reconstruction.

    Returns:
        A human-readable mismatch for every field that differs; empty when
        the snapshots match exactly.
    """
    mismatches: list[str] = []

    if expected.schema_version != actual.schema_version:
        mismatches.append(
            "schema_version expected="
            f"{expected.schema_version!r} actual={actual.schema_version!r}"
        )
    if expected.name != actual.name:
        mismatches.append(
            f"object.name expected={expected.name!r} actual={actual.name!r}"
        )
    if expected.enabled != actual.enabled:
        mismatches.append(
            f"object.enabled expected={expected.enabled!r} "
            f"actual={actual.enabled!r}"
        )

    def compare_atom(
        label: str, exp_atom: AtomRecord, act_atom: AtomRecord
    ) -> None:
        for field in dataclasses.fields(AtomRecord):
            e = getattr(exp_atom, field.name)
            a = getattr(act_atom, field.name)
            if field.name == "coord":
                if not all(
                    abs(x - y) < 1e-3 for x, y in zip(e, a, strict=True)
                ):
                    mismatches.append(f"{label}.coord expected={e} actual={a}")
                continue
            if e != a:
                mismatches.append(
                    f"{label}.{field.name} expected={e!r} actual={a!r}"
                )

    if len(expected.states) != len(actual.states):
        mismatches.append(
            f"n_states expected={len(expected.states)} "
            f"actual={len(actual.states)}"
        )
    else:
        for s_idx, (exp_state, act_state) in enumerate(
            zip(expected.states, actual.states, strict=True)
        ):
            if len(exp_state.atoms) != len(act_state.atoms):
                mismatches.append(
                    f"state{s_idx}.n_atoms expected={len(exp_state.atoms)} "
                    f"actual={len(act_state.atoms)}"
                )
                continue
            for a_idx, (exp_atom, act_atom) in enumerate(
                zip(exp_state.atoms, act_state.atoms, strict=True)
            ):
                compare_atom(f"state{s_idx}.atom{a_idx}", exp_atom, act_atom)

    expected_bonds = sorted(
        (b.atom_index_a, b.atom_index_b, b.order) for b in expected.bonds
    )
    actual_bonds = sorted(
        (b.atom_index_a, b.atom_index_b, b.order) for b in actual.bonds
    )
    if expected_bonds != actual_bonds:
        mismatches.append(
            f"bonds expected={expected_bonds} actual={actual_bonds}"
        )

    if not all(
        abs(x - y) < 1e-3
        for x, y in zip(expected.view, actual.view, strict=True)
    ):
        mismatches.append(f"view expected={expected.view} actual={actual.view}")

    if expected.settings != actual.settings:
        mismatches.append(
            f"settings expected={expected.settings} actual={actual.settings}"
        )

    return mismatches


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[Any]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL cmd module.
    """
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


@pytest.fixture
def loaded_fixture(real_pymol: Any) -> Iterator[Any]:
    """Load the full-V1 discovery fixture fresh for one test and delete it.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module with the fixture object loaded.
    """
    real_pymol.load(str(FIXTURE_PATH), "fx")
    real_pymol.color("red", "fx and chain A")
    real_pymol.show("sticks", "fx")
    real_pymol.show("spheres", "fx and resn ZN")
    real_pymol.label("fx and name CA", "name")
    real_pymol.set_view(
        (
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
    )
    real_pymol.set("sphere_scale", "0.35", "fx")
    real_pymol.set("cartoon_transparency", "0.25", "fx")
    real_pymol.disable("fx")
    real_pymol.sync()
    try:
        yield real_pymol
    finally:
        real_pymol.delete("fx")


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

    assert snapshot.schema_version == CANDIDATE_A_SCHEMA_VERSION
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
    """Candidate A rejects JSON from an unknown private schema version."""
    payload = json.loads(to_json(extract(loaded_fixture, "fx")))
    payload["schema_version"] = CANDIDATE_A_SCHEMA_VERSION + 1

    with pytest.raises(
        ValueError, match="unsupported candidate-A schema version"
    ):
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
        schema_version=CANDIDATE_A_SCHEMA_VERSION + 1,
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

    environment = os.environ.copy()
    environment[SNAPSHOT_ENV_VAR] = str(snapshot_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(__file__),
            "-k",
            "test_reconstruct_from_env_snapshot_matches_original",
            "-q",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
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
