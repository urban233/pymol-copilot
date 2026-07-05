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

"""Integration tests for headless PyMOL session lifecycle."""

from __future__ import annotations

import pytest

import pymol_copilot.ai.execution.pymol_session as pymol_session_module


@pytest.mark.integration
def test_headless_session_start_and_shutdown() -> None:
    """HeadlessPyMOLSession should start and stop cleanly."""
    pytest.importorskip("pymol2")
    session = pymol_session_module.HeadlessPyMOLSession()
    assert not session.is_ready()
    session.start()
    assert session.is_ready()
    assert session.get_cmd() is not None
    session.shutdown()
    assert not session.is_ready()
