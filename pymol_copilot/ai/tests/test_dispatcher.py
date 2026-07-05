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

"""Unit tests for plan-step dispatch to the PyMOL wrapper."""

from __future__ import annotations

import unittest.mock

import pytest

import pymol_copilot.ai.execution.dispatcher as dispatcher_module
import pymol_copilot.ai.pymol_wrapper as pymol_wrapper_module
import pymol_copilot.ai.schemas.tool_schemas as tool_schemas_module


@pytest.mark.unit
def test_dispatcher_registry_matches_schemas() -> None:
    """Dispatcher should cover every schema tool name."""
    dispatcher_module.assert_registry_matches_schemas()


@pytest.mark.unit
def test_dispatch_unknown_tool_raises() -> None:
    """Unknown tool names should raise DispatcherError."""
    with pytest.raises(dispatcher_module.DispatcherError):
        dispatcher_module.dispatch_step("not_a_tool", {})


@pytest.mark.unit
def test_dispatch_load_structure_calls_wrapper() -> None:
    """load_structure dispatch should forward kwargs to the wrapper."""
    with unittest.mock.patch.object(
        pymol_wrapper_module,
        "load_structure",
        return_value="7BZ5",
    ) as mocked:
        result = dispatcher_module.dispatch_step(
            "load_structure",
            {"pdb_id": "7BZ5"},
        )
    mocked.assert_called_once_with("7BZ5", None)
    assert result == "7BZ5"


@pytest.mark.unit
def test_dispatch_save_session_calls_wrapper() -> None:
    """save_session dispatch should forward the file path to the wrapper."""
    with unittest.mock.patch.object(
        pymol_wrapper_module,
        "save_session",
        return_value=None,
    ) as mocked:
        dispatcher_module.dispatch_step(
            "save_session",
            {"file_path": "analysis.pse"},
        )
    mocked.assert_called_once_with("analysis.pse")


@pytest.mark.unit
def test_dispatch_wrapper_error_propagates() -> None:
    """WrapperError from the wrapper should propagate unchanged."""
    with (
        unittest.mock.patch.object(
            pymol_wrapper_module,
            "remove_object",
            side_effect=pymol_wrapper_module.WrapperError("bad object"),
        ),
        pytest.raises(
            pymol_wrapper_module.WrapperError,
            match="bad object",
        ),
    ):
        dispatcher_module.dispatch_step(
            "remove_object",
            {"object_name": ""},
        )


@pytest.mark.unit
def test_known_tool_names_count() -> None:
    """Registry should contain exactly 21 tools."""
    assert len(dispatcher_module.known_tool_names()) == len(
        tool_schemas_module.TOOL_SCHEMAS,
    )
