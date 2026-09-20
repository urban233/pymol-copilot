# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the prompt builder: no PyMOL required.

Covers pmc_core.prompt: that every prompt carries the four contract
versions on its first lines, that a representative prompt renders fixed
bytes, that a prompt outside its bounds is refused at construction rather
than at render, and that the dataset and runtime caller seams produce
identical bytes.

The seam parity test is the one master plan item 13 asks for. Neither
real caller exists yet -- the dataset pipeline generalizes in item 14 and
the runtime path arrives with items 8 and 9 -- so it is written against
the two seams themselves, which are real code this test executes. That
is deliberately not the shape review rejected twice on the error
envelope, where a textual scan for co-occurring strings proved nothing:
breaking either seam turns this test red today.
"""

from dataclasses import replace
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from consumer_scan import consumer_sources
from consumer_scan import foreign_calls

from pmc_core.card import CARD_VERSION
from pmc_core.card import render
from pmc_core.grammar import GRAMMAR_VERSION
from pmc_core.policy import POLICY_VERSION
from pmc_core.prompt import MAX_INTENT_CHARACTERS
from pmc_core.prompt import PROMPT_VERSION
from pmc_core.prompt import PromptV1
from pmc_core.prompt import build_for_data
from pmc_core.prompt import build_for_runtime
from pmc_core.prompt import build_prompt
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import BondRecord
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot

_IDENTITY_VIEW = (
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    -0.5,
    0.5,
    -20.0,
)

_INTENT = "color chain A red"


def _snapshot() -> ObjectSnapshot:
    """Build a representative two-atom, one-state, one-bond snapshot.

    Returns:
        A hand-constructed snapshot the card renders as complete.
    """
    atom_a = AtomRecord(
        1,
        "CA",
        "",
        "ALA",
        "A",
        1,
        "",
        "C",
        False,
        1.0,
        20.0,
        3,
        ("sticks", "lines"),
        "CA",
        (1.0, 2.0, 3.0),
    )
    atom_b = AtomRecord(
        2,
        "ZN",
        "B",
        "ZN",
        "A",
        2,
        "A",
        "ZN",
        True,
        0.5,
        10.0,
        7,
        ("spheres",),
        None,
        (4.0, 5.0, 6.0),
    )
    return ObjectSnapshot(
        1,
        "fx",
        False,
        (StateSnapshot((atom_b, atom_a)),),
        (BondRecord(1, 0, 1),),
        _IDENTITY_VIEW,
        (("sphere_scale", "0.35"), ("cartoon_transparency", "0.25")),
        DECLARED_UNSUPPORTED,
    )


def _multi_state_snapshot() -> ObjectSnapshot:
    """Build a snapshot whose card carries more than one state.

    Returns:
        A two-state snapshot, so seam parity is proved over a card that
        is not the single-state one every other case uses.
    """
    base = _snapshot()
    return replace(base, states=(base.states[0], base.states[0]))


def _malformed_snapshot() -> ObjectSnapshot:
    """Build a snapshot the card refuses to render.

    Returns:
        A snapshot with a bond outside the first state's atom range, so
        render() returns the malformed card rather than a complete one.
    """
    return replace(_snapshot(), bonds=(BondRecord(0, 5, 1),))


#: Every card outcome pmc_core.card can produce, so seam parity is proved
#: across all three rather than only the happy path.
_SNAPSHOTS = (
    ("complete card", _snapshot()),
    ("multi-state card", _multi_state_snapshot()),
    ("malformed card", _malformed_snapshot()),
)


def test_every_stamped_version_is_a_non_bool_int() -> None:
    """A version merely equal to 1 is not that contract's version 1.

    True == 1 and 1.0 == 1 in Python, so a stamped version that was
    never type-checked would let either through. The error envelope
    shipped with exactly that gap and had to be corrected in review.
    """
    for version in (
        PROMPT_VERSION,
        CARD_VERSION,
        GRAMMAR_VERSION,
        POLICY_VERSION,
    ):
        assert isinstance(version, int)
        assert not isinstance(version, bool)


def test_the_prompt_carries_every_version_on_its_first_lines() -> None:
    """All four versions are readable without parsing the rest."""
    text = build_for_runtime(_snapshot(), _INTENT).text()

    assert text.splitlines()[:4] == [
        f"prompt-version={PROMPT_VERSION}",
        f"card-version={CARD_VERSION}",
        f"grammar-version={GRAMMAR_VERSION}",
        f"policy-version={POLICY_VERSION}",
    ]


def test_the_golden_prompt_has_stable_bytes() -> None:
    """A representative snapshot and intent render fixed prompt bytes.

    This is what turns a future change to the instruction text into a
    deliberate PROMPT_VERSION bump rather than a silent one: rewording
    the instructions moves these bytes and nothing else would notice.
    """
    prompt = build_for_data(_snapshot(), _INTENT)
    card = render(_snapshot())

    assert prompt.text() == (
        "prompt-version=1\n"
        "card-version=1\n"
        "grammar-version=1\n"
        "policy-version=1\n"
        "You write PyMOL commands in a restricted language. Given the "
        "structure card below and the user's intent, emit only the "
        "commands that carry out that intent, one per line, and nothing "
        "else.\n"
        f"{card}"
        "intent=color chain A red\n"
    )


def test_the_prompt_ends_in_exactly_one_newline() -> None:
    """The prompt is concatenable without a caller fixing it up."""
    text = build_for_data(_snapshot(), _INTENT).text()

    assert text.endswith("\n")
    assert not text.endswith("\n\n")


@pytest.mark.parametrize(
    ("label", "snapshot"), _SNAPSHOTS, ids=[case[0] for case in _SNAPSHOTS]
)
def test_data_and_runtime_seams_have_byte_parity(
    label: str, snapshot: ObjectSnapshot
) -> None:
    """Both caller seams build the same prompt, byte for byte.

    Item 13's requirement that the dataset generator and the runtime
    call the same code reduces to this while neither caller exists. It
    is proved over every card outcome, because a divergence that only
    showed on a malformed card would be the hardest kind to notice.
    """
    assert (
        build_for_data(snapshot, _INTENT).text()
        == build_for_runtime(snapshot, _INTENT).text()
    ), label


def test_the_seams_agree_on_every_stamped_field_too() -> None:
    """Parity is not only in the text: the values agree as well."""
    assert build_for_data(_snapshot(), _INTENT) == build_for_runtime(
        _snapshot(), _INTENT
    )


_REFUSED: tuple[tuple[str, dict[str, Any]], ...] = (
    ("an empty intent", {"intent": ""}),
    ("an overlong intent", {"intent": "x" * (MAX_INTENT_CHARACTERS + 1)}),
    ("a non-string intent", {"intent": 3}),
    ("a card from somewhere else", {"card": "status=complete\n"}),
    ("a non-string card", {"card": 3}),
    ("a boolean prompt version", {"prompt_version": True}),
    ("a float card version", {"card_version": 1.0}),
    ("a wrong grammar version", {"grammar_version": 2}),
    ("a boolean policy version", {"policy_version": True}),
)


@pytest.mark.parametrize(
    ("label", "change"), _REFUSED, ids=[case[0] for case in _REFUSED]
)
def test_a_prompt_outside_its_bounds_is_refused(
    label: str, change: dict[str, Any]
) -> None:
    """Construction fails rather than rendering something unusable.

    A value that constructs and then fails at the point of use would,
    for the dataset writer, fail thousands of samples into a run.
    """
    del label  # Carried for the test id, not read.
    valid = build_for_data(_snapshot(), _INTENT)

    with pytest.raises(ValueError):
        replace(valid, **change)


def test_the_longest_accepted_intent_still_builds() -> None:
    """The bound is inclusive, matching the protocol's own limit."""
    prompt = build_prompt(render(_snapshot()), "x" * MAX_INTENT_CHARACTERS)

    assert isinstance(prompt, PromptV1)
    assert prompt.text().endswith("x" * MAX_INTENT_CHARACTERS + "\n")


#: The one prompt builder a consumer may reach.
_CANONICAL_BUILDER = "pmc_core.prompt.build_prompt"

#: Definitions that would mean a consumer had assembled a prompt of its
#: own instead of calling this module's.
_BUILDER_DEFINITIONS = (
    "def build_prompt(",
    "def build_for_data(",
    "def build_for_runtime(",
    "class PromptV1",
)


def test_no_consumer_builds_a_prompt_of_its_own() -> None:
    """Neither consumer may grow a second prompt builder.

    Item 13 requires the dataset generator and the runtime to call this
    module. Their call sites arrive with items 14 and 8, so no test here
    can yet prove that both *reach* it; what a divergence would have to
    defeat first is that neither has written its own.
    """
    sources = consumer_sources()
    assert sources, "no consumer sources were found to scan"
    for source in sources:
        body = source.read_text(encoding="utf-8")
        for definition in _BUILDER_DEFINITIONS:
            assert definition not in body, (
                f"{source.name} defines its own {definition.strip()}"
            )


def test_a_consumer_that_builds_a_prompt_reaches_this_module() -> None:
    """A consumer calling build_prompt() must reach this module's.

    Inert until items 14 and 8 add their call sites, and armed by the
    shared scan in consumer_scan, whose own discriminating cases are
    proved in test_errors.py. Reusing that machinery rather than writing
    a second check is what keeps the two items from drifting into
    different notions of what reaching the shared core means.
    """
    for source in consumer_sources():
        foreign = foreign_calls(
            source.read_text(encoding="utf-8"), _CANONICAL_BUILDER
        )
        assert not foreign, (
            f"{source.name} builds prompts through {sorted(foreign)} "
            f"rather than {_CANONICAL_BUILDER}"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
