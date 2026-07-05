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

"""Unit tests for injectable PyMOL cmd session context."""

from __future__ import annotations

import pytest

import pymol_copilot.ai.execution.session_context as session_context_module


class _FakeCmd:
    """Minimal stand-in for a PyMOL cmd handle."""


@pytest.mark.unit
def test_get_active_cmd_defaults_to_none() -> None:
    """Without a bound context, get_active_cmd returns None."""
    assert session_context_module.get_active_cmd() is None


@pytest.mark.unit
def test_use_cmd_sets_and_resets_context() -> None:
    """use_cmd should bind and restore the active cmd handle."""
    fake = _FakeCmd()
    assert session_context_module.get_active_cmd() is None
    with session_context_module.use_cmd(fake):
        assert session_context_module.get_active_cmd() is fake
    assert session_context_module.get_active_cmd() is None


@pytest.mark.unit
def test_use_cmd_nested_contexts() -> None:
    """Nested use_cmd blocks should restore the outer handle."""
    outer = _FakeCmd()
    inner = _FakeCmd()
    with session_context_module.use_cmd(outer):
        with session_context_module.use_cmd(inner):
            assert session_context_module.get_active_cmd() is inner
        assert session_context_module.get_active_cmd() is outer
