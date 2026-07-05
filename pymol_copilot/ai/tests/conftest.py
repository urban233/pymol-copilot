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

"""Pytest configuration for pymol_copilot.ai unit tests."""

from __future__ import annotations

import pathlib
import sys
import typing

import pytest


@pytest.fixture
def training_config_module() -> typing.Iterator[typing.Any]:
    """Import ``config.training_config`` from the training package root.

    Yields:
      The loaded ``training_config`` module.
    """
    training_dir = pathlib.Path(__file__).resolve().parents[1] / "training"
    sys.path.insert(0, str(training_dir))
    import config.training_config as training_config

    yield training_config
    sys.path.remove(str(training_dir))


@pytest.fixture
def chat_templates_module() -> typing.Iterator[typing.Any]:
    """Import ``config.chat_templates`` from the training package root.

    Yields:
      The loaded ``chat_templates`` module.
    """
    training_dir = pathlib.Path(__file__).resolve().parents[1] / "training"
    sys.path.insert(0, str(training_dir))
    import config.chat_templates as chat_templates

    yield chat_templates
    sys.path.remove(str(training_dir))


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for the AI test suite.

    Args:
      config: Pytest configuration object.
    """
    config.addinivalue_line(
        "markers", "unit: isolated pymol_copilot.ai unit tests"
    )
    config.addinivalue_line(
        "markers",
        "integration: tests requiring live PyMOL or heavy deps",
    )
