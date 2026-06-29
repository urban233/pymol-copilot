"""Tests for the InputBar composite widget."""

from __future__ import annotations

import unittest.mock

from PyQt6 import QtGui
from PyQt6 import QtWidgets

from fluentqt.composites import input_bar as input_bar_module
from fluentqt.core import dp as dp_module
from fluentqt.enums import roles as roles_module


def test_input_bar_initialization(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify default properties and layout structure of InputBar.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    tmp_input_bar = input_bar_module.InputBar()

    assert tmp_input_bar.elevation() == roles_module.ElevationPreset.Card
    assert tmp_input_bar.orientation() == "horizontal"
    assert tmp_input_bar.border_radius() == 18
    assert tmp_input_bar.frame is not None
    assert tmp_input_bar.content_layout is not None
    assert isinstance(tmp_input_bar.content_layout, QtWidgets.QHBoxLayout)

    # Verify children are instantiated and are in layout
    assert tmp_input_bar.plus_button is not None
    assert tmp_input_bar.input_field is not None
    assert tmp_input_bar.model_dropdown is not None
    assert tmp_input_bar.mic_button is not None

    assert tmp_input_bar.content_layout.count() == 4
    assert tmp_input_bar.input_field.placeholderText() == "Ask Gemini"
    assert tmp_input_bar.model_dropdown.count() == 3


def test_input_bar_dpi_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify that InputBar frame and buttons scale correctly with DPI change.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    tmp_mock_screen = unittest.mock.create_autospec(QtGui.QScreen)
    tmp_mock_screen.logicalDotsPerInch.return_value = 96.0

    # Patch primaryScreen so the dp() function queries our mock
    with unittest.mock.patch.object(
        QtWidgets.QApplication, "primaryScreen", return_value=tmp_mock_screen
    ):
        tmp_input_bar = input_bar_module.InputBar()

        # Check default layout height at 1.0x scale (36 dp -> 36 px)
        assert tmp_input_bar.frame is not None
        assert tmp_input_bar.frame.minimumHeight() == 36
        assert tmp_input_bar.frame.maximumHeight() == 36

        # Simulate scaling change to 2.0x (192 DPI)
        tmp_mock_screen.logicalDotsPerInch.return_value = 192.0

        try:
            dp_module.notifier.scale_changed.emit(2.0)

            # Check height at 2.0x scale (36 dp -> 72 px)
            assert tmp_input_bar.frame.minimumHeight() == 72
            assert tmp_input_bar.frame.maximumHeight() == 72

            # Check button sizes at 2.0x scale (28 dp -> 56 px)
            assert tmp_input_bar.plus_button is not None
            assert tmp_input_bar.plus_button.width() == 56
            assert tmp_input_bar.plus_button.height() == 56
        finally:
            # Clean up: restore the scale factor to 1.0x (96 DPI)
            tmp_mock_screen.logicalDotsPerInch.return_value = 96.0
            dp_module.notifier.scale_changed.emit(1.0)
