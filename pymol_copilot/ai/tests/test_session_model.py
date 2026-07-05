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

"""Unit tests for session domain models."""

from __future__ import annotations

import pytest

import pymol_copilot.ai.app.models.session as session_module


@pytest.mark.unit
def test_default_pse_filename_from_prompt() -> None:
    """Default .pse names should derive from the first prompt line."""
    name = session_module.Session.default_pse_filename(
        "Please load the 1DPX protein and color it red.",
    )
    assert name.endswith(".pse")
    assert "1DPX" in name


@pytest.mark.unit
def test_default_pse_filename_empty_prompt() -> None:
    """Empty prompts should fall back to a generic filename."""
    assert (
        session_module.Session.default_pse_filename("   ")
        == "pymol_copilot_session.pse"
    )


@pytest.mark.unit
def test_default_pse_filename_strips_special_chars() -> None:
    """Special characters should be replaced for filesystem safety."""
    name = session_module.Session.default_pse_filename(
        "Load 1DPX!!! @#$ now",
    )
    assert name.endswith(".pse")
    assert "!" not in name
    assert "@" not in name
    assert "#" not in name
