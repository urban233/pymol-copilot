# Copyright 2026 PyMOL Copilot contributors.
"""The denied-form corpus: every shape V1 must refuse, with zero execution.

The specification's explicit-denial list names Python-evaluating forms,
shell and system commands, script inclusion, plugins and extensions,
arbitrary namespaces, unrestricted settings, file paths, load/save/export,
destructive or molecular-data mutations, and anything unknown. This module
is that list turned into literal inputs.

Every case asserts two things: the parser returned a typed rejection, and
Open-Source PyMOL was never imported while doing so. The second assertion is
what makes "denied with zero execution" a measured fact rather than a claim
about control flow -- pmc_core has no PyMOL dependency at all, so an import
appearing here would mean text had escaped the boundary.

Each case asserts the category that denies it, not merely that something
did. That was not the original design and the original design was wrong: with
only an "is rejected" assertion, a case like `load /etc/passwd` is denied
because `/etc/passwd` is not a selection expression, and would go on passing
if `load` were quietly mapped onto an allowlisted verb. Mutation testing
confirmed exactly that -- rewriting the verb lookup so `load` resolved to
`orient` left the whole suite green. Pinning the category is what makes this
corpus test the thing its ids claim.

Where a form is denied by a lexical rule before the verb or grammar is ever
consulted -- a backslash in a Windows path, quotes around a Python call --
the case says so rather than pretending otherwise.
"""

import sys

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from denied_forms import DENIED_EXPRESSION_FORMS
from denied_forms import LEXICALLY_DENIED_FORMS
from denied_forms import UNKNOWN_VERB_FORMS
from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml
from pmc_core.plan import COMMAND_ALLOWLIST


def deny(text: str, expected_category: str) -> None:
    """Assert text is denied, for the stated reason, with nothing executed.

    Args:
        text: The adversarial input.
        expected_category: The rejection category that must deny it. Pinning
            this is what keeps a case from passing for an unrelated reason.
    """
    assert "pymol" not in sys.modules

    result = parse_pml(text)

    assert isinstance(result, ParseRejection), (
        f"accepted a denied form: {text!r}"
    )
    assert result.category == expected_category, (
        f"{text!r} was denied as {result.category!r}, not {expected_category!r}"
    )
    assert not any(
        name == "pymol" or name.startswith("pymol.")
        for name in list(sys.modules)
    )


@pytest.mark.parametrize(
    "text",
    [text for text, _ in UNKNOWN_VERB_FORMS],
    ids=[case_id for _, case_id in UNKNOWN_VERB_FORMS],
)
def test_verbs_outside_the_allowlist_are_denied_as_unknown(text: str) -> None:
    """A dangerous verb is denied *because it is not allowlisted*.

    The category matters here more than anywhere else in the corpus. Denial
    for some incidental reason -- a malformed argument -- would leave the
    verb allowlist itself untested, and a change that quietly mapped one of
    these onto an allowlisted verb would go unnoticed.

    Args:
        text: Command text naming a verb outside the allowlist.
    """
    deny(f"{text}\n", "unknown_verb")


@pytest.mark.parametrize(
    "text",
    [text for text, _ in DENIED_EXPRESSION_FORMS],
    ids=[case_id for _, case_id in DENIED_EXPRESSION_FORMS],
)
def test_dangerous_payloads_in_argument_position_are_denied(
    text: str,
) -> None:
    """An allowlisted verb does not make its argument anything goes.

    Args:
        text: Command text carrying a denied payload as an argument.
    """
    deny(f"{text}\n", "invalid_selection_expression")


@pytest.mark.parametrize(
    ("text", "expected_category"),
    [(text, category) for text, category, _ in LEXICALLY_DENIED_FORMS],
    ids=[case_id for _, _, case_id in LEXICALLY_DENIED_FORMS],
)
def test_forms_denied_by_a_lexical_rule(
    text: str, expected_category: str
) -> None:
    """Quotes, backslashes and comments are refused before the grammar runs.

    Args:
        text: Command text denied by a lexical rule.
        expected_category: The lexical rule that denies it.
    """
    deny(f"{text}\n", expected_category)


@pytest.mark.parametrize(
    ("text", "expected_category"),
    [
        ("select copilot_a, chain A\ndelete all\n", "unknown_verb"),
        (
            "select copilot_a, chain A\ncolor red, copilot_a\nsystem id\n",
            "unknown_verb",
        ),
        ("orient chain A\nload /etc/passwd\n", "unknown_verb"),
    ],
    ids=[
        "denied_verb_after_a_valid_command",
        "denied_verb_after_two_valid_commands",
        "load_after_a_valid_command",
    ],
)
def test_a_denied_form_rejects_the_whole_plan(
    text: str, expected_category: str
) -> None:
    """One denied command denies the plan; no prefix of it is dispatched.

    This is the property that matters most in this module. A parser that
    returned the valid prefix and reported the rest as an error would hand a
    dispatcher something to run.

    Args:
        text: Command text whose valid prefix precedes a denied form.
        expected_category: The category that must deny it.
    """
    deny(text, expected_category)


def test_every_allowlisted_verb_is_absent_from_the_denied_corpus() -> None:
    """The corpus never accidentally lists a verb the language supports.

    A denied-form case naming an allowlisted verb would be denied for its
    argument and quietly stop testing what its id claims.
    """
    denied_verbs = {text.split(" ")[0] for text, _ in UNKNOWN_VERB_FORMS}

    assert denied_verbs.isdisjoint(set(COMMAND_ALLOWLIST))


def test_the_corpus_covers_every_named_denial_family() -> None:
    """Each family the specification names explicitly has cases here."""
    every_case = (
        [case_id for _, case_id in UNKNOWN_VERB_FORMS]
        + [case_id for _, case_id in DENIED_EXPRESSION_FORMS]
        + [case_id for _, _, case_id in LEXICALLY_DENIED_FORMS]
    )

    for required in (
        "dunder_import",
        "shell_command",
        "absolute_posix_path",
        "load_system_file",
        "save_session",
        "fetch_accession",
        "plugin_load",
        "script_inclusion",
    ):
        assert required in every_case


def test_the_corpus_never_imports_pymol() -> None:
    """The whole corpus runs without Open-Source PyMOL ever being loaded."""
    assert "pymol" not in sys.modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
