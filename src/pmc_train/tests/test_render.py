# Copyright 2026 PyMOL Copilot contributors.
"""Training prompts are byte- and token-identical to what the engine sees.

The fixtures under `data/engine_render/` were captured from the
evaluation engine by `pmc_train.capture_engine_render`: llama-server's
own template rendering, its tokenization of that rendering, and the
prompt-token count Lemonade reported for a real chat request. If the
Hugging Face template, the date or the tokenizer drifted from the
engine's, the fine-tune would learn on prompts the evaluation never
sends.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from pmc_train.config import TrainConfig
from pmc_train.render import BEGIN_OF_TEXT
from pmc_train.render import prompt_ids
from pmc_train.render import render_prompt

FIXTURES = sorted(
    (Path(__file__).parent / "data" / "engine_render").glob("*.json")
)


def _load(path: Path) -> dict[str, Any]:
    """Read one engine capture.

    Args:
        path: The fixture file.

    Returns:
        The decoded capture.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixtures_cover_gold_and_train() -> None:
    """Captures exist for the longest gold and train prompts and two short ones."""
    names = {path.stem for path in FIXTURES}
    assert {"gold_061", "everything_four_chains_00153"} <= names
    assert len(names) >= 4
    for path in FIXTURES:
        capture = _load(path)
        digest = hashlib.sha256(capture["prompt_text"].encode("utf-8"))
        assert digest.hexdigest() == capture["prompt_sha256"]
        assert "26 Jul 2024" in capture["engine"]["llamacpp_args"]


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_render_is_byte_identical_to_the_engine(
    path: Path, tokenizer: Any, config: TrainConfig
) -> None:
    """The rendered text is the engine's, plus the one BOS it adds back."""
    capture = _load(path)
    rendered = render_prompt(
        tokenizer, capture["prompt_text"], config.chat_template_date
    )
    assert rendered == BEGIN_OF_TEXT + capture["engine_render"]


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_token_ids_are_the_engine_ones(
    path: Path, tokenizer: Any, config: TrainConfig
) -> None:
    """The token ids are llama.cpp's, and as many as the server counted."""
    capture = _load(path)
    ids = prompt_ids(
        tokenizer, capture["prompt_text"], config.chat_template_date
    )
    assert ids == capture["engine_token_ids"]
    assert len(ids) == capture["engine_prompt_tokens"]
    assert ids.count(tokenizer.bos_token_id) == 1
    assert ids[0] == tokenizer.bos_token_id


def test_date_is_pinned_and_today_is_absent(
    tokenizer: Any, config: TrainConfig
) -> None:
    """The template shows the pinned date, never the day it runs on."""
    rendered = render_prompt(tokenizer, "hi", config.chat_template_date)
    assert "Today Date: 26 Jul 2024" in rendered
    today = datetime.datetime.now(tz=datetime.UTC).strftime("%d %b %Y")
    assert today not in rendered


def test_another_date_breaks_parity(tokenizer: Any) -> None:
    """Rendering with another date no longer matches the engine."""
    capture = _load(FIXTURES[0])
    rendered = render_prompt(tokenizer, capture["prompt_text"], "27 Sep 2026")
    assert rendered != BEGIN_OF_TEXT + capture["engine_render"]
