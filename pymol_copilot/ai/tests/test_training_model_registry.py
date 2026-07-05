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

"""Unit tests for the training model registry helpers."""

from __future__ import annotations

import typing

import pytest


@pytest.mark.unit
def test_resolve_model_key_accepts_short_name(
    training_config_module: typing.Any,
) -> None:
    """Registry keys should resolve to themselves."""
    assert (
        training_config_module.resolve_model_key("qwen3-0.6b") == "qwen3-0.6b"
    )


@pytest.mark.unit
def test_resolve_hf_model_id_accepts_hf_name(
    training_config_module: typing.Any,
) -> None:
    """Full HuggingFace ids should resolve to canonical ids."""
    assert (
        training_config_module.resolve_hf_model_id("Qwen/Qwen3-0.6B")
        == "Qwen/Qwen3-0.6B"
    )


@pytest.mark.unit
def test_resolve_model_key_rejects_unknown_model(
    training_config_module: typing.Any,
) -> None:
    """Unknown model identifiers should raise ValueError."""
    with pytest.raises(ValueError):
        training_config_module.resolve_model_key("unknown-model")


@pytest.mark.unit
def test_resolve_training_model_defaults_to_qwen25(
    training_config_module: typing.Any,
) -> None:
    """Missing CLI and checkpoint metadata should use the default model."""
    assert (
        training_config_module.resolve_training_model(None)
        == "Qwen/Qwen2.5-1.5B-Instruct"
    )


@pytest.mark.unit
def test_require_transformers_exits_for_old_qwen3_version(
    training_config_module: typing.Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Qwen3 should fail fast when transformers is too old."""
    monkeypatch.setattr(
        training_config_module,
        "transformers_version_tuple",
        lambda: (4, 46, 3),
    )
    with pytest.raises(SystemExit):
        training_config_module.require_transformers_for_model("qwen3-0.6b")


@pytest.mark.unit
def test_require_transformers_allows_qwen3_on_new_version(
    training_config_module: typing.Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Qwen3 should pass the version gate on supported transformers."""
    monkeypatch.setattr(
        training_config_module,
        "transformers_version_tuple",
        lambda: (4, 51, 3),
    )
    training_config_module.require_transformers_for_model("qwen3-0.6b")
