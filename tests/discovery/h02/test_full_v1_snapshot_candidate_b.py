# Copyright 2026 PyMOL Copilot contributors.
"""H-02 discovery: candidate B (standard export + manifest) differential.

Candidate B exports the loaded fixture with `cmd.save(..., format="pdb")`
-- a standard, portable, hand-inspectable molecular file format -- and
pairs it with an explicit JSON manifest carrying everything a plain PDB
file cannot: per-atom color/representation, camera view, `SAFE_SETTINGS`,
labels, and bonds. Reconstruction in a genuinely fresh second process
loads only the exported `.pdb` and manifest paths (never the source
fixture file), applies the manifest to the freshly loaded structure, then
re-extracts with the shared `extract()` from harness.py and diffs against
the original extraction with the shared `_diff()`.

Real, empirically confirmed facts this candidate depends on, each of which
cost a probe to discover:

- `cmd.save(path, object_name, state=0, format="pdb")` writes every
  coordinate state as its own MODEL/ENDMDL block; the default `state=-1`
  (current state only) silently drops every state but one, so `state=0`
  is required to preserve the fixture's second MODEL.
- PyMOL's PDB writer emits **zero** CONECT records for this fixture
  (confirmed empirically: the exported file contains no "CONECT"
  substring at all), even though every bond in the fixture is a plain
  single bond between adjacent, geometrically bonded atoms. This
  candidate's manifest therefore records bonds explicitly rather than
  relying on CONECT, exactly as H-02 anticipated.
- Despite writing no CONECT records, reloading the plain PDB in a fresh
  process still reports the fixture's original 15 bonds with the
  original bond orders (confirmed empirically) -- but only because
  PyMOL's PDB loader independently *re-perceives* a bond graph from
  interatomic geometry by default, not because the file itself encodes
  those bonds. That auto-perceived graph would silently mask a broken or
  missing manifest bond list in this fixture's case (every bond order
  happens to be 1, and every bonded pair happens to be close enough to
  re-perceive). `apply_manifest()` below therefore calls `cmd.unbond()`
  to strip PyMOL's own guess before adding back only the manifest's
  explicit bonds, so this candidate's round trip actually exercises its
  own bond-recording mechanism rather than coasting on a coincidence.
- A plain atom-identity selection -- `chain "<chain>" and resi
  "<resi>" and resn "<resn>" and name "<name>" and alt "<alt>"` --
  addresses exactly one atom for every atom in this fixture (confirmed
  empirically), including the insertion-code residue (`resi "3A"`) and
  both members of the altloc pair (`alt "A"`/`alt "B"`). The manifest
  therefore keys per-atom display state by this identity tuple rather
  than by a reconstruction-time positional index, unlike candidate A's
  `segi` tag trick -- atom order was also observed to survive this
  fixture's PDB round trip unchanged, but the identity key does not
  depend on that holding in general.
- A plain PDB export/reload does not preserve every atom's original
  serial number (confirmed empirically: the hetero ZN atom's serial is
  13 in the original loaded fixture but reloads as 10, shifting this
  fixture's chain-B atoms from 10-12 to 11-13) -- `cmd.save(...,
  format="pdb")` renumbers serials sequentially by write order rather
  than preserving each atom's original value. The manifest therefore
  also carries each atom's original serial by identity, alongside color/
  reps/label, and `apply_manifest()` restores it with `cmd.alter(sel,
  f"ID={serial}")` (PyMOL's atom-serial attribute is the uppercase `ID`
  field, same as candidate A's own finding above it).
- Exporting a measurement object through `cmd.save(..., format="pdb")`
  fails outright with the same "Invalid selection name" error candidate
  A's negative-result test already found for atom-based queries --
  a measurement object is not a selectable set of atoms by either path,
  so no standard export format can carry one either. See
  test_measurement_objects_are_not_recoverable_via_pdb_export below.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from harness import REP_NAMES
from harness import SAFE_SETTINGS
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

CANDIDATE_B_MANIFEST_SCHEMA_VERSION = 1
PDB_PATH_ENV_VAR = "H02_CANDIDATE_B_PDB_PATH"
MANIFEST_PATH_ENV_VAR = "H02_CANDIDATE_B_MANIFEST_JSON"
SNAPSHOT_ENV_VAR = "H02_CANDIDATE_B_SNAPSHOT_JSON"


@dataclass(frozen=True)
class ManifestAtomEntry:
    """One atom's display state that a plain PDB file cannot carry.

    Attributes:
        chain: Chain identifier, matching the exported PDB atom.
        resi: The folded residue-number/insertion-code string (e.g. "3A").
        resn: Residue name.
        name: Atom name.
        alt: Alternate location indicator, or "" when absent.
        serial: The atom's original PyMOL ID (serial number). A plain PDB
            export/reload does not reliably preserve it (see the module
            docstring's empirical finding), so the manifest carries it
            explicitly and apply_manifest() restores it after reload.
        color: The PyMOL color index.
        reps: The names of every representation this atom is shown in.
        label: The atom label text, or None when unlabeled.
    """

    chain: str
    resi: str
    resn: str
    name: str
    alt: str
    serial: int
    color: int
    reps: tuple[str, ...]
    label: str | None


@dataclass(frozen=True)
class ManifestBondEntry:
    """One explicit bond, addressed by each endpoint atom's identity.

    Attributes:
        atom_a: The (chain, resi, resn, name, alt) identity of the first
            bonded atom.
        atom_b: The (chain, resi, resn, name, alt) identity of the second
            bonded atom.
        order: The bond order.
    """

    atom_a: tuple[str, str, str, str, str]
    atom_b: tuple[str, str, str, str, str]
    order: int


@dataclass(frozen=True)
class CandidateBManifest:
    """Everything a plain PDB file cannot carry for candidate B.

    Attributes:
        schema_version: This manifest format's own private schema version;
            independent of harness.SNAPSHOT_SCHEMA_VERSION and of any other
            candidate's manifest/export format version.
        name: The object name the reconstructed structure is loaded under.
        enabled: Whether the object was enabled in the original session.
        view: The camera view, as `cmd.get_view()` returns it.
        settings: The (setting name, value) pairs this candidate tracks.
        atoms: Per-atom color/representation/label state, keyed by identity.
        bonds: Every explicit bond, addressed by endpoint atom identity.
    """

    schema_version: int
    name: str
    enabled: bool
    view: tuple[float, ...]
    settings: tuple[tuple[str, str], ...]
    atoms: tuple[ManifestAtomEntry, ...]
    bonds: tuple[ManifestBondEntry, ...]


def _atom_selection(
    object_name: str, chain: str, resi: str, resn: str, name: str, alt: str
) -> str:
    """Build a selection expression addressing exactly one atom by identity.

    Args:
        object_name: The loaded object's name.
        chain: Chain identifier.
        resi: Folded residue-number/insertion-code string (e.g. "3A").
        resn: Residue name.
        name: Atom name.
        alt: Alternate location indicator, or "" for none.

    Returns:
        A PyMOL selection expression matching exactly that one atom.
    """
    return (
        f'{object_name} and chain "{chain}" and resi "{resi}" '
        f'and resn "{resn}" and name "{name}" and alt "{alt}"'
    )


def build_manifest(cmd: Any, object_name: str) -> CandidateBManifest:
    """Capture everything a plain PDB export of this object cannot carry.

    Args:
        cmd: The real PyMOL cmd module.
        object_name: Name of the loaded object to build a manifest for.

    Returns:
        The manifest to pair with a `cmd.save(..., format="pdb")` export.
    """
    colors: list[int] = []
    labels: list[str | None] = []
    cmd.iterate(
        object_name,
        "colors.append(color); labels.append(label)",
        space={"colors": colors, "labels": labels},
    )
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

    model = cmd.get_model(object_name, state=1)
    atoms: list[ManifestAtomEntry] = []
    identity_by_index: list[tuple[str, str, str, str, str]] = []
    for index, atom in enumerate(model.atom):
        identity = (atom.chain, atom.resi, atom.resn, atom.name, atom.alt)
        identity_by_index.append(identity)
        atoms.append(
            ManifestAtomEntry(
                chain=identity[0],
                resi=identity[1],
                resn=identity[2],
                name=identity[3],
                alt=identity[4],
                serial=atom.id,
                color=colors[index],
                reps=tuple(reps_by_id.get(atom.id, [])),
                label=labels[index] or None,
            )
        )

    bonds = tuple(
        ManifestBondEntry(
            atom_a=identity_by_index[bond.index[0]],
            atom_b=identity_by_index[bond.index[1]],
            order=bond.order,
        )
        for bond in model.bond
    )
    view = tuple(cmd.get_view())
    settings = tuple(
        (setting, cmd.get(setting, object_name)) for setting in SAFE_SETTINGS
    )

    return CandidateBManifest(
        schema_version=CANDIDATE_B_MANIFEST_SCHEMA_VERSION,
        name=object_name,
        enabled=object_name in cmd.get_names("objects", enabled_only=1),
        view=view,
        settings=settings,
        atoms=tuple(atoms),
        bonds=bonds,
    )


def manifest_to_json(manifest: CandidateBManifest) -> str:
    """Serialize a manifest to JSON for cross-process transfer.

    Args:
        manifest: The manifest to serialize.

    Returns:
        The compact JSON text.
    """
    return json.dumps(asdict(manifest))


def manifest_from_json(text: str) -> CandidateBManifest:
    """Deserialize a manifest from JSON.

    Args:
        text: JSON text produced by manifest_to_json.

    Returns:
        The reconstructed CandidateBManifest dataclass tree.

    Raises:
        ValueError: If the JSON's schema_version does not match this
            candidate's CANDIDATE_B_MANIFEST_SCHEMA_VERSION.
    """
    data = json.loads(text)
    if data.get("schema_version") != CANDIDATE_B_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "unsupported candidate-B manifest schema version: "
            f"{data.get('schema_version')!r}; "
            f"expected {CANDIDATE_B_MANIFEST_SCHEMA_VERSION}"
        )
    return CandidateBManifest(
        schema_version=data["schema_version"],
        name=data["name"],
        enabled=data["enabled"],
        view=tuple(data["view"]),
        settings=tuple((s, v) for s, v in data["settings"]),
        atoms=tuple(
            ManifestAtomEntry(
                chain=a["chain"],
                resi=a["resi"],
                resn=a["resn"],
                name=a["name"],
                alt=a["alt"],
                serial=a["serial"],
                color=a["color"],
                reps=tuple(a["reps"]),
                label=a["label"],
            )
            for a in data["atoms"]
        ),
        bonds=tuple(
            ManifestBondEntry(
                atom_a=tuple(b["atom_a"]),
                atom_b=tuple(b["atom_b"]),
                order=b["order"],
            )
            for b in data["bonds"]
        ),
    )


def apply_manifest(cmd: Any, manifest: CandidateBManifest) -> None:
    """Apply everything a plain PDB load could not carry to a loaded object.

    Args:
        cmd: The real PyMOL cmd module, with `manifest.name` already
            loaded from the paired PDB export.
        manifest: The manifest exported alongside that PDB file.
    """
    name = manifest.name

    # Strip PyMOL's own geometry-based bond guess first (see the module
    # docstring's empirical finding) so re-adding the manifest's bonds
    # actually exercises this candidate's explicit bond recording.
    cmd.unbond(name, name)
    cmd.sync()

    for entry in manifest.atoms:
        sel = _atom_selection(
            name, entry.chain, entry.resi, entry.resn, entry.name, entry.alt
        )
        # Restore the original serial the PDB export/reload did not
        # reliably preserve (see the module docstring's empirical
        # finding); the identity selection above never depends on this
        # value, so restoring it here is safe regardless of what
        # serial cmd.load assigned on reload.
        cmd.alter(sel, f"ID={entry.serial}")
        cmd.color(str(entry.color), sel)
        cmd.hide("everything", sel)
        for rep_name in entry.reps:
            cmd.show(rep_name, sel)
        if entry.label is not None:
            cmd.label(sel, repr(entry.label))
    cmd.sync()

    for bond in manifest.bonds:
        cmd.bond(
            _atom_selection(name, *bond.atom_a),
            _atom_selection(name, *bond.atom_b),
            order=bond.order,
        )
    cmd.sync()

    cmd.set_view(manifest.view)
    for setting_name, value in manifest.settings:
        cmd.set(setting_name, value, name)
    if manifest.enabled:
        cmd.enable(name)
    else:
        cmd.disable(name)
    cmd.sync()


def test_manifest_captures_display_state_a_plain_pdb_cannot(
    loaded_fixture: Any,
) -> None:
    """The manifest independently records what a plain PDB export drops."""
    manifest = build_manifest(loaded_fixture, "fx")

    assert manifest.schema_version == CANDIDATE_B_MANIFEST_SCHEMA_VERSION
    assert manifest.name == "fx"
    assert manifest.enabled is False
    ca = next(
        a
        for a in manifest.atoms
        if (a.chain, a.resi, a.name, a.alt) == ("A", "1", "CA", "")
    )
    zinc = next(
        a
        for a in manifest.atoms
        if (a.chain, a.resi, a.name, a.alt) == ("A", "101", "ZN", "")
    )
    assert ca.color == loaded_fixture.get_color_index("red")
    assert ca.label == "CA"
    assert "sticks" in ca.reps
    assert ca.serial == 2
    assert "spheres" in zinc.reps
    assert zinc.serial == 13
    assert manifest.settings == (
        ("sphere_scale", "0.35000"),
        ("cartoon_transparency", "0.25000"),
    )
    assert len(manifest.bonds) == 15


def test_pdb_export_does_not_emit_conect_records_for_this_fixture(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Empirical finding: PyMOL's PDB writer omits CONECT for this fixture.

    Recorded explicitly rather than assumed, per H-02's requirement to
    check this empirically: this candidate's manifest carries bonds
    itself precisely because CONECT is not available to fall back on.
    """
    pdb_path = tmp_path / "fx_export.pdb"
    loaded_fixture.save(str(pdb_path), "fx", state=0, format="pdb")
    loaded_fixture.sync()

    pdb_text = pdb_path.read_text()

    assert "CONECT" not in pdb_text
    assert pdb_text.count("MODEL") == 2


def test_measurement_objects_are_not_recoverable_via_pdb_export(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Negative result: a plain PDB export cannot carry a measurement object.

    Mirrors candidate A's own negative-result test: a measurement object
    is not a selectable set of atoms via any query API, so `cmd.save`
    cannot export one to any standard structure format either. Confirmed
    empirically that `cmd.save` fails differently than the `count_atoms`
    call candidate A's own negative test exercises: it raises
    `pymol.parsing.QuietException` with an *empty* message (the "Invalid
    selection name" diagnostic only reaches PyMOL's own stdout, not the
    Python exception), rather than `pymol.CmdException` carrying that text
    -- so this test only asserts that saving fails, not on message text.

    Args:
        loaded_fixture: The real PyMOL cmd module with the fixture loaded.
        tmp_path: A pytest-provided temporary directory.
    """
    loaded_fixture.distance(
        "d1",
        "fx and chain A and resi 1 and name CA",
        "fx and chain A and resi 2 and name CA",
    )
    loaded_fixture.sync()

    assert loaded_fixture.get_type("d1") == "object:measurement"
    with pytest.raises(Exception):  # noqa: B017
        loaded_fixture.save(str(tmp_path / "d1.pdb"), "d1", format="pdb")


def test_candidate_b_round_trips_through_a_fresh_process(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Candidate B reconstructs via PDB+manifest in a fresh process.

    Extracts the loaded fixture's canonical snapshot and builds its
    manifest in this process, exports the PDB, then spawns a genuinely
    fresh nested pytest process -- one that launches its own real PyMOL
    and never opens h02_full_v1_fixture.pdb -- to load the exported PDB,
    apply the manifest, and diff the result against the original
    extraction.

    Args:
        loaded_fixture: The real PyMOL cmd module with the fixture loaded.
        tmp_path: A pytest-provided temporary directory for the exported
            files.

    Raises:
        AssertionError: If reconstruction was not faithful, with every
            field-level mismatch the nested process reported.
    """
    original = extract(loaded_fixture, "fx")
    manifest = build_manifest(loaded_fixture, "fx")

    pdb_path = tmp_path / "fx_export.pdb"
    loaded_fixture.save(str(pdb_path), "fx", state=0, format="pdb")
    loaded_fixture.sync()

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest_to_json(manifest))
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(to_json(original))

    result = run_nested_snapshot_process(
        __file__,
        "test_reconstruct_from_env_pdb_and_manifest_matches_original",
        {
            PDB_PATH_ENV_VAR: str(pdb_path),
            MANIFEST_PATH_ENV_VAR: str(manifest_path),
            SNAPSHOT_ENV_VAR: str(snapshot_path),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_reconstruct_from_env_pdb_and_manifest_matches_original() -> None:
    """Reconstruct from an externally supplied PDB+manifest and diff it.

    Only meaningful when invoked as the nested subprocess spawned by
    test_candidate_b_round_trips_through_a_fresh_process, which sets
    PDB_PATH_ENV_VAR, MANIFEST_PATH_ENV_VAR, and SNAPSHOT_ENV_VAR. Skips
    when run any other way, since it has nothing to reconstruct from and
    no assertion to make.

    Raises:
        AssertionError: If the re-extracted snapshot differs from the
            original in any recorded field.
    """
    pdb_path = os.environ.get(PDB_PATH_ENV_VAR)
    manifest_path = os.environ.get(MANIFEST_PATH_ENV_VAR)
    snapshot_path = os.environ.get(SNAPSHOT_ENV_VAR)
    if not (pdb_path and manifest_path and snapshot_path):
        pytest.skip(
            f"{PDB_PATH_ENV_VAR}/{MANIFEST_PATH_ENV_VAR}/{SNAPSHOT_ENV_VAR} "
            "not set; not the nested invocation"
        )

    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        original = from_json(Path(snapshot_path).read_text())
        manifest = manifest_from_json(Path(manifest_path).read_text())

        cmd.load(pdb_path, manifest.name)
        cmd.sync()
        apply_manifest(cmd, manifest)

        reconstructed = extract(cmd, manifest.name)
        mismatches = _diff(original, reconstructed)
        assert not mismatches, "\n".join(mismatches)
    finally:
        cmd.do("quit")


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (the same defect documented and
    # fixed the same way in tests/integration/test_real_pymol_command.py
    # and candidate A's own __main__ block). os._exit bypasses that
    # interpreter-shutdown window entirely, so pytest's real result is what
    # Bazel actually sees. os._exit skips the normal stdio flush, so flush
    # explicitly first -- otherwise a real failure's traceback and summary
    # can be silently lost from the captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
