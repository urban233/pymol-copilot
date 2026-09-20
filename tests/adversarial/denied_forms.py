# Copyright 2026 PyMOL Copilot contributors.
"""The denied-form corpus: every shape V1 must refuse, with zero execution.

Extracted from test_denied_forms.py so `src/pmc_core/screen.py`'s own test
(test_hostile_screen.py) can assert against exactly the same literals that
prove the parser and policy deny them, rather than a second, hand-copied
list that could quietly drift from this one. See test_denied_forms.py's own
module docstring for what each table represents and why the category each
case is denied under matters.
"""

#: Spelled indirectly so no module using this table ever has to escape one.
SINGLE_QUOTE = chr(39)

#: Spelled indirectly for the same reason.
BACKSLASH = chr(92)

#: Denied because the verb is not in the command allowlist. Every case here
#: carries a well-formed argument on purpose: a bare verb is refused for
#: having no argument, before the allowlist is ever consulted, which would
#: leave the allowlist itself untested.
UNKNOWN_VERB_FORMS = (
    ("python print(1)", "bare_python_interpreter"),
    ("run script.py", "script_execution"),
    ("system id", "shell_command"),
    ("spawn script.py", "process_spawn"),
    ("cd /tmp", "directory_change"),
    ("load /etc/passwd", "load_system_file"),
    ("load 1abc.pdb", "load_structure"),
    ("save session.pse", "save_session"),
    ("fetch 1abc", "fetch_accession"),
    ("png /tmp/out.png", "render_to_file"),
    ("export /tmp/out.pdb", "export"),
    ("delete all", "delete_everything"),
    ("remove chain A", "remove_atoms"),
    ("alter chain A, b=0", "alter_atom_data"),
    ("create copy, chain A", "create_object"),
    ("quit all", "quit"),
    ("reinitialize now", "reinitialize"),
    ("set ray_trace_mode, 1", "unreviewed_setting"),
    ("set_key F1, delete all", "key_binding"),
    ("plugin load evil.py", "plugin_load"),
    ("import pmg_tk", "import_statement"),
    ("extend mycmd, myfunc", "extend_command_set"),
    ("alias ls, system ls", "alias_command"),
    ("feedback disable, all, everything", "feedback"),
    ("api version", "api"),
    ("label chain A, name", "deferred_label_family"),
    ("orientate chain A", "verb_with_suffix"),
)

#: Denied because the argument is not a selection expression. The verb here
#: is an allowlisted one, so these prove the grammar refuses the payload even
#: when it arrives in a position the language does accept.
DENIED_EXPRESSION_FORMS = (
    ("select copilot_a, __import__(os)", "dunder_import"),
    ("color red, eval(1+1)", "eval_call"),
    ("orient exec(print(1))", "exec_call"),
    ("orient globals()", "globals_call"),
    ("orient os.system(id)", "os_system_call"),
    ("orient cmd.do(delete all)", "cmd_namespace_call"),
    ("select copilot_a, lambda x", "lambda_expression"),
    ("orient chain A if True else chain B", "conditional_expression"),
    ("orient chain %s", "format_string_interpolation"),
    ("orient chain A; rm -rf /", "semicolon_command_chain"),
    ("color red, chain A && id", "and_operator"),
    ("color red, chain A | tee out", "pipe"),
    ("orient chain A > out.txt", "output_redirect"),
    ("orient chain A < in.txt", "input_redirect"),
    ("orient $(id)", "command_substitution"),
    ("orient `id`", "backtick_substitution"),
    ("orient chain A&", "background_operator"),
    ("orient /etc/passwd", "absolute_posix_path"),
    ("orient ../../etc/passwd", "relative_traversal_path"),
    ("color red, /tmp/x", "path_as_target"),
    ("orient ~/.ssh/id_rsa", "home_relative_path"),
    ("orient file:///etc/passwd", "file_url"),
    ("orient http://example.com/x.pdb", "http_url"),
    ("orient @script.pml", "script_inclusion"),
    ("orient chain A" + chr(0), "null_byte"),
)

#: Denied by a lexical rule before the verb or the grammar is consulted.
#: Recorded honestly rather than filed under a category they never reach.
LEXICALLY_DENIED_FORMS = (
    (
        "select copilot_a, __import__("
        + SINGLE_QUOTE
        + "os"
        + SINGLE_QUOTE
        + ")",
        "quoting",
        "quoted_python_call",
    ),
    ('color "red", chain A', "quoting", "quoted_argument"),
    (
        "orient C:" + BACKSLASH + BACKSLASH + "Windows",
        "continuation",
        "windows_drive_path",
    ),
    (
        "orient " + BACKSLASH + BACKSLASH + "server" + BACKSLASH + "share",
        "continuation",
        "unc_path",
    ),
    ("orient chain A # then delete all", "comment", "trailing_comment"),
    (
        "select copilot_a, chain A, /tmp/x",
        "invalid_syntax",
        "path_as_extra_argument",
    ),
    ("orient getattr(cmd, do)", "invalid_syntax", "getattr_call"),
)
