# Copyright 2026 PyMOL Copilot contributors.
"""Independent-oracle tests, hermetic half.

These tests never import PyMOL. The original chain-A derivation is
proved against the controlled gold-case fixture's own chain field, by
comparing against atom identities read independently here.

The generalized selection evaluator is proved against a controlled
structure whose contents this module states outright, and against the
structural shape of the typed expression tree -- that `not` binds inside
a factor, `and` across a clause and `or` across clauses. Whether those
semantics match Open-Source PyMOL's own is a different claim and is
settled in test_oracle_real_pymol.py, against real PyMOL.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import Factor
from pmc_core.plan import HetatmTerm
from pmc_core.plan import NameTerm
from pmc_core.plan import PolymerTerm
from pmc_core.plan import ResiTerm
from pmc_core.plan import ResnTerm
from pmc_core.plan import SelectionExpression
from pmc_data.oracle import UNSUPPORTED_POLYMER_CLASSIFICATION
from pmc_data.oracle import UnsupportedAssertionError
from pmc_data.oracle import atom_matches_expression
from pmc_data.oracle import expected_chain_atom_ids
from pmc_data.oracle import selected_serials
from pmc_data.oracle import unsupported_reasons
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "chain_a_gold_fixture.pdb"
)


def test_expected_chain_a_atom_ids_match_the_known_fixture_layout() -> None:
    """Chain A's expected identities are exactly the fixture's first three atoms, by direct inspection of the controlled file."""
    assert expected_chain_atom_ids(FIXTURE_PATH, "A") == frozenset({1, 2, 3})


def test_expected_chain_b_atom_ids_match_the_known_fixture_layout() -> None:
    """Chain B's expected identities are exactly the fixture's last two atoms, by direct inspection of the controlled file."""
    assert expected_chain_atom_ids(FIXTURE_PATH, "B") == frozenset({4, 5})


def test_expected_atom_ids_for_an_absent_chain_are_empty() -> None:
    """A chain identifier absent from the fixture yields an empty set rather than an error, since the oracle only reports observed membership."""
    assert expected_chain_atom_ids(FIXTURE_PATH, "Z") == frozenset()


#: One controlled structure this module states the contents of outright:
#: two chains of four ALA/SER/GLY/VAL backbone residues (N, CA, C, O),
#: one altloc CB pair on chain A residue 1, and one ZN hetero atom per
#: chain. Serial numbers run 1..N in that order.
EVALUATOR_SPEC = StructureSpec(
    spec_id="oracle_unit_structure",
    seed=7,
    chain_count=2,
    residues_per_chain=4,
    hetero_residues=1,
    state_count=2,
    altloc_residues=1,
    insertion_residues=0,
    with_bonds=False,
)


def _expression(*clauses: AndClause) -> SelectionExpression:
    """Build one selection expression from its clauses.

    Args:
        clauses: The clauses to union.

    Returns:
        The assembled expression.
    """
    return SelectionExpression(clauses=clauses)


def _clause(*factors: Factor) -> AndClause:
    """Build one and-clause from its factors.

    Args:
        factors: The factors to intersect.

    Returns:
        The assembled clause.
    """
    return AndClause(factors=factors)


def test_each_term_kind_selects_what_the_structure_declares() -> None:
    """Every gradable term reads the field it names, and only that field."""
    snapshot = build_structure(EVALUATOR_SPEC)
    atoms = snapshot.states[0].atoms
    serial = {atom.serial: atom for atom in atoms}

    chain_a = selected_serials(
        snapshot, _expression(_clause(Factor(ChainTerm("A"))))
    )
    hetatm = selected_serials(
        snapshot, _expression(_clause(Factor(HetatmTerm())))
    )
    name_ca = selected_serials(
        snapshot, _expression(_clause(Factor(NameTerm("CA"))))
    )
    resn_ala = selected_serials(
        snapshot, _expression(_clause(Factor(ResnTerm("ALA"))))
    )

    assert chain_a == {s for s, a in serial.items() if a.chain == "A"}
    assert hetatm == {s for s, a in serial.items() if a.hetatm}
    assert name_ca == {s for s, a in serial.items() if a.name == "CA"}
    assert resn_ala == {s for s, a in serial.items() if a.resn == "ALA"}
    assert chain_a and hetatm and name_ca and resn_ala


def test_a_residue_range_is_inclusive_at_both_ends() -> None:
    """An exclusive upper bound would silently drop a residue."""
    snapshot = build_structure(EVALUATOR_SPEC)

    selected = selected_serials(
        snapshot, _expression(_clause(Factor(ResiTerm(2, 3))))
    )

    residues = {
        atom.resv
        for atom in snapshot.states[0].atoms
        if atom.serial in selected
    }
    assert residues == {2, 3}


def test_precedence_matches_the_typed_tree() -> None:
    """`not` binds inside a factor, `and` across a clause, `or` across clauses."""
    snapshot = build_structure(EVALUATOR_SPEC)
    atoms = snapshot.states[0].atoms

    negated = selected_serials(
        snapshot, _expression(_clause(Factor(HetatmTerm(), negated=True)))
    )
    intersection = selected_serials(
        snapshot,
        _expression(
            _clause(Factor(ChainTerm("A")), Factor(HetatmTerm(), negated=True))
        ),
    )
    union = selected_serials(
        snapshot,
        _expression(
            _clause(Factor(ChainTerm("A")), Factor(NameTerm("CA"))),
            _clause(Factor(HetatmTerm())),
        ),
    )

    assert negated == {a.serial for a in atoms if not a.hetatm}
    assert intersection == {
        a.serial for a in atoms if a.chain == "A" and not a.hetatm
    }
    assert union == {
        a.serial
        for a in atoms
        if (a.chain == "A" and a.name == "CA") or a.hetatm
    }


def test_membership_is_read_from_the_first_state_only() -> None:
    """No term is coordinate-dependent, so states cannot disagree."""
    snapshot = build_structure(EVALUATOR_SPEC)
    assert len(snapshot.states) > 1

    expression = _expression(_clause(Factor(ChainTerm("A"))))
    per_state = {
        frozenset(
            atom.serial
            for atom in state.atoms
            if atom_matches_expression(expression, atom)
        )
        for state in snapshot.states
    }

    assert per_state == {selected_serials(snapshot, expression)}


def test_an_empty_selection_is_reported_not_refused() -> None:
    """Selecting nothing is a real answer, not an error."""
    snapshot = build_structure(EVALUATOR_SPEC)

    assert (
        selected_serials(snapshot, _expression(_clause(Factor(ChainTerm("Z")))))
        == frozenset()
    )


def test_polymer_is_reported_unsupported_rather_than_guessed() -> None:
    """The snapshot format declares polymer classification unsupported.

    Returning False, or treating "not a hetero atom" as "polymer",
    would be a guess presented as ground truth.
    """
    expression = _expression(_clause(Factor(PolymerTerm())))

    assert unsupported_reasons(expression) == (
        UNSUPPORTED_POLYMER_CLASSIFICATION,
    )
    with pytest.raises(UnsupportedAssertionError, match="polymer"):
        selected_serials(build_structure(EVALUATOR_SPEC), expression)


def test_a_gradable_expression_reports_no_unsupported_reason() -> None:
    """Marking a gradable category unsupported would hide real coverage."""
    assert (
        unsupported_reasons(
            _expression(
                _clause(Factor(ChainTerm("A")), Factor(HetatmTerm())),
                _clause(Factor(ResiTerm(1, 4))),
            )
        )
        == ()
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
