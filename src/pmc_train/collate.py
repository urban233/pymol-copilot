# Copyright 2026 PyMOL Copilot contributors.
"""Batch examples for the trainer, padding on the right.

Padding carries no loss (`IGNORE_INDEX`) and no attention. The batch
also carries each row's `completion_start`, so the loss can check,
batch by batch, that every prompt token is still masked when it reaches
the loss (`pmc_train.loss.assert_batch_masked`).
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

import torch

from pmc_train.examples import IGNORE_INDEX
from pmc_train.examples import Example


def example_item(example: Example) -> dict[str, Any]:
    """Turn an example into the item a dataset yields.

    Args:
        example: The example.

    Returns:
        Its token lists and completion start.
    """
    return {
        "input_ids": list(example.input_ids),
        "labels": list(example.labels),
        "completion_start": example.completion_start,
    }


class ExampleDataset(torch.utils.data.Dataset):
    """A fixed sequence of examples, in a fixed order."""

    def __init__(self, examples: Sequence[Example]) -> None:
        """Hold the examples.

        Args:
            examples: The examples, in the order to visit them.
        """
        self._examples = tuple(examples)

    def __len__(self) -> int:
        """Count the examples.

        Returns:
            The number of examples.
        """
        return len(self._examples)

    def __getitem__(self, index: int) -> dict[str, Any]:
        """Yield one example as a dataset item.

        Args:
            index: Its position.

        Returns:
            The item.
        """
        return example_item(self._examples[index])


class CompletionCollator:
    """Pad a list of dataset items into one batch."""

    def __init__(self, pad_id: int) -> None:
        """Remember the padding token.

        Args:
            pad_id: The token id padding positions hold.
        """
        self.pad_id = pad_id

    def __call__(
        self, items: Sequence[Mapping[str, Any]]
    ) -> dict[str, torch.Tensor]:
        """Pad the items on the right.

        Args:
            items: Dataset items from `example_item`.

        Returns:
            `input_ids`, `attention_mask`, `labels` and
            `completion_start` tensors.
        """
        width = max(len(item["input_ids"]) for item in items)
        input_ids = torch.full((len(items), width), self.pad_id)
        labels = torch.full((len(items), width), IGNORE_INDEX)
        attention = torch.zeros((len(items), width), dtype=torch.long)
        for row, item in enumerate(items):
            length = len(item["input_ids"])
            input_ids[row, :length] = torch.tensor(item["input_ids"])
            labels[row, :length] = torch.tensor(item["labels"])
            attention[row, :length] = 1
        return {
            "input_ids": input_ids,
            "attention_mask": attention,
            "labels": labels,
            "completion_start": torch.tensor(
                [item["completion_start"] for item in items]
            ),
        }
