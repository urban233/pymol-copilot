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

"""Unit tests for training chat template adapter selection."""

from __future__ import annotations

import typing

import pytest


@pytest.mark.unit
def test_for_model_selects_qwen3_adapter(
    chat_templates_module: typing.Any,
) -> None:
    """Qwen3 HuggingFace ids should map to the Qwen3 adapter."""
    adapter = chat_templates_module.ChatTemplateAdapter.for_model(
        "Qwen/Qwen3-0.6B",
    )
    assert isinstance(
        adapter,
        chat_templates_module.Qwen3ChatTemplateAdapter,
    )


@pytest.mark.unit
def test_for_model_selects_qwen2_adapter(
    chat_templates_module: typing.Any,
) -> None:
    """Qwen2.5 HuggingFace ids should map to the Qwen2 adapter."""
    adapter = chat_templates_module.ChatTemplateAdapter.for_model(
        "Qwen/Qwen2.5-1.5B-Instruct",
    )
    assert isinstance(
        adapter,
        chat_templates_module.Qwen2ChatTemplateAdapter,
    )
