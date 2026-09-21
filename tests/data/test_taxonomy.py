# Copyright 2026 PyMOL Copilot contributors.
"""Evidence that every enumerated plan is legal and honestly labelled.

Nothing here needs PyMOL. Two independent authorities already decide
whether a plan is well-formed -- `pmc_core.policy.evaluate_plan`, which
re-derives its verdict from the typed value, and
`pmc_core.parser.parse_pml`, which is the only authority on what text
is legal. A generated plan that either one rejects would be discovered
at execution time as a policy denial or a command failure, and counted
as a rejection, which would misreport a generator defect as evidence
about PyMOL.

The other property proved here is that the taxonomy does not quietly
lose a category. A verb or term missing from the corpus produces no
failure at all -- just an absence -- which is exactly what item 14's
"report the rejection rate per category honestly" clause is guarding
against.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections import Counter

import pytest

from pmc_core.parser import parse_pml
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import TERM_TYPES
from pmc_core.policy import evaluate_plan
from pmc_core.prompt import MAX_INTENT_CHARACTERS
from pmc_core.prompt import MIN_INTENT_CHARACTERS
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures
from pmc_data.taxonomy import UNOBSERVABLE_REPRESENTATIONS
from pmc_data.taxonomy import categorize
from pmc_data.taxonomy import enumerate_plans

SEED = 20260921

STRUCTURES = tuple(
    (spec, build_structure(spec)) for spec in enumerate_structures(SEED)
)

CANDIDATES = tuple(
    candidate
    for spec, snapshot in STRUCTURES
    for candidate in enumerate_plans(snapshot, seed=spec.seed)
)


def test_the_enumeration_is_not_trivially_small() -> None:
    """Item 14 asks for a few thousand samples; the plans must exist."""
    assert len(CANDIDATES) >= 3000


def test_every_emitted_plan_is_allowed_and_round_trips() -> None:
    """Both independent authorities must accept every generated plan.

    A denial here would surface at execution as a rejection, making a
    generator defect look like evidence about PyMOL.
    """
    denied = [
        candidate.plan.render_pml()
        for candidate in CANDIDATES
        if not evaluate_plan(candidate.plan).allowed
    ]
    drifted = [
        candidate.plan.render_pml()
        for candidate in CANDIDATES
        if parse_pml(candidate.plan.render_pml()) != candidate.plan
    ]

    assert denied == []
    assert drifted == []


def test_taxonomy_covers_every_verb_and_term() -> None:
    """Every verb and term must appear, including the ungradable ones.

    `polymer` and the four unobservable representations are generated
    on purpose. They cannot be graded, and the report has to be able to
    say so -- which it cannot do about a category that was never
    attempted.
    """
    categories = {candidate.category for candidate in CANDIDATES}
    verbs = {
        verb
        for category in categories
        for verb in category.split("/")[0].split("+")
    }
    keywords = {
        keyword
        for category in categories
        for keyword in category.split("/")[1].split("+")
    }

    assert verbs == set(COMMAND_ALLOWLIST)
    assert keywords == {term.KEYWORD for term in TERM_TYPES}


def test_every_boolean_shape_the_language_can_express_appears() -> None:
    """The expression tree has four shapes and a negation flag."""
    shapes = {candidate.category.split("/")[2] for candidate in CANDIDATES}

    assert {"single", "and", "or", "and_or"} <= shapes
    assert any("not" in shape for shape in shapes)


def test_every_unobservable_representation_is_attempted() -> None:
    """A category left ungenerated cannot be reported as unsupported."""
    attempted = {
        line.split(" ", 2)[1].rstrip(",")
        for candidate in CANDIDATES
        for line in candidate.plan.render_pml().splitlines()
        if line.startswith(("show ", "hide "))
    }

    assert set(UNOBSERVABLE_REPRESENTATIONS) <= attempted


def test_categories_are_derived_from_the_plan_not_carried_alongside() -> None:
    """Re-deriving a category must reproduce the recorded one exactly."""
    mismatched = [
        candidate.category
        for candidate in CANDIDATES
        if categorize(candidate.plan) != candidate.category
    ]

    assert mismatched == []


def test_no_category_is_a_single_sample() -> None:
    """A category with one member reports a rate of 0% or 100% and no more."""
    counts = Counter(candidate.category for candidate in CANDIDATES)

    assert [category for category, n in counts.items() if n < 2] == []


def test_every_intent_fits_the_prompt_contract() -> None:
    """An out-of-range intent would be rejected when the prompt is built."""
    out_of_range = [
        candidate.intent
        for candidate in CANDIDATES
        if not (
            MIN_INTENT_CHARACTERS
            <= len(candidate.intent)
            <= MAX_INTENT_CHARACTERS
        )
    ]

    assert out_of_range == []


def test_enumeration_is_deterministic_for_a_seed() -> None:
    """A corpus must be rebuildable from the seed its samples record."""
    spec, snapshot = STRUCTURES[-1]

    first = enumerate_plans(snapshot, seed=spec.seed)
    second = enumerate_plans(snapshot, seed=spec.seed)

    assert [c.plan.render_pml() for c in first] == [
        c.plan.render_pml() for c in second
    ]
    assert [c.intent for c in first] == [c.intent for c in second]


def test_selection_names_are_never_reused_within_a_plan() -> None:
    """Policy denies a duplicate name; construction must not produce one."""
    for candidate in CANDIDATES:
        created = [
            line.split(" ", 2)[1].rstrip(",")
            for line in candidate.plan.render_pml().splitlines()
            if line.startswith("select ")
        ]
        assert len(created) == len(set(created))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
