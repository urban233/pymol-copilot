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

Bounded is meant literally, because the card is spent from a model's
context budget: `render()` emits at most `max_states` states, at most
`max_atoms_per_state` atoms per emitted state and at most `max_bonds`
bond lines, each omission carrying its own explicit marker, and it
rejects as malformed a snapshot whose individual text or numeric fields
fall outside the fixed limits below. A card's size is therefore a
function of those bounds alone, never of how large the snapshot it came
from happens to be.
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

#: The largest absolute magnitude any numeric snapshot field may carry.
#: Real PyMOL produces nothing near this, and an unbounded Python int is
#: not renderable at all: `math.isfinite()` raises `OverflowError` on one
#: too large to convert to a float, and `_number()` would turn one into a
#: line of arbitrary length. Values outside the range are rejected as
#: malformed rather than rendered.
_MAX_ABS_NUMBER = 10**12

#: The longest any single text field -- object name, atom name, alt,
#: resn, chain, insertion code, element, label, representation name, or
#: setting name or value -- may be. JSON escaping expands a character to
#: at most six bytes, so this bounds the rendered form too. An overlong
#: field is rejected as malformed rather than shortened: a silently
#: truncated name is one the model would read as if it were whole.
_MAX_TEXT_CHARS = 256

#: The largest number of setting pairs one snapshot may carry.
#: `pmc_core.snapshot.SAFE_SETTINGS` declares two today; this leaves that
#: set room to grow without leaving the settings block unbounded.
_MAX_SETTINGS = 64

#: The largest number of representations one atom may carry.
#: `pmc_core.snapshot.MOLECULE_REP_NAMES` declares ten today, and the
#: same room-to-grow reasoning applies.
_MAX_REPS_PER_ATOM = 32


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

    The key leads with the seven identity fields, which is what makes the
    order readable, but it continues through every remaining rendered
    field so that it is total: two atoms agreeing on their identity but
    differing in coordinates, color, label or representations would
    otherwise keep their input order under a stable sort, and permuting
    the input would move their lines and their canonical bond indices.
    Atoms that agree on the whole key render identical lines, and
    `_valid_snapshot` rejects a state containing two of them.

    Args:
        atom: The atom to key.

    Returns:
        A tuple ordering atoms by rendered content rather than array
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
        atom.elem,
        atom.hetatm,
        atom.q,
        atom.b,
        atom.color,
        atom.reps,
        atom.label is not None,
        atom.label or "",
        atom.coord,
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
    """Return whether value is a finite, non-bool, in-range numeric value.

    The magnitude test is deliberately written as a comparison rather
    than a `math.isfinite()` call on an arbitrary int: `isfinite()`
    raises OverflowError for an int too large to convert to a float, and
    this predicate has to answer False for such a value rather than
    propagate out of the validator that exists to fail closed.

    Args:
        value: The value to check.

    Returns:
        True if value is an int or float, is not a bool, is finite, and
        lies within _MAX_ABS_NUMBER of zero.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return -_MAX_ABS_NUMBER <= value <= _MAX_ABS_NUMBER


def _is_int(value: object) -> bool:
    """Return whether value is a non-bool int small enough to render.

    Args:
        value: The value to check.

    Returns:
        True if value is an int, is not a bool, and lies within
        _MAX_ABS_NUMBER of zero.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return -_MAX_ABS_NUMBER <= value <= _MAX_ABS_NUMBER


def _is_text(value: object) -> bool:
    """Return whether value is a string short enough to render.

    Args:
        value: The value to check.

    Returns:
        True if value is a str of at most _MAX_TEXT_CHARS characters.
    """
    return isinstance(value, str) and len(value) <= _MAX_TEXT_CHARS


def _valid_atom(atom: object) -> bool:
    """Return whether one atom has the shape render() can safely render.

    Args:
        atom: The candidate value to validate.

    Returns:
        True if every atom field render() reads has the type, range and
        size render() assumes; False otherwise.
    """
    if not isinstance(atom, AtomRecord):
        return False
    if not all(
        _is_text(value)
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
    if not isinstance(atom.hetatm, bool) or not isinstance(atom.reps, tuple):
        return False
    if len(atom.reps) > _MAX_REPS_PER_ATOM:
        return False
    if not all(_is_text(rep) for rep in atom.reps):
        return False
    return atom.label is None or _is_text(atom.label)


def _valid_snapshot(snapshot: object) -> bool:
    """Return whether snapshot has the shape render() can safely render.

    The snapshot's own `schema_version` is not checked here: render()
    gates on it before calling this, so that a version mismatch and a
    malformed body stay two distinguishable card outcomes.

    Args:
        snapshot: The candidate value to validate.

    Returns:
        True if every field render() reads has the type, range and size
        render() assumes; False otherwise, in which case render() emits a
        malformed card rather than raising or emitting partial output.
    """
    if not isinstance(snapshot, ObjectSnapshot):
        return False
    # A snapshot may not author its own unsupported markers -- the card's
    # unsupported lines are a pass-through of pmc_core.snapshot's one
    # declaration, never an independent claim rendered as-is.
    if snapshot.unsupported != DECLARED_UNSUPPORTED:
        return False
    if not _is_text(snapshot.name) or not isinstance(snapshot.enabled, bool):
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
        if not all(_valid_atom(atom) for atom in state.atoms):
            return False
        # Two atoms indistinguishable in every rendered field leave their
        # relative order -- and, in the first state, the canonical index
        # of any bond ending on one of them -- decided by input position
        # rather than by content. Reject rather than emit bytes a caller
        # could change by permuting its input.
        if len({_atom_key(atom) for atom in state.atoms}) != len(state.atoms):
            return False
    if (
        not isinstance(snapshot.view, tuple)
        or len(snapshot.view) != 18
        or not all(_is_number(value) for value in snapshot.view)
    ):
        return False
    if (
        not isinstance(snapshot.settings, tuple)
        or len(snapshot.settings) > _MAX_SETTINGS
        or not all(
            isinstance(setting, tuple)
            and len(setting) == 2
            and all(_is_text(value) for value in setting)
            for setting in snapshot.settings
        )
    ):
        return False
    atom_count = len(snapshot.states[0].atoms) if snapshot.states else 0
    return all(
        isinstance(bond, BondRecord)
        and _is_int(bond.atom_index_a)
        and _is_int(bond.atom_index_b)
        and 0 <= bond.atom_index_a < atom_count
        and 0 <= bond.atom_index_b < atom_count
        and _is_int(bond.order)
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


def render(
    snapshot: ObjectSnapshot,
    *,
    max_atoms_per_state: int = 256,
    max_states: int = 8,
    max_bonds: int = 1024,
) -> str:
    """Render a deterministic, bounded card for one canonical snapshot.

    The three bounds are what make a card's size a function of this
    module rather than of the snapshot: a trajectory with thousands of
    states or a fabricated snapshot with millions of bonds still renders
    a card of the same order of size as a single small structure. Every
    omission a bound causes is recorded in the card itself, so a reader
    never has to infer that something was dropped.

    Args:
        snapshot: The canonical snapshot to render.
        max_atoms_per_state: The maximum number of atoms emitted per
            emitted state; atoms past this bound are omitted and the
            state line records the truncation explicitly.
        max_states: The maximum number of states emitted, lowest state
            index first; states past this bound are omitted behind an
            "omitted-states" marker line. A card is a view of a
            structure, not a trajectory dump.
        max_bonds: The maximum number of bond lines emitted, in the
            card's own canonical bond order; bonds past this bound are
            omitted behind an "omitted-bonds reason=bond-limit" marker
            line.

    Returns:
        The rendered card text, ending in a single trailing newline.

    Raises:
        ValueError: If any of the three bounds is not positive.
    """
    version = getattr(snapshot, "schema_version", None)
    # _is_int first, and not equality alone: True == 1 and 1.0 == 1 in
    # Python, so a snapshot carrying either as its schema version would
    # otherwise pass the version gate and be rendered as complete.
    if not _is_int(version) or version != SNAPSHOT_VERSION:
        return (
            f"card-version={CARD_VERSION}\n"
            "status=unsupported reason=snapshot-schema-version\n"
        )
    if max_atoms_per_state < 1 or max_states < 1 or max_bonds < 1:
        raise ValueError(
            "max_atoms_per_state, max_states and max_bonds must be positive"
        )
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
    emitted_states = snapshot.states[:max_states]
    for index, state in enumerate(emitted_states, start=1):
        atoms = sorted(state.atoms, key=_atom_key)
        emitted = atoms[:max_atoms_per_state]
        lines.append(
            "state "
            f"index={_number(index)} atoms={_number(len(atoms))} "
            f"emitted={_number(len(emitted))} truncated={str(len(emitted) != len(atoms)).lower()}"
        )
        lines.extend(_atom_line(index, atom) for atom in emitted)
    omitted_states = len(snapshot.states) - len(emitted_states)
    if omitted_states:
        lines.append(
            f"omitted-states reason=state-limit count={_number(omitted_states)}"
        )

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

    in_range_bonds = [
        bond
        for bond in snapshot.bonds
        if canonical_indices[bond.atom_index_a]
        < min(max_atoms_per_state, len(snapshot.states[0].atoms))
        and canonical_indices[bond.atom_index_b]
        < min(max_atoms_per_state, len(snapshot.states[0].atoms))
    ]
    ordered_bonds = sorted(
        in_range_bonds,
        key=lambda bond: (
            min(*canonical_bond_indices(bond)),
            max(*canonical_bond_indices(bond)),
            bond.order,
        ),
    )
    emitted_bonds = ordered_bonds[:max_bonds]
    truncated_bonds = len(snapshot.bonds) - len(in_range_bonds)
    limited_bonds = len(in_range_bonds) - len(emitted_bonds)
    lines.extend(
        "bond "
        f"from={_number(min(*canonical_bond_indices(bond)))} "
        f"to={_number(max(*canonical_bond_indices(bond)))} "
        f"order={_number(bond.order)}"
        for bond in emitted_bonds
    )
    if truncated_bonds:
        lines.append(
            "omitted-bonds reason=atom-truncation "
            f"count={_number(truncated_bonds)}"
        )
    if limited_bonds:
        lines.append(
            f"omitted-bonds reason=bond-limit count={_number(limited_bonds)}"
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
