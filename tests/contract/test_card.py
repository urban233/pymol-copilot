# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the structure card format: no PyMOL required.

Covers pmc_core.card's deterministic renderer: the golden card bytes, its
invariance to semantically unordered collection order and signed-zero
value differences, canonical bond remapping under atom permutation, the
byte parity between its two caller seams, per-field-mutation sensitivity,
and its fail-closed handling of truncation, undeclared-unsupported,
schema-version mismatch and malformed input. The real-PyMOL extraction-
then-render path lives in
tests/integration/test_card_real_pymol.py, since it needs a real PyMOL
process to produce a snapshot worth rendering.
"""

from dataclasses import replace
from typing import Any
from typing import cast

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.card import CARD_VERSION
from pmc_core.card import render
from pmc_core.card import render_for_data
from pmc_core.card import render_for_runtime
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import BondRecord
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot

_IDENTITY_VIEW = (
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


def _snapshot() -> ObjectSnapshot:
    """Build a representative two-atom, one-state, one-bond snapshot.

    Returns:
        A hand-constructed snapshot exercising every card field: a
        polymer atom and a hetero atom, one bond between them, a
        non-identity display setting pair, and a non-default view.
    """
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
        _IDENTITY_VIEW,
        (("sphere_scale", "0.35"), ("cartoon_transparency", "0.25")),
        DECLARED_UNSUPPORTED,
    )


def test_golden_card_has_stable_bytes() -> None:
    """A representative snapshot renders fixed card bytes."""
    card = render(_snapshot())

    assert card == (
        "card-version=1\nstatus=complete\n"
        "unsupported state=measurement-objects route=plan-report\n"
        "unsupported state=explicit-polymer-classification route=contract-freeze\n"
        'object name="fx" enabled=false states=1\n'
        "state index=1 atoms=2 emitted=2 truncated=false\n"
        'atom state=1 serial=1 name="CA" alt="" resn="ALA" chain="A" resv=1 ins="" elem="C" hetatm=false occupancy=1 b_factor=20 color=3 reps="lines,sticks" label="CA" coord="1,2,3"\n'
        'atom state=1 serial=2 name="ZN" alt="B" resn="ZN" chain="A" resv=2 ins="A" elem="ZN" hetatm=true occupancy=0.5 b_factor=10 color=7 reps="spheres" label=null coord="4,5,6"\n'
        'bond from=0 to=1 order=1\nview values="1,0,0,0,1,0,0,0,1,0,0,0,0,0,0,-0.5,0.5,-20"\n'
        'setting name="cartoon_transparency" value="0.25"\nsetting name="sphere_scale" value="0.35"\n'
    )


def test_every_card_carries_the_version_on_its_first_line() -> None:
    """A rejected card is still attributable to a card version.

    Covers all three card outcomes -- complete, malformed-snapshot, and
    snapshot-schema-version -- so a caller can always read CARD_VERSION
    off the first line regardless of whether rendering succeeded.
    """
    snapshot = _snapshot()
    malformed = replace(snapshot, bonds=(BondRecord(0, 2, 1),))
    wrong_version = replace(snapshot, schema_version=2)

    for card in (render(snapshot), render(malformed), render(wrong_version)):
        assert card.startswith(f"card-version={CARD_VERSION}\n")


def test_equivalent_collection_order_produces_identical_card() -> None:
    """Semantically unordered collections do not affect card bytes."""
    snapshot = _snapshot()
    equivalent = replace(
        snapshot,
        bonds=tuple(reversed(snapshot.bonds)),
        settings=tuple(reversed(snapshot.settings)),
    )

    assert render(equivalent) == render(snapshot)


def test_signed_zero_coordinates_produce_identical_card() -> None:
    """Coordinate values differing only by signed zero are canonicalized."""
    original = _snapshot()
    snapshot = replace(
        original,
        states=(
            StateSnapshot(
                (
                    replace(original.states[0].atoms[0], coord=(0.0, 2.0, 3.0)),
                    original.states[0].atoms[1],
                )
            ),
        ),
    )
    signed_zero = replace(
        snapshot,
        states=(
            StateSnapshot(
                (
                    replace(
                        snapshot.states[0].atoms[0], coord=(-0.0, 2.0, 3.0)
                    ),
                    snapshot.states[0].atoms[1],
                )
            ),
        ),
    )

    assert render(signed_zero) == render(snapshot)


def test_signed_zero_view_values_produce_identical_card() -> None:
    """View values differing only by signed zero are canonicalized."""
    snapshot = _snapshot()
    signed_zero = replace(
        snapshot,
        view=tuple(-0.0 if value == 0.0 else value for value in snapshot.view),
    )

    assert render(signed_zero) == render(snapshot)


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


def test_data_and_runtime_callers_have_byte_parity() -> None:
    """Both caller seams delegate to the same pure renderer."""
    snapshot = _snapshot()

    assert render_for_data(snapshot) == render_for_runtime(snapshot)


def _with_atom(snapshot: ObjectSnapshot, **changes: object) -> ObjectSnapshot:
    """Return snapshot with one model-relevant atom field changed.

    Args:
        snapshot: The snapshot to derive from.
        **changes: The AtomRecord field(s) to replace on the first atom.

    Returns:
        A new snapshot with the first atom of its first state changed.
    """
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
    """Each tracked snapshot field changes the rendered card.

    Args:
        mutation: A one-argument callable returning a snapshot with one
            model-relevant field changed from _snapshot()'s baseline.
    """
    snapshot = _snapshot()

    assert render(mutation(snapshot)) != render(snapshot)


def test_truncation_and_unsupported_schema_are_explicit() -> None:
    """Bounded and unknown inputs carry visible state markers."""
    snapshot = _snapshot()

    assert "emitted=1 truncated=true" in render(snapshot, max_atoms_per_state=1)
    assert render(replace(snapshot, schema_version=2)) == (
        "card-version=1\nstatus=unsupported reason=snapshot-schema-version\n"
    )


def test_invalid_bond_endpoint_returns_stable_malformed_card() -> None:
    """A bond outside the first state's atom range fails closed."""
    malformed = replace(_snapshot(), bonds=(BondRecord(0, 2, 1),))

    assert render(malformed) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )


def test_undeclared_unsupported_set_returns_stable_malformed_card() -> None:
    """A snapshot may not author its own unsupported markers."""
    malformed = replace(
        _snapshot(),
        unsupported=("unsupported state=invented route=nowhere",),
    )

    assert render(malformed) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )


def test_malformed_structural_value_returns_stable_malformed_card() -> None:
    """A malformed view value fails closed without changing schema handling."""
    malformed = replace(_snapshot(), view=cast(Any, ("not-a-number",)))

    assert render(malformed) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )


@pytest.mark.parametrize(
    "view", [(), _IDENTITY_VIEW[:-1], (*_IDENTITY_VIEW, 0.0)]
)
def test_invalid_view_length_returns_stable_malformed_card(
    view: tuple[float, ...],
) -> None:
    """Views must contain exactly the 18 values returned by cmd.get_view().

    Args:
        view: A malformed view tuple, either too short, too long, or empty.
    """
    malformed = replace(_snapshot(), view=view)

    assert render(malformed) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )


def test_truncation_omits_bonds_with_missing_endpoint_atoms() -> None:
    """Truncation never emits a bond to an omitted atom."""
    card = render(_snapshot(), max_atoms_per_state=1)

    assert "bond " not in card
    assert "omitted-bonds reason=atom-truncation count=1\n" in card


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
