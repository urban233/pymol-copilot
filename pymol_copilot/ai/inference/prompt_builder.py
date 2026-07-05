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

"""ChatML prompt builder for Qwen2.5 and Qwen3 tool-call inference."""

from __future__ import annotations

import json

import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.inference.conversation as conversation_module
import pymol_copilot.ai.schemas.tool_schemas as tool_schemas_module

_IM_START = "<|im_start|>"
_IM_END = "<|" + "im_end" + "|>"
_THINK_OPEN = "<" + "think" + ">"
_THINK_CLOSE = "</" + "think" + ">"


def _tools_block_qwen2(tool_schemas: list[dict]) -> str:
    """Format tool schemas for Qwen2.5-style system prompts.

    Args:
      tool_schemas: Hermes-style tool schema dicts.

    Returns:
      Tools XML block appended to the system message.
    """
    tools_json = json.dumps(tool_schemas, indent=2)
    return (
        "\n\n# Tools\n\n"
        "You may call one or more functions to assist with the user query.\n\n"
        "You are provided with function signatures within "
        "<tools></tools> XML tags:\n"
        f"<tools>\n{tools_json}\n</tools>\n\n"
        "For each function call, return a json object with function name "
        "and arguments within <tool_call></tool_call> XML tags:\n"
        "<tool_call>\n"
        '{"name": <function-name>, "arguments": <args-json-object>}\n'
        "</tool_call>"
    )


def _tools_block_qwen3(tool_schemas: list[dict]) -> str:
    """Format tool schemas for Qwen3-style system prompts.

    Args:
      tool_schemas: Hermes-style tool schema dicts.

    Returns:
      Tools block appended to the system message.
    """
    lines = [
        "\n\n# Tools\n\n",
        "You may call one or more functions to assist with the user query.\n\n",
        "You are provided with function signatures within XML tags:\n",
    ]
    for schema in tool_schemas:
        lines.append("\n")
        lines.append(json.dumps(schema))
    lines.extend(
        [
            "\n \n\n",
            "For each function call, return a json object with function "
            "name and arguments within <tool_call></tool_call> XML tags:\n",
            "<tool_call>\n",
            '{"name":, "arguments":}\n',
            "</tool_call>",
        ]
    )
    return "".join(lines)


def _assistant_suffix(prompt_family: config_module.PromptFamily) -> str:
    """Return the assistant-turn suffix for the given prompt family.

    Args:
      prompt_family: ``'qwen2'`` or ``'qwen3'``.

    Returns:
      ChatML suffix ending at the start of model generation.
    """
    suffix = f"{_IM_START}assistant\n"
    if prompt_family == "qwen3":
        suffix += f"{_THINK_OPEN}\n\n{_THINK_CLOSE}\n\n"
    return suffix


def build_prompt(
    conversation: conversation_module.Conversation,
    tool_schemas: list[dict] | None = None,
    prompt_family: config_module.PromptFamily = "qwen2",
) -> str:
    """Build a ChatML prompt ending at the assistant turn.

    The system prompt and embedded tool schemas are kept byte-stable across
    calls so llama.cpp can reuse KV-cache slots for the prefix.

    Args:
      conversation: Multi-turn user/assistant history.
      tool_schemas: Tool definitions; defaults to ``TOOL_SCHEMAS``.
      prompt_family: ``'qwen2'`` for Qwen2.5 GGUFs or ``'qwen3'`` for Qwen3.

    Returns:
      Formatted prompt string ready for llama.cpp completion.
    """
    schemas = tool_schemas or tool_schemas_module.TOOL_SCHEMAS
    if prompt_family == "qwen3":
        tools_text = _tools_block_qwen3(schemas)
    else:
        tools_text = _tools_block_qwen2(schemas)
    system_text = conversation.system_prompt + tools_text

    parts: list[str] = [
        f"{_IM_START}system\n{system_text}{_IM_END}\n",
    ]

    for turn in conversation.turns:
        role = turn.get("role", "")
        content = turn.get("content") or ""
        parts.append(f"{_IM_START}{role}\n{content}{_IM_END}\n")

    parts.append(_assistant_suffix(prompt_family))
    return "".join(parts)


def estimate_token_budget(prompt: str) -> int:
    """Rough token estimate for context budgeting.

    Args:
      prompt: Full formatted prompt string.

    Returns:
      Approximate token count using a 4-char heuristic.
    """
    return max(1, len(prompt) // 4)
