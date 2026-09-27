# Copyright 2026 PyMOL Copilot contributors.
"""Turn a dataset sample into one completion-only training example.

The model is trained to write a sample's plan, then stop. So an
example is the engine's own rendering of the prompt (`pmc_train.render`)
followed by the plan's tokens and `<|eot_id|>`, and its labels are
`IGNORE_INDEX` on every prompt token: only the plan and the end of turn
carry loss. The end of turn is supervised on purpose. The untuned base
model never stopped on its own (docs/evaluation/baseline/BASELINE.md:
nearly every sample `truncated`), and a plan the model cannot end is a
plan the harness cannot score.

A sequence longer than the configured limit is refused, never
truncated: cutting a prompt would drop part of the structure card the
plan depends on, and cutting a target would teach a plan that does not
stop.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pmc_train.render import END_OF_TURN
from pmc_train.render import prompt_ids

#: The label PyTorch's cross-entropy, and every loss here, skips.
IGNORE_INDEX = -100


class SequenceTooLongError(ValueError):
    """A prompt plus its target does not fit the configured length."""


@dataclass(frozen=True)
class Example:
    """One tokenized training example.

    Attributes:
        sample_id: The sample it came from.
        input_ids: The prompt's tokens, then the completion's.
        labels: `IGNORE_INDEX` for every prompt token, then the
            completion's tokens.
        completion_start: The index of the first completion token.
    """

    sample_id: str
    input_ids: tuple[int, ...]
    labels: tuple[int, ...]
    completion_start: int


def end_of_turn_id(tokenizer: Any) -> int:
    """Find the end-of-turn token's id.

    Args:
        tokenizer: The base model's tokenizer.

    Returns:
        The id of `<|eot_id|>`.
    """
    return int(tokenizer.convert_tokens_to_ids(END_OF_TURN))


def completion_ids(tokenizer: Any, plan_pml: str) -> list[int]:
    """Tokenize a plan as the reply the model should write.

    Args:
        tokenizer: The base model's tokenizer.
        plan_pml: The sample's canonical plan, ending in a newline.

    Returns:
        The plan's tokens, then `<|eot_id|>`.
    """
    plan = list(tokenizer(plan_pml, add_special_tokens=False)["input_ids"])
    return [*plan, end_of_turn_id(tokenizer)]


def build_example(
    sample_id: str,
    prompt_text: str,
    plan_pml: str,
    tokenizer: Any,
    date_string: str,
    max_seq_length: int,
) -> Example:
    """Build one completion-only example.

    Args:
        sample_id: The sample's id.
        prompt_text: The sample's prompt.
        plan_pml: The sample's canonical plan.
        tokenizer: The base model's tokenizer.
        date_string: The date the chat template is pinned to.
        max_seq_length: The longest sequence allowed.

    Returns:
        The example.

    Raises:
        SequenceTooLongError: If the prompt and completion together are
            longer than `max_seq_length`.
    """
    prompt = prompt_ids(tokenizer, prompt_text, date_string)
    completion = completion_ids(tokenizer, plan_pml)
    length = len(prompt) + len(completion)
    if length > max_seq_length:
        raise SequenceTooLongError(
            f"{sample_id}: {length} tokens exceed {max_seq_length}"
        )
    return Example(
        sample_id=sample_id,
        input_ids=(*prompt, *completion),
        labels=(*([IGNORE_INDEX] * len(prompt)), *completion),
        completion_start=len(prompt),
    )


def sequence_lengths(
    rows: Iterable[tuple[str, str, str]], tokenizer: Any, date_string: str
) -> dict[str, Any]:
    """Measure every example's prompt-plus-completion length.

    Args:
        rows: `(sample_id, prompt_text, plan_pml)` for each sample.
        tokenizer: The base model's tokenizer.
        date_string: The date the chat template is pinned to.

    Returns:
        The count, the longest length and its sample, and the counts
        above 4096 and 8192 tokens.
    """
    lengths: dict[str, int] = {}
    for sample_id, prompt_text, plan_pml in rows:
        lengths[sample_id] = len(
            prompt_ids(tokenizer, prompt_text, date_string)
        ) + len(completion_ids(tokenizer, plan_pml))
    longest = max(lengths, key=lambda key: (lengths[key], key))
    return {
        "samples": len(lengths),
        "longest_sample": longest,
        "longest_tokens": lengths[longest],
        "total_tokens": sum(lengths.values()),
        "over_4096": sum(1 for value in lengths.values() if value > 4096),
        "over_8192": sum(1 for value in lengths.values() if value > 8192),
    }
