"""Tests for PyMOLColorGrid and ColorFlyout widgets."""

from __future__ import annotations

from PyQt6 import QtWidgets
import pytest

from pymol_copilot.gui.qt.widgets import color_grid


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


def test_color_grid_buttons(q_app: QtWidgets.QApplication) -> None:
    """Verify that PyMOLColorGrid initializes all color buttons.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange & Act
    tmp_grid = color_grid.PyMOLColorGrid()

    # Assert
    tmp_buttons = tmp_grid.get_all_color_buttons()
    assert len(tmp_buttons) == 32
    assert "red" in tmp_buttons
    assert "green" in tmp_buttons
    assert "blue" in tmp_buttons


def test_color_flyout_widget(q_app: QtWidgets.QApplication) -> None:
    """Verify that ColorFlyout has a color grid correctly added.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange & Act
    tmp_flyout = color_grid.ColorFlyout()

    # Assert
    assert tmp_flyout._color_grid is not None
    # Check that _color_grid is actually in the layouts/widget tree of FlyoutFrame
    assert tmp_flyout._color_grid.parent() is not None
