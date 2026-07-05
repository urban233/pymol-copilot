# cBioMOL - open C++ and Python platform for BioMOLecular visualization and analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
# Source code is available at <https://github.com/urban233/cBioMOL>
# -------------------------------------------------------------------
# It is unlawful to modify or remove this copyright notice.
# -------------------------------------------------------------------
# Please see the accompanying LICENSE file for further information.
# -------------------------------------------------------------------
# Primary author of this source file:
#
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================

"""Unit tests for schema-driven GBNF generation."""

from __future__ import annotations

import pytest

import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.grammar.gbnf_generator as gbnf_generator_module
import pymol_copilot.ai.schemas.tool_schemas as tool_schemas_module


@pytest.mark.unit
def test_all_tool_names_in_grammar() -> None:
    """Every tool schema name must appear in the generated grammar."""
    grammar = gbnf_generator_module.generate_grammar()
    for schema in tool_schemas_module.TOOL_SCHEMAS:
        assert schema["name"] in grammar


@pytest.mark.unit
def test_grammar_contains_root_and_tool_call_block() -> None:
    """Grammar should define root and tool-call-block productions."""
    grammar = gbnf_generator_module.generate_grammar()
    assert "root ::=" in grammar
    assert "tool-call-block ::=" in grammar
    assert "tool-name ::=" in grammar


@pytest.mark.unit
def test_grammar_is_non_empty() -> None:
    """Generated grammar should contain multiple rules."""
    grammar = gbnf_generator_module.generate_grammar()
    rule_count = grammar.count("::=")
    assert rule_count > len(tool_schemas_module.TOOL_SCHEMAS)


@pytest.mark.unit
def test_grammar_rule_names_use_hyphens_not_underscores() -> None:
    """GBNF rule identifiers must not contain underscores."""
    grammar = gbnf_generator_module.generate_grammar()
    for line in grammar.splitlines():
        if " ::=" not in line:
            continue
        rule_name = line.split(" ::=")[0].strip()
        assert "_" not in rule_name, f"underscore in rule name: {rule_name}"


@pytest.mark.unit
def test_grammar_uses_hyphenated_args_rules() -> None:
    """Per-tool argument rules should use hyphenated identifiers."""
    grammar = gbnf_generator_module.generate_grammar()
    assert "args-load-structure ::=" in grammar
    assert "args_load_structure ::=" not in grammar


@pytest.mark.unit
def test_pattern_rules_emit_quoted_json_strings() -> None:
    """Pattern-constrained string fields must include JSON quote literals."""
    grammar = gbnf_generator_module.generate_grammar()
    assert 'args-load-structure-pdb-id ::= "\\""' in grammar
    assert (
        '"\\""'
        in grammar.split("args-load-structure-pdb-id ::=")[1].split("\n")[0]
    )


@pytest.mark.integration
def test_grammar_streams_without_crash() -> None:
    """Generated grammar must survive llama.cpp sampling, not just from_string."""
    pytest.importorskip("llama_cpp")

    import llama_cpp

    model_path = config_module.resolve_model_path(None)
    if not model_path.exists():
        pytest.skip(f"GGUF model not found: {model_path}")

    grammar = gbnf_generator_module.generate_grammar()
    llm = llama_cpp.Llama(
        model_path=str(model_path),
        n_ctx=4096,
        n_threads=2,
        verbose=False,
    )
    gr = llama_cpp.LlamaGrammar.from_string(grammar)
    stream = llm(
        "Load 1DPX and color it red",
        max_tokens=128,
        stream=True,
        grammar=gr,
        temperature=0.1,
    )
    output = "".join(chunk["choices"][0]["text"] for chunk in stream)
    assert isinstance(output, str)

    import pymol_copilot.ai.app.models.plan_parser as plan_parser_module

    payloads = plan_parser_module.iter_tool_call_payloads(output)
    for payload in payloads:
        parsed = plan_parser_module.parse_tool_call_payload(payload)
        assert parsed is not None
        assert isinstance(parsed.get("name"), str)
