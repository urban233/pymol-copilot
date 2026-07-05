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

"""Unit tests for incremental plan parsing."""

from __future__ import annotations

import pytest

import pymol_copilot.ai.app.models.plan_parser as plan_parser_module
import pymol_copilot.ai.app.models.session as session_module


@pytest.mark.unit
def test_plan_parser_incremental_feed() -> None:
    """Streaming chunks should yield steps once blocks close."""
    parser = plan_parser_module.PlanParser()
    chunk_a = (
        "Loading structure.\n<tool_call>\n"
        '{"name": "load_structure", "arguments": {"pdb_id": "7BZ5"}}\n'
    )
    assert parser.feed(chunk_a) == []

    chunk_b = "</tool_call>\n"
    new_steps = parser.feed(chunk_b)
    assert len(new_steps) == 1
    assert new_steps[0].name == "load_structure"
    assert new_steps[0].arguments["pdb_id"] == "7BZ5"


@pytest.mark.unit
def test_plan_parser_finalize_strips_tool_calls() -> None:
    """Finalize should return prose with tool blocks removed."""
    parser = plan_parser_module.PlanParser()
    text = (
        "Ready.\n<tool_call>\n"
        '{"name": "load_structure", "arguments": {"pdb_id": "1CRN"}}\n'
        "</tool_call>"
    )
    parser.feed(text)
    steps, prose = parser.finalize()
    assert len(steps) == 1
    assert steps[0].state == session_module.StepState.DONE
    assert "tool_call" not in prose
    assert "Ready." in prose


@pytest.mark.unit
def test_plan_parser_refusal_has_no_steps() -> None:
    """Prose-only output should produce zero plan steps."""
    parser = plan_parser_module.PlanParser()
    parser.feed("Please rotate the view manually.")
    steps, prose = parser.finalize()
    assert steps == []
    assert "rotate" in prose


@pytest.mark.unit
def test_format_step_summary() -> None:
    """Summary formatter should render compact action lines."""
    summary = plan_parser_module.format_step_summary(
        "load_structure",
        {"pdb_id": "7BZ5"},
    )
    assert summary == 'load_structure · pdb_id="7BZ5"'


@pytest.mark.unit
def test_plan_parser_multiple_nested_tool_calls() -> None:
    """Multiple tool calls with nested arguments should all parse."""
    parser = plan_parser_module.PlanParser()
    text = (
        "<tool_call>\n"
        '{"name": "load_structure", "arguments": {"pdb_id": "1DPX"}}\n'
        "</tool_call>\n"
        "<tool_call>\n"
        '{"name": "color_by_scheme", "arguments": {"target": "1DPX", '
        '"color": "red"}}\n'
        "</tool_call>\n"
        "<tool_call>\n"
        '{"name": "set_representation", "arguments": {"target": "1DPX", '
        '"style": "cartoon"}}\n'
        "</tool_call>"
    )
    steps = parser.feed(text)
    assert len(steps) == 3
    assert steps[0].name == "load_structure"
    assert steps[1].name == "color_by_scheme"
    assert steps[2].arguments["style"] == "cartoon"


@pytest.mark.unit
def test_plan_parser_repairs_malformed_screenshot_payloads() -> None:
    """Bare identifiers from grammar sampling should still parse."""
    parser = plan_parser_module.PlanParser()
    text = (
        "<tool_call>\n"
        '{"name":          load_structure,\n'
        '"arguments": {"pdb_id": 1DPX, "object_name": "1DPX"}}\n'
        "</tool_call>\n"
        "<tool_call>\n"
        '{"name":          color_by_scheme,\n'
        '"arguments": {"target": "1DPX", "color": "red"}}\n'
        "</tool_call>\n"
        "<tool_call>\n"
        '{"name":          set_representation,\n'
        '"arguments": {"target": "1DPX", "style":          cartoon}}\n'
        "</tool_call>"
    )
    steps = parser.feed(text)
    assert len(steps) == 3
    assert steps[0].arguments["pdb_id"] == "1DPX"
    assert steps[1].arguments["color"] == "red"
    assert steps[2].arguments["style"] == "cartoon"


@pytest.mark.unit
def test_plan_parser_handles_escaped_quotes_in_arguments() -> None:
    """Brace extraction must respect escaped quotes inside JSON strings."""
    parser = plan_parser_module.PlanParser()
    text = (
        "<tool_call>\n"
        '{"name": "save_image", "arguments": {"file_path": "a\\"b.png"}}\n'
        "</tool_call>"
    )
    steps = parser.feed(text)
    assert len(steps) == 1
    assert steps[0].arguments["file_path"] == 'a"b.png'


@pytest.mark.unit
def test_iter_tool_call_payloads_and_strip_helpers() -> None:
    """Shared helpers should extract payloads and strip closed blocks."""
    text = (
        'Intro\n<tool_call>{"name": "load_structure", '
        '"arguments": {"pdb_id": "1DPX"}}</tool_call>\nTail'
    )
    payloads = plan_parser_module.iter_tool_call_payloads(text)
    assert len(payloads) == 1
    assert plan_parser_module.parse_tool_call_payload(payloads[0]) is not None
    assert "tool_call" not in plan_parser_module.strip_tool_call_blocks(text)
    assert "Intro" in plan_parser_module.strip_tool_call_blocks(text)
