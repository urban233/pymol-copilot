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

"""Unit tests for ChatML prompt construction."""

from __future__ import annotations

import pytest

import pymol_copilot.ai.inference.conversation as conversation_module
import pymol_copilot.ai.inference.prompt_builder as prompt_builder_module
import pymol_copilot.ai.schemas.tool_schemas as tool_schemas_module


@pytest.mark.unit
def test_build_prompt_contains_tools_and_assistant_suffix() -> None:
    """Prompt should embed tools and end at the assistant turn."""
    conversation = conversation_module.Conversation()
    conversation.append_user("Load 7BZ5.")
    prompt = prompt_builder_module.build_prompt(conversation)
    assert "<|im_start|>system" in prompt
    assert "<tools>" in prompt
    assert "load_structure" in prompt
    assert "<|im_start|>user" in prompt
    assert "Load 7BZ5." in prompt
    assert prompt.endswith("<|im_start|>assistant\n")


@pytest.mark.unit
def test_build_prompt_qwen3_uses_no_think_suffix() -> None:
    """Qwen3 prompts should include the empty thinking block."""
    conversation = conversation_module.Conversation()
    conversation.append_user("Load 7BZ5.")
    prompt = prompt_builder_module.build_prompt(
        conversation,
        prompt_family="qwen3",
    )
    assert "<tools>" not in prompt
    assert "<" + "think" + ">" in prompt
    assert prompt.endswith("<" + "think" + ">\n\n</" + "think" + ">\n\n")


@pytest.mark.unit
def test_build_prompt_qwen3_tools_use_json_lines() -> None:
    """Qwen3 tool blocks should omit the Qwen2 tools wrapper."""
    conversation = conversation_module.Conversation()
    conversation.append_user("test")
    prompt = prompt_builder_module.build_prompt(
        conversation,
        tool_schemas=[{"name": "load_structure", "description": "Load"}],
        prompt_family="qwen3",
    )
    assert '"name": "load_structure"' in prompt
    assert "<tools>" not in prompt


@pytest.mark.unit
def test_stable_system_prefix_across_turns() -> None:
    """System/tools prefix should remain identical as turns grow."""
    conversation = conversation_module.Conversation()
    conversation.append_user("First request.")
    first = prompt_builder_module.build_prompt(conversation)
    prefix_len = first.index("<|im_start|>user")

    conversation.append_assistant("Done.")
    conversation.append_user("Second request.")
    second = prompt_builder_module.build_prompt(conversation)
    assert second[:prefix_len] == first[:prefix_len]


@pytest.mark.unit
def test_all_tool_names_present_in_tools_block() -> None:
    """Every registered tool name should appear in the prompt tools JSON."""
    conversation = conversation_module.Conversation()
    conversation.append_user("test")
    prompt = prompt_builder_module.build_prompt(conversation)
    for schema in tool_schemas_module.TOOL_SCHEMAS:
        assert schema["name"] in prompt
