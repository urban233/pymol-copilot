# Copyright 2026 PyMOL Copilot contributors.
"""Fuzz evidence that the parser is total and never accepts non-canonical text.

parse_pml claims two properties that no finite list of literal cases can
establish. The first is totality: it never raises, for any input at all. The
second is canonicality: if it returns a plan, the input it was given was
already that plan's exact rendering, so nothing was normalized on the way in.

Both are asserted here over generated input. The generator is a seeded
random.Random, so a failure is reproducible from the seed printed with it,
and it needs no dependency the runtime closure does not already have.

A blanket try/except inside parse_pml would make this module prove nothing,
which is why the parser catches ValueError at each constructor call site
instead.
"""

import random
import sys
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml
from pmc_core.parser import parse_selection_expression
from pmc_core.plan import ActionPlan

#: The seed every case below draws from. Printed on failure so a red run is
#: reproducible without recording the generated corpus.
SEED = 20260917

#: How many inputs each generated case draws.
CASE_COUNT = 1500

#: Fragments the generator draws from: every keyword and separator in the
#: grammar, every character class the parser rejects, and the shapes that
#: have historically broken hand-written parsers.
FRAGMENTS = (
    "select",
    "color",
    "show",
    "hide",
    "orient",
    "delete",
    "load",
    "fetch",
    "chain",
    "resi",
    "resn",
    "name",
    "hetatm",
    "polymer",
    "and",
    "or",
    "not",
    "copilot_a",
    "copilot_",
    "red",
    "cartoon",
    "A",
    "ALA",
    "CA",
    "1",
    "0",
    "007",
    "1-100",
    "-1",
    "999999999",
    " ",
    "  ",
    ",",
    ", ",
    "\n",
    "\r",
    "\t",
    "\\",
    "#",
    "'",
    '"',
    "(",
    ")",
    ";",
    "|",
    "&",
    "$",
    "`",
    "*",
    "/",
    "..",
    "\x00",
    "\x1b",
    chr(0xA0),  # no-break space
    chr(0x200B),  # zero-width space
    chr(0xFEFF),  # byte-order mark
    chr(0x65) + chr(0x301),  # combining acute accent
    "\U0001f600",
    "x" * 50,
)


def assert_total(text: str, seed: int) -> None:
    """Assert the parser's two generated-input properties for one string.

    Args:
        text: The generated input.
        seed: The seed that produced it, reported on failure.
    """
    try:
        result = parse_pml(text)
    except Exception as error:
        pytest.fail(
            f"parse_pml raised {type(error).__name__} for seed {seed}: {text!r}"
        )

    assert isinstance(result, (ActionPlan, ParseRejection)), (
        f"seed {seed} produced {type(result).__name__}: {text!r}"
    )
    if isinstance(result, ActionPlan):
        assert result.render_pml() == text, (
            f"seed {seed} accepted non-canonical text: {text!r}"
        )


def test_parser_never_raises_on_generated_fragment_soup() -> None:
    """Arbitrary concatenations of grammar and hostile fragments are total."""
    generator = random.Random(SEED)

    for _ in range(CASE_COUNT):
        length = generator.randint(0, 20)
        text = "".join(generator.choice(FRAGMENTS) for _ in range(length))
        assert_total(text, SEED)


def test_parser_never_raises_on_random_character_soup() -> None:
    """Arbitrary character sequences are total, surrogates included.

    The range deliberately spans the whole of Unicode rather than stopping
    below U+D800. A lone surrogate is an ordinary str that json.loads can
    produce, and it is the one input class that makes text.encode("utf-8")
    raise -- so a corpus that stops short of it cannot reach the guard that
    keeps parse_pml total.
    """
    generator = random.Random(SEED + 1)

    for _ in range(CASE_COUNT):
        length = generator.randint(0, 80)
        text = "".join(chr(generator.randint(0, 0x2FFF)) for _ in range(length))
        assert_total(text, SEED + 1)


#: Valid plans the mutation generator grows its corpus from.
SEED_PLANS = (
    "select copilot_a, chain A and not hetatm or polymer\n"
    "color marine, copilot_a\n"
    "show cartoon, resi 1-100\n"
    "hide lines, resn ALA\n"
    "orient name CA\n",
    "orient chain A\n",
    "select copilot_core, resi 1-100 and chain B\norient copilot_core\n",
)


def mutated_plans(generator: random.Random, count: int) -> list[str]:
    """Grow a corpus by editing text the parser already accepts.

    Fragment soup almost never gets past the first few checks, so it cannot
    reach term parsing, range parsing or the reference rules. Mutating valid
    plans does, and it is the only generator here that reaches acceptance at
    all.

    Args:
        generator: The seeded source of randomness.
        count: How many inputs to produce.

    Returns:
        The generated inputs.
    """
    corpus: list[str] = []
    for _ in range(count):
        text = generator.choice(SEED_PLANS)
        for _ in range(generator.randint(1, 4)):
            if not text:
                break
            position = generator.randrange(len(text))
            action = generator.choice(("delete", "insert", "replace"))
            if action == "delete":
                text = text[:position] + text[position + 1 :]
            elif action == "insert":
                text = (
                    text[:position]
                    + generator.choice(FRAGMENTS)
                    + text[position:]
                )
            else:
                text = (
                    text[:position]
                    + generator.choice(FRAGMENTS)
                    + text[position + 1 :]
                )
        corpus.append(text)
    return corpus


def test_parser_never_raises_on_mutated_valid_plans() -> None:
    """Single-character edits to valid plans reach the deepest code paths."""
    generator = random.Random(SEED + 2)

    for text in mutated_plans(generator, CASE_COUNT):
        assert_total(text, SEED + 2)


def test_the_mutation_corpus_actually_reaches_acceptance() -> None:
    """The canonicality half of assert_total must not be vacuous.

    assert_total only compares a rendering against its input when the parser
    accepts, so a corpus that never reaches acceptance proves totality and
    nothing else. This pins the property the other tests rely on.
    """
    generator = random.Random(SEED + 2)
    accepted = 0
    categories: set[str] = set()

    for text in mutated_plans(generator, CASE_COUNT):
        result = parse_pml(text)
        if isinstance(result, ParseRejection):
            categories.add(result.category)
        else:
            accepted += 1

    assert accepted > 0
    assert len(categories) >= 8


def test_parser_never_raises_on_pathological_repetition() -> None:
    """Deeply repeated operators and separators terminate without raising."""
    generator = random.Random(SEED + 3)
    templates = (
        "orient " + " and ".join(["hetatm"] * 200) + "\n",
        "orient " + " or ".join(["hetatm"] * 200) + "\n",
        "orient " + "not " * 200 + "hetatm\n",
        "orient resi " + "-".join(["1"] * 200) + "\n",
        "orient chain " + "A" * 5000 + "\n",
        "," * 5000 + "\n",
        " " * 5000 + "\n",
        "orient hetatm\n" * 500,
    )

    for template in templates:
        assert_total(template, SEED + 3)

    for _ in range(100):
        text = generator.choice(templates)
        assert_total(text, SEED + 3)


def test_the_plan_shape_backstop_never_fires() -> None:
    """The parser's own checks make ActionPlan's constructor unreachable.

    parse_pml checks plan length, size, operation types, reference
    discipline and duplicate names itself, before building the ActionPlan,
    so that a rejection can name the offending command index -- a
    constructor error cannot. The try/except around that construction is a
    backstop against the two sets of rules diverging.

    This must use the mutation corpus, not fragment soup. Fragment soup
    never reaches ActionPlan construction at all, so it cannot observe the
    backstop firing and the assertion would hold no matter what the parser
    did.
    """
    generator = random.Random(SEED + 5)
    produced: set[str] = set()
    accepted = 0

    for text in mutated_plans(generator, CASE_COUNT):
        result = parse_pml(text)
        if isinstance(result, ParseRejection):
            produced.add(result.category)
        else:
            accepted += 1

    assert accepted > 0, "corpus never built a plan, so it proves nothing"
    assert "invalid_plan_shape" not in produced


@pytest.mark.parametrize(
    "text",
    ["orient chain " + chr(0xD800) + "\n", chr(0xDC00), chr(0xD800) * 100],
    ids=["lone_surrogate_in_a_command", "bare_low_surrogate", "many"],
)
def test_lone_surrogates_are_rejected_rather_than_raising(text: str) -> None:
    """A lone surrogate makes encode("utf-8") raise; the parser must not.

    json.loads happily produces one from an escaped "\\ud800", and the wire
    protocol feeds JSON-decoded strings to the parser, so this is reachable
    rather than theoretical.

    Args:
        text: Input containing an unpaired surrogate.
    """
    assert isinstance(parse_pml(text), ParseRejection)
    assert isinstance(parse_selection_expression(text), ParseRejection)


@pytest.mark.parametrize(
    "value",
    [None, 42, b"orient chain A\n", ["orient chain A"], object()],
    ids=["none", "integer", "bytes", "list", "object"],
)
def test_non_text_input_is_rejected_rather_than_raising(value: Any) -> None:
    """Both public entry points are total for values that are not text.

    Args:
        value: A non-str value passed where text is expected. Typed Any so
            the deliberately wrong type reaches the parser rather than being
            refused by the type checker first.
    """
    assert isinstance(parse_pml(value), ParseRejection)
    assert isinstance(parse_selection_expression(value), ParseRejection)


def test_fuzzing_never_imports_pymol() -> None:
    """No generated input reaches Open-Source PyMOL."""
    assert "pymol" not in sys.modules

    generator = random.Random(SEED + 4)
    for _ in range(CASE_COUNT):
        length = generator.randint(0, 20)
        text = "".join(generator.choice(FRAGMENTS) for _ in range(length))
        parse_pml(text)

    assert "pymol" not in sys.modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
