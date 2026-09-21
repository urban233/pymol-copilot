# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL differential evidence for the generalized oracle.

The oracle predicts what a selection expression matches without PyMOL.
Whether that prediction is *right* cannot be settled by more Python: it
is a claim about Open-Source PyMOL's own selection semantics, so it is
settled here, against real headless PyMOL, by reconstructing a
controlled structure and comparing the oracle's serial set against what
`cmd.iterate` actually reports for the same expression.

This is the test that would catch a wrong reading of PyMOL -- a `resi`
range that is exclusive rather than inclusive, a `resn` comparison that
should have been case-folded, or a `hetatm` flag that does not survive
reconstruction through `pseudoatom`.

Every collaborator is real: real headless PyMOL, the real
`pmc_core.snapshot.reconstruct`, and the real controlled structures the
corpus is built from. Nothing here is a PyMOL test double.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
import sys
from collections.abc import Iterator
from typing import Any

import pytest

import winstage

from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import Factor
from pmc_core.plan import HetatmTerm
from pmc_core.plan import NameTerm
from pmc_core.plan import ResiTerm
from pmc_core.plan import ResnTerm
from pmc_core.plan import SelectionExpression
from pmc_core.snapshot import reconstruct
from pmc_data.oracle import selected_serials
from pmc_data.structures import OBJECT_NAME
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

#: The seed the admission gate and the corpus run both use.
SEED = 20260921


def _clause(*factors: Factor) -> AndClause:
    """Build one and-clause from its factors.

    Args:
        factors: The factors to intersect.

    Returns:
        The assembled clause.
    """
    return AndClause(factors=factors)


def _expression(*clauses: AndClause) -> SelectionExpression:
    """Build one selection expression from its clauses.

    Args:
        clauses: The clauses to union.

    Returns:
        The assembled expression.
    """
    return SelectionExpression(clauses=clauses)


#: Expressions covering every gradable term kind and every boolean
#: shape the language can express: a bare term, a negated term, an
#: intersection, a union, and a union of intersections.
EXPRESSIONS: tuple[SelectionExpression, ...] = (
    _expression(_clause(Factor(ChainTerm("A")))),
    _expression(_clause(Factor(ChainTerm("B")))),
    _expression(_clause(Factor(ChainTerm("A"), negated=True))),
    _expression(_clause(Factor(ResiTerm(1)))),
    _expression(_clause(Factor(ResiTerm(2, 4)))),
    _expression(_clause(Factor(ResiTerm(1, 999)))),
    _expression(_clause(Factor(ResiTerm(901, 902)))),
    _expression(_clause(Factor(ResnTerm("ALA")))),
    _expression(_clause(Factor(ResnTerm("GLY")))),
    _expression(_clause(Factor(ResnTerm("ZN")))),
    _expression(_clause(Factor(ResnTerm("HOH")))),
    _expression(_clause(Factor(NameTerm("CA")))),
    _expression(_clause(Factor(NameTerm("CB")))),
    _expression(_clause(Factor(NameTerm("N"), negated=True))),
    _expression(_clause(Factor(HetatmTerm()))),
    _expression(_clause(Factor(HetatmTerm(), negated=True))),
    _expression(_clause(Factor(ChainTerm("A")), Factor(ResnTerm("ALA")))),
    _expression(
        _clause(Factor(ChainTerm("A")), Factor(HetatmTerm(), negated=True))
    ),
    _expression(
        _clause(Factor(ChainTerm("A")), Factor(NameTerm("CA"))),
        _clause(Factor(HetatmTerm())),
    ),
    _expression(
        _clause(Factor(ChainTerm("A")), Factor(ResiTerm(1, 2))),
        _clause(Factor(ChainTerm("B")), Factor(ResiTerm(3, 4))),
    ),
    _expression(
        _clause(
            Factor(ChainTerm("A")),
            Factor(NameTerm("CA")),
            Factor(ResnTerm("GLY"), negated=True),
        )
    ),
)

#: The structures the differential runs against. Reconstruction is the
#: expensive part, so this is the richest handful rather than the whole
#: matrix: every declared feature -- several chains, hetero atoms,
#: several states, alternate locations and insertion codes -- appears at
#: least once across them.
DIFFERENTIAL_SPEC_IDS = (
    "everything_small",
    "everything_four_chains",
    "altloc_and_hetatm",
    "insertion_and_hetatm",
    "two_chains_hetatm",
)

SPECS = tuple(
    spec
    for spec in enumerate_structures(SEED)
    if spec.spec_id in DIFFERENTIAL_SPEC_IDS
)


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[Any]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL cmd module.
    """
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


def _pymol_serials(cmd: Any, rendered: str) -> frozenset[int]:
    """Read the atom identities real PyMOL matches for an expression.

    Uses the uppercase `ID` namespace field, the loaded structure's own
    serial number, for the same reason pmc_data.verifier does: PyMOL's
    `index` is a per-session ordinal and comparing it against the
    oracle's serial-based prediction would mis-grade a correct
    selection.

    Args:
        cmd: The real PyMOL cmd module.
        rendered: The canonical selection expression text.

    Returns:
        The frozen set of serial numbers PyMOL matches.
    """
    serials: list[int] = []
    cmd.iterate(
        f"{OBJECT_NAME} and ({rendered})",
        "serials.append(ID)",
        space={"serials": serials},
    )
    return frozenset(serials)


@pytest.mark.parametrize("spec", SPECS, ids=[s.spec_id for s in SPECS])
def test_membership_agrees_with_real_pymol(spec: Any, real_pymol: Any) -> None:
    """Every expression must select exactly what real PyMOL selects.

    Args:
        spec: The controlled structure spec under test.
        real_pymol: The real PyMOL cmd module.
    """
    snapshot = build_structure(spec)
    reconstruct(real_pymol, snapshot)
    real_pymol.sync()
    try:
        disagreements: list[str] = []
        for expression in EXPRESSIONS:
            rendered = expression.render()
            predicted = selected_serials(snapshot, expression)
            observed = _pymol_serials(real_pymol, rendered)
            if predicted != observed:
                disagreements.append(
                    f"{rendered!r}: predicted={sorted(predicted)} "
                    f"observed={sorted(observed)}"
                )
    finally:
        real_pymol.delete(OBJECT_NAME)

    assert disagreements == [], (
        f"{spec.spec_id}: the oracle disagrees with real PyMOL"
    )


@pytest.mark.parametrize("spec", SPECS, ids=[s.spec_id for s in SPECS])
def test_the_differential_is_not_vacuous(spec: Any) -> None:
    """Agreement is only evidence if the expressions match something.

    An expression set that selected nothing would agree with PyMOL
    perfectly and prove nothing at all. Some expressions are expected
    to be empty on some structures -- `chain B` on a one-chain
    structure, or `resi 1` where residue 1 carries an insertion code --
    so this asserts a healthy majority match rather than all of them,
    and that something covers the whole structure.

    Args:
        spec: The controlled structure spec under test.
    """
    snapshot = build_structure(spec)
    total_atoms = len(snapshot.states[0].atoms)
    matched = [
        len(selected_serials(snapshot, expression))
        for expression in EXPRESSIONS
    ]

    assert sum(1 for count in matched if count > 0) >= len(EXPRESSIONS) // 2, (
        f"{spec.spec_id}: most expressions select nothing: {matched}"
    )
    assert max(matched) == total_atoms, (
        f"{spec.spec_id}: no expression selects the whole structure"
    )


def test_every_expression_matches_somewhere() -> None:
    """No expression in the set may be dead weight on every structure.

    An expression that selects nothing everywhere contributes no
    evidence, and would quietly stop covering the term it was added
    for if a structure change made it unsatisfiable.
    """
    snapshots = [build_structure(spec) for spec in SPECS]

    never_matched = [
        expression.render()
        for expression in EXPRESSIONS
        if not any(
            selected_serials(snapshot, expression) for snapshot in snapshots
        )
    ]

    assert never_matched == []


if __name__ == "__main__":
    code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    # Real PyMOL's shutdown can clobber a failing exit code, the same
    # reason tests/data/test_gold_case_verifier.py exits this way.
    os._exit(code)
