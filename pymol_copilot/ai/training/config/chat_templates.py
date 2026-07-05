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
# ==============================================================================
#
"""Model-agnostic chat template adapter registry.

Different LLM families use incompatible wire formats for tool calls.
This module decouples the training scripts from those format details.
Adding support for a new model requires only a new ``ChatTemplateAdapter``
subclass registered in ``_REGISTRY`` — no changes to ``finetune.py``.

Supported adapters
------------------
``qwen2``
    Qwen2 / Qwen2.5 family.  Uses ``<|im_start|>`` / ``<|im_end|>`` tokens
    and ``<tool_call>`` XML blocks.  The tokenizer's built-in
    ``apply_chat_template`` handles the exact formatting.

``qwen3``
    Qwen3 family.  Same ChatML and ``<tool_call>`` wire format as Qwen2.5,
    but inference must pass ``enable_thinking=False`` to suppress the
    optional reasoning block.

``generic``
    Any model with a standard HuggingFace chat template.  Tool calls are
    embedded as JSON in the assistant content string.
"""

from __future__ import annotations

import json
from typing import Any


class ChatTemplateAdapter:
    """Base class for model-specific chat template helpers.

    Subclasses must implement ``apply``, ``format_for_training``,
    ``response_template_token``, and ``response_template_token_ids``.
    The training scripts call only the public interface defined here,
    never the HuggingFace tokenizer API directly.
    """

    @property
    def response_template_token(self) -> str:
        """The token string that marks the start of an assistant turn.

        ``DataCollatorForCompletionOnlyLM`` uses this to locate the boundary
        between the prompt (masked) and the target (trained on) in each
        sequence.

        Returns:
          A string token sequence present verbatim in the formatted output.

        Raises:
          NotImplementedError: If the subclass does not override this property.
        """
        raise NotImplementedError

    def response_template_token_ids(self, tokenizer: Any) -> list[int]:
        """Return token IDs for the response template.

        Encoding the template string via this method is more reliable than
        passing the raw string to ``DataCollatorForCompletionOnlyLM``.
        The tokenizer may assign different IDs to the same character
        sequence depending on surrounding context (BPE merges, newline
        handling).  Encoding the template as a stand-alone sequence with
        ``add_special_tokens=False`` matches what appears inside the
        formatted training text.

        Args:
          tokenizer: A HuggingFace tokenizer for the target model.

        Returns:
          A list of integer token IDs for the response template.

        Raises:
          NotImplementedError: If the subclass does not override this method.
        """
        raise NotImplementedError

    def format_for_training(self, messages: list[dict]) -> str:
        """Format messages into a compact string for training.

        Unlike ``apply``, this method does NOT inject full tool schemas into
        the system prompt.  Tool schemas serialised as JSON can exceed 1500
        tokens, pushing the assistant turn past the sequence-length budget
        and causing ``DataCollatorForCompletionOnlyLM`` to mask all labels
        to -100.  Fine-tuning teaches the FORMAT of tool calls; schemas are
        injected at inference time by the model's chat template.

        Args:
          messages: Conversation turns in the OpenAI messages format.
            Each dict has at minimum a ``role`` key and a ``content`` key.
            Assistant turns may carry ``tool_calls`` as a list.

        Returns:
          A compact formatted string ready for tokenisation.

        Raises:
          NotImplementedError: If the subclass does not override this method.
        """
        raise NotImplementedError

    def apply(
        self,
        tokenizer: Any,
        messages: list[dict],
        tool_schemas: list[dict],
    ) -> str:
        """Apply the model's chat template and return the formatted string.

        Args:
          tokenizer: A HuggingFace ``PreTrainedTokenizer`` or
            ``PreTrainedTokenizerFast`` instance for the target model.
          messages: Conversation turns in the OpenAI messages format.
            Each dict has at minimum a ``role`` key ('system', 'user',
            or 'assistant') and a ``content`` key.  Assistant turns may
            additionally carry ``tool_calls``.
          tool_schemas: List of JSON-serialisable tool schema dicts (the
            same list stored in ``data/tools.json``).

        Returns:
          A single formatted string ready for tokenisation.

        Raises:
          NotImplementedError: If the subclass does not override this method.
        """
        raise NotImplementedError

    @staticmethod
    def for_model(model_name: str) -> "ChatTemplateAdapter":
        """Return the appropriate adapter for a given model name.

        The factory inspects the model name string to determine the model
        family and returns the matching adapter.  Unknown models fall back
        to the ``generic`` adapter.

        Args:
          model_name: HuggingFace model identifier, e.g.
            ``'Qwen/Qwen2.5-1.5B-Instruct'``.

        Returns:
          A ``ChatTemplateAdapter`` instance for the detected model family.
        """
        lower = model_name.lower()
        for key, adapter_cls in _REGISTRY.items():
            if key in lower:
                return adapter_cls()
        return GenericChatTemplateAdapter()


class Qwen2ChatTemplateAdapter(ChatTemplateAdapter):
    """Adapter for Qwen2 / Qwen2.5 models.

    Delegates to the tokenizer's built-in ``apply_chat_template`` with the
    ``tools`` argument, which inserts the ``<tools>`` block and wraps tool
    calls in ``<tool_call>`` XML tags automatically.
    """

    @property
    def response_template_token(self) -> str:
        """The Qwen2.5 token sequence that begins an assistant turn.

        Returns:
          The literal string ``'<|im_start|>assistant'``.
        """
        return "<|im_start|>assistant"

    def response_template_token_ids(self, tokenizer: Any) -> list[int]:
        """Return token IDs for ``<|im_start|>assistant``.

        Encodes the template with ``add_special_tokens=False`` so the IDs
        match exactly what appears inside the ChatML-formatted text (where
        ``<|im_start|>`` is always a single special token).

        Args:
          tokenizer: Qwen2.5 tokenizer instance.

        Returns:
          List of token IDs: [id(<|im_start|>), id(assistant)].
        """
        return tokenizer.encode(
            "<|im_start|>assistant",
            add_special_tokens=False,
        )

    def format_for_training(self, messages: list[dict]) -> str:
        """Build a compact Qwen2.5 ChatML string for training.

        Constructs the ``<|im_start|>`` / ``<|im_end|>`` format manually.
        Tool calls are rendered as ``<tool_call>`` XML blocks.  No tool
        schemas are embedded in the system prompt — they are injected at
        inference time via ``apply_chat_template``.

        Args:
          messages: Conversation turns (system / user / assistant).
            Assistant turns may have a ``tool_calls`` list with entries
            of the form ``{"function": {"name": str, "arguments": str}}``.

        Returns:
          Formatted ChatML string ending with ``<|im_end|>\n``.
        """
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []

            parts.append(f"<|im_start|>{role}\n")

            if role == "assistant" and tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    # ``arguments`` is a JSON-encoded string stored by
                    # _build_messages() in generate_dataset.py.
                    args = fn.get("arguments", "{}")
                    parts.append(
                        f"<tool_call>\n"
                        f'{{"name": "{name}", "arguments": {args}}}\n'
                        f"</tool_call>\n"
                    )
            else:
                parts.append(content + "\n")

            parts.append("<|im_end|>\n")

        return "".join(parts)

    def apply(
        self,
        tokenizer: Any,
        messages: list[dict],
        tool_schemas: list[dict],
    ) -> str:
        """Apply the Qwen2.5 native chat template with tool-call support.

        Calls ``tokenizer.apply_chat_template`` with the Qwen2.5 default
        template, which automatically formats tool schemas and tool calls.

        Args:
          tokenizer: Qwen2.5 tokenizer instance.
          messages: Conversation turns (system / user / assistant).
          tool_schemas: Tool schemas to embed in the system prompt.

        Returns:
          Formatted string with ``<|im_start|>`` / ``<|im_end|>`` tokens.
        """
        return tokenizer.apply_chat_template(
            messages,
            tools=tool_schemas,
            tokenize=False,
            add_generation_prompt=False,
        )


class Qwen3ChatTemplateAdapter(Qwen2ChatTemplateAdapter):
    """Adapter for Qwen3 models.

    Training format matches Qwen2 ChatML.  Inference disables the optional
    thinking block via ``enable_thinking=False``.
    """

    def apply(
        self,
        tokenizer: Any,
        messages: list[dict],
        tool_schemas: list[dict],
    ) -> str:
        """Apply the Qwen3 native chat template with tool-call support.

        Args:
          tokenizer: Qwen3 tokenizer instance.
          messages: Conversation turns (system / user / assistant).
          tool_schemas: Tool schemas to embed in the system prompt.

        Returns:
          Formatted string with ``<|im_start|>`` / ``<|im_end|>`` tokens.
        """
        return tokenizer.apply_chat_template(
            messages,
            tools=tool_schemas,
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=False,
        )


class GenericChatTemplateAdapter(ChatTemplateAdapter):
    """Adapter for any model with a standard HuggingFace chat template.

    Tool calls are embedded as a compact JSON block in the assistant content
    string, since the generic template has no tool-call slot.
    """

    @property
    def response_template_token(self) -> str:
        """A common HuggingFace Llama-style assistant header token.

        Returns:
          The literal string
          ``'<|start_header_id|>assistant<|end_header_id|>'``.
        """
        return "<|start_header_id|>assistant<|end_header_id|>"

    def response_template_token_ids(self, tokenizer: Any) -> list[int]:
        """Return token IDs for the Llama-style assistant header.

        Args:
          tokenizer: Tokenizer for the target model.

        Returns:
          List of token IDs for the assistant header sequence.
        """
        return tokenizer.encode(
            "<|start_header_id|>assistant<|end_header_id|>",
            add_special_tokens=False,
        )

    def format_for_training(self, messages: list[dict]) -> str:
        """Build a compact training string using HuggingFace ChatML format.

        Tool calls are serialised as JSON inside ``<tool_calls>`` tags and
        appended to the assistant content string.  No tool schemas are
        embedded in the system message.

        Args:
          messages: Conversation turns.

        Returns:
          A formatted string produced by ``apply`` with an empty tool schema
          list, so the system message stays compact.
        """
        # Re-use the generic embed helpers but with no schemas injected.
        processed = _embed_tool_calls_in_content(messages)
        # Build the template string manually to avoid requiring a tokenizer.
        # For the generic adapter the canonical format uses the
        # Llama-3/Mistral header tokens.
        parts: list[str] = []
        for msg in processed:
            role = msg.get("role", "")
            content = msg.get("content") or ""
            parts.append(
                f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"
            )
        return "".join(parts)

    def apply(
        self,
        tokenizer: Any,
        messages: list[dict],
        tool_schemas: list[dict],
    ) -> str:
        """Apply the tokenizer's default chat template.

        Tool schemas are injected into the system message content.
        Tool calls are serialised as JSON and appended to the assistant
        content string.

        Args:
          tokenizer: Any HuggingFace tokenizer that has a ``chat_template``.
          messages: Conversation turns.
          tool_schemas: Tool schemas to append to the system message.

        Returns:
          Formatted string produced by ``tokenizer.apply_chat_template``.
        """
        processed = _embed_tool_schemas_in_system(messages, tool_schemas)
        processed = _embed_tool_calls_in_content(processed)
        return tokenizer.apply_chat_template(
            processed,
            tokenize=False,
            add_generation_prompt=False,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _embed_tool_schemas_in_system(
    messages: list[dict],
    tool_schemas: list[dict],
) -> list[dict]:
    """Append tool schema JSON to the system message content.

    Args:
      messages: Original conversation turns.
      tool_schemas: Tool schemas to embed.

    Returns:
      A new list of message dicts with the system content augmented.
    """
    schema_block = "\n\nAvailable tools (JSON):\n" + json.dumps(
        tool_schemas, indent=2
    )
    result: list[dict] = []
    found_system = False
    for msg in messages:
        if msg.get("role") == "system" and not found_system:
            new_msg = dict(msg)
            new_msg["content"] = (msg.get("content") or "") + schema_block
            result.append(new_msg)
            found_system = True
        else:
            result.append(msg)
    if not found_system:
        result.insert(
            0,
            {
                "role": "system",
                "content": "You are a helpful AI assistant." + schema_block,
            },
        )
    return result


def _embed_tool_calls_in_content(
    messages: list[dict],
) -> list[dict]:
    """Convert tool_calls fields to JSON text in assistant content.

    HuggingFace's generic template does not render ``tool_calls``; this
    helper serialises them into the ``content`` string so they appear in
    the formatted output.

    Args:
      messages: Conversation turns, potentially with ``tool_calls``.

    Returns:
      A new list of message dicts with ``tool_calls`` embedded as text.
    """
    result: list[dict] = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            new_msg = dict(msg)
            calls_json = json.dumps(
                [tc["function"] for tc in msg["tool_calls"]],
                indent=2,
            )
            existing = msg.get("content") or ""
            new_msg["content"] = (
                existing
                + ("\n" if existing else "")
                + "<tool_calls>\n"
                + calls_json
                + "\n</tool_calls>"
            )
            new_msg.pop("tool_calls", None)
            result.append(new_msg)
        else:
            result.append(msg)
    return result


# Registry maps model name substrings to adapter classes.
# Checked in order; first match wins.
_REGISTRY: dict[str, type[ChatTemplateAdapter]] = {
    "qwen3": Qwen3ChatTemplateAdapter,
    "qwen2": Qwen2ChatTemplateAdapter,
}
