# Copyright 2026 PyMOL Copilot contributors.
"""Candidate-private deterministic card renderer for H-02 ObjectSnapshot.

This is discovery evidence only. It does not select H-02's serialization or
define a production structure-card contract.
"""

from __future__ import annotations

import json
import math

from harness import AtomRecord
from harness import BondRecord
from harness import ObjectSnapshot
from harness import StateSnapshot

CARD_VERSION = "candidate-1"


def _text(value: str) -> str:
    """Return an ASCII-stable quoted string."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _number(value: float | int) -> str:
    """Return one locale-independent normalized number."""
    return format(value, ".6f").rstrip("0").rstrip(".") or "0"


def _atom_key(atom: AtomRecord) -> tuple[object, ...]:
    return (
        atom.chain,
        atom.resv,
        atom.ins_code,
        atom.resn,
        atom.name,
        atom.alt,
        atom.serial,
    )


def _atom_line(state_index: int, atom: AtomRecord) -> str:
    fields = (
        ("serial", _number(atom.serial)),
        ("name", _text(atom.name)),
        ("alt", _text(atom.alt)),
        ("resn", _text(atom.resn)),
        ("chain", _text(atom.chain)),
        ("resv", _number(atom.resv)),
        ("ins", _text(atom.ins_code)),
        ("elem", _text(atom.elem)),
        ("hetatm", str(atom.hetatm).lower()),
        ("occupancy", _number(atom.q)),
        ("b_factor", _number(atom.b)),
        ("color", _number(atom.color)),
        ("reps", _text(",".join(sorted(atom.reps)))),
        ("label", "null" if atom.label is None else _text(atom.label)),
        ("coord", _text(",".join(_number(value) for value in atom.coord))),
    )
    return (
        "atom state="
        + _number(state_index)
        + " "
        + " ".join(f"{name}={value}" for name, value in fields)
    )


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_snapshot(snapshot: object) -> bool:
    if not isinstance(snapshot, ObjectSnapshot):
        return False
    if not isinstance(snapshot.name, str) or not isinstance(
        snapshot.enabled, bool
    ):
        return False
    if not isinstance(snapshot.states, tuple) or not isinstance(
        snapshot.bonds, tuple
    ):
        return False
    for state in snapshot.states:
        if not isinstance(state, StateSnapshot) or not isinstance(
            state.atoms, tuple
        ):
            return False
        for atom in state.atoms:
            if not isinstance(atom, AtomRecord):
                return False
            if not all(
                isinstance(value, str)
                for value in (
                    atom.name,
                    atom.alt,
                    atom.resn,
                    atom.chain,
                    atom.ins_code,
                    atom.elem,
                )
            ):
                return False
            if not isinstance(atom.coord, tuple) or len(atom.coord) != 3:
                return False
            if not all(
                _is_number(value)
                for value in (
                    atom.q,
                    atom.b,
                    *atom.coord,
                )
            ):
                return False
            if not all(
                _is_int(value) for value in (atom.serial, atom.resv, atom.color)
            ):
                return False
            if not isinstance(atom.hetatm, bool) or not isinstance(
                atom.reps, tuple
            ):
                return False
            if not all(isinstance(rep, str) for rep in atom.reps):
                return False
            if atom.label is not None and not isinstance(atom.label, str):
                return False
    if not isinstance(snapshot.view, tuple) or not all(
        _is_number(value) for value in snapshot.view
    ):
        return False
    if not isinstance(snapshot.settings, tuple) or not all(
        isinstance(setting, tuple)
        and len(setting) == 2
        and all(isinstance(value, str) for value in setting)
        for setting in snapshot.settings
    ):
        return False
    atom_count = len(snapshot.states[0].atoms) if snapshot.states else 0
    return all(
        isinstance(bond, BondRecord)
        and isinstance(bond.atom_index_a, int)
        and not isinstance(bond.atom_index_a, bool)
        and isinstance(bond.atom_index_b, int)
        and not isinstance(bond.atom_index_b, bool)
        and 0 <= bond.atom_index_a < atom_count
        and 0 <= bond.atom_index_b < atom_count
        and isinstance(bond.order, int)
        and not isinstance(bond.order, bool)
        for bond in snapshot.bonds
    )


def _malformed_card() -> str:
    return f"card-version={CARD_VERSION}\nstatus=unsupported reason=malformed-snapshot\n"


def render(snapshot: ObjectSnapshot, *, max_atoms_per_state: int = 256) -> str:
    """Render a deterministic, bounded card for one H-02 candidate snapshot."""
    if getattr(snapshot, "schema_version", None) != 1:
        return (
            f"card-version={CARD_VERSION}\n"
            "status=unsupported reason=snapshot-schema-version\n"
        )
    if max_atoms_per_state < 1:
        raise ValueError("max_atoms_per_state must be positive")
    if not _valid_snapshot(snapshot):
        return _malformed_card()

    lines = [
        f"card-version={CARD_VERSION}",
        "status=complete",
        "unsupported state=measurement-objects route=plan-report",
        "unsupported state=explicit-polymer-classification route=contract-freeze",
        "object "
        f"name={_text(snapshot.name)} enabled={str(snapshot.enabled).lower()} "
        f"states={_number(len(snapshot.states))}",
    ]
    for index, state in enumerate(snapshot.states, start=1):
        atoms = sorted(state.atoms, key=_atom_key)
        emitted = atoms[:max_atoms_per_state]
        lines.append(
            "state "
            f"index={_number(index)} atoms={_number(len(atoms))} "
            f"emitted={_number(len(emitted))} truncated={str(len(emitted) != len(atoms)).lower()}"
        )
        lines.extend(_atom_line(index, atom) for atom in emitted)

    canonical_indices = (
        {
            original_index: canonical_index
            for canonical_index, (original_index, _atom) in enumerate(
                sorted(
                    enumerate(snapshot.states[0].atoms),
                    key=lambda item: _atom_key(item[1]),
                )
            )
        }
        if snapshot.states
        else {}
    )

    def canonical_bond_indices(bond: BondRecord) -> tuple[int, int]:
        return (
            canonical_indices[bond.atom_index_a],
            canonical_indices[bond.atom_index_b],
        )

    emitted_bonds = [
        bond
        for bond in snapshot.bonds
        if canonical_indices[bond.atom_index_a]
        < min(max_atoms_per_state, len(snapshot.states[0].atoms))
        and canonical_indices[bond.atom_index_b]
        < min(max_atoms_per_state, len(snapshot.states[0].atoms))
    ]
    omitted_bonds = len(snapshot.bonds) - len(emitted_bonds)
    lines.extend(
        "bond "
        f"from={_number(min(*canonical_bond_indices(bond)))} "
        f"to={_number(max(*canonical_bond_indices(bond)))} "
        f"order={_number(bond.order)}"
        for bond in sorted(
            emitted_bonds,
            key=lambda bond: (
                min(*canonical_bond_indices(bond)),
                max(*canonical_bond_indices(bond)),
                bond.order,
            ),
        )
    )
    if omitted_bonds:
        lines.append(
            "omitted-bonds reason=atom-truncation "
            f"count={_number(omitted_bonds)}"
        )
    lines.append(
        "view values="
        + _text(",".join(_number(value) for value in snapshot.view))
    )
    lines.extend(
        f"setting name={_text(name)} value={_text(value)}"
        for name, value in sorted(snapshot.settings)
    )
    return "\n".join(lines) + "\n"


def render_for_data(snapshot: ObjectSnapshot) -> str:
    """Return candidate card bytes for the dataset caller seam."""
    return render(snapshot)


def render_for_runtime(snapshot: ObjectSnapshot) -> str:
    """Return candidate card bytes for the runtime caller seam."""
    return render(snapshot)
