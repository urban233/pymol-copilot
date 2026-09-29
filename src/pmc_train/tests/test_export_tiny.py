# Copyright 2026 PyMOL Copilot contributors.
"""The export pipeline turns a model into a checked Q4_K_M GGUF.

Drives `pmc_train.export.export` end to end with the pinned llama.cpp,
on a tiny randomly initialized Llama over the real tokenizer: merge,
save, convert, quantize, check. It needs the llama.cpp build from
`src/pmc_train/build_llama_cpp.sh`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path
from typing import Any

import pytest
import torch
from transformers import LlamaConfig
from transformers import LlamaForCausalLM

from pmc_train.config import DEFAULT_CONFIG
from pmc_train.config import TrainConfig
from pmc_train.export import export
from pmc_train.gguf_check import compare
from pmc_train.gguf_check import metadata
from pmc_train.train import base_weights_path

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.slow
def test_tiny_model_exports_to_a_checked_q4_k_m(
    tmp_path: Path, tokenizer: Any, config: TrainConfig
) -> None:
    """Merge-free export of a tiny model yields a self-consistent Q4_K_M."""

    def tiny() -> LlamaForCausalLM:
        torch.manual_seed(0)
        return LlamaForCausalLM(
            LlamaConfig(
                vocab_size=len(tokenizer),
                hidden_size=256,
                intermediate_size=512,
                num_hidden_layers=1,
                num_attention_heads=4,
                num_key_value_heads=2,
                max_position_embeddings=131072,
                rope_scaling={
                    "rope_type": "llama3",
                    "factor": 32.0,
                    "low_freq_factor": 1.0,
                    "high_freq_factor": 4.0,
                    "original_max_position_embeddings": 8192,
                },
                rope_theta=500000.0,
                tie_word_embeddings=True,
                bos_token_id=tokenizer.bos_token_id,
                eos_token_id=[128001, 128008, 128009],
            )
        ).to(torch.bfloat16)

    first = _write_reference(tmp_path, tiny, config)
    record = export(
        ROOT / DEFAULT_CONFIG,
        ROOT,
        tmp_path / "export",
        adapter=None,
        name="tiny",
        reference=first,
        weights=base_weights_path(config),
        load_base=tiny,
    )
    assert record["file_type"] == "MOSTLY_Q4_K_M"
    assert record["check"]["ok"]
    written = json.loads(
        (tmp_path / "export" / "export.json").read_text(encoding="utf-8")
    )
    assert written["gguf_sha256"] == record["gguf_sha256"]
    gguf = tmp_path / "export" / record["gguf"]
    values, _ = metadata(gguf)
    assert "26 Jul 2024" in values["tokenizer.chat_template"]
    assert not any(key.startswith("general.sampling.") for key in values)
    assert compare(gguf, first).ok


def _write_reference(tmp_path: Path, tiny: Any, config: TrainConfig) -> Path:
    """Export the tiny model once, as the reference to check against.

    Args:
        tmp_path: A scratch directory.
        tiny: Builds the tiny model.
        config: The committed training config.

    Returns:
        The reference GGUF.
    """
    from pmc_train.export import convert_and_quantize
    from pmc_train.export import llama_cpp_dir
    from pmc_train.export import save_merged

    merged = tmp_path / "reference-hf"
    save_merged(base_weights_path(config), None, merged, tiny)
    return convert_and_quantize(
        llama_cpp_dir(ROOT, config),
        merged,
        tmp_path / "reference-Q4_K_M.gguf",
        config.export.quantization,
    )
