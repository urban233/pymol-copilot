# Copyright 2026 PyMOL Copilot contributors.
"""Every training sample fits the configured length, measured exactly.

Item 16 recorded the longest *gold* prompt, 5,495 tokens. Training
prompts are longer: two training structures list four and three chains
of atoms. `data/train_lengths.json` records the exact figures with the
real tokenizer and template; this test recomputes them, so the record
cannot drift from the data, and fails if any sample would have to be
truncated.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path
from typing import Any

import pytest

from pmc_data.sample import read_samples
from pmc_train.config import TrainConfig
from pmc_train.examples import sequence_lengths

ROOT = Path(__file__).resolve().parents[3]
RECORD = Path(__file__).parent / "data" / "train_lengths.json"


@pytest.mark.slow
def test_every_training_sample_fits(
    tokenizer: Any, config: TrainConfig
) -> None:
    """The recomputed lengths equal the record, and all fit the limit."""
    samples = read_samples(ROOT / config.split.dir / "train.jsonl")
    measured = sequence_lengths(
        ((s.sample_id, s.prompt_text, s.plan_pml) for s in samples),
        tokenizer,
        config.chat_template_date,
    )
    measured["split_id"] = config.split.split_id
    assert measured == json.loads(RECORD.read_text(encoding="utf-8"))
    assert measured["longest_tokens"] <= config.max_seq_length
