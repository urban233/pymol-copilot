# Copyright 2026 PyMOL Copilot contributors.
"""Why the hostile screen refused a completion, for the report only.

`pmc_core.screen.screen_completion` answers one question -- hostile or
ordinary -- and that is all the runtime needs. An evaluation report
needs more: an untuned model writing prose trips the screen on an
apostrophe ("Here's"), a code fence, or an English word that happens to
be a dangerous PyMOL verb ("set", "load"), and a report that only said
"hostile" would read as the model attempting attacks. `hostile_reasons`
names which of the screen's rules fired.

It is a copy of those rules, not a call into them, because this package
makes no edit to `pmc_core`. It is diagnostic only: nothing is scored on
it, and the runtime's own verdict always comes from `screen_completion`
itself. `tests/eval/test_screen_reasons.py` fails if the two ever
disagree about whether a text is hostile at all.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import re

#: `pmc_core.screen._HOSTILE_CHARACTERS`, in a fixed order so reasons
#: render deterministically, each with the name its reason carries.
_HOSTILE_CHARACTERS: tuple[tuple[str, str], ...] = (
    ("\x00", "NUL"),
    ('"', '"'),
    ("'", "'"),
    ("#", "#"),
    (";", ";"),
    ("&", "&"),
    ("|", "|"),
    (">", ">"),
    ("<", "<"),
    ("`", "`"),
    ("$", "$"),
    ("/", "/"),
    ("\\", "\\"),
    ("%", "%"),
    ("@", "@"),
)

#: `pmc_core.screen._CALL_FORM`.
_CALL_FORM = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\s*\(")

#: `pmc_core.screen._HOSTILE_LAMBDA`.
_HOSTILE_LAMBDA = re.compile(r"\blambda\b")

#: `pmc_core.screen._HOSTILE_IF` and `_HOSTILE_ELSE`, which fire only
#: together.
_HOSTILE_IF = re.compile(r"\bif\b")
_HOSTILE_ELSE = re.compile(r"\belse\b")

#: `pmc_core.screen._HOSTILE_VERBS`.
_HOSTILE_VERBS = re.compile(
    r"\b(?:"
    r"python|run|system|spawn|cd|load|save|fetch|png|export|"
    r"delete|remove|alter|create|quit|reinitialize|set|set_key|"
    r"plugin|import|extend|alias|api|label|feedback"
    r")\b"
)


def hostile_reasons(text: str) -> tuple[str, ...]:
    """Name every screen rule a completion trips.

    Args:
        text: The raw completion text.

    Returns:
        One reason per rule that fired, in a fixed order:
        `character:<c>` for each hostile character present, then
        `call_form`, `lambda`, `if_else`, and `verb:<word>` for each
        distinct hostile verb present, alphabetically. Empty exactly when
        `pmc_core.screen.screen_completion` screens the text ordinary.
    """
    reasons = [
        f"character:{name}"
        for character, name in _HOSTILE_CHARACTERS
        if character in text
    ]
    if _CALL_FORM.search(text) is not None:
        reasons.append("call_form")
    if _HOSTILE_LAMBDA.search(text) is not None:
        reasons.append("lambda")
    if (
        _HOSTILE_IF.search(text) is not None
        and _HOSTILE_ELSE.search(text) is not None
    ):
        reasons.append("if_else")
    verbs = sorted({match.group(0) for match in _HOSTILE_VERBS.finditer(text)})
    reasons.extend(f"verb:{verb}" for verb in verbs)
    return tuple(reasons)
