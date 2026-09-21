# Copyright 2026 PyMOL Copilot contributors.
"""A default-deny screen for whether a rejected completion may be repaired.

Orchestration rule 7 (SPECIFICATION.md:534-536) gives an ordinary denial one
repair opportunity and a hostile class none: "Denied commands receive at
most one repair opportunity; traversal, arbitrary-code, or other hostile
classes receive none." The parser and policy cannot make that distinction
themselves -- both `pmc_core.parser.parse_pml` and
`pmc_core.policy.evaluate_plan` file every dangerous payload
`tests/adversarial/test_denied_forms.py` carries under the same ordinary
rejection categories an honest syntax typo lands in
(`invalid_selection_expression`, `quoting`, `invalid_syntax`, and so on),
because refusing the payload is their whole job and naming *why* it is
refused is this module's job instead.

`screen_completion` is not a second parser and does not decide whether text
is acceptable -- the total parser and default-deny policy already do that,
completely, before this module is ever consulted. It decides only whether a
completion the parser or policy has already rejected is safe to feed back
to the model for one more attempt. It is deliberately asymmetric: a false
positive (screening an ordinary typo as hostile) costs one repair attempt
the request would otherwise have had; a false negative (screening a
dangerous payload as ordinary) hands the model another turn to try again
with nothing yet having executed anywhere. The corpus in
tests/adversarial/test_denied_forms.py -- every case docs/master_plan.md
item 2 already proves the parser and policy deny with zero execution -- is
this module's own fixture, so the two suites cannot drift apart.

This module imports no PyMOL and performs no I/O, in the same hermetic
half of pmc_core as `plan.py`, `policy.py`, and `errors.py`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import re

#: A completion carries none of the markers below: it may still be denied
#: by the parser or policy for an ordinary reason, but it is eligible for
#: repair.
SCREEN_ORDINARY = "ordinary"

#: A completion carries at least one marker the restricted command language
#: has no legitimate use for at all. Never repaired, regardless of which
#: category the parser or policy filed the denial under.
SCREEN_HOSTILE = "hostile"

#: The restricted command language (SPECIFICATION.md's five verbs, six
#: selection-term forms, and/or/not, and bare selection names) has no
#: legitimate use for any of these characters or forms. Their presence
#: alone is what this module screens on -- it never inspects what a
#: character or form is attempting to do, only that the language has
#: nothing it could mean.
#:
#: - A null byte: never valid in this language's text at all.
#: - Either quote character: the grammar has no quoted-string argument
#:   form anywhere; a quote is the signature of an attempt to smuggle a
#:   string literal past it.
#: - `#`: the parser's own "comment" lexical-denial category exists
#:   because PyMOL's real .pml format treats it as a comment marker; a
#:   model completion using it is attempting to have trailing text
#:   silently ignored rather than parsed.
#: - `;`: command chaining, in both a shell and PyMOL's own `cmd.do()`.
#: - A shell metacharacter: `&`, `|`, `>`, `<`, or a backtick, covering
#:   background execution, piping, redirection, and command substitution.
#: - `$(`: POSIX command substitution, not otherwise caught by the single
#:   shell-metacharacter check above.
#: - `/` or a backslash: every denied path and URL form in the adversarial
#:   corpus -- absolute POSIX paths, relative traversal, home-relative
#:   paths, file and http URLs, and both Windows drive and UNC paths --
#:   carries one or the other. The restricted grammar has no path or URL
#:   argument form at all, so either character's presence alone is
#:   sufficient; this module does not attempt to tell a legitimate-looking
#:   path from a traversal.
#: - `%`: printf-style format-string interpolation.
#: - `@`: PyMOL's own native `.pml` script-inclusion syntax, which the
#:   restricted language never grants a model access to.
_HOSTILE_CHARACTERS = frozenset(
    {
        "\x00",
        '"',
        "'",
        "#",
        ";",
        "&",
        "|",
        ">",
        "<",
        "`",
        "$",
        "/",
        "\\",
        "%",
        "@",
    }
)

#: A Python call or attribute-access form: an identifier, optionally
#: dotted, immediately followed by `(`. The restricted grammar never uses
#: a parenthesis at all, so this single pattern catches every named-call
#: form in the corpus -- `__import__(`, `eval(`, `exec(`, `globals(`,
#: `os.system(`, `cmd.do(`, and `getattr(` -- without enumerating callables
#: one at a time, which would leave the next one unnamed here as a gap.
_CALL_FORM = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\s*\(")

#: A bare lambda expression. Matched as a whole word, but with no co-
#: occurrence condition needed the way `if`/`else` below have one:
#: `pmc_core.plan.MAX_CHAIN_IDENTIFIER` caps a chain identifier at 4
#: characters, and no selection-name or verb token is "lambda" either, so
#: this word cannot appear in this language's own accepted vocabulary at
#: all.
_HOSTILE_LAMBDA = re.compile(r"\blambda\b")

#: The two halves of a conditional expression, each matched as a whole
#: word. Unlike `lambda`, `if` and `else` are individually indistinguishable
#: from a legitimate chain identifier -- both are within
#: `pmc_core.plan.MAX_CHAIN_IDENTIFIER`'s 4-character limit and contain only
#: letters, so `chain if` or `chain else` alone is ordinary, parseable text
#: for a structure with a chain literally named that. A real conditional
#: expression needs both halves, so `screen_completion` requires both
#: keywords present before treating the pair as hostile, catching the
#: adversarial corpus's own `"... if True else ..."` form without flagging
#: either word alone.
_HOSTILE_IF = re.compile(r"\bif\b")
_HOSTILE_ELSE = re.compile(r"\belse\b")

#: Every verb name in `tests/adversarial/denied_forms.UNKNOWN_VERB_FORMS`
#: that names a real, dangerous PyMOL or system capability outside this
#: language's own five verbs (select, color, show, hide, orient) --
#: interpreter access, process/shell execution, file or session I/O,
#: destructive session mutation, and settings/key-binding/plugin
#: reconfiguration. `_CALL_FORM` and `_HOSTILE_CHARACTERS` do not catch
#: these: a bare verb word like `run script.py` or `delete all` carries
#: no parenthesis and no punctuation this module already screens on.
#: Matched as whole words, not by verb position, so a verb named this
#: deep inside otherwise-unrelated text is still caught.
#:
#: Deliberately excludes `orientate`, which UNKNOWN_VERB_FORMS also
#: carries: it is one character away from the accepted verb `orient`, the
#: shape of an honest typo rather than an attempt at any of the
#: capabilities above, and is exactly the kind of case repair exists for.
_HOSTILE_VERBS = re.compile(
    r"\b(?:"
    r"python|run|system|spawn|cd|load|save|fetch|png|export|"
    r"delete|remove|alter|create|quit|reinitialize|set|set_key|"
    r"plugin|import|extend|alias|api|label|feedback"
    r")\b"
)


def screen_completion(text: str) -> str:
    """Screen a rejected completion for whether it may be repaired.

    Args:
        text: The raw model completion text that the parser or policy has
            already rejected.

    Returns:
        SCREEN_HOSTILE when `text` carries a marker the restricted command
        language has no legitimate use for; SCREEN_ORDINARY otherwise.
    """
    if not _HOSTILE_CHARACTERS.isdisjoint(text):
        return SCREEN_HOSTILE
    if _CALL_FORM.search(text) is not None:
        return SCREEN_HOSTILE
    if _HOSTILE_LAMBDA.search(text) is not None:
        return SCREEN_HOSTILE
    if (
        _HOSTILE_IF.search(text) is not None
        and _HOSTILE_ELSE.search(text) is not None
    ):
        return SCREEN_HOSTILE
    if _HOSTILE_VERBS.search(text) is not None:
        return SCREEN_HOSTILE
    return SCREEN_ORDINARY
