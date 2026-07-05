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
"""Hyperparameters and path constants for the cBioMOL AI training pipeline.

All tunable values are centralised here.  Scripts import this module and
reference constants by name.  No magic numbers should appear anywhere else.

Hardware target
---------------
NVIDIA RTX 4060 8 GB VRAM (Ada Lovelace architecture).  All memory-related
defaults are calibrated for this hardware; see each section's comment for the
rationale.
"""

from __future__ import annotations

import json
import pathlib
import typing

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

# Verified target modules for Qwen2ForCausalLM and Qwen3ForCausalLM.
_DEFAULT_LORA_TARGET_MODULES: list[str] = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]

# Short CLI keys map to HuggingFace ids and per-model LoRA settings.
SUPPORTED_BASE_MODELS: dict[str, dict[str, typing.Any]] = {
    "qwen2.5-1.5b": {
        "hf_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "lora_target_modules": _DEFAULT_LORA_TARGET_MODULES,
    },
    "qwen3-0.6b": {
        "hf_id": "Qwen/Qwen3-0.6B",
        "lora_target_modules": _DEFAULT_LORA_TARGET_MODULES,
    },
}

DEFAULT_MODEL_KEY: str = "qwen2.5-1.5b"

# Qwen3 support landed in transformers 4.51.0; older versions raise
# ``KeyError: 'qwen3'`` when loading ``Qwen/Qwen3-0.6B``.
QWEN3_MODEL_KEY: str = "qwen3-0.6b"
QWEN3_MIN_TRANSFORMERS_VERSION: tuple[int, int, int] = (4, 51, 0)


def _parse_version_tuple(raw: str) -> tuple[int, int, int]:
    """Parse a semver string into ``(major, minor, patch)``.

    Args:
      raw: Version string such as ``'4.51.3'`` or ``'4.51.3+cu121'``.

    Returns:
      Three integer components for major, minor, and patch.
    """
    base = raw.split("+", maxsplit=1)[0]
    base = base.split("-", maxsplit=1)[0]
    parts = base.split(".")
    nums: list[int] = []
    for idx in range(3):
        if idx < len(parts):
            nums.append(int(parts[idx]))
        else:
            nums.append(0)
    return nums[0], nums[1], nums[2]


def transformers_version_tuple() -> tuple[int, int, int]:
    """Return the installed ``transformers`` version as a tuple.

    Returns:
      ``(major, minor, patch)`` parsed from ``transformers.__version__``.
    """
    import transformers

    return _parse_version_tuple(transformers.__version__)


def require_transformers_for_model(key_or_hf_id: str) -> None:
    """Ensure ``transformers`` is new enough for the selected base model.

    Args:
      key_or_hf_id: Registry key or HuggingFace model identifier.

    Raises:
      SystemExit: When Qwen3 is requested but ``transformers`` is too old.
      ValueError: If the input does not match any supported model.
    """
    import sys

    key = resolve_model_key(key_or_hf_id)
    if key != QWEN3_MODEL_KEY:
        return
    installed = transformers_version_tuple()
    if installed >= QWEN3_MIN_TRANSFORMERS_VERSION:
        return
    installed_str = ".".join(str(part) for part in installed)
    required_str = ".".join(
        str(part) for part in QWEN3_MIN_TRANSFORMERS_VERSION
    )
    print(
        f"[ERROR] {key} requires transformers>={required_str}, "
        f"but {installed_str} is installed.\n"
        "Upgrade from the training directory:\n"
        "  pip install -r requirements.txt\n"
        "Or install transformers only:\n"
        f"  pip install 'transformers>={required_str}'",
        file=sys.stderr,
    )
    sys.exit(1)


def resolve_model_key(key_or_hf_id: str) -> str:
    """Return the registry key for a short name or HuggingFace model id.

    Args:
      key_or_hf_id: Registry key (e.g. ``'qwen3-0.6b'``) or full HF id.

    Returns:
      The matching registry key string.

    Raises:
      ValueError: If the input does not match any supported model.
    """
    if key_or_hf_id in SUPPORTED_BASE_MODELS:
        return key_or_hf_id
    lower = key_or_hf_id.lower()
    for key, spec in SUPPORTED_BASE_MODELS.items():
        hf_id = typing.cast(str, spec["hf_id"])
        if hf_id.lower() == lower:
            return key
    supported = ", ".join(sorted(SUPPORTED_BASE_MODELS))
    raise ValueError(
        f"Unknown model {key_or_hf_id!r}. Supported keys: {supported}"
    )


def resolve_hf_model_id(key_or_hf_id: str) -> str:
    """Return the HuggingFace model id for a registry key or HF id.

    Args:
      key_or_hf_id: Registry key or full HuggingFace model identifier.

    Returns:
      Canonical HuggingFace model id string.

    Raises:
      ValueError: If the input does not match any supported model.
    """
    key = resolve_model_key(key_or_hf_id)
    return typing.cast(str, SUPPORTED_BASE_MODELS[key]["hf_id"])


def resolve_lora_target_modules(key_or_hf_id: str) -> list[str]:
    """Return LoRA target module names for a registry key or HF id.

    Args:
      key_or_hf_id: Registry key or full HuggingFace model identifier.

    Returns:
      List of projection layer names to attach LoRA adapters to.

    Raises:
      ValueError: If the input does not match any supported model.
    """
    key = resolve_model_key(key_or_hf_id)
    modules = SUPPORTED_BASE_MODELS[key]["lora_target_modules"]
    return list(typing.cast(list[str], modules))


def resolve_training_model(
    cli_model: str | None,
    checkpoint_dir: pathlib.Path | None = None,
) -> str:
    """Resolve the HuggingFace model id for training or export scripts.

    Prefers an explicit CLI value, then ``adapter_config.json`` inside a
    checkpoint directory, then the default registry entry.

    Args:
      cli_model: Optional registry key or HuggingFace model identifier.
      checkpoint_dir: Optional LoRA adapter directory for auto-detection.

    Returns:
      Canonical HuggingFace model id string.

    Raises:
      ValueError: If ``cli_model`` or checkpoint metadata is unsupported.
    """
    if cli_model:
        return resolve_hf_model_id(cli_model)
    if checkpoint_dir is not None:
        adapter_cfg = checkpoint_dir / "adapter_config.json"
        if adapter_cfg.exists():
            with open(adapter_cfg, encoding="utf-8") as fh:
                data = json.load(fh)
            base = data.get("base_model_name_or_path")
            if base:
                return resolve_hf_model_id(str(base))
    return resolve_hf_model_id(DEFAULT_MODEL_KEY)


# Qwen2.5-1.5B-Instruct is the clear choice for an 8 GB fine-tune target.
# In 4-bit NF4 the model weights occupy ~1.0 GB, leaving ample headroom for
# LoRA adapters, optimizer states, and activations.
BASE_MODEL_NAME: str = resolve_hf_model_id(DEFAULT_MODEL_KEY)

# ---------------------------------------------------------------------------
# BitsAndBytes (4-bit quantization)
# ---------------------------------------------------------------------------

LOAD_IN_4BIT: bool = True
# Nested (double) quantization saves ~0.3 GB with negligible quality loss.
BNB_4BIT_USE_DOUBLE_QUANT: bool = True
# NF4 is optimal for normally-distributed neural network weights.
BNB_4BIT_QUANT_TYPE: str = "nf4"
# RTX 4060 Ada has native bf16 hardware; avoids fp16 NaN instability.
BNB_4BIT_COMPUTE_DTYPE: str = "bfloat16"

# ---------------------------------------------------------------------------
# LoRA
# ---------------------------------------------------------------------------

# r=16 is the sweet spot for narrow, structured SFT tasks such as tool-call
# format learning.  r=8 underfits; r=64 wastes VRAM.
LORA_R: int = 16
# alpha = 2 * r is the standard initialisation.
LORA_ALPHA: int = 32
LORA_DROPOUT: float = 0.05
LORA_BIAS: str = "none"

LORA_TARGET_MODULES: list[str] = _DEFAULT_LORA_TARGET_MODULES

# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

# batch=1 is mandatory on 8 GB VRAM; effective batch = 1 * 16 = 16 via accum.
PER_DEVICE_TRAIN_BATCH_SIZE: int = 1
GRADIENT_ACCUMULATION_STEPS: int = 16
NUM_TRAIN_EPOCHS: int = 3
LEARNING_RATE: float = 2e-4
WARMUP_RATIO: float = 0.05
LR_SCHEDULER_TYPE: str = "cosine"
# bf16 on Ada, not fp16; see BNB_4BIT_COMPUTE_DTYPE rationale above.
BF16: bool = True
FP16: bool = False
# Gradient checkpointing halves activation VRAM at ~15% speed cost.
# Always the correct trade-off on 8 GB.
GRADIENT_CHECKPOINTING: bool = True
# 8-bit AdamW from bitsandbytes; ~0.3 GB vs ~0.8 GB for fp32 AdamW.
OPTIM: str = "adamw_bnb_8bit"
LOGGING_STEPS: int = 10
EVAL_STEPS: int = 100
SAVE_STEPS: int = 200
# Keep only best + 1 backup to conserve disk.
SAVE_TOTAL_LIMIT: int = 2
# 2048 tokens fits multi-step tool-call sequences with headroom.
MAX_SEQ_LENGTH: int = 2048
# 0 avoids multiprocessing issues on Windows and some Linux setups.
DATALOADER_NUM_WORKERS: int = 0

# ---------------------------------------------------------------------------
# Dataset generation
# ---------------------------------------------------------------------------

TRAIN_SPLIT_RATIO: float = 0.9
# Number of scenario seeds included in each prompt batch file.
BATCH_SIZE_PER_PROMPT_FILE: int = 50

# ---------------------------------------------------------------------------
# GGUF export
# ---------------------------------------------------------------------------

# Q4_K_M: 4-bit weights with 6-bit for attention/embedding layers.
# Best quality-to-size ratio for CPU inference.  ~1.0 GB output.
DEFAULT_QUANTIZATION: str = "Q4_K_M"
