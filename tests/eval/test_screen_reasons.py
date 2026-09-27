# Copyright 2026 PyMOL Copilot contributors.
"""The report's hostile reasons agree with the screen's own verdict.

`pmc_eval.screen_reasons` copies `pmc_core.screen`'s rules so the report
can say which one fired. A copy can drift; this suite is what catches it,
over the adversarial corpus the screen is itself proved against plus the
kinds of text an untuned model actually writes.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import pytest

from denied_forms import DENIED_EXPRESSION_FORMS
from denied_forms import LEXICALLY_DENIED_FORMS
from denied_forms import UNKNOWN_VERB_FORMS
from pmc_core.screen import SCREEN_HOSTILE
from pmc_core.screen import screen_completion
from pmc_eval.screen_reasons import hostile_reasons

#: What an untuned instruct model writes around, or instead of, a plan,
#: plus legal plans and near-misses the screen must leave ordinary.
MODEL_SHAPED_TEXTS = (
    "color magenta, resn ZN\n",
    "select copilot_a, chain A and not hetatm\ncolor red, copilot_a\n",
    "show sticks, resi 3-5\n",
    "orient chain B\n",
    "Here's the command:\ncolor red, chain A\n",
    "```\ncolor red, chain A\n```\n",
    "To do this, set the color of chain A to red.\n",
    "Sure! You can load the structure and color it.",
    "color(red, chain A)",
    "Use cmd.color to colour chain A red.",
    "color red, chain A # the first chain\n",
    "Colour chain A red; then show sticks.",
    "The answer is: color red, chain A",
    "Set chain A to red.",
    "if chain A else chain B",
    "chain if\n",
    "orientate chain A\n",
    "",
    "ask: which chain do you mean?",
)

TEXTS = (
    *(text for text, _ in UNKNOWN_VERB_FORMS),
    *(text for text, _ in DENIED_EXPRESSION_FORMS),
    *(text for text, _, _ in LEXICALLY_DENIED_FORMS),
    *MODEL_SHAPED_TEXTS,
)


@pytest.mark.parametrize("text", TEXTS)
def test_reasons_agree_with_the_screen(text: str) -> None:
    """There are reasons exactly when the screen calls the text hostile.

    Args:
        text: A corpus or model-shaped text.
    """
    hostile = screen_completion(text) == SCREEN_HOSTILE

    assert bool(hostile_reasons(text)) == hostile


def test_reasons_name_the_rules_that_fired() -> None:
    """Prose is refused for its apostrophe and for an English verb."""
    assert hostile_reasons("Here's how to set it: color red, chain A") == (
        "character:'",
        "verb:set",
    )


def test_reasons_are_empty_for_a_legal_plan() -> None:
    """A plan in the restricted language trips no rule."""
    assert hostile_reasons("color red, chain A\n") == ()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
