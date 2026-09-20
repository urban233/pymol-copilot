# Copyright 2026 PyMOL Copilot contributors.
"""GBNF grammar for the restricted command language, generated from it.

`build_grammar()` emits one GBNF document describing the text
`pmc_core.parser` accepts, for an inference engine to constrain generation
with (master plan item 9). The Lemonade capability spike proved a supplied
grammar is enforced per request down to an exact forced token -- see
tests/discovery/lemonade/FINDINGS.md, Q1 -- so this is a real constraint on
what a model can emit, not a hint.

Two properties matter more than the grammar's contents.

**It never substitutes for the parser or the policy.**
SPECIFICATION.md:488 states this as a contract clause, and it is what keeps
the grammar outside the security boundary: every byte a constrained model
emits is still parsed by `pmc_core.parser` and adjudicated by
`pmc_core.policy` afterwards, exactly as unconstrained text would be. The
grammar makes malformed output rarer; it is never what makes output safe.

**It is deliberately no narrower than the parser.** Anything the parser
accepts, this grammar accepts. The converse is not promised: GBNF can only
express a bounded repeat by unrolling it, so the language's own
`MAX_COMMANDS` and `MAX_EXPRESSION_TERMS` bounds stay the parser's job and
the grammar admits longer plans than the parser will take. That direction
is safe -- the parser rejects what it always would -- while the opposite
direction is not, because a grammar narrower than the parser would make
legal plans unreachable and the model would never learn it could write
them. `tests/contract/test_grammar.py` pins the direction.

Every terminal is read from `pmc_core.plan` at build time. Nothing here
restates a verb, a color, a representation or a term spelling as a
literal, so adding a color to the allowlist cannot leave this module
behind, and removing one cannot leave it advertising a color the parser
now rejects.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.plan import COLOR_ALLOWLIST
from pmc_core.plan import COMMAND_ALLOWLIST
from pmc_core.plan import MAX_ATOM_NAME
from pmc_core.plan import MAX_CHAIN_IDENTIFIER
from pmc_core.plan import MAX_RESIDUE_IDENTIFIER
from pmc_core.plan import MAX_RESIDUE_NAME
from pmc_core.plan import MAX_SELECTION_NAME_BODY
from pmc_core.plan import REPRESENTATION_ALLOWLIST
from pmc_core.plan import SELECTION_NAME_PREFIX

#: This module's own grammar contract version, stamped into every prompt by
#: pmc_core.prompt and recorded with a model or evaluation artifact
#: (SPECIFICATION.md:491). An int, matching the other pmc_core contract
#: versions. Bump it whenever build_grammar()'s output changes at all: a
#: model trained or evaluated against one grammar is not comparable to one
#: trained against another, and the version is what makes that decidable
#: rather than a matter of reading two artifacts side by side.
GRAMMAR_VERSION = 1

#: The number of digits a residue identifier may carry. Derived rather
#: than written down, so the grammar tracks the language's own bound.
_RESIDUE_DIGITS = len(str(MAX_RESIDUE_IDENTIFIER))


def _alternation(values: tuple[str, ...]) -> str:
    """Return one GBNF alternation over literal strings.

    Args:
        values: The accepted literals, in the allowlist's own order.

    Returns:
        The alternation body, each literal double-quoted.

    Raises:
        ValueError: If values is empty, which would produce a rule no
            input can satisfy and so a grammar nothing can generate.
    """
    if not values:
        raise ValueError("a GBNF alternation needs at least one literal")
    return " | ".join(f'"{value}"' for value in values)


def _repeat(rule: str, maximum: int) -> str:
    """Return a GBNF fragment matching one to maximum repetitions.

    Args:
        rule: The rule name being repeated.
        maximum: The greatest number of repetitions accepted.

    Returns:
        The rule followed by maximum-1 optional repetitions, which is how
        GBNF expresses a bounded repeat -- it has no counted form.
    """
    return rule + "".join(f" {rule}?" for _ in range(maximum - 1))


def _command_rule(verb: str) -> str:
    """Return the GBNF rule body for one verb's command line.

    The argument forms come from that verb's own allowlist row rather
    than from a table here, so a verb whose forms change in
    pmc_core.plan changes shape here too.

    Args:
        verb: The verb to describe.

    Returns:
        The rule body, without the rule name or the assignment.

    Raises:
        ValueError: If the verb carries an argument form this module has
            no spelling for, which means pmc_core.plan grew a form and
            this module was not updated with it.
    """
    forms = COMMAND_ALLOWLIST[verb].argument_forms
    spellings = {
        "selection_name": "sel-name",
        "expression": "expression",
        "target": "target",
        "color": "color",
        "representation": "representation",
    }
    unknown = [form for form in forms if form not in spellings]
    if unknown:
        raise ValueError(f"no GBNF spelling for argument forms {unknown}")
    arguments = ' ", " '.join(spellings[form] for form in forms)
    return f'"{verb} " {arguments} "\\n"'


def build_grammar() -> str:
    """Return the GBNF grammar for the restricted command language.

    Returns:
        A GBNF document whose root matches one or more canonical command
        lines, generated from pmc_core.plan's allowlist tables.
    """
    verbs = tuple(COMMAND_ALLOWLIST)
    rules = [
        "root ::= command+",
        "command ::= " + " | ".join(f"{verb}-cmd" for verb in verbs),
    ]
    rules.extend(f"{verb}-cmd ::= {_command_rule(verb)}" for verb in verbs)
    rules.extend(
        [
            "target ::= sel-name | expression",
            f'sel-name ::= "{SELECTION_NAME_PREFIX}" '
            + _repeat("sel-char", MAX_SELECTION_NAME_BODY),
            "sel-char ::= [a-z0-9_]",
            'expression ::= and-clause (" or " and-clause)*',
            'and-clause ::= factor (" and " factor)*',
            'factor ::= ("not ")? term',
            "term ::= chain-term | resi-term | resn-term | name-term"
            ' | "hetatm" | "polymer"',
            'chain-term ::= "chain " '
            + _repeat("chain-char", MAX_CHAIN_IDENTIFIER),
            "chain-char ::= [a-zA-Z0-9]",
            'resi-term ::= "resi " residue ("-" residue)?',
            "residue ::= " + _repeat("digit", _RESIDUE_DIGITS),
            "digit ::= [0-9]",
            'resn-term ::= "resn " ' + _repeat("resn-char", MAX_RESIDUE_NAME),
            "resn-char ::= [A-Z0-9]",
            'name-term ::= "name " ' + _repeat("name-char", MAX_ATOM_NAME),
            "name-char ::= [A-Z0-9]",
            "color ::= " + _alternation(COLOR_ALLOWLIST),
            "representation ::= " + _alternation(REPRESENTATION_ALLOWLIST),
        ]
    )
    return "\n".join(rules) + "\n"
