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

from pathlib import Path

from pmc_core.plan import ChainTerm
from pmc_core.plan import HetatmTerm
from pmc_core.plan import NameTerm
from pmc_core.plan import PolymerTerm
from pmc_core.plan import ResiTerm
from pmc_core.plan import ResnTerm
from pmc_core.plan import SelectionExpression
from pmc_core.plan import TERM
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import ObjectSnapshot
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
