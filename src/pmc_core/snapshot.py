# Copyright 2026 PyMOL Copilot contributors.
"""Canonical PyMOL object snapshots: extract, serialize, digest, rebuild.

This is the production promotion of H-02's differential discovery work
(originally `tests/discovery/h02/harness.py` plus candidate A's own
`reconstruct()`). Candidate A -- extraction and reconstruction entirely
through PyMOL's ordinary object-construction API (`get_model`/`iterate` for
reads; `pseudoatom`/`bond`/`alter`/`alter_state`/`color`/`show`/`hide`/
`set`/`set_view` for writes) -- was the chosen approach after a three-way
comparison against a PDB-plus-manifest candidate and PyMOL's own session
serialization; that comparison is not revisited here.

`extract()` and `reconstruct()` take the live PyMOL `cmd` module as an
untyped parameter and never import `pymol` themselves, so this module has
no PyMOL dependency and no dependency on the Windows short-path staging
shim (`tools/winstage`). Both stay confined to test code, which is the only
code that actually launches a PyMOL process.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import hashlib
import json
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

#: This module's own snapshot schema version. A snapshot whose
#: `schema_version` field does not match this constant is rejected by
#: from_json rather than partially decoded.
SNAPSHOT_VERSION = 1

#: PyMOL's named representations, in the order membership is queried --
#: there is no documented Python-level bit layout for the raw per-atom
#: `reps` integer, so extraction records membership by name instead.
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

#: The bounded set of "safe" display settings this module tracks at object
#: scope. This proves the get/set/reconstruct path for a representative
#: non-view, non-atom-level setting; it is not a claim that every PyMOL
#: setting is covered.
SAFE_SETTINGS = ("sphere_scale", "cartoon_transparency")

#: The declared-unsupported set every snapshot carries as an explicit
#: marker, never a silent drop. Every `ObjectSnapshot` this module produces
#: carries exactly this tuple; extraction never scans a session to decide
#: whether either case is actually present.
#:
#: - Measurement objects (`cmd.distance` and siblings): `cmd.get_session`
#:   is the only introspection path found that exposes a measurement
#:   object's defining data, and it returns a raw baked-in coordinate/color
#:   array rather than a live reference to the atoms it measures --
#:   structurally PyMOL's own session-serialization mechanism, not
#:   something an ordinary query API (`iterate`/`get_model`) read can
#:   reuse. `get_model`/`iterate`, this module's only extraction APIs, do
#:   not recognize a measurement object as a selectable set of atoms at
#:   all; PyMOL raises rather than returning an empty selection.
#: - The explicit polymer selection-language flag: covering it is deferred
#:   to the command language's own contract-freeze checkpoint, not decided
#:   by this snapshot format.
DECLARED_UNSUPPORTED = (
    "unsupported state=measurement-objects route=plan-report",
    "unsupported state=explicit-polymer-classification route=contract-freeze",
)


class SnapshotDecodeError(ValueError):
    """Raised when a snapshot value does not match its declared version."""


@dataclass(frozen=True)
class AtomRecord:
    """One atom's full-V1 relevant state, as this module represents it.

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
        schema_version: This module's SNAPSHOT_VERSION at extraction time.
        name: The object's name.
        enabled: Whether the object is enabled in the PyMOL session.
        states: Every coordinate state, in order.
        bonds: Every bond, addressed by first-state atom position.
        view: The camera view, as `cmd.get_view()` returns it.
        settings: The (setting name, value) pairs this module tracks.
        unsupported: The declared-unsupported set this snapshot format does
            not cover (DECLARED_UNSUPPORTED, always -- see its own
            docstring). Present as an explicit marker on every snapshot,
            never a silent drop.
    """

    schema_version: int
    name: str
    enabled: bool
    states: tuple[StateSnapshot, ...]
    bonds: tuple[BondRecord, ...]
    view: tuple[float, ...]
    settings: tuple[tuple[str, str], ...]
    unsupported: tuple[str, ...]


def extract(cmd: Any, object_name: str) -> ObjectSnapshot:
    """Extract a canonical structured snapshot of one live PyMOL object.

    Reads live PyMOL state only through ordinary query APIs (`iterate`/
    `get_model`/`get_view`/`get`), regardless of how that live state was
    built.

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
        schema_version=SNAPSHOT_VERSION,
        name=object_name,
        enabled=object_name in cmd.get_names("objects", enabled_only=1),
        states=tuple(states),
        bonds=bonds,
        view=view,
        settings=settings,
        unsupported=DECLARED_UNSUPPORTED,
    )


def reconstruct(cmd: Any, snapshot: ObjectSnapshot) -> None:
    """Rebuild a live PyMOL object from a canonical structured snapshot.

    Uses only PyMOL's object-construction API (`pseudoatom`/`bond`/`alter`/
    `alter_state`/`color`/`show`/`hide`/`set`/`set_view`) -- never a
    molecular file format and never session serialization.

    Real, empirically confirmed API facts this reconstruction depends on,
    each of which cost a wrong first attempt to discover:

    - `cmd.load_coords` shares the same NumPy 2.x ABI break already
      documented for `cmd.get_coords` in
      tests/integration/test_real_pymol_command.py -- the pinned
      pymol-open-source-whl==3.2.0.2 build's compiled `_cmd` extension
      cannot call into a NumPy-2.x-linked coordinate array. `cmd.alter_state`'s
      per-atom Python expression avoids NumPy entirely and is used here for
      every multi-state coordinate write.
    - The per-atom serial number lives in the iterate/alter namespace as
      uppercase `ID`; lowercase `id` is a different name that `cmd.alter`
      accepts syntactically but never applies.
    - An insertion code has no independent alter()-able property. PyMOL
      only derives it by parsing an icode suffix out of `resi` (e.g.
      `"3A"`), the same folded string `get_model().atom[i].resi` already
      returns -- so reconstruction must fold resv+ins_code back into that
      one string at creation time rather than trying to set ins_code
      separately afterward.
    - `pseudoatom` silently renames an atom on a same-residue
      (chain, resi, resn, name) collision at creation time, regardless of
      alt -- both atoms still have alt='' at their own creation moment.
      `name` is an ordinary alterable property, so the practical fix is to
      always set every atom's true name back explicitly after creation
      rather than try to avoid the collision.
    - Addressing an atom by `index N` is not stable across the rest of one
      reconstruct() run: a later pseudoatom() call can silently reassign
      what `index N` points to for an earlier atom (confirmed empirically
      -- a same-residue altloc pair's name, alt, q, and coordinates ended
      up swapped across two positions after only later atoms were added,
      with no edit ever addressed at the earlier position by number). A
      stable per-atom tag -- this function uses the otherwise-unused
      `segi` field -- makes every post-creation edit safe regardless of
      internal reordering.
    - The per-atom `reps` integer has no documented Python-level bit
      layout. Querying membership by name through the `rep <name>`
      selection keyword (REP_NAMES) is the robust, stable alternative.

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
    """Serialize a canonical snapshot to deterministic JSON.

    Keys are sorted and separators are fixed, so two structurally equal
    snapshots always serialize to byte-identical text regardless of field
    construction order or interpreter hash-seed. NaN/Infinity coordinates
    are rejected rather than silently emitted as non-round-trippable JSON.

    Args:
        snapshot: The snapshot to serialize.

    Returns:
        The deterministic, compact JSON text.

    Raises:
        ValueError: If any float field is NaN or infinite.
    """
    return json.dumps(
        asdict(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


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

    Raises:
        SnapshotDecodeError: If the JSON's schema_version does not match
            SNAPSHOT_VERSION, or its declared-unsupported set does not
            match DECLARED_UNSUPPORTED -- a snapshot claiming to cover
            what this module declares unsupported is not one this module
            can decode.
    """
    data = json.loads(text)
    if data.get("schema_version") != SNAPSHOT_VERSION:
        raise SnapshotDecodeError(
            "unsupported snapshot schema version: "
            f"{data.get('schema_version')!r}; "
            f"expected {SNAPSHOT_VERSION}"
        )
    unsupported = tuple(data.get("unsupported", ()))
    if unsupported != DECLARED_UNSUPPORTED:
        raise SnapshotDecodeError(
            "snapshot declares an unsupported set this module does not "
            f"recognize: {unsupported!r}; expected {DECLARED_UNSUPPORTED!r}"
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
        unsupported=unsupported,
    )


def structure_digest(snapshot: ObjectSnapshot) -> str:
    """Compute a stable digest over a snapshot's structural fields only.

    Covers `schema_version`, `name`, `states`, `bonds`, and `unsupported`.
    Deliberately excludes `view`, `settings`, and `enabled`: those are
    object-level display/visibility state, not structure, and the command
    language's only camera-affecting verb (`orient`) or a display-setting
    change must never invalidate a plan bound to this digest. A per-atom
    `color`/`show`/`hide`/label change *is* structural under that same
    rule, since those verbs mutate AtomRecord fields this digest covers.

    Args:
        snapshot: The snapshot to digest.

    Returns:
        The digest as "sha256:<hex>", matching this repository's
        snapshotDigest wire convention (see pmc_core.protocol).

    Raises:
        ValueError: If any float field is NaN or infinite.
    """
    excluded = {"view", "settings", "enabled"}
    payload = {
        key: value
        for key, value in asdict(snapshot).items()
        if key not in excluded
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def diff(expected: ObjectSnapshot, actual: ObjectSnapshot) -> list[str]:
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
    if expected.unsupported != actual.unsupported:
        mismatches.append(
            "object.unsupported expected="
            f"{expected.unsupported!r} actual={actual.unsupported!r}"
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
