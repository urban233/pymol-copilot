# Copyright 2026 PyMOL Copilot contributors.
"""The one prompt builder, shared by the dataset pipeline and the runtime.

`build_prompt()` turns a rendered structure card plus a user intent into a
`PromptV1`: a frozen value carrying its parts and the four contract
versions that decide what the model sees -- the prompt's own, the card's,
the grammar's and the policy's. `text()` renders it to canonical bytes.

Master plan item 13 requires that the dataset generator and the runtime
call *this* code rather than each assembling a prompt of its own, because
a model trained against one prompt and served another is a silent failure
with no symptom. Neither caller exists yet -- the dataset pipeline
generalizes in item 14, the runtime path arrives with items 8 and 9 -- so
what ships now is the pair of seams they will call, `build_for_data()` and
`build_for_runtime()`, proved byte-identical by a contract test. This is
the same shape `pmc_core.card` ships for the same reason, and
`card.render_for_runtime()` already names this module as its caller.

Four versions rather than three. Item 13 asks for the card, grammar and
policy versions; `PROMPT_VERSION` is here as well because without it a
change to the instruction text below would alter every prompt while every
recorded version stayed the same, and a dataset built across that change
would be silently inhomogeneous. SPECIFICATION.md:491 lists
"prompt/card/grammar/error versions" among the fields a model artifact
pins, so the prompt is expected to carry one.

The grammar itself is not embedded in the prompt. It constrains the
engine's decoding (master plan item 9) rather than instructing the model
in prose, so only its version is stamped here -- what the model may emit
is enforced, not requested, and `pmc_core.parser` and `pmc_core.policy`
still adjudicate the result either way.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from dataclasses import dataclass

from pmc_core.card import CARD_VERSION
from pmc_core.card import render_for_data
from pmc_core.card import render_for_runtime
from pmc_core.grammar import GRAMMAR_VERSION
from pmc_core.policy import POLICY_VERSION
from pmc_core.snapshot import ObjectSnapshot

#: This module's own prompt contract version, stamped as the first line of
#: every prompt. An int, matching the other pmc_core contract versions.
#: Bump it whenever text() renders different bytes for the same card and
#: intent -- including a pure rewording of the instructions below, which is
#: exactly the change no other version here would record.
PROMPT_VERSION = 1

#: The bounds on a user intent, matching
#: pmc_core.protocol.PlanRequestV1's own 1..4096 limit. Re-checked here
#: rather than assumed: the dataset path never crosses the wire, so the
#: protocol's validation never runs for it, and a builder that trusted its
#: caller would let an unbounded intent into a prompt that claims to be
#: bounded.
MIN_INTENT_CHARACTERS = 1
MAX_INTENT_CHARACTERS = 4096

#: The first line of any card pmc_core.card renders, including both of its
#: failure cards. A card that does not start with this is not something
#: this module was handed by the renderer, and it is refused rather than
#: wrapped: a prompt whose card came from somewhere else would defeat the
#: point of stamping a card version beside it.
_CARD_PREFIX = "card-version="

#: The instruction text the model is given, above the card and the intent.
#: Deliberately short: the grammar constrains the shape of the output, so
#: this says what the task is rather than describing a syntax the engine
#: already enforces. Any edit here is a PROMPT_VERSION bump.
_INSTRUCTIONS = (
    "You write PyMOL commands in a restricted language. "
    "Given the structure card below and the user's intent, emit only the "
    "commands that carry out that intent, one per line, and nothing else."
)


def _is_version(value: object, expected: int) -> bool:
    """Return whether value is the expected version, as an int.

    The type test comes first and is not redundant: `True == 1` and
    `1.0 == 1` in Python, so an equality-only gate would accept either as
    version 1. `pmc_core.errors` carries the same check for the same
    reason, after review found that exact gap.

    Args:
        value: The candidate version.
        expected: The version this module requires.

    Returns:
        True if value is a non-bool int equal to expected.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value == expected


@dataclass(frozen=True)
class PromptV1:
    """One model prompt, with every contract version it depends on.

    Validates in __post_init__, so a PromptV1 that exists at all is one
    text() can render: the alternative is a value that constructs and
    then fails at the point of use, which for the dataset writer would be
    thousands of samples into a run.

    Attributes:
        prompt_version: This module's PROMPT_VERSION.
        card_version: pmc_core.card's CARD_VERSION.
        grammar_version: pmc_core.grammar's GRAMMAR_VERSION.
        policy_version: pmc_core.policy's POLICY_VERSION.
        card: The rendered structure card, as pmc_core.card produced it.
        intent: The user's natural-language intent.
    """

    prompt_version: int
    card_version: int
    grammar_version: int
    policy_version: int
    card: str
    intent: str

    def __post_init__(self) -> None:
        """Reject anything text() could not render.

        Raises:
            ValueError: If any stamped version is not its module's
                current one, if the intent is not a str within the
                declared bounds, or if the card is not one
                pmc_core.card rendered.
        """
        versions = (
            ("prompt_version", self.prompt_version, PROMPT_VERSION),
            ("card_version", self.card_version, CARD_VERSION),
            ("grammar_version", self.grammar_version, GRAMMAR_VERSION),
            ("policy_version", self.policy_version, POLICY_VERSION),
        )
        for name, value, expected in versions:
            if not _is_version(value, expected):
                raise ValueError(f"{name} is not version {expected}")
        if not isinstance(self.intent, str):
            raise ValueError("intent is not a string")
        if not (
            MIN_INTENT_CHARACTERS <= len(self.intent) <= MAX_INTENT_CHARACTERS
        ):
            raise ValueError("intent length is outside the V1 limit")
        if not isinstance(self.card, str) or not self.card.startswith(
            _CARD_PREFIX
        ):
            raise ValueError("card was not rendered by pmc_core.card")

    def text(self) -> str:
        """Render this prompt to its one canonical form.

        The four versions lead, each on its own line, so a stamped
        version is readable off the top of a recorded sample without
        parsing the rest -- the same discipline the card itself follows.

        Returns:
            The prompt text, ending in exactly one newline.
        """
        return (
            f"prompt-version={self.prompt_version}\n"
            f"card-version={self.card_version}\n"
            f"grammar-version={self.grammar_version}\n"
            f"policy-version={self.policy_version}\n"
            f"{_INSTRUCTIONS}\n"
            f"{self.card}"
            f"intent={self.intent}\n"
        )


def build_prompt(card: str, intent: str) -> PromptV1:
    """Build one prompt from a rendered card and a user intent.

    Args:
        card: The structure card, as pmc_core.card rendered it.
        intent: The user's natural-language intent.

    Returns:
        The stamped, validated prompt.

    Raises:
        ValueError: If the card or the intent is outside what this
            module accepts.
    """
    return PromptV1(
        prompt_version=PROMPT_VERSION,
        card_version=CARD_VERSION,
        grammar_version=GRAMMAR_VERSION,
        policy_version=POLICY_VERSION,
        card=card,
        intent=intent,
    )


def build_for_data(snapshot: ObjectSnapshot, intent: str) -> PromptV1:
    """Return the prompt for the dataset writer caller seam.

    Args:
        snapshot: The canonical snapshot to describe.
        intent: The user's natural-language intent.

    Returns:
        The same prompt build_for_runtime returns, through the seam the
        dataset writer (master plan item 14) calls.
    """
    return build_prompt(render_for_data(snapshot), intent)


def build_for_runtime(snapshot: ObjectSnapshot, intent: str) -> PromptV1:
    """Return the prompt for the runtime prompt-builder caller seam.

    Args:
        snapshot: The canonical snapshot to describe.
        intent: The user's natural-language intent.

    Returns:
        The same prompt build_for_data returns, through the seam the
        runtime request graph (master plan items 8 and 9) calls.
    """
    return build_prompt(render_for_runtime(snapshot), intent)
