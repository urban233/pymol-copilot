"""Tests for the divider primitive."""

from __future__ import annotations

from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.primitives.divider as divider_module


def test_token_divider_default_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify default properties of TokenDivider.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_divider = divider_module.TokenDivider()

    # Assert
    assert tmp_divider.frameShape() == QtWidgets.QFrame.Shape.HLine
    assert tmp_divider.frameShadow() == QtWidgets.QFrame.Shadow.Plain


def test_token_divider_dpi_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify line width scales correctly with DPI.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_divider = divider_module.TokenDivider()

    tmp_apply_called = False

    def tmp_apply_tokens_spy() -> None:
        nonlocal tmp_apply_called
        tmp_apply_called = True

    tmp_divider._apply_tokens = tmp_apply_tokens_spy

    # Act
    dp_module.notifier.scale_changed.emit(2.0)

    # Assert
    assert tmp_apply_called is True

    # Clean up / reset scale notifier
    dp_module.notifier.scale_changed.emit(1.0)


def test_token_divider_thickness_calculation(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify that divider thickness is at least 1 pixel.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_divider = divider_module.TokenDivider()

    # Act & Assert
    assert tmp_divider._geometry.thickness_px >= 1
