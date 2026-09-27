# Copyright 2026 PyMOL Copilot contributors.
"""The completion-only loss, and the check that a batch is still masked.

`completion_loss` is the loss the fine-tune trains on. It is the
standard next-token cross-entropy with prompt positions ignored, but it
applies the output layer only at positions whose next token is
supervised. A 16384-token sequence over Llama 3.2's 128,256-token
vocabulary would otherwise need a 16384 x 128256 logit tensor, about
4 GB in bf16, of which all but the plan's few dozen rows are masked
out anyway. `tests/test_masking.py` proves it equals the full-logit
masked loss and never touches a prompt position.

`assert_batch_masked` runs on every batch as it reaches the loss, so a
rewrite of the labels anywhere between the collator and the loss (by
the trainer, or by Unsloth's patches) stops the run instead of
silently training on the prompt.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Mapping
from typing import Any

import torch
import torch.nn.functional as functional

from pmc_train.examples import IGNORE_INDEX


class MaskingError(AssertionError):
    """A batch reached the loss with a prompt token supervised."""


def completion_loss(
    hidden: torch.Tensor,
    lm_head: Any,
    labels: torch.Tensor,
    num_items: int | torch.Tensor | None = None,
) -> torch.Tensor:
    """Compute the next-token loss over supervised positions only.

    Position `i`'s hidden state predicts token `i + 1`, so it is used
    only when label `i + 1` is supervised.

    Args:
        hidden: The final hidden states, `[batch, length, width]`.
        lm_head: The output layer.
        labels: `[batch, length]`, `IGNORE_INDEX` where not supervised.
        num_items: The supervised-token count to divide by (the trainer
            passes the count across an accumulated step); by default,
            this batch's own count.

    Returns:
        The mean cross-entropy, a scalar.
    """
    targets = labels[:, 1:]
    supervised = targets != IGNORE_INDEX
    logits = lm_head(hidden[:, :-1][supervised]).float()
    total = functional.cross_entropy(
        logits, targets[supervised], reduction="sum"
    )
    count = supervised.sum() if num_items is None else num_items
    return total / count


def assert_batch_masked(batch: Mapping[str, torch.Tensor], eot_id: int) -> int:
    """Check that a batch supervises exactly each row's completion.

    Args:
        batch: `input_ids`, `attention_mask`, `labels` and
            `completion_start`.
        eot_id: The end-of-turn token every completion ends with.

    Returns:
        The number of supervised tokens in the batch.

    Raises:
        MaskingError: If a prompt or padding position is supervised, a
            completion position is not, or a completion does not end in
            the end of turn.
    """
    input_ids = batch["input_ids"]
    labels = batch["labels"]
    lengths = batch["attention_mask"].sum(dim=1)
    supervised = 0
    for row, start in enumerate(batch["completion_start"].tolist()):
        length = int(lengths[row])
        if not 0 < start < length:
            raise MaskingError(f"row {row}: completion starts at {start}")
        if bool((labels[row, :start] != IGNORE_INDEX).any()):
            raise MaskingError(f"row {row}: a prompt token is supervised")
        if bool((labels[row, length:] != IGNORE_INDEX).any()):
            raise MaskingError(f"row {row}: a padding token is supervised")
        if not torch.equal(
            labels[row, start:length], input_ids[row, start:length]
        ):
            raise MaskingError(f"row {row}: completion labels differ")
        if int(labels[row, length - 1]) != eot_id:
            raise MaskingError(f"row {row}: completion does not end the turn")
        supervised += length - start
    return supervised
