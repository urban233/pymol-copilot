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
from pmc_core.executor import STATUS_OK
from pmc_core.plan import ActionPlan
from pmc_core.plan import ColorOperation
from pmc_core.plan import HideOperation
from pmc_core.plan import NamedSelection
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectOperation
from pmc_core.plan import ShowOperation
from pmc_core.snapshot import extract
from pmc_core.snapshot import diff
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.oracle import UNSUPPORTED_CAMERA_VIEW
from pmc_data.oracle import apply_plan
from pmc_data.oracle import selected_serials
from pmc_sidecar.child import run_plan
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


#: Plans covering every verb and every target form the language has: a
#: bare expression target, a named-selection target, several selections
#: in one plan, and a show/hide pair whose order decides the result.
_CHAIN_A = _expression(_clause(Factor(ChainTerm("A"))))
_HETATM = _expression(_clause(Factor(HetatmTerm())))
_BACKBONE = _expression(
    _clause(Factor(NameTerm("CA"))), _clause(Factor(NameTerm("N")))
)

PREDICTABLE_PLANS: tuple[tuple[str, ActionPlan], ...] = (
    (
        "select_then_color_named",
        ActionPlan(
            operations=(
                SelectOperation(
                    selection_name="copilot_target", expression=_CHAIN_A
                ),
                ColorOperation(
                    color="red", target=NamedSelection("copilot_target")
                ),
            )
        ),
    ),
    (
        "color_an_expression_directly",
        ActionPlan(operations=(ColorOperation(color="blue", target=_HETATM),)),
    ),
    (
        "show_cartoon",
        ActionPlan(
            operations=(
                ShowOperation(representation="cartoon", target=_CHAIN_A),
            )
        ),
    ),
    (
        "hide_the_starting_representation",
        ActionPlan(
            operations=(HideOperation(representation="lines", target=_CHAIN_A),)
        ),
    ),
    (
        "show_then_hide_the_same_representation",
        ActionPlan(
            operations=(
                ShowOperation(representation="spheres", target=_BACKBONE),
                HideOperation(representation="spheres", target=_BACKBONE),
            )
        ),
    ),
    (
        "two_selections_and_two_colors",
        ActionPlan(
            operations=(
                SelectOperation(
                    selection_name="copilot_first", expression=_CHAIN_A
                ),
                SelectOperation(
                    selection_name="copilot_second", expression=_HETATM
                ),
                ColorOperation(
                    color="green", target=NamedSelection("copilot_first")
                ),
                ColorOperation(
                    color="magenta", target=NamedSelection("copilot_second")
                ),
                ShowOperation(
                    representation="sticks",
                    target=NamedSelection("copilot_first"),
                ),
            )
        ),
    ),
    (
        "color_everything_then_recolor_a_part",
        ActionPlan(
            operations=(
                ColorOperation(
                    color="white",
                    target=_expression(
                        _clause(Factor(HetatmTerm(), negated=True)),
                        _clause(Factor(HetatmTerm())),
                    ),
                ),
                ColorOperation(color="orange", target=_HETATM),
            )
        ),
    ),
)

#: The structure the plan predictions run against. Rich enough to have
#: several chains, hetero atoms, altlocs, insertion codes and two
#: states, so a prediction has every field kind to get wrong.
PLAN_SPEC = next(
    spec
    for spec in enumerate_structures(SEED)
    if spec.spec_id == "everything_small"
)


@pytest.fixture
def reconstructed(real_pymol: Any) -> Iterator[Any]:
    """Rebuild the plan structure fresh for one test and delete it after.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module with the structure reconstructed.
    """
    reconstruct(real_pymol, build_structure(PLAN_SPEC))
    real_pymol.sync()
    try:
        yield real_pymol
    finally:
        real_pymol.delete(OBJECT_NAME)
        for name in ("copilot_target", "copilot_first", "copilot_second"):
            real_pymol.delete(name)


@pytest.mark.parametrize(
    ("label", "plan"),
    PREDICTABLE_PLANS,
    ids=[label for label, _ in PREDICTABLE_PLANS],
)
def test_predicted_snapshot_matches_extraction(
    label: str, plan: ActionPlan, reconstructed: Any
) -> None:
    """The predicted snapshot must be what extraction actually reports.

    This is the claim the executor's fidelity gate rests on: the
    oracle's `to_json` hash is handed in as
    `expected_resulting_fingerprint`, so anything less than byte
    equality here means every sample in the category is rejected.

    Args:
        label: The plan's descriptive identity.
        plan: The typed plan to run.
        reconstructed: Real PyMOL with the structure already rebuilt.
    """
    snapshot = build_structure(PLAN_SPEC)
    expected = apply_plan(snapshot, plan)
    assert expected.snapshot is not None, f"{label}: nothing predicted"

    result = run_plan(reconstructed, plan)
    reconstructed.sync()
    assert result.status == STATUS_OK, f"{label}: {result.command_outcomes}"

    extracted = extract(reconstructed, OBJECT_NAME)

    assert diff(expected.snapshot, extracted) == [], f"{label}: fields differ"
    assert to_json(extracted) == to_json(expected.snapshot), (
        f"{label}: prediction differs from extraction in bytes"
    )


@pytest.mark.parametrize(
    ("label", "plan"),
    PREDICTABLE_PLANS,
    ids=[label for label, _ in PREDICTABLE_PLANS],
)
def test_predicted_selection_counts_match_real_pymol(
    label: str, plan: ActionPlan, reconstructed: Any
) -> None:
    """Counts are the only assertion available for an unpredictable plan.

    They are also the check that `cmd.count_atoms` counts an atom once
    rather than once per state, which the oracle assumes when it reads
    membership off the first state alone.

    Args:
        label: The plan's descriptive identity.
        plan: The typed plan to run.
        reconstructed: Real PyMOL with the structure already rebuilt.
    """
    expected = apply_plan(build_structure(PLAN_SPEC), plan)

    result = run_plan(reconstructed, plan)
    reconstructed.sync()
    assert result.status == STATUS_OK, f"{label}: {result.command_outcomes}"

    observed = tuple(
        (name, reconstructed.count_atoms(name))
        for name, _ in expected.selection_counts
    )

    assert observed == expected.selection_counts


def test_orient_changes_only_the_camera(reconstructed: Any) -> None:
    """The oracle refuses to predict the view; this says what it may claim.

    `orient` is marked unsupported because PyMOL's view matrix cannot
    be predicted without reimplementing its principal-axis fit. What
    can be asserted is the rest: nothing structural moves, and the
    camera really did.

    Args:
        reconstructed: Real PyMOL with the structure already rebuilt.
    """
    snapshot = build_structure(PLAN_SPEC)
    plan = ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_target", expression=_CHAIN_A
            ),
            OrientOperation(target=NamedSelection("copilot_target")),
        )
    )
    expected = apply_plan(snapshot, plan)

    assert expected.snapshot is None
    assert UNSUPPORTED_CAMERA_VIEW in expected.unsupported

    result = run_plan(reconstructed, plan)
    reconstructed.sync()
    assert result.status == STATUS_OK

    extracted = extract(reconstructed, OBJECT_NAME)

    assert structure_digest(extracted) == structure_digest(snapshot), (
        "orient changed structural state, not only the camera"
    )
    assert extracted.view != snapshot.view, "orient did not move the camera"


if __name__ == "__main__":
    code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    # Real PyMOL's shutdown can clobber a failing exit code, the same
    # reason tests/data/test_gold_case_verifier.py exits this way.
    os._exit(code)
