# Copyright 2026 PyMOL Copilot contributors.
"""Render a training prompt exactly as the evaluation engine does.

The engine (item 9's Lemonade adapter, `pmc_agent.inference.lemonade`)
sends every prompt as one user message, with no system message, to a
llama-server running the GGUF's own Jinja chat template, with the
template's date pinned by `--chat-template-kwargs
{"date_string":"26 Jul 2024"}` (configs/evaluation/README.md). A model
trained on any other bytes would be evaluated on a prompt it never saw.

llama-server strips the template's leading `<|begin_of_text|>` and adds
the token back when it tokenizes, so the model sees exactly one. The
Hugging Face template keeps it in the text, so the rendered text is
tokenized here without adding special tokens. The render-parity test
(`tests/test_render.py`) pins both the text and the token ids against
captures from the engine itself.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from typing import Any

#: The Llama 3 beginning-of-text marker the template emits.
BEGIN_OF_TEXT = "<|begin_of_text|>"

#: The end-of-turn marker a chat completion stops at.
END_OF_TURN = "<|eot_id|>"


def messages_for(prompt_text: str) -> list[dict[str, str]]:
    """Wrap a prompt the way the engine adapter sends it.

    Args:
        prompt_text: A sample's `prompt_text`.

    Returns:
        The one-message chat the adapter posts.
    """
    return [{"role": "user", "content": prompt_text}]


def render_prompt(tokenizer: Any, prompt_text: str, date_string: str) -> str:
    """Render a prompt through the chat template, ready for the reply.

    Args:
        tokenizer: The base model's Hugging Face tokenizer.
        prompt_text: A sample's `prompt_text`.
        date_string: The date the engine pins the template to.

    Returns:
        The rendered text, from `<|begin_of_text|>` through the
        assistant header.
    """
    rendered = tokenizer.apply_chat_template(
        messages_for(prompt_text),
        tokenize=False,
        add_generation_prompt=True,
        date_string=date_string,
    )
    if not isinstance(rendered, str):
        raise TypeError("the chat template did not render text")
    return rendered


def prompt_ids(tokenizer: Any, prompt_text: str, date_string: str) -> list[int]:
    """Tokenize a prompt as the engine does.

    Args:
        tokenizer: The base model's Hugging Face tokenizer.
        prompt_text: A sample's `prompt_text`.
        date_string: The date the engine pins the template to.

    Returns:
        The prompt's token ids, starting with exactly one
        `<|begin_of_text|>`.
    """
    rendered = render_prompt(tokenizer, prompt_text, date_string)
    return list(tokenizer(rendered, add_special_tokens=False)["input_ids"])
