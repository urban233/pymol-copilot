# Copyright 2026 PyMOL Copilot contributors.
"""Candidate-private deterministic card renderer for H-02 ObjectSnapshot.

This is discovery evidence only. It does not select H-02's serialization or
define a production structure-card contract.
"""

from __future__ import annotations

import json

from harness import AtomRecord
from harness import ObjectSnapshot

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


def render(snapshot: ObjectSnapshot, *, max_atoms_per_state: int = 256) -> str:
    """Render a deterministic, bounded card for one H-02 candidate snapshot."""
    if snapshot.schema_version != 1:
        return (
            f"card-version={CARD_VERSION}\n"
            "status=unsupported reason=snapshot-schema-version\n"
        )
    if max_atoms_per_state < 1:
        raise ValueError("max_atoms_per_state must be positive")

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
    lines.extend(
        "bond "
        f"from={_number(min(bond.atom_index_a, bond.atom_index_b))} "
        f"to={_number(max(bond.atom_index_a, bond.atom_index_b))} "
        f"order={_number(bond.order)}"
        for bond in sorted(
            snapshot.bonds,
            key=lambda bond: (
                min(bond.atom_index_a, bond.atom_index_b),
                max(bond.atom_index_a, bond.atom_index_b),
                bond.order,
            ),
        )
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
