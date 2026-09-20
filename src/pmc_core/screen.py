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

#: Python keywords with no legitimate use in this language: a bare lambda
#: expression, and the two halves of a conditional expression. Matched as
#: whole words so a chain or selection name that merely contains one of
#: these letters in sequence -- there is no such name in the accepted
#: corpus, but this module does not assume there never will be -- is not
#: screened as hostile on that basis alone.
_HOSTILE_KEYWORDS = re.compile(r"\b(?:lambda|if|else)\b")


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
    if _HOSTILE_KEYWORDS.search(text) is not None:
        return SCREEN_HOSTILE
    return SCREEN_ORDINARY
