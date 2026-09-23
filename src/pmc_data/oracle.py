# Copyright 2026 PyMOL Copilot contributors.
"""Independent oracle predicting a plan's result without PyMOL.

This module never imports PyMOL and never calls a PyMOL selection query,
so everything it produces is ground truth that was not made by the
machinery it is used to grade.

It carries two derivations. `expected_chain_atom_ids` reads a controlled
PDB file's own records (via pmc_data.pdb) and serves the original
chain-A gold case. The rest evaluates `pmc_core.plan`'s typed selection
expressions directly against a `pmc_core.snapshot.ObjectSnapshot`, which
is what the generalized dataset pipeline predicts with: the snapshot is
authored outright by pmc_data.structures, so it is the oracle's input
rather than a PyMOL observation.

Where a prediction cannot be made it is refused, never guessed --
`unsupported_reasons()` reports that in advance and
`UnsupportedAssertionError` enforces it if a caller asks anyway.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path

from pmc_core.plan import ActionPlan
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import HetatmTerm
from pmc_core.plan import HideOperation
from pmc_core.plan import NamedSelection
from pmc_core.plan import NameTerm
from pmc_core.plan import OrientOperation
from pmc_core.plan import PolymerTerm
from pmc_core.plan import ResiTerm
from pmc_core.plan import ResnTerm
from pmc_core.plan import SelectionExpression
from pmc_core.plan import SelectOperation
from pmc_core.plan import ShowOperation
from pmc_core.plan import TARGET
from pmc_core.plan import TERM
from pmc_core.plan import referenced_selection_name
from pmc_core.snapshot import MOLECULE_REP_NAMES
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot
from pmc_data.colors import COLOR_INDEX_BY_NAME
from pmc_data.pdb import atom_ids_for_chain
from pmc_data.pdb import read_atoms


def expected_chain_atom_ids(pdb_path: Path, chain_id: str) -> frozenset[int]:
    """Derive the expected atom identities for one chain, independently.

    Args:
        pdb_path: Path to the controlled structure file.
        chain_id: The chain identifier to compute expected membership for.

    Returns:
        The frozen set of atom identities independently derived from the
        structure file's own chain field, never from a PyMOL selection.
    """
    atoms = read_atoms(pdb_path)
    return atom_ids_for_chain(atoms, chain_id)


#: The reason code recorded when a plan asks for the `polymer` flag.
#: `pmc_core.snapshot.DECLARED_UNSUPPORTED` already declares explicit
#: polymer classification outside the snapshot format, so there is no
#: observable ground truth to grade against. The term is legal to emit
#: and legal to execute; it is the *assertion* that cannot exist.
UNSUPPORTED_POLYMER_CLASSIFICATION = "polymer_classification"


class UnsupportedAssertionError(Exception):
    """Raised when the oracle is asked for a prediction it cannot make.

    Never caught and turned into a guess. A caller that wants to know in
    advance whether a plan is gradable asks `unsupported_reasons()`
    rather than provoking this.
    """


def atom_matches_term(term: TERM, atom: AtomRecord) -> bool:
    """Decide whether one atom matches one selection term.

    Args:
        term: The selection term to evaluate.
        atom: The atom record to test.

    Returns:
        True when the atom matches the term.

    Raises:
        UnsupportedAssertionError: If term is a PolymerTerm, whose flag
            the snapshot format does not carry, or a term type this
            function does not know -- fail closed rather than silently
            reporting no match, which would look like a correct empty
            selection.
    """
    match term:
        case ChainTerm():
            return atom.chain == term.chain_id
        case ResiTerm():
            if term.last is None:
                # A bare `resi N` is a literal residue-identifier match
                # in PyMOL, not a numeric one. Confirmed empirically
                # against real PyMOL: on a structure whose residue 1
                # carries insertion code A -- identifier "1A" --
                # `resi 1` matches no atom at all. A range is a
                # different comparison: `resi 1-999` does match "1A",
                # also confirmed. The command language cannot express
                # an insertion code at all (pmc_core.plan declares them
                # unsupported for ResiTerm), so `resi N` can only ever
                # mean the plain residue N.
                return atom.resv == term.first and atom.ins_code == ""
            return term.first <= atom.resv <= term.last
        case ResnTerm():
            return atom.resn == term.residue_name
        case NameTerm():
            return atom.name == term.atom_name
        case HetatmTerm():
            return atom.hetatm
        case PolymerTerm():
            raise UnsupportedAssertionError(
                "polymer classification is declared unsupported by the "
                "snapshot format; there is no ground truth to grade"
            )
        case _:
            raise UnsupportedAssertionError(
                f"unsupported selection term: {term!r}"
            )


def atom_matches_expression(
    expression: SelectionExpression, atom: AtomRecord
) -> bool:
    """Decide whether one atom matches a whole selection expression.

    The typed expression is already in disjunctive normal form -- `or`
    across clauses, `and` across factors, `not` inside a factor -- so
    this is a direct structural recursion over that shape rather than a
    second opinion about precedence.

    Args:
        expression: The selection expression to evaluate.
        atom: The atom record to test.

    Returns:
        True when the atom matches the expression.

    Raises:
        UnsupportedAssertionError: If the expression holds a term the
            oracle cannot predict.
    """
    for clause in expression.clauses:
        if all(
            atom_matches_term(factor.term, atom) != factor.negated
            for factor in clause.factors
        ):
            return True
    return False


def selected_serials(
    snapshot: ObjectSnapshot, expression: SelectionExpression
) -> frozenset[int]:
    """Derive the atom identities one expression selects, independently.

    Membership is read off the snapshot's first state: every state
    carries the same atoms and differs only in coordinates, and no term
    in the language is coordinate-dependent.

    Args:
        snapshot: The structure to select within.
        expression: The selection expression to evaluate.

    Returns:
        The frozen set of atom serial numbers the expression matches.

    Raises:
        UnsupportedAssertionError: If the expression holds a term the
            oracle cannot predict.
    """
    return frozenset(
        atom.serial
        for atom in snapshot.states[0].atoms
        if atom_matches_expression(expression, atom)
    )


def unsupported_reasons(expression: SelectionExpression) -> tuple[str, ...]:
    """Report why an expression cannot be graded, before evaluating it.

    This is how a caller distinguishes "the oracle cannot grade this"
    from "the oracle graded this and it failed". A category the oracle
    cannot grade is reported as unsupported, never guessed.

    Args:
        expression: The selection expression to inspect.

    Returns:
        The deduplicated reason codes, in first-appearance order; empty
        when the whole expression is gradable.
    """
    reasons: list[str] = []
    for clause in expression.clauses:
        for factor in clause.factors:
            if (
                isinstance(factor.term, PolymerTerm)
                and UNSUPPORTED_POLYMER_CLASSIFICATION not in reasons
            ):
                reasons.append(UNSUPPORTED_POLYMER_CLASSIFICATION)
    return tuple(reasons)


#: The reason code recorded when a plan orients the camera. `orient`
#: changes only `ObjectSnapshot.view`, and predicting PyMOL's exact view
#: matrix would mean reimplementing its principal-axis fit and zoom to
#: float equality. That is a guess, so it is not attempted -- but the
#: view is inside the fingerprint the executor compares, so a plan that
#: orients cannot be fingerprint-graded at all.
UNSUPPORTED_CAMERA_VIEW = "camera_view"

#: Prefix of the reason code recorded when a plan shows or hides a
#: representation the snapshot format does not record. The command is
#: legal and executes; there is simply nothing observable to assert
#: about it afterwards.
UNOBSERVABLE_REPRESENTATION_PREFIX = "unobservable_representation:"


@dataclass(frozen=True)
class ExpectedOutcome:
    """What the oracle predicts one plan does to one structure.

    Attributes:
        snapshot: The predicted resulting snapshot, or None when it
            cannot be predicted at all. A caller must pass the
            fingerprint of this value to the executor only when it is
            not None; there is deliberately no "best effort" snapshot.
        selection_counts: The predicted (name, atom count) of every
            selection the plan names, in the executor's own
            first-appearance order. Empty when nothing is predictable.
        unsupported: The assertions that could not be evaluated, named
            rather than silently omitted.
    """

    snapshot: ObjectSnapshot | None
    selection_counts: tuple[tuple[str, int], ...]
    unsupported: tuple[str, ...]


def _ordered_reps(reps: frozenset[str]) -> tuple[str, ...]:
    """Put representation names in the order extraction reports them.

    `pmc_core.snapshot.extract` builds each atom's `reps` by walking
    MOLECULE_REP_NAMES in order, so a prediction that used any other
    order would differ from the real extraction in bytes while naming
    the same set.

    Args:
        reps: The representations the atom is shown in.

    Returns:
        Those names, in MOLECULE_REP_NAMES order.
    """
    return tuple(name for name in MOLECULE_REP_NAMES if name in reps)


def _target_serials(
    snapshot: ObjectSnapshot,
    target: TARGET,
    selections: Mapping[str, frozenset[int]],
) -> frozenset[int]:
    """Resolve what a command acts on to a set of atom identities.

    Args:
        snapshot: The structure being acted on.
        target: The command's target, a named selection or expression.
        selections: The selections earlier commands in the plan created.

    Returns:
        The atom serial numbers the target resolves to.

    Raises:
        UnsupportedAssertionError: If the target names a selection no
            earlier command created. Policy already rejects such a
            plan, so reaching this means the plan bypassed it.
    """
    if isinstance(target, NamedSelection):
        if target.name not in selections:
            raise UnsupportedAssertionError(
                f"plan references undefined selection {target.name!r}"
            )
        return selections[target.name]
    return selected_serials(snapshot, target)


def _plan_unsupported_reasons(plan: ActionPlan) -> tuple[str, ...]:
    """Report every assertion a plan makes impossible, before predicting.

    Args:
        plan: The typed plan to inspect.

    Returns:
        The deduplicated reason codes, in first-appearance order.
    """
    reasons: list[str] = []

    def note(reason: str) -> None:
        """Record a reason once.

        Args:
            reason: The reason code to record.
        """
        if reason not in reasons:
            reasons.append(reason)

    for operation in plan.operations:
        expression: SelectionExpression | None = None
        if isinstance(operation, SelectOperation):
            expression = operation.expression
        elif isinstance(
            getattr(operation, "target", None), SelectionExpression
        ):
            expression = operation.target  # pyrefly: ignore.
        if expression is not None:
            for reason in unsupported_reasons(expression):
                note(reason)
        if isinstance(operation, OrientOperation):
            note(UNSUPPORTED_CAMERA_VIEW)
        if isinstance(operation, ShowOperation | HideOperation) and (
            operation.representation not in MOLECULE_REP_NAMES
        ):
            note(UNOBSERVABLE_REPRESENTATION_PREFIX + operation.representation)
    return tuple(reasons)


def apply_plan(snapshot: ObjectSnapshot, plan: ActionPlan) -> ExpectedOutcome:
    """Predict a plan's whole result against one structure, without PyMOL.

    The returned snapshot is what `pmc_core.snapshot.extract` must
    report after the plan runs, so its `to_json` hash is exactly the
    `expected_resulting_fingerprint` the executor compares against.

    Per verb: `select` changes nothing about the object and only binds a
    name; `color` sets every matching atom's color index in every
    state; `show` and `hide` add or remove a representation; `orient`
    moves only the camera, which is why it is unpredictable.

    Args:
        snapshot: The structure the plan runs against.
        plan: The typed plan to predict.

    Returns:
        The prediction. `snapshot` is None whenever the result cannot be
        predicted exactly, and `unsupported` says why.

    Raises:
        UnsupportedAssertionError: If the plan references a selection no
            earlier command created, which policy already forbids.
    """
    unsupported = _plan_unsupported_reasons(plan)
    if UNSUPPORTED_POLYMER_CLASSIFICATION in unsupported:
        # Nothing about this plan is predictable: the oracle cannot even
        # say which atoms the selection holds, so neither the resulting
        # state nor the selection counts can be claimed.
        return ExpectedOutcome(
            snapshot=None, selection_counts=(), unsupported=unsupported
        )

    # Atom state is per-object, not per-state: color and representation
    # membership are read once by extraction and repeated into every
    # state, so an edit is applied at the same position in each.
    per_state: list[list[AtomRecord]] = [
        list(state.atoms) for state in snapshot.states
    ]
    position_of_serial = {
        atom.serial: index
        for index, atom in enumerate(snapshot.states[0].atoms)
    }
    selections: dict[str, frozenset[int]] = {}
    counts: dict[str, int] = {}

    def edit(
        serials: frozenset[int], change: Callable[[AtomRecord], AtomRecord]
    ) -> None:
        """Apply one per-atom change across every state.

        Args:
            serials: The atom identities to change.
            change: The replacement applied to each matching record.
        """
        for serial in serials:
            index = position_of_serial[serial]
            for atoms in per_state:
                atoms[index] = change(atoms[index])

    for operation in plan.operations:
        match operation:
            case SelectOperation():
                serials = selected_serials(snapshot, operation.expression)
                selections[operation.selection_name] = serials
                counts.setdefault(operation.selection_name, len(serials))
            case ColorOperation():
                index = COLOR_INDEX_BY_NAME[operation.color]
                edit(
                    _target_serials(snapshot, operation.target, selections),
                    lambda atom, index=index: replace(atom, color=index),
                )
            case ShowOperation():
                if operation.representation in MOLECULE_REP_NAMES:
                    rep = operation.representation
                    edit(
                        _target_serials(snapshot, operation.target, selections),
                        lambda atom, rep=rep: replace(
                            atom,
                            reps=_ordered_reps(frozenset(atom.reps) | {rep}),
                        ),
                    )
            case HideOperation():
                if operation.representation in MOLECULE_REP_NAMES:
                    rep = operation.representation
                    edit(
                        _target_serials(snapshot, operation.target, selections),
                        lambda atom, rep=rep: replace(
                            atom,
                            reps=_ordered_reps(frozenset(atom.reps) - {rep}),
                        ),
                    )
            case OrientOperation():
                # Only the camera moves; no atom state changes. The view
                # itself is what cannot be predicted.
                pass
            case _:
                raise UnsupportedAssertionError(
                    f"unsupported operation: {operation!r}"
                )
        referenced = referenced_selection_name(operation)
        if referenced is not None:
            counts.setdefault(referenced, len(selections[referenced]))

    predicted = None
    if UNSUPPORTED_CAMERA_VIEW not in unsupported:
        predicted = replace(
            snapshot,
            states=tuple(
                StateSnapshot(atoms=tuple(atoms)) for atoms in per_state
            ),
        )
    return ExpectedOutcome(
        snapshot=predicted,
        selection_counts=tuple(counts.items()),
        unsupported=unsupported,
    )
