"""Tests for the frame primitive."""

from __future__ import annotations

from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.enums.roles as roles_module
import fluentqt.primitives.frame as frame_module


def test_token_frame_default_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify default properties of TokenFrame.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_frame = frame_module.TokenFrame()

    # Assert
    assert tmp_frame.elevation() == roles_module.ElevationPreset.Flat
    assert tmp_frame.fill_role() == roles_module.FillRole.Transparent
    assert tmp_frame.graphicsEffect() is not None
    assert isinstance(
        tmp_frame.graphicsEffect(), QtWidgets.QGraphicsDropShadowEffect
    )
    assert not tmp_frame.graphicsEffect().isEnabled()


def test_token_frame_custom_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify custom properties and shadow effect state for TokenFrame.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_frame = frame_module.TokenFrame(
        elevation=roles_module.ElevationPreset.Card,
        fill_role=roles_module.FillRole.Control,
    )

    # Assert
    assert tmp_frame.elevation() == roles_module.ElevationPreset.Card
    assert tmp_frame.fill_role() == roles_module.FillRole.Control
    assert tmp_frame.graphicsEffect().isEnabled()


def test_token_frame_property_setters(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify property setters update properties and trigger style application.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_frame = frame_module.TokenFrame()

    # Act
    tmp_frame.set_elevation(roles_module.ElevationPreset.Dialog)
    tmp_frame.set_fill_role(roles_module.FillRole.Accent)

    # Assert
    assert tmp_frame.elevation() == roles_module.ElevationPreset.Dialog
    assert tmp_frame.fill_role() == roles_module.FillRole.Accent
    assert tmp_frame.graphicsEffect().isEnabled()


def test_token_frame_dpi_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify geometry recalculates on device scale changes.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_frame = frame_module.TokenFrame(
        elevation=roles_module.ElevationPreset.Card
    )

    # Spy on _apply_tokens
    tmp_apply_called = False

    def tmp_apply_tokens_spy() -> None:
        nonlocal tmp_apply_called
        tmp_apply_called = True

    tmp_frame._apply_tokens = tmp_apply_tokens_spy

    # Act: emit scale_changed
    dp_module.notifier.scale_changed.emit(2.0)

    # Assert
    assert tmp_apply_called is True

    # Clean up / reset scale notifier to original state
    dp_module.notifier.scale_changed.emit(1.0)
