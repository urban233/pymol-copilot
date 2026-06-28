"""Tests for the main window of the PyMOL Copilot application."""
from __future__ import annotations

from PyQt6 import QtWidgets
import pytest

from pymol_copilot.gui import main_window


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


def test_main_window_instantiation(q_app: QtWidgets.QApplication) -> None:
    """Tests that the MainWindow can be instantiated correctly.

    Args:
        q_app: The QApplication fixture.
    """
    # Arrange & Act
    assert q_app is not None
    tmp_window = main_window.MainWindow()

    # Assert
    assert tmp_window.windowTitle() == "PyMOL Copilot"
    assert tmp_window.centralWidget() is not None
