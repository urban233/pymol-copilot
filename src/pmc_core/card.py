# Copyright 2026 PyMOL Copilot contributors.
"""Deterministic structure-card rendering for pmc_core.snapshot.

This is the production promotion of M-02's discovery work (originally
`tests/discovery/m02/card_candidate.py`): a pure, bounded, deterministic
text rendering of one canonical `ObjectSnapshot` into the compact card
format the model sees. `render()` takes an already-extracted
`ObjectSnapshot` and never imports `pymol` itself, so this module has no
PyMOL dependency, exactly like `pmc_core.snapshot` it is built on.

`render_for_data()` and `render_for_runtime()` are separate caller seams
that exist to be proved byte-identical, not because they differ -- the
dataset writer (master plan item 14) and the runtime prompt builder
(master plan item 13) each call one, and a parity test fails if they ever
diverge.

The card's `unsupported` lines are a pure pass-through of
`pmc_core.snapshot.DECLARED_UNSUPPORTED`, never independently authored: a
snapshot claiming a different unsupported set is rejected as malformed
rather than rendered, so this module never becomes a second place that
could drift from that declaration.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import math

from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import BondRecord
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot

#: This module's own structure-card contract version, stamped as the
#: first line of every card -- including both failure cards, so a
#: rejected card is still attributable to a version. Both caller seams
#: below emit it; the dataset writer (master plan item 14) and the
#: prompt builder (item 13) stamp it into their own records by calling
#: them.
CARD_VERSION = 1


def _text(value: str) -> str:
    """Return an ASCII-stable quoted string.

    Args:
        value: The string to encode.

    Returns:
        The JSON-quoted, ASCII-escaped form of value.
    """
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _number(value: float | int) -> str:
    """Return one locale-independent normalized number.

    Trailing zeros and a trailing decimal point are stripped, and both
    positive and negative zero normalize to "0", so structurally equal
    numeric values always render identical text regardless of their
    original float representation.

    Args:
        value: The number to normalize.

    Returns:
        The normalized decimal text.
    """
    normalized = format(value, ".6f").rstrip("0").rstrip(".") or "0"
    return "0" if normalized in {"0", "-0"} else normalized


def _atom_key(atom: AtomRecord) -> tuple[object, ...]:
    """Return the canonical sort key for one atom.

    Args:
        atom: The atom to key.

    Returns:
        A tuple ordering atoms by identity fields rather than array
        position, so permuted atom collections sort identically.
    """
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
    """Render one atom's card line for one state.

    Args:
        state_index: The 1-based state number this atom belongs to.
        atom: The atom to render.

    Returns:
        One newline-free "atom ..." line covering every model-relevant
        atom field.
    """
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
    """Return whether value is a finite, non-bool numeric value.

    Args:
        value: The value to check.

    Returns:
        True if value is an int or float, is not a bool, and is finite.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_int(value: object) -> bool:
    """Return whether value is a non-bool int.

    Args:
        value: The value to check.

    Returns:
        True if value is an int and not a bool.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_snapshot(snapshot: object) -> bool:
    """Return whether snapshot has the shape render() can safely render.

    Args:
        snapshot: The candidate value to validate.

    Returns:
        True if every field render() reads has the type and range render()
        assumes; False otherwise, in which case render() emits a malformed
        card rather than raising or emitting partial output.
    """
    if not isinstance(snapshot, ObjectSnapshot):
        return False
    # A snapshot may not author its own unsupported markers -- the card's
    # unsupported lines are a pass-through of pmc_core.snapshot's one
    # declaration, never an independent claim rendered as-is.
    if snapshot.unsupported != DECLARED_UNSUPPORTED:
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
    if (
        not isinstance(snapshot.view, tuple)
        or len(snapshot.view) != 18
        or not all(_is_number(value) for value in snapshot.view)
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
    """Return the fixed, stable card for a malformed snapshot.

    Returns:
        The single "malformed-snapshot" status card, identical for every
        malformed input so a caller cannot infer anything about why a
        snapshot was rejected from a diff.
    """
    return f"card-version={CARD_VERSION}\nstatus=unsupported reason=malformed-snapshot\n"


def render(snapshot: ObjectSnapshot, *, max_atoms_per_state: int = 256) -> str:
    """Render a deterministic, bounded card for one canonical snapshot.

    Args:
        snapshot: The canonical snapshot to render.
        max_atoms_per_state: The maximum number of atoms emitted per
            state; atoms past this bound are omitted and the state line
            records the truncation explicitly.

    Returns:
        The rendered card text, ending in a single trailing newline.

    Raises:
        ValueError: If max_atoms_per_state is not positive.
    """
    if getattr(snapshot, "schema_version", None) != SNAPSHOT_VERSION:
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
        *snapshot.unsupported,
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
    """Return card bytes for the dataset writer caller seam.

    Args:
        snapshot: The canonical snapshot to render.

    Returns:
        The same bytes render() returns, through the seam the dataset
        writer (master plan item 14) calls.
    """
    return render(snapshot)


def render_for_runtime(snapshot: ObjectSnapshot) -> str:
    """Return card bytes for the runtime prompt builder caller seam.

    Args:
        snapshot: The canonical snapshot to render.

    Returns:
        The same bytes render() returns, through the seam the runtime
        prompt builder (master plan item 13) calls.
    """
    return render(snapshot)
