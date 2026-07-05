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
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================

"""Runtime configuration for the cBioMOL AI assistant inference backend."""

from __future__ import annotations

import dataclasses
import os
import pathlib
import typing


PromptFamily = typing.Literal["qwen2", "qwen3"]


_DEFAULT_MODEL_REL = "src/python/pymol_copilot/ai/training/models/pymol_copilot-pymol-assistant-Q4_K_M.gguf"


def _default_thread_count() -> int:
    """Return a safe default llama.cpp thread count.

    Returns:
      Logical CPU count minus two, floored at one.
    """
    inference_threads, _ = compute_thread_budget()
    return inference_threads


def compute_thread_budget(
    reserved_for_viewport: int = 2,
) -> tuple[int, int]:
    """Return inference and reserved viewport thread counts.

    Args:
      reserved_for_viewport: Cores to reserve for viewport rendering.

    Returns:
      Tuple of ``(inference_threads, reserved_viewport_threads)``.
    """
    count = os.cpu_count() or 4
    reserved = min(max(reserved_for_viewport, 0), max(count - 1, 0))
    inference = max(1, count - reserved)
    return inference, reserved


def detect_prompt_family(model_path: pathlib.Path) -> PromptFamily:
    """Infer the ChatML prompt family from a GGUF filename.

    Args:
      model_path: Path to the quantized GGUF model file.

    Returns:
      ``'qwen3'`` when the filename contains ``qwen3``; otherwise ``'qwen2'``.
    """
    if "qwen3" in model_path.name.lower():
        return "qwen3"
    return "qwen2"


def resolve_model_path(
    cli_path: pathlib.Path | None,
) -> pathlib.Path:
    """Resolve the GGUF model path from CLI, env, or project default.

    Args:
      cli_path: Optional path supplied on the command line.

    Returns:
      Resolved path to the GGUF model file.

    Raises:
      FileNotFoundError: If no path resolves to an existing file and mock
        mode is not enabled by the caller.
    """
    if cli_path is not None:
        return cli_path.expanduser().resolve()

    env_raw = os.environ.get("CBIOMOL_AI_MODEL_PATH")
    if env_raw:
        return pathlib.Path(env_raw).expanduser().resolve()

    repo_root = pathlib.Path(__file__).resolve().parents[5]
    return (repo_root / _DEFAULT_MODEL_REL).resolve()


@dataclasses.dataclass(frozen=True)
class InferenceConfig:
    """Immutable inference settings for llama.cpp or mock backends."""

    model_path: pathlib.Path
    n_ctx: int = 2048
    n_threads: int = dataclasses.field(default_factory=_default_thread_count)
    n_gpu_layers: int = 0
    max_tokens: int = 512
    temperature: float = 0.1
    use_grammar: bool = True
    mock: bool = False
    dry_run: bool = False
    viewport_cores: int = 2
    prompt_family: PromptFamily = "qwen2"
