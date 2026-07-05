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

"""Unit tests for the mock inference backend."""

from __future__ import annotations

import pathlib
import threading

import pytest

import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.backend.mock_engine as mock_engine_module


@pytest.mark.unit
def test_mock_engine_positive_prompt_streams_tool_calls() -> None:
    """Load/color prompts should emit tool-call blocks."""
    engine = mock_engine_module.MockEngine()
    config = config_module.InferenceConfig(
        model_path=pathlib.Path("unused.gguf"),
        mock=True,
    )
    engine.load(config)
    tokens: list[str] = []

    output = engine.stream_completion(
        "<|im_start|>user\nLoad hemoglobin and color it.\n",
        threading.Event(),
        tokens.append,
    )
    assert "<tool_call>" in output
    assert tokens


@pytest.mark.unit
def test_mock_engine_refusal_for_viewport_prompt() -> None:
    """Viewport prompts should return prose without tool calls."""
    engine = mock_engine_module.MockEngine()
    config = config_module.InferenceConfig(
        model_path=pathlib.Path("unused.gguf"),
        mock=True,
    )
    engine.load(config)
    output = engine.stream_completion(
        "<|im_start|>user\nRotate the molecule 90 degrees.\n",
        threading.Event(),
        lambda _delta: None,
    )
    assert "<tool_call>" not in output
