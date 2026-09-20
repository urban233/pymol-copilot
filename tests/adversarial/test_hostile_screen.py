# Copyright 2026 PyMOL Copilot contributors.
"""Tests for src/pmc_core/screen.py's default-deny repair-eligibility gate.

Asserts against exactly the same corpus test_denied_forms.py already
proves the parser and policy deny (denied_forms.py, shared rather than
duplicated) plus this repository's own valid `.pml` grammar, so the two
suites cannot silently disagree about what the restricted language accepts.
"""

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from denied_forms import DENIED_EXPRESSION_FORMS
from denied_forms import LEXICALLY_DENIED_FORMS
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.screen import SCREEN_HOSTILE
from pmc_core.screen import SCREEN_ORDINARY
from pmc_core.screen import screen_completion

#: One representative valid text per verb, per term form, and a couple of
#: multi-command and boolean-expression shapes -- the same grammar
#: tests/contract/test_parser.py proves round-trips, restated here (not
#: imported) because that module exposes no shared table, only inline
#: pytest.mark.parametrize literals.
VALID_PML_FORMS = (
    "select copilot_core, chain A\n",
    "color red, chain A\n",
    "show cartoon, chain A\n",
    "hide lines, chain A\n",
    "orient chain A\n",
    "orient resi 5\n",
    "orient resi 1-100\n",
    "orient resn ALA\n",
    "orient name CA\n",
    "orient hetatm\n",
    "orient polymer\n",
    "orient chain A and resi 1-100\n",
    "orient chain A or chain B\n",
    "orient not chain A\n",
    "select copilot_a, chain A\ncolor red, copilot_a\n",
    "select copilot_a, chain A\nshow sticks, copilot_a\norient copilot_a\n",
)

#: A small, deliberately unremarkable set of ordinary mistakes a model
#: might make -- a misspelled color, a missing selection expression, a bare
#: verb with no argument at all -- none of which carry any marker this
#: language has no legitimate use for. These are exactly the completions
#: repair exists to fix, so the screen must never file them as hostile.
ORDINARY_MISTAKES = (
    "color reddd, chain A\n",
    "select copilot_a, chain\n",
    "orient chain\n",
    "colour red, chain A\n",
    "select copilot_a, resi\n",
)


@pytest.mark.parametrize(
    "text",
    [text for text, _ in DENIED_EXPRESSION_FORMS],
    ids=[case_id for _, case_id in DENIED_EXPRESSION_FORMS],
)
def test_every_denied_expression_form_screens_hostile(text: str) -> None:
    """Every dangerous-payload case in the corpus screens hostile.

    Args:
        text: One case from denied_forms.DENIED_EXPRESSION_FORMS.
    """
    assert screen_completion(text) == SCREEN_HOSTILE


@pytest.mark.parametrize(
    "text",
    [text for text, _, _ in LEXICALLY_DENIED_FORMS],
    ids=[case_id for _, _, case_id in LEXICALLY_DENIED_FORMS],
)
def test_every_lexically_denied_form_screens_hostile(text: str) -> None:
    """Every lexically denied case in the corpus screens hostile.

    Args:
        text: One case from denied_forms.LEXICALLY_DENIED_FORMS.
    """
    assert screen_completion(text) == SCREEN_HOSTILE


@pytest.mark.parametrize("text", VALID_PML_FORMS)
def test_every_valid_form_screens_ordinary(text: str) -> None:
    """Valid, parser-accepted text never screens hostile.

    Args:
        text: Canonical `.pml` text the parser accepts outright.
    """
    assert isinstance(parse_pml(text), ActionPlan), (
        f"fixture drifted from the grammar: {text!r} no longer parses"
    )

    assert screen_completion(text) == SCREEN_ORDINARY


@pytest.mark.parametrize("text", ORDINARY_MISTAKES)
def test_an_ordinary_mistake_screens_ordinary(text: str) -> None:
    """A plain syntax slip stays eligible for repair.

    This is the assertion that matters most: a screen broad enough to file
    every ordinary typo as hostile would silently disable repair
    altogether, which test_every_denied_expression_form_screens_hostile
    and test_every_lexically_denied_form_screens_hostile above cannot
    detect on their own -- a screen that always returns SCREEN_HOSTILE
    would pass both.

    Args:
        text: An ordinary mistake carrying no hostile marker.
    """
    assert screen_completion(text) == SCREEN_ORDINARY


def test_a_null_byte_alone_screens_hostile() -> None:
    """A bare null byte, with no other marker, still screens hostile."""
    assert screen_completion("orient chain A\x00") == SCREEN_HOSTILE


def test_empty_text_screens_ordinary() -> None:
    """Empty text carries no hostile marker and screens ordinary.

    An empty completion is handled by the request graph's own
    clarification classification, upstream of this screen -- this module
    only asserts it does not itself misclassify the empty case.
    """
    assert screen_completion("") == SCREEN_ORDINARY


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
