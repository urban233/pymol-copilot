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

These tests deliberately assert only that each input is denied, not which
category denies it. The categories are pinned in test_parser_rejections.py;
pinning them again here would make this corpus fail when the parser is
restructured, which is the opposite of what a corpus is for.
"""

import sys

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml

#: Spelled indirectly so this module never has to escape one.
SINGLE_QUOTE = chr(39)

#: Spelled indirectly for the same reason.
BACKSLASH = chr(92)


def deny(text: str) -> None:
    """Assert that text is denied and that nothing was executed for it.

    Args:
        text: The adversarial input.
    """
    assert "pymol" not in sys.modules

    result = parse_pml(text)

    assert isinstance(result, ParseRejection), (
        f"accepted a denied form: {text!r}"
    )
    assert not any(
        name == "pymol" or name.startswith("pymol.")
        for name in list(sys.modules)
    )


@pytest.mark.parametrize(
    "text",
    [
        "select copilot_a, __import__("
        + SINGLE_QUOTE
        + "os"
        + SINGLE_QUOTE
        + ")\n",
        "color red, eval(1+1)\n",
        "orient exec(print(1))\n",
        "python\n",
        "python print(1)\n",
        "run script.py\n",
        "orient chain A if True else chain B\n",
        "select copilot_a, lambda: 1\n",
        "orient os.system(id)\n",
        "orient cmd.do(delete all)\n",
        "orient globals()\n",
        "orient getattr(cmd, do)\n",
        "orient chain ${A}\n",
        "orient chain %s\n",
    ],
    ids=[
        "dunder_import",
        "eval_call",
        "exec_call",
        "bare_python_verb",
        "python_verb_with_statement",
        "run_verb",
        "conditional_expression",
        "lambda_expression",
        "os_system_call",
        "cmd_do_call",
        "globals_call",
        "getattr_call",
        "shell_style_interpolation",
        "format_string_interpolation",
    ],
)
def test_python_evaluating_forms_are_denied(text: str) -> None:
    """No input can reach a Python evaluator through the parser.

    Args:
        text: Command text containing a Python-evaluating form.
    """
    deny(text)


@pytest.mark.parametrize(
    "text",
    [
        "orient chain A; rm -rf /\n",
        "color red, chain A && id\n",
        "color red, chain A | tee out\n",
        "orient chain A > out.txt\n",
        "orient chain A < in.txt\n",
        "orient $(id)\n",
        "orient `id`\n",
        "system id\n",
        "orient chain A" + BACKSLASH + "nid\n",
        "orient chain A\x00\n",
        "orient chain A & \n",
        "select copilot_a, chain A; delete all\n",
    ],
    ids=[
        "semicolon_command_chain",
        "and_operator",
        "pipe",
        "output_redirect",
        "input_redirect",
        "command_substitution",
        "backtick_substitution",
        "system_verb",
        "escaped_newline_literal",
        "null_byte",
        "background_operator",
        "chained_destructive_command",
    ],
)
def test_shell_metacharacters_are_denied(text: str) -> None:
    """No input can smuggle a shell construct past the parser.

    Args:
        text: Command text containing a shell metacharacter.
    """
    deny(text)


@pytest.mark.parametrize(
    "text",
    [
        "orient /etc/passwd\n",
        "orient ../../etc/passwd\n",
        "color red, /tmp/x\n",
        "orient ~/.ssh/id_rsa\n",
        "orient C:" + BACKSLASH + BACKSLASH + "Windows\n",
        "orient " + BACKSLASH + BACKSLASH + "server" + BACKSLASH + "share\n",
        "cd /tmp\n",
        "orient file:///etc/passwd\n",
        "orient http://example.com/x.pdb\n",
        "select copilot_a, chain A, /tmp/x\n",
    ],
    ids=[
        "absolute_posix_path",
        "relative_traversal_path",
        "path_as_target",
        "home_relative_path",
        "windows_drive_path",
        "unc_path",
        "cd_verb",
        "file_url",
        "http_url",
        "path_as_extra_argument",
    ],
)
def test_file_paths_are_denied(text: str) -> None:
    """No input can name a filesystem location.

    Args:
        text: Command text containing a file path.
    """
    deny(text)


@pytest.mark.parametrize(
    "text",
    [
        "load /etc/passwd\n",
        "load 1abc.pdb\n",
        "save session.pse\n",
        "save /tmp/out.pdb, chain A\n",
        "fetch 1abc\n",
        "fetch 1abc, async=0\n",
        "png /tmp/out.png\n",
        "export /tmp/out.pdb\n",
        "cif /tmp/out.cif\n",
        "set_view (1,0,0)\n",
        "delete all\n",
        "remove chain A\n",
        "alter chain A, b=0\n",
        "create copy, chain A\n",
        "quit\n",
        "reinitialize\n",
    ],
    ids=[
        "load_system_file",
        "load_structure",
        "save_session",
        "save_with_selection",
        "fetch_accession",
        "fetch_with_argument",
        "png_render",
        "export",
        "cif_export",
        "set_view",
        "delete_all",
        "remove",
        "alter",
        "create",
        "quit",
        "reinitialize",
    ],
)
def test_load_save_and_fetch_forms_are_denied(text: str) -> None:
    """No input can read, write, fetch, or destroy anything.

    Args:
        text: Command text naming a file or destructive operation.
    """
    deny(text)


@pytest.mark.parametrize(
    "text",
    [
        "plugin load evil.py\n",
        "plugin\n",
        "import pmg_tk\n",
        "extend mycmd, myfunc\n",
        "alias ls, system ls\n",
        "@script.pml\n",
        "spawn script.py\n",
        "cmd.extend(mycmd, myfunc)\n",
        "feedback disable, all, everything\n",
        "set pse_export_version, 1\n",
        "set_key F1, delete all\n",
        "api\n",
    ],
    ids=[
        "plugin_load",
        "bare_plugin_verb",
        "import_statement",
        "extend_verb",
        "alias_verb",
        "script_inclusion",
        "spawn_verb",
        "cmd_namespace_call",
        "feedback_verb",
        "unreviewed_setting",
        "key_binding",
        "api_verb",
    ],
)
def test_plugin_and_extension_invocations_are_denied(text: str) -> None:
    """No input can load a plugin, extend the command set, or bind a key.

    Args:
        text: Command text invoking a plugin or extension mechanism.
    """
    deny(text)


@pytest.mark.parametrize(
    "text",
    [
        "select copilot_a, chain A\ndelete all\n",
        "select copilot_a, chain A\ncolor red, copilot_a\nsystem id\n",
        "orient chain A\n@script.pml\n",
    ],
    ids=[
        "denied_form_after_a_valid_command",
        "denied_form_after_two_valid_commands",
        "script_inclusion_after_a_valid_command",
    ],
)
def test_a_denied_form_rejects_the_whole_plan(text: str) -> None:
    """One denied command denies the plan; no prefix of it is dispatched.

    This is the property that matters most in this module. A parser that
    returned the valid prefix and reported the rest as an error would hand
    a dispatcher something to run.

    Args:
        text: Command text whose valid prefix precedes a denied form.
    """
    deny(text)


def test_the_corpus_never_imports_pymol() -> None:
    """The whole corpus runs without Open-Source PyMOL ever being loaded."""
    assert "pymol" not in sys.modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
