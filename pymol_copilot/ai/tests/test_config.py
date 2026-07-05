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

"""Unit tests for CPU thread budget helpers."""

from __future__ import annotations

import pathlib

import pytest

import pymol_copilot.ai.backend.config as config_module


@pytest.mark.unit
def test_compute_thread_budget_reserves_viewport_cores() -> None:
    """Thread budget should reserve viewport cores from the CPU count."""
    inference, reserved = config_module.compute_thread_budget(2)
    assert reserved == 2
    assert inference >= 1


@pytest.mark.unit
def test_compute_thread_budget_never_reserves_all_cores() -> None:
    """At least one core should remain for inference."""
    inference, _reserved = config_module.compute_thread_budget(999)
    assert inference >= 1


@pytest.mark.unit
def test_detect_prompt_family_from_qwen3_filename() -> None:
    """Qwen3 GGUF filenames should select the qwen3 prompt family."""
    path = pathlib.Path(
        "models/pymol_copilot-pymol-assistant-qwen3-0.6b-Q4_K_M.gguf"
    )
    assert config_module.detect_prompt_family(path) == "qwen3"


@pytest.mark.unit
def test_detect_prompt_family_defaults_to_qwen2() -> None:
    """Legacy GGUF filenames should keep the qwen2 prompt family."""
    path = pathlib.Path("models/pymol_copilot-pymol-assistant-Q4_K_M.gguf")
    assert config_module.detect_prompt_family(path) == "qwen2"
