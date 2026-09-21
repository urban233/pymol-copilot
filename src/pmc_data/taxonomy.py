# Copyright 2026 PyMOL Copilot contributors.
"""Plan enumeration and the category taxonomy the report is grouped by.

This module turns one controlled structure into the plans the corpus is
generated from, each labelled with a category, a difficulty and a
templated natural-language intent.

Two properties matter more than breadth. **Categories are derived from
the plan's own shape** -- its verbs, its term kinds and its boolean
composition -- rather than hand-labelled at the call site, so the
per-category rejection report cannot drift from what was actually
generated. And **terms are instantiated from the structure's real
content**: a plan selects a chain the structure has and a residue name
it carries, so an empty result means the oracle and PyMOL disagree
rather than that the plan asked for something absent.

Intents are templated from the plan, not written by a teacher model.
Item 14 is program-first for each verb, and teacher back-translation
stays out of scope exactly as it already is for the chain-A pipeline.

Plans are emitted to satisfy `pmc_core.policy` by construction: a
selection is always created before it is referenced, no name is
created twice, and no plan approaches MAX_COMMANDS.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import itertools
import random
from dataclasses import dataclass

from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
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
from pmc_core.plan import TERM
from pmc_core.plan import COLOR_ALLOWLIST
from pmc_core.plan import OPERATION
from pmc_core.plan import REPRESENTATION_ALLOWLIST
from pmc_core.snapshot import MOLECULE_REP_NAMES
from pmc_core.snapshot import ObjectSnapshot

#: Difficulty labels, assigned from the plan's own shape.
DIFFICULTY_BASIC = "basic"
DIFFICULTY_INTERMEDIATE = "intermediate"
DIFFICULTY_ADVANCED = "advanced"

#: How many colors and representations each expression is paired with.
#: Small on purpose: breadth comes from the expression and verb axes,
#: and pairing every expression with all 177 colors would bury every
#: other category in the report.
_COLORS_PER_EXPRESSION = 4
_REPRESENTATIONS_PER_EXPRESSION = 3

#: The four representations that are legal to emit but absent from
#: `pmc_core.snapshot.MOLECULE_REP_NAMES`, so nothing observable
#: follows from showing one. Generated deliberately, so the report can
#: state they are unsupported rather than leave them missing.
UNOBSERVABLE_REPRESENTATIONS = tuple(
    name for name in REPRESENTATION_ALLOWLIST if name not in MOLECULE_REP_NAMES
)


@dataclass(frozen=True)
class PlanCandidate:
    """One plan to attempt, with the labels its sample will carry.

    Attributes:
        plan: The typed plan to verify.
        category: The taxonomy category, derived from the plan's shape.
        difficulty: The difficulty label, derived the same way.
        intent: The templated natural-language intent.
    """

    plan: ActionPlan
    category: str
    difficulty: str
    intent: str


def _terms_of(plan: ActionPlan) -> tuple[TERM, ...]:
    """Collect every selection term a plan mentions, in order.

    Args:
        plan: The plan to inspect.

    Returns:
        The terms, including repeats.
    """
    terms: list[TERM] = []
    for operation in plan.operations:
        expression: SelectionExpression | None = None
        if isinstance(operation, SelectOperation):
            expression = operation.expression
        elif isinstance(
            getattr(operation, "target", None), SelectionExpression
        ):
            expression = operation.target  # pyrefly: ignore.
        if expression is None:
            continue
        for clause in expression.clauses:
            terms.extend(factor.term for factor in clause.factors)
    return tuple(terms)


def _expressions_of(plan: ActionPlan) -> tuple[SelectionExpression, ...]:
    """Collect every selection expression a plan holds.

    Args:
        plan: The plan to inspect.

    Returns:
        The expressions, in operation order.
    """
    expressions: list[SelectionExpression] = []
    for operation in plan.operations:
        if isinstance(operation, SelectOperation):
            expressions.append(operation.expression)
        elif isinstance(
            getattr(operation, "target", None), SelectionExpression
        ):
            expressions.append(operation.target)  # pyrefly: ignore.
    return tuple(expressions)


def _verb_of(operation: OPERATION) -> str:
    """Name the verb one operation renders as.

    Args:
        operation: The operation to name.

    Returns:
        The verb text.

    Raises:
        ValueError: If the operation is not one of the five verbs.
    """
    match operation:
        case SelectOperation():
            return "select"
        case ColorOperation():
            return "color"
        case ShowOperation():
            return "show"
        case HideOperation():
            return "hide"
        case OrientOperation():
            return "orient"
        case _:
            raise ValueError(f"unsupported operation: {operation!r}")


def _shape_of(plan: ActionPlan) -> str:
    """Describe a plan's boolean composition in one token.

    Args:
        plan: The plan to inspect.

    Returns:
        One of "none", "single", "and", "or", "and_or", with "+not"
        appended when any factor is negated.
    """
    expressions = _expressions_of(plan)
    if not expressions:
        return "none"
    has_or = any(len(e.clauses) > 1 for e in expressions)
    has_and = any(
        len(clause.factors) > 1 for e in expressions for clause in e.clauses
    )
    has_not = any(
        factor.negated
        for e in expressions
        for clause in e.clauses
        for factor in clause.factors
    )
    if has_or and has_and:
        shape = "and_or"
    elif has_or:
        shape = "or"
    elif has_and:
        shape = "and"
    else:
        shape = "single"
    return shape + "+not" if has_not else shape


def categorize(plan: ActionPlan) -> str:
    """Derive a plan's taxonomy category from the plan itself.

    Deriving rather than labelling is the point: a category that was
    passed in alongside the plan could describe something the plan does
    not do, and the rejection report would then group honestly-measured
    results under a dishonest heading.

    Args:
        plan: The plan to categorize.

    Returns:
        The category, as "<verbs>/<terms>/<shape>".
    """
    verbs = sorted({_verb_of(operation) for operation in plan.operations})
    keywords = sorted({type(term).KEYWORD for term in _terms_of(plan)})
    return f"{'+'.join(verbs)}/{'+'.join(keywords) or 'none'}/{_shape_of(plan)}"


def difficulty_of(plan: ActionPlan) -> str:
    """Derive a plan's difficulty label from its own shape.

    Args:
        plan: The plan to label.

    Returns:
        One of the DIFFICULTY_* labels.
    """
    terms = _terms_of(plan)
    shape = _shape_of(plan)
    if len(plan.operations) >= 3 or "or" in shape or len(terms) >= 3:
        return DIFFICULTY_ADVANCED
    if len(plan.operations) == 2 or len(terms) == 2 or "not" in shape:
        return DIFFICULTY_INTERMEDIATE
    return DIFFICULTY_BASIC


def _describe_term(term: TERM) -> str:
    """Render one term as the words an intent would use.

    Args:
        term: The term to describe.

    Returns:
        The description.

    Raises:
        ValueError: If the term is not one of the six accepted kinds.
    """
    match term:
        case ChainTerm():
            return f"chain {term.chain_id}"
        case ResiTerm():
            if term.last is None:
                return f"residue {term.first}"
            return f"residues {term.first} to {term.last}"
        case ResnTerm():
            return f"{term.residue_name} residues"
        case NameTerm():
            return f"{term.atom_name} atoms"
        case HetatmTerm():
            return "hetero atoms"
        case PolymerTerm():
            return "polymer atoms"
        case _:
            raise ValueError(f"unsupported selection term: {term!r}")


def describe_expression(expression: SelectionExpression) -> str:
    """Render a whole expression as the words an intent would use.

    Args:
        expression: The expression to describe.

    Returns:
        The description.
    """
    return " or ".join(
        " and ".join(
            (
                f"not {_describe_term(factor.term)}"
                if factor.negated
                else _describe_term(factor.term)
            )
            for factor in clause.factors
        )
        for clause in expression.clauses
    )


def _resi_terms(residues: list[int], plain_residues: list[int]) -> list[TERM]:
    """Draw the residue terms one structure is exercised with.

    Only residues without an insertion code get a bare `resi N`: that
    form is a literal identifier match in PyMOL, so `resi 3` selects
    nothing when residue 3's identifier is "3A". A range is a numeric
    comparison and has no such restriction.

    Args:
        residues: Every polymer residue number in the structure.
        plain_residues: Those without an insertion code.

    Returns:
        The residue terms to draw from.
    """
    terms: list[TERM] = [ResiTerm(resv) for resv in plain_residues[:3]]
    terms.append(ResiTerm(residues[0], residues[-1]))
    if len(residues) > 2:
        terms.append(ResiTerm(residues[0], residues[len(residues) // 2]))
    return terms


def _structure_terms(snapshot: ObjectSnapshot) -> dict[str, list[TERM]]:
    """Draw terms that actually match something in one structure.

    A term instantiated from an allowlist rather than from the
    structure would select nothing, and an empty result grades as
    agreement no matter what the oracle does.

    Args:
        snapshot: The structure to draw from.

    Returns:
        Candidate terms, grouped by their keyword.
    """
    atoms = snapshot.states[0].atoms
    chains = sorted({atom.chain for atom in atoms})
    residues = sorted({atom.resv for atom in atoms if not atom.hetatm})
    plain_residues = sorted(
        {atom.resv for atom in atoms if not atom.hetatm and not atom.ins_code}
    )
    names = sorted({atom.name for atom in atoms})
    resns = sorted({atom.resn for atom in atoms})
    drawn: dict[str, list[TERM]] = {
        "chain": [ChainTerm(chain) for chain in chains],
        # Only residues without an insertion code: a bare `resi N` is a
        # literal identifier match in PyMOL, so `resi 3` selects nothing
        # when residue 3's identifier is "3A". A range is a numeric
        # comparison and has no such restriction.
        "resi": _resi_terms(residues, plain_residues),
        "resn": [ResnTerm(resn) for resn in resns],
        "name": [NameTerm(name) for name in names],
        "polymer": [PolymerTerm()],
    }
    if any(atom.hetatm for atom in atoms):
        drawn["hetatm"] = [HetatmTerm()]
    return drawn


def _candidate_expressions(
    snapshot: ObjectSnapshot, rng: random.Random
) -> tuple[SelectionExpression, ...]:
    """Build the expression set one structure is exercised with.

    Covers each term kind on its own, a negation, an intersection, a
    union, and a union of intersections -- every shape the language can
    express, since it has no parentheses.

    Args:
        snapshot: The structure to draw terms from.
        rng: The seeded source of choices.

    Returns:
        The expressions, deduplicated by their canonical rendering.
    """
    drawn = _structure_terms(snapshot)
    expressions: list[SelectionExpression] = []

    def add(*clauses: AndClause) -> None:
        """Append one expression.

        Args:
            clauses: The clauses to union.
        """
        expressions.append(SelectionExpression(clauses=clauses))

    for terms in drawn.values():
        for term in terms:
            add(AndClause(factors=(Factor(term),)))

    chains = drawn["chain"]
    resns = drawn["resn"]
    names = drawn["name"]
    hetatm = drawn.get("hetatm")

    add(AndClause(factors=(Factor(rng.choice(chains), negated=True),)))
    if hetatm:
        add(AndClause(factors=(Factor(hetatm[0], negated=True),)))
        add(
            AndClause(
                factors=(Factor(chains[0]), Factor(hetatm[0], negated=True))
            )
        )
    add(AndClause(factors=(Factor(chains[0]), Factor(rng.choice(resns)))))
    add(AndClause(factors=(Factor(chains[0]), Factor(rng.choice(names)))))
    if len(chains) > 1:
        add(
            AndClause(factors=(Factor(chains[0]),)),
            AndClause(factors=(Factor(chains[1]),)),
        )
        add(
            AndClause(factors=(Factor(chains[0]), Factor(rng.choice(names)))),
            AndClause(factors=(Factor(chains[1]),)),
        )
    add(
        AndClause(factors=(Factor(rng.choice(resns)),)),
        AndClause(factors=(Factor(rng.choice(names)),)),
    )

    unique: dict[str, SelectionExpression] = {}
    for expression in expressions:
        unique.setdefault(expression.render(), expression)
    return tuple(unique.values())


def _named(index: int) -> str:
    """Build a legal selection name for one plan.

    Args:
        index: The plan's position within its structure's enumeration.

    Returns:
        A name matching the copilot_ prefix and body rules.
    """
    return f"copilot_sel{index:04d}"


def _candidate(plan: ActionPlan, intent: str) -> PlanCandidate:
    """Label one plan with its derived category and difficulty.

    Args:
        plan: The plan to label.
        intent: The templated intent.

    Returns:
        The labelled candidate.
    """
    return PlanCandidate(
        plan=plan,
        category=categorize(plan),
        difficulty=difficulty_of(plan),
        intent=intent,
    )


def enumerate_plans(
    snapshot: ObjectSnapshot, *, seed: int
) -> tuple[PlanCandidate, ...]:
    """Enumerate every plan one controlled structure is exercised with.

    Deterministic for a given structure and seed, so a corpus can be
    rebuilt from what its samples record.

    Args:
        snapshot: The structure to build plans against.
        seed: The seed every choice derives from.

    Returns:
        The labelled plan candidates, in a stable order.
    """
    rng = random.Random(seed)
    expressions = _candidate_expressions(snapshot, rng)
    # Each expression is paired with the next one round, so the
    # two-selection plan shape below always has two genuinely different
    # selections to name rather than the same one twice.
    partners = expressions[1:] + expressions[:1]
    observable = [
        name for name in REPRESENTATION_ALLOWLIST if name in MOLECULE_REP_NAMES
    ]
    candidates: list[PlanCandidate] = []
    index = 0
    # Its own cycle, stepping by exactly one per expression: the plan
    # index advances several times per loop, so cycling on that would
    # only ever reach half of these four.
    unobservable_cycle = itertools.cycle(UNOBSERVABLE_REPRESENTATIONS)

    for expression, partner in zip(expressions, partners, strict=True):
        described = describe_expression(expression)
        partner_described = describe_expression(partner)
        colors = rng.sample(list(COLOR_ALLOWLIST), _COLORS_PER_EXPRESSION)
        reps = rng.sample(observable, _REPRESENTATIONS_PER_EXPRESSION)

        for color in colors:
            index += 1
            name = _named(index)
            candidates.append(
                _candidate(
                    ActionPlan(
                        operations=(
                            SelectOperation(
                                selection_name=name, expression=expression
                            ),
                            ColorOperation(
                                color=color, target=NamedSelection(name)
                            ),
                        )
                    ),
                    f"Select {described} and color it {color}.",
                )
            )
            index += 1
            candidates.append(
                _candidate(
                    ActionPlan(
                        operations=(
                            ColorOperation(color=color, target=expression),
                        )
                    ),
                    f"Color {described} {color}.",
                )
            )

        for representation in reps:
            index += 1
            candidates.append(
                _candidate(
                    ActionPlan(
                        operations=(
                            ShowOperation(
                                representation=representation,
                                target=expression,
                            ),
                        )
                    ),
                    f"Show {described} as {representation}.",
                )
            )
            index += 1
            candidates.append(
                _candidate(
                    ActionPlan(
                        operations=(
                            HideOperation(
                                representation=representation,
                                target=expression,
                            ),
                        )
                    ),
                    f"Hide the {representation} representation for "
                    f"{described}.",
                )
            )

        index += 1
        name = _named(index)
        candidates.append(
            _candidate(
                ActionPlan(
                    operations=(
                        SelectOperation(
                            selection_name=name, expression=expression
                        ),
                        OrientOperation(target=NamedSelection(name)),
                    )
                ),
                f"Select {described} and orient the view on it.",
            )
        )

        index += 1
        name = _named(index)
        candidates.append(
            _candidate(
                ActionPlan(
                    operations=(
                        SelectOperation(
                            selection_name=name, expression=expression
                        ),
                        ColorOperation(
                            color=colors[0], target=NamedSelection(name)
                        ),
                        ShowOperation(
                            representation=reps[0],
                            target=NamedSelection(name),
                        ),
                    )
                ),
                f"Select {described}, color it {colors[0]} and show it as "
                f"{reps[0]}.",
            )
        )

        index += 1
        candidates.append(
            _candidate(
                ActionPlan(
                    operations=(
                        ShowOperation(
                            representation=reps[0], target=expression
                        ),
                        HideOperation(
                            representation=reps[1], target=expression
                        ),
                    )
                ),
                f"Show {described} as {reps[0]}, then hide its {reps[1]} "
                "representation.",
            )
        )

        index += 1
        first_name = _named(index)
        index += 1
        second_name = _named(index)
        candidates.append(
            _candidate(
                ActionPlan(
                    operations=(
                        SelectOperation(
                            selection_name=first_name, expression=expression
                        ),
                        SelectOperation(
                            selection_name=second_name, expression=partner
                        ),
                        ColorOperation(
                            color=colors[1],
                            target=NamedSelection(first_name),
                        ),
                        ShowOperation(
                            representation=reps[1],
                            target=NamedSelection(second_name),
                        ),
                    )
                ),
                f"Select {described} and color it {colors[1]}, then select "
                f"{partner_described} and show it as {reps[1]}.",
            )
        )

        # Deliberately unobservable: legal to emit and legal to run, but
        # absent from the snapshot format, so the report can say the
        # category is unsupported rather than leave it out entirely.
        index += 1
        unobservable = next(unobservable_cycle)
        candidates.append(
            _candidate(
                ActionPlan(
                    operations=(
                        ShowOperation(
                            representation=unobservable, target=expression
                        ),
                    )
                ),
                f"Show {described} as {unobservable}.",
            )
        )

    return tuple(candidates)
