"""Tests for stylesheet generation."""

from __future__ import annotations

from PyQt6 import QtGui

from fluentqt.core import stylesheet
from fluentqt.enums import roles


def test_build_frame_style_no_border() -> None:
    """Verify build_frame_style output when no border is present."""
    # Arrange
    tmp_bg = QtGui.QColor("#ffffff")
    tmp_radius = 8
    tmp_border = None
    tmp_border_width = 0

    # Act
    tmp_result = stylesheet.build_frame_style(
        tmp_bg, tmp_radius, tmp_border, tmp_border_width
    )

    # Assert
    assert "background-color: #ffffff;" in tmp_result
    assert "border-radius: 8px;" in tmp_result
    assert "border: none;" in tmp_result


def test_build_frame_style_with_border() -> None:
    """Verify build_frame_style output when a border is present."""
    # Arrange
    tmp_bg = QtGui.QColor("#ffffff")
    tmp_radius = 8
    tmp_border = QtGui.QColor("#e5e5e5")
    tmp_border_width = 1

    # Act
    tmp_result = stylesheet.build_frame_style(
        tmp_bg, tmp_radius, tmp_border, tmp_border_width
    )

    # Assert
    assert "background-color: #ffffff;" in tmp_result
    assert "border-radius: 8px;" in tmp_result
    assert "border: 1px solid #e5e5e5;" in tmp_result


def test_build_frame_style_with_rgba() -> None:
    """Verify build_frame_style correctly formats RGBA colors."""
    # Arrange
    tmp_bg = QtGui.QColor(255, 255, 255, 128)
    tmp_radius = 4
    tmp_border = QtGui.QColor(0, 0, 0, 80)
    tmp_border_width = 2

    # Act
    tmp_result = stylesheet.build_frame_style(
        tmp_bg, tmp_radius, tmp_border, tmp_border_width
    )

    # Assert
    assert "background-color: rgba(255, 255, 255, 128);" in tmp_result
    assert "border-radius: 4px;" in tmp_result
    assert "border: 2px solid rgba(0, 0, 0, 80);" in tmp_result


def test_build_label_style() -> None:
    """Verify build_label_style output."""
    # Arrange
    tmp_color = QtGui.QColor("#333333")
    tmp_size = 14
    tmp_weight = 400
    tmp_family = "Segoe UI"

    # Act
    tmp_result = stylesheet.build_label_style(
        tmp_color, tmp_size, tmp_weight, tmp_family
    )

    # Assert
    assert "QLabel {" in tmp_result
    assert "color: #333333;" in tmp_result
    assert "font-size: 14px;" in tmp_result
    assert "font-weight: 400;" in tmp_result
    assert 'font-family: "Segoe UI";' in tmp_result


def test_build_button_style() -> None:
    """Verify build_button_style generates all pseudo-selectors."""
    # Arrange
    tmp_states = {
        roles.ControlState.Default: (
            QtGui.QColor("#ffffff"),
            QtGui.QColor("#e5e5e5"),
            QtGui.QColor("#000000"),
        ),
        roles.ControlState.Hovered: (
            QtGui.QColor("#f9f9f9"),
            QtGui.QColor("#d2d2d2"),
            QtGui.QColor("#000000"),
        ),
    }
    tmp_radius = 4

    # Act
    tmp_result = stylesheet.build_button_style(tmp_states, tmp_radius)

    # Assert
    assert "QPushButton {" in tmp_result
    assert "background-color: #ffffff;" in tmp_result
    assert "border: 1px solid #e5e5e5;" in tmp_result
    assert "color: #000000;" in tmp_result
    assert "border-radius: 4px;" in tmp_result

    assert "QPushButton:hover {" in tmp_result
    assert "background-color: #f9f9f9;" in tmp_result
    assert "border: 1px solid #d2d2d2;" in tmp_result
    assert "color: #000000;" in tmp_result


def test_build_input_style() -> None:
    """Verify build_input_style output with optional focus border."""
    # Arrange
    tmp_bg = QtGui.QColor("#ffffff")
    tmp_border = QtGui.QColor("#e5e5e5")
    tmp_radius = 4
    tmp_text = QtGui.QColor("#000000")
    tmp_placeholder = QtGui.QColor("#808080")
    tmp_focus_border = QtGui.QColor("#0078d4")

    # Act
    tmp_result = stylesheet.build_input_style(
        tmp_bg,
        tmp_border,
        tmp_radius,
        tmp_text,
        tmp_placeholder,
        tmp_focus_border,
    )

    # Assert
    assert "QFrame {" in tmp_result
    assert "background-color: #ffffff;" in tmp_result
    assert "border: 1px solid #e5e5e5;" in tmp_result
    assert "border-radius: 4px;" in tmp_result

    assert 'QFrame:focus, QFrame[state="focused"] {' in tmp_result
    assert "border: 2px solid #0078d4;" in tmp_result

    assert "QLineEdit {" in tmp_result
    assert "background-color: transparent;" in tmp_result
    assert "border: none;" in tmp_result
    assert "color: #000000;" in tmp_result
    assert "placeholder-text-color: #808080;" in tmp_result
