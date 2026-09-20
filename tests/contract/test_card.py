# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the structure card format: no PyMOL required.

Covers pmc_core.card's deterministic renderer: the golden card bytes, its
invariance to semantically unordered collection order and signed-zero
value differences, canonical bond remapping under atom permutation, the
byte parity between its two caller seams, per-field-mutation sensitivity,
the explicit markers behind each of its three size bounds, and its
fail-closed handling of truncation, undeclared-unsupported,
indistinguishable atoms, out-of-range or unbounded field values,
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


def _multi_bond_snapshot() -> ObjectSnapshot:
    """Build a three-atom snapshot whose bonds are genuinely reorderable.

    Returns:
        A snapshot carrying two bonds stored in the opposite of the
        card's canonical bond order, so that dropping the renderer's bond
        sort changes its bytes. _snapshot()'s single bond cannot show
        that: reversing a one-element tuple is a no-op.
    """
    base = _snapshot()
    atom_b, atom_a = base.states[0].atoms
    atom_c = replace(atom_a, serial=3, name="CB", coord=(7.0, 8.0, 9.0))
    return replace(
        base,
        states=(StateSnapshot((atom_b, atom_a, atom_c)),),
        bonds=(BondRecord(0, 2, 2), BondRecord(1, 2, 1)),
    )


def _reordered_reps(atom: AtomRecord) -> tuple[str, ...]:
    """Return one atom's representations in a genuinely different order.

    Reversing a one-element tuple is a no-op, which is how the bond half
    of the old ordering test passed without testing anything. Fail
    loudly here rather than let a fixture change quietly empty out the
    two tests that reorder representations.

    Args:
        atom: The atom whose representations to reorder.

    Returns:
        The same representation names in the opposite order.
    """
    assert len(atom.reps) > 1, "fixture atom cannot show a reps reordering"
    return tuple(reversed(atom.reps))


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


def test_equivalent_bond_order_produces_identical_card() -> None:
    """Bond order in the snapshot does not affect card bytes."""
    snapshot = _multi_bond_snapshot()
    equivalent = replace(snapshot, bonds=tuple(reversed(snapshot.bonds)))

    assert render(equivalent) == render(snapshot)
    assert "bond from=0 to=1 order=1\nbond from=1 to=2 order=2\n" in render(
        snapshot
    )


def test_equivalent_setting_order_produces_identical_card() -> None:
    """Setting order in the snapshot does not affect card bytes."""
    snapshot = _snapshot()
    equivalent = replace(snapshot, settings=tuple(reversed(snapshot.settings)))

    assert render(equivalent) == render(snapshot)


def test_equivalent_representation_order_produces_identical_card() -> None:
    """Representation order in the snapshot does not affect card bytes.

    An atom's representations render sorted, so the tuple's own order is
    invisible in the card. It has to be invisible in the canonical atom
    order too: two atoms sharing the seven identity fields are separated
    by the key components that follow, and keying the raw tuple there
    lets a reordering the card never shows decide which atom line comes
    first and which canonical index a bond endpoint gets.
    """
    base = _snapshot()
    atom_b, atom_a = base.states[0].atoms
    twin = replace(atom_a, coord=(-1.0, -2.0, -3.0))
    snapshot = replace(
        base,
        states=(StateSnapshot((atom_a, twin, atom_b)),),
        bonds=(BondRecord(0, 2, 1),),
    )
    reordered = replace(
        snapshot,
        states=(
            StateSnapshot(
                (
                    replace(atom_a, reps=_reordered_reps(atom_a)),
                    twin,
                    atom_b,
                )
            ),
        ),
    )

    assert render(snapshot).startswith("card-version=1\nstatus=complete\n")
    assert "bond from=1 to=2 order=1\n" in render(snapshot)
    assert render(reordered) == render(snapshot)


def test_atoms_sharing_identity_fields_are_ordered_by_content() -> None:
    """Two atoms with one identity sort by what distinguishes them.

    The canonical atom order leads with the seven identity fields, but it
    cannot stop there: atoms agreeing on all seven and differing only in
    coordinates, color or label would otherwise keep their input order,
    and permuting the input would move their lines.
    """
    base = _snapshot()
    atom_b, atom_a = base.states[0].atoms
    twin = replace(atom_a, coord=(9.0, 9.0, 9.0), color=4, label=None)
    snapshot = replace(
        base, states=(StateSnapshot((atom_a, twin, atom_b)),), bonds=()
    )
    permuted = replace(
        snapshot, states=(StateSnapshot((twin, atom_b, atom_a)),)
    )

    assert render(snapshot).startswith("card-version=1\nstatus=complete\n")
    assert render(permuted) == render(snapshot)


@pytest.mark.parametrize(
    "reorder_reps",
    [
        pytest.param(False, id="identical-atom"),
        pytest.param(True, id="representations-reordered"),
    ],
)
def test_indistinguishable_atoms_return_stable_malformed_card(
    reorder_reps: bool,
) -> None:
    """Atoms equal in every rendered field have no canonical order.

    Their lines would be identical, but the canonical index of a bond
    ending on one of them would still be decided by input position, so
    the snapshot fails closed rather than rendering permutable bytes.

    The second case is the one a raw-tuple key misses: reordering the
    representations renders the same line, so the duplicate is just as
    real, but the two atoms would no longer tie on the key and the card
    would render as complete.
    """
    base = _snapshot()
    atom_b, atom_a = base.states[0].atoms
    duplicate = replace(
        atom_a,
        reps=_reordered_reps(atom_a) if reorder_reps else atom_a.reps,
    )
    malformed = replace(
        base, states=(StateSnapshot((atom_b, atom_a, duplicate)),)
    )

    assert render(malformed) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )


def test_atoms_differing_below_rendered_precision_are_malformed() -> None:
    """A difference the card rounds away does not make two atoms distinct.

    _number() renders six decimals, so coordinates closer together than
    that produce identical atom lines. A key taken from the raw float
    would both order the two atoms by a difference the card never shows
    and hide them from the duplicate check, leaving a card carrying two
    identical atom lines and a bond endpoint attributable to neither.
    """
    base = _snapshot()
    atom_b, atom_a = base.states[0].atoms
    x, y, z = atom_a.coord
    below_precision = replace(atom_a, coord=(x + 1e-9, y, z))
    malformed = replace(
        base, states=(StateSnapshot((atom_b, atom_a, below_precision)),)
    )

    assert render(malformed) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )


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
        lambda value: replace(value, view=(2.0, *value.view[1:])),
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


@pytest.mark.parametrize("version", [True, 1.0])
def test_non_integer_schema_version_returns_unsupported_card(
    version: object,
) -> None:
    """A version merely equal to 1 is not snapshot schema version 1.

    True == 1 and 1.0 == 1 in Python, so an equality test alone would let
    a JSON snapshot carrying either be rendered as a complete card.

    Args:
        version: A non-int value that compares equal to SNAPSHOT_VERSION.
    """
    snapshot = replace(_snapshot(), schema_version=cast(Any, version))

    assert render(snapshot) == (
        "card-version=1\nstatus=unsupported reason=snapshot-schema-version\n"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: _with_atom(value, q=10**400),
        lambda value: _with_atom(value, serial=10**400),
        lambda value: _with_atom(value, coord=(10**400, 2.0, 3.0)),
        lambda value: replace(
            value, view=cast(Any, (10**400, *value.view[1:]))
        ),
        lambda value: replace(value, bonds=(BondRecord(1, 0, 10**400),)),
    ],
)
def test_unrenderable_number_returns_stable_malformed_card(
    mutation: Any,
) -> None:
    """A number too large to render fails closed instead of raising.

    An integer beyond float range is not merely large: math.isfinite()
    raises OverflowError on one, so the validator has to answer without
    calling it.

    Args:
        mutation: A one-argument callable returning a snapshot with one
            numeric field set beyond the renderable range.
    """
    assert render(mutation(_snapshot())) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: replace(value, name="x" * 10_000),
        lambda value: _with_atom(value, label="x" * 10_000),
        lambda value: _with_atom(value, reps=("x" * 10_000,)),
        lambda value: _with_atom(
            value, reps=tuple(f"r{index}" for index in range(10_000))
        ),
        lambda value: replace(
            value, settings=(("sphere_scale", "0" * 10_000),)
        ),
        lambda value: replace(
            value,
            settings=tuple((f"s{index}", "0") for index in range(10_000)),
        ),
    ],
)
def test_unbounded_field_returns_stable_malformed_card(mutation: Any) -> None:
    """A field large enough to unbound the card fails closed.

    Names, labels, representations and settings are the card's only
    caller-sized fields, and the card is spent from a model's context
    budget, so an oversized one is rejected rather than shortened: a
    silently truncated name is one the model would read as whole.

    Args:
        mutation: A one-argument callable returning a snapshot with one
            text or collection field grown past its bound.
    """
    assert render(mutation(_snapshot())) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )


def test_state_limit_is_explicit() -> None:
    """States past the bound are omitted behind their own marker."""
    snapshot = _snapshot()
    trajectory = replace(snapshot, states=snapshot.states * 3)

    card = render(trajectory, max_states=1)

    assert 'object name="fx" enabled=false states=3\n' in card
    assert card.count("\nstate index=") == 1
    assert "omitted-states reason=state-limit count=2\n" in card


def test_bond_limit_is_explicit() -> None:
    """Bonds past the bound are omitted behind their own marker."""
    card = render(_multi_bond_snapshot(), max_bonds=1)

    assert "bond from=0 to=1 order=1\n" in card
    assert "bond from=1 to=2 order=2\n" not in card
    assert "omitted-bonds reason=bond-limit count=1\n" in card


@pytest.mark.parametrize(
    "bound", ["max_atoms_per_state", "max_states", "max_bonds"]
)
def test_non_positive_bound_is_rejected(bound: str) -> None:
    """Each of the three size bounds must be positive.

    Args:
        bound: The name of the bound keyword to set to zero.
    """
    with pytest.raises(ValueError, match="must be positive"):
        render(_snapshot(), **cast(Any, {bound: 0}))


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
