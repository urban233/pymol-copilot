# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the engine grammar: no PyMOL required.

Covers pmc_core.grammar's generated GBNF: that every terminal comes from
pmc_core.plan's allowlist tables rather than from a literal in the
generator, and that the grammar agrees with pmc_core.parser over an
accept/reject corpus -- the evidence SPECIFICATION.md:488 asks for.

The agreement is deliberately one-directional. Anything the parser
accepts, the grammar must accept; the converse is not promised, because
GBNF expresses a bounded repeat only by unrolling it and the language's
own MAX_COMMANDS and MAX_EXPRESSION_TERMS bounds stay the parser's job.
A grammar wider than the parser is safe -- the parser rejects what it
always would. A grammar narrower than the parser is not, because it
makes legal plans unreachable, so that is the direction pinned here.

The GBNF matcher below is test-only, and deliberately so: production
code never interprets this grammar, the inference engine does. It exists
to make the corpus an executable claim rather than a reading exercise.
"""

import re

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.grammar import GRAMMAR_VERSION
from pmc_core.grammar import build_grammar
from pmc_core.parser import parse_pml
from pmc_core.plan import COLOR_ALLOWLIST
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import REPRESENTATION_ALLOWLIST
from pmc_core.plan import TERM_TYPES
from pmc_core.plan import ActionPlan

_TOKEN = re.compile(
    r'"(?:[^"\\]|\\.)*"|\[(?:[^\]\\]|\\.)*\]|[A-Za-z][A-Za-z0-9-]*|[()|?*+]'
)


def _parse_gbnf(text: str) -> dict[str, object]:
    """Parse a GBNF document into rule trees.

    Args:
        text: The grammar document, one rule per line.

    Returns:
        Each rule name against its parsed alternation.
    """
    rules: dict[str, object] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        name, separator, body = line.partition(" ::= ")
        assert separator, f"not a GBNF rule: {line!r}"
        tokens = _TOKEN.findall(body)
        _assert_fully_tokenized(body, tokens)
        rules[name.strip()] = _parse_alternation(tokens)
    return rules


def _assert_fully_tokenized(body: str, tokens: list[str]) -> None:
    """Fail when the tokenizer silently dropped part of a rule body.

    `re.findall` skips anything it cannot match, so a rule body carrying
    stray characters would tokenize to the same list as a clean one and
    the matcher would bless a document no real GBNF engine accepts. The
    matcher's verdicts only mean something if it read the whole document.

    Args:
        body: The rule body as written.
        tokens: What the tokenizer produced from it.

    Raises:
        AssertionError: If any non-whitespace character went unconsumed.
    """
    remaining = body
    for token in tokens:
        head, _, remaining = remaining.partition(token)
        assert not head.strip(), f"unconsumed {head.strip()!r} in {body!r}"
    assert not remaining.strip(), (
        f"unconsumed {remaining.strip()!r} in {body!r}"
    )


def _parse_alternation(tokens: list[str]) -> object:
    """Split tokens on top-level `|` and parse each branch.

    Args:
        tokens: The tokenized rule body.

    Returns:
        An ("alt", branches) node.
    """
    branches: list[list[str]] = [[]]
    depth = 0
    for token in tokens:
        if token == "|" and depth == 0:
            branches.append([])
            continue
        depth += (token == "(") - (token == ")")
        branches[-1].append(token)
    return ("alt", [_parse_sequence(branch) for branch in branches])


def _parse_sequence(tokens: list[str]) -> object:
    """Parse one alternation branch into a sequence node.

    Args:
        tokens: The branch's tokens.

    Returns:
        A ("seq", items) node.
    """
    items: list[object] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "(":
            depth, end = 1, index + 1
            while depth:
                depth += (tokens[end] == "(") - (tokens[end] == ")")
                end += 1
            node: object = _parse_alternation(tokens[index + 1 : end - 1])
            index = end
        elif token.startswith('"'):
            literal = token[1:-1].replace("\\n", "\n").replace('\\"', '"')
            node = ("lit", literal)
            index += 1
        elif token.startswith("["):
            node = ("cls", token)
            index += 1
        else:
            node = ("ref", token)
            index += 1
        while index < len(tokens) and tokens[index] in "?*+":
            suffix = {"?": "opt", "*": "star", "+": "plus"}[tokens[index]]
            node = (suffix, node)
            index += 1
        items.append(node)
    return ("seq", items)


def _class_matches(spec: str, character: str) -> bool:
    """Return whether a character class admits one character.

    Args:
        spec: The bracketed class, e.g. "[a-z0-9_]".
        character: The character to test.

    Returns:
        True if the class admits it.
    """
    body = spec[1:-1]
    index = 0
    while index < len(body):
        if index + 2 < len(body) and body[index + 1] == "-":
            if body[index] <= character <= body[index + 2]:
                return True
            index += 3
        else:
            if body[index] == character:
                return True
            index += 1
    return False


def _match(
    node: object,
    rules: dict[str, object],
    text: str,
    position: int,
    seen: frozenset[tuple[str, int]] = frozenset(),
) -> set[int]:
    """Return every position reachable by matching node at position.

    Args:
        node: The rule tree node to match.
        rules: Every rule in the grammar.
        text: The candidate text.
        position: Where in text to start.
        seen: Rule/position pairs already being expanded, which stops a
            left-recursive rule from recursing forever.

    Returns:
        The set of end positions; empty when the node does not match.
    """
    kind = node[0]  # pyrefly: ignore.
    if kind == "lit":
        literal = node[1]  # pyrefly: ignore.
        return (
            {position + len(literal)}
            if text.startswith(literal, position)
            else set()
        )
    if kind == "cls":
        if position < len(text) and _class_matches(
            node[1],  # pyrefly: ignore.
            text[position],
        ):
            return {position + 1}
        return set()
    if kind == "ref":
        key = (node[1], position)  # pyrefly: ignore.
        if key in seen:
            return set()
        return _match(
            rules[node[1]],  # pyrefly: ignore.
            rules,
            text,
            position,
            seen | {key},
        )
    if kind == "alt":
        reachable: set[int] = set()
        for branch in node[1]:  # pyrefly: ignore.
            reachable |= _match(branch, rules, text, position, seen)
        return reachable
    if kind == "seq":
        positions = {position}
        for item in node[1]:  # pyrefly: ignore.
            following: set[int] = set()
            for each in positions:
                following |= _match(item, rules, text, each, seen)
            if not following:
                return set()
            positions = following
        return positions
    if kind == "opt":
        return {position} | _match(
            node[1],  # pyrefly: ignore.
            rules,
            text,
            position,
            seen,
        )
    reached = set() if kind == "plus" else {position}
    frontier = _match(node[1], rules, text, position, seen)  # pyrefly: ignore.
    while frontier:
        reached |= frontier
        following = set()
        for each in frontier:
            following |= {
                end
                for end in _match(
                    node[1],  # pyrefly: ignore.
                    rules,
                    text,
                    each,
                    seen,
                )
                if end > each
            }
        frontier = following - reached
    return reached


def _grammar_accepts(text: str) -> bool:
    """Return whether the generated grammar admits text in full.

    Args:
        text: The candidate plan text.

    Returns:
        True if the whole string is derivable from the root rule.
    """
    rules = _parse_gbnf(build_grammar())
    return len(text) in _match(rules["root"], rules, text, 0)


def _parser_accepts(text: str) -> bool:
    """Return whether pmc_core.parser admits text as a plan.

    Args:
        text: The candidate plan text.

    Returns:
        True if parse_pml returns a typed plan.
    """
    return isinstance(parse_pml(text), ActionPlan)


#: Plans the parser accepts. Every one of the six selection terms, every
#: verb, both target forms and each precedence level appears at least
#: once, so dropping any of them from the generated grammar fails a case
#: here rather than passing unnoticed.
_ACCEPTED = (
    ("select with one term", "select copilot_sel, chain A\n"),
    ("select with a residue range", "select copilot_sel, resi 10-20\n"),
    ("select with resn and name", "select copilot_s, resn ALA and name CA\n"),
    ("select polymer", "select copilot_s, polymer\n"),
    ("select hetatm", "select copilot_s, hetatm\n"),
    ("negation", "select copilot_s, not chain A\n"),
    (
        "all three precedence levels",
        "select copilot_s, chain A and resi 5 or not polymer\n",
    ),
    ("color onto an expression", "color red, chain A\n"),
    ("show onto an expression", "show cartoon, chain B\n"),
    ("hide onto an expression", "hide lines, resn ALA\n"),
    ("orient an expression", "orient chain A\n"),
    (
        "a name target, defined first",
        "select copilot_sel, chain A\ncolor red, copilot_sel\n",
    ),
    (
        "several commands",
        "select copilot_sel, chain A\nshow cartoon, copilot_sel\norient copilot_sel\n",
    ),
)

#: Text the language has no spelling for at all. The grammar is allowed
#: to be wider than the parser on *bounds*, but not on vocabulary: none
#: of these may be derivable.
_REJECTED = (
    ("a verb outside the allowlist", "delete copilot_sel\n"),
    ("a color outside the allowlist", "color notacolor, chain A\n"),
    ("a representation outside the allowlist", "show notarep, chain A\n"),
    ("a selection name without the prefix", "select mysel, chain A\n"),
    ("parentheses", "select copilot_s, (chain A)\n"),
    ("the all keyword", "select copilot_s, all\n"),
    ("a lowercase residue name", "select copilot_s, resn ala\n"),
    ("no trailing newline", "orient chain A"),
)


def test_the_grammar_is_generated_from_the_allowlists() -> None:
    """Every terminal comes from pmc_core.plan, and only from there.

    The second half is the one that catches drift: a color added to
    COLOR_ALLOWLIST must not need an edit here, and one removed must not
    be left behind advertising something the parser now rejects.
    """
    grammar = build_grammar()
    color_rule = next(
        line for line in grammar.splitlines() if line.startswith("color ::= ")
    )
    representation_rule = next(
        line
        for line in grammar.splitlines()
        if line.startswith("representation ::= ")
    )

    assert set(re.findall(r'"([^"]+)"', color_rule)) == set(COLOR_ALLOWLIST)
    assert set(re.findall(r'"([^"]+)"', representation_rule)) == set(
        REPRESENTATION_ALLOWLIST
    )
    for verb in COMMAND_ALLOWLIST:
        assert f"{verb}-cmd ::= " in grammar, verb


def test_the_grammar_version_is_a_non_bool_int() -> None:
    """A version merely equal to 1 is not grammar version 1."""
    assert isinstance(GRAMMAR_VERSION, int)
    assert not isinstance(GRAMMAR_VERSION, bool)


@pytest.mark.parametrize(
    ("label", "text"), _ACCEPTED, ids=[case[0] for case in _ACCEPTED]
)
def test_the_grammar_accepts_everything_the_parser_accepts(
    label: str, text: str
) -> None:
    """The grammar may never be narrower than the parser.

    A grammar that rejects a plan the parser would have accepted makes
    that plan unreachable for a constrained model, which is a silent
    capability loss rather than a visible failure.
    """
    assert _parser_accepts(text), f"corpus case is not a valid plan: {label}"
    assert _grammar_accepts(text), label


@pytest.mark.parametrize(
    ("label", "text"), _REJECTED, ids=[case[0] for case in _REJECTED]
)
def test_the_grammar_rejects_what_the_language_has_no_spelling_for(
    label: str, text: str
) -> None:
    """Vocabulary the parser denies must not be derivable either.

    This is also what keeps the matcher above honest: a matcher that
    accepted everything would pass the previous test and fail every case
    here.
    """
    assert not _parser_accepts(text), label
    assert not _grammar_accepts(text), label


def test_the_matcher_refuses_a_document_it_cannot_fully_read() -> None:
    """Stray characters must fail loudly rather than be skipped.

    `re.findall` drops what it cannot match, so `root ::= "ok" @@@`
    would otherwise tokenize exactly like `root ::= "ok"` and the matcher
    would accept a document no GBNF engine would load. This is the
    matcher's own honesty check: its verdicts elsewhere in this file only
    mean something if it read every character it was given.
    """
    with pytest.raises(AssertionError, match="unconsumed"):
        _parse_gbnf('root ::= "ok" @@@\n')

    assert _parse_gbnf('root ::= "ok"\n')


def test_every_selection_term_reaches_the_grammar() -> None:
    """A term added to pmc_core.plan cannot be left out silently.

    The grammar derives its term rules from TERM_TYPES, so a new term
    raises at build time rather than being omitted -- but that guard is
    only as good as this assertion that all six are present today.
    """
    grammar = build_grammar()
    for term in TERM_TYPES:
        assert term.KEYWORD in grammar, term.__name__
    assert len(TERM_TYPES) == 6


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
