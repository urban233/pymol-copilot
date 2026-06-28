"""Tests for the label primitive."""

from __future__ import annotations

from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.enums.roles as roles_module
import fluentqt.primitives.label as label_module


def test_token_label_default_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify default properties of TokenLabel.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_label = label_module.TokenLabel()

    # Assert
    assert tmp_label.text() == ""
    assert tmp_label.role() == roles_module.TextRole.Primary
    assert tmp_label.style() == roles_module.TypeStyle.Body


def test_token_label_custom_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify custom properties are correctly applied.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_label = label_module.TokenLabel(
        text="Hello World",
        role=roles_module.TextRole.Secondary,
        style=roles_module.TypeStyle.Subtitle,
    )

    # Assert
    assert tmp_label.text() == "Hello World"
    assert tmp_label.role() == roles_module.TextRole.Secondary
    assert tmp_label.style() == roles_module.TypeStyle.Subtitle


def test_token_label_setters(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify properties can be dynamically updated via setters.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_label = label_module.TokenLabel()

    # Act
    tmp_label.setText("New Text")
    tmp_label.set_role(roles_module.TextRole.OnAccent)
    tmp_label.set_style(roles_module.TypeStyle.Title)

    # Assert
    assert tmp_label.text() == "New Text"
    assert tmp_label.role() == roles_module.TextRole.OnAccent
    assert tmp_label.style() == roles_module.TypeStyle.Title


def test_token_label_dpi_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify style is re-applied on screen scale changes.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_label = label_module.TokenLabel()

    tmp_apply_called = False

    def tmp_apply_tokens_spy() -> None:
        nonlocal tmp_apply_called
        tmp_apply_called = True

    tmp_label._apply_tokens = tmp_apply_tokens_spy

    # Act
    dp_module.notifier.scale_changed.emit(2.0)

    # Assert
    assert tmp_apply_called is True

    # Clean up / reset scale notifier
    dp_module.notifier.scale_changed.emit(1.0)
