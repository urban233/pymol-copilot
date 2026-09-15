# Copyright 2026 PyMOL Copilot contributors.
"""Golden, parity, mutation, and boundedness tests for M-02's card candidate."""

from __future__ import annotations

from dataclasses import replace
import os
import sys
from typing import Any, cast

import pytest
from card_candidate import render
from card_candidate import render_for_data
from card_candidate import render_for_runtime
from harness import AtomRecord
from harness import BondRecord
from harness import ObjectSnapshot
from harness import StateSnapshot
from harness import extract


def _snapshot() -> ObjectSnapshot:
    atom_a = AtomRecord(
        1,
        "CA",
        "",
        "ALA",
        "A",
        1,
        "",
        "C",
        False,
        1.0,
        20.0,
        3,
        ("sticks", "lines"),
        "CA",
        (1.0, 2.0, 3.0),
    )
    atom_b = AtomRecord(
        2,
        "ZN",
        "B",
        "ZN",
        "A",
        2,
        "A",
        "ZN",
        True,
        0.5,
        10.0,
        7,
        ("spheres",),
        None,
        (4.0, 5.0, 6.0),
    )
    return ObjectSnapshot(
        1,
        "fx",
        False,
        (StateSnapshot((atom_b, atom_a)),),
        (BondRecord(1, 0, 1),),
        (1.0, 0.0, -20.0),
        (("sphere_scale", "0.35"), ("cartoon_transparency", "0.25")),
    )


def test_golden_card_has_stable_bytes() -> None:
    """A representative candidate snapshot renders fixed card bytes."""
    card = render(_snapshot())

    assert card == (
        "card-version=candidate-1\nstatus=complete\n"
        "unsupported state=measurement-objects route=plan-report\n"
        "unsupported state=explicit-polymer-classification route=contract-freeze\n"
        'object name="fx" enabled=false states=1\n'
        "state index=1 atoms=2 emitted=2 truncated=false\n"
        'atom state=1 serial=1 name="CA" alt="" resn="ALA" chain="A" resv=1 ins="" elem="C" hetatm=false occupancy=1 b_factor=20 color=3 reps="lines,sticks" label="CA" coord="1,2,3"\n'
        'atom state=1 serial=2 name="ZN" alt="B" resn="ZN" chain="A" resv=2 ins="A" elem="ZN" hetatm=true occupancy=0.5 b_factor=10 color=7 reps="spheres" label=null coord="4,5,6"\n'
        'bond from=0 to=1 order=1\nview values="1,0,-20"\n'
        'setting name="cartoon_transparency" value="0.25"\nsetting name="sphere_scale" value="0.35"\n'
    )


def test_equivalent_collection_order_produces_identical_card() -> None:
    """Semantically unordered collections do not affect candidate bytes."""
    snapshot = _snapshot()
    equivalent = replace(
        snapshot,
        bonds=tuple(reversed(snapshot.bonds)),
        settings=tuple(reversed(snapshot.settings)),
    )

    assert render(equivalent) == render(snapshot)


def test_atom_permutation_remaps_bonds_to_canonical_positions() -> None:
    """Reordered atoms preserve card bytes and canonical bond endpoints."""
    atom_a = replace(
        _snapshot().states[0].atoms[1],
        serial=10,
        name="A",
        alt="",
        resn="X",
        resv=1,
        ins_code="",
    )
    atom_b = replace(
        _snapshot().states[0].atoms[0],
        serial=20,
        name="B",
        alt="",
        resn="X",
        resv=1,
        ins_code="",
    )
    atom_c = replace(atom_a, serial=30, name="C")
    base = replace(
        _snapshot(),
        states=(StateSnapshot((atom_b, atom_a, atom_c)),),
        bonds=(BondRecord(0, 2, 1), BondRecord(1, 0, 2)),
    )
    reordered = replace(
        base,
        states=(StateSnapshot((atom_c, atom_b, atom_a)),),
        bonds=(BondRecord(0, 1, 1), BondRecord(1, 2, 2)),
    )

    assert render(reordered) == render(base)
    assert "bond from=0 to=1 order=2\n" in render(base)
    assert "bond from=1 to=2 order=1\n" in render(base)


def test_data_and_runtime_candidate_callers_have_byte_parity() -> None:
    """Both candidate callers delegate to the same pure renderer."""
    snapshot = _snapshot()

    assert render_for_data(snapshot) == render_for_runtime(snapshot)


def _with_atom(snapshot: ObjectSnapshot, **changes: object) -> ObjectSnapshot:
    """Return snapshot with one model-relevant atom field changed."""
    first, second = snapshot.states[0].atoms
    return replace(
        snapshot,
        states=(StateSnapshot((replace(cast(Any, first), **changes), second)),),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: replace(value, name="other"),
        lambda value: replace(value, enabled=True),
        lambda value: replace(value, view=(2.0, 0.0, -20.0)),
        lambda value: replace(value, settings=(("sphere_scale", "0.5"),)),
        lambda value: replace(value, bonds=(BondRecord(0, 1, 2),)),
        lambda value: _with_atom(value, serial=9),
        lambda value: _with_atom(value, name="QX"),
        lambda value: _with_atom(value, alt="A"),
        lambda value: _with_atom(value, resn="GLY"),
        lambda value: _with_atom(value, chain="B"),
        lambda value: _with_atom(value, resv=9),
        lambda value: _with_atom(value, ins_code="B"),
        lambda value: _with_atom(value, elem="N"),
        lambda value: _with_atom(value, hetatm=False),
        lambda value: _with_atom(value, q=0.6),
        lambda value: _with_atom(value, b=11.0),
        lambda value: _with_atom(value, color=4),
        lambda value: _with_atom(value, reps=("sticks",)),
        lambda value: _with_atom(value, label="changed"),
        lambda value: _with_atom(value, coord=(7.0, 2.0, 3.0)),
    ],
)
def test_model_relevant_field_mutation_changes_card(mutation: Any) -> None:
    """Each tracked snapshot field changes the candidate card."""
    snapshot = _snapshot()

    assert render(mutation(snapshot)) != render(snapshot)


def test_h02_candidate_a_snapshot_renders_as_a_complete_card(
    loaded_fixture: Any,
) -> None:
    """Candidate A's real extracted fixture feeds the same pure renderer."""
    card = render(extract(loaded_fixture, "fx"))

    assert "status=complete" in card
    assert "unsupported state=measurement-objects route=plan-report" in card
    assert "states=2" in card
    assert 'chain="A"' in card
    assert 'resn="ZN"' in card


def test_truncation_and_unsupported_schema_are_explicit() -> None:
    """Bounded and unknown candidate inputs carry visible state markers."""
    snapshot = _snapshot()

    assert "emitted=1 truncated=true" in render(snapshot, max_atoms_per_state=1)
    assert render(replace(snapshot, schema_version=2)) == (
        "card-version=candidate-1\nstatus=unsupported reason=snapshot-schema-version\n"
    )


def test_invalid_bond_endpoint_returns_stable_malformed_card() -> None:
    """A bond outside the first state's atom range fails closed."""
    malformed = replace(_snapshot(), bonds=(BondRecord(0, 2, 1),))

    assert render(malformed) == (
        "card-version=candidate-1\n"
        "status=unsupported reason=malformed-snapshot\n"
    )


def test_malformed_structural_value_returns_stable_malformed_card() -> None:
    """A malformed view value fails closed without changing schema handling."""
    malformed = replace(_snapshot(), view=cast(Any, ("not-a-number",)))

    assert render(malformed) == (
        "card-version=candidate-1\n"
        "status=unsupported reason=malformed-snapshot\n"
    )


def test_truncation_omits_bonds_with_missing_endpoint_atoms() -> None:
    """Truncation never emits a bond to an omitted atom."""
    card = render(_snapshot(), max_atoms_per_state=1)

    assert "bond " not in card
    assert "omitted-bonds reason=atom-truncation count=1\n" in card


if __name__ == "__main__":
    # PyMOL's shutdown can replace pytest's nonzero result with zero. Flush
    # before os._exit so Bazel receives both the real result and test output.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
