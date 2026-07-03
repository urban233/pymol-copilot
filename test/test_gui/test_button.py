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
# Martin Urban
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================
#
"""Unit tests for button widgets."""

from __future__ import annotations

from PyQt6 import QtGui
from PyQt6 import QtWidgets
import pytest

from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt.widgets import button as button_module


@pytest.fixture
def q_app() -> QtWidgets.QApplication:
    """Fixture for providing a QApplication instance.

    Returns:
        The QApplication instance.
    """
    tmp_app = QtWidgets.QApplication.instance()
    if isinstance(tmp_app, QtWidgets.QApplication):
        return tmp_app
    return QtWidgets.QApplication([])


def test_circle_icon_button_properties(q_app: QtWidgets.QApplication) -> None:
    """Verify that CircleIconButton properties are set correctly.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_pixmap = QtGui.QPixmap(16, 16)
    tmp_icon = QtGui.QIcon(tmp_pixmap)

    # Act
    tmp_button = button_module.CircleIconButton(tmp_icon, size_dp=40)

    # Assert
    assert tmp_button.text() == ""
    assert not tmp_button.icon().isNull()
    assert tmp_button._size_dp == 40


def test_circle_icon_button_styles_and_dimensions(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify CircleIconButton styling and dynamic dimension setup.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_pixmap = QtGui.QPixmap(16, 16)
    tmp_icon = QtGui.QIcon(tmp_pixmap)

    # Act
    tmp_button = button_module.CircleIconButton(tmp_icon, size_dp=32)
    tmp_qss = tmp_button.styleSheet()

    # Assert
    assert "QPushButton {" in tmp_qss
    assert "border-radius:" in tmp_qss
    assert "min-width:" in tmp_qss


def test_circle_icon_button_scale_changed(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify CircleIconButton responds correctly to DPI scale changes.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_pixmap = QtGui.QPixmap(16, 16)
    tmp_icon = QtGui.QIcon(tmp_pixmap)
    tmp_button = button_module.CircleIconButton(tmp_icon, size_dp=32)

    # Act & Assert
    # We trigger the scale_changed signal; it must execute without exceptions.
    theme.get_notifier().scale_changed.emit(2.0)
    assert tmp_button.styleSheet() != ""
