# Copyright 2026 PyMOL Copilot contributors.
"""Fixtures shared by the training tests."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from pathlib import Path
from typing import Any

import pytest

from pmc_train.config import DEFAULT_CONFIG
from pmc_train.config import TrainConfig
from pmc_train.config import load_config

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def config() -> TrainConfig:
    """The committed training config.

    Returns:
        The parsed `configs/training/lora-v1.json`.
    """
    return load_config(ROOT / DEFAULT_CONFIG)


@pytest.fixture(scope="session")
def tokenizer(config: TrainConfig) -> Any:
    """The base model's tokenizer, at the pinned revision.

    Args:
        config: The committed training config.

    Returns:
        The Hugging Face tokenizer.
    """
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        config.base_model.repo, revision=config.base_model.revision
    )
