"""Tests for the icon primitive."""

from __future__ import annotations

from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.core.factory as factory_module
import fluentqt.enums.roles as roles_module
import fluentqt.primitives.icon as icon_module


def test_token_icon_default_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify default properties of TokenIcon.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_icon = icon_module.TokenIcon("test_icon")

    # Assert
    assert tmp_icon.icon() == "test_icon"
    assert tmp_icon.size_preset() == roles_module.IconSize.Medium


def test_token_icon_custom_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify custom properties are correctly applied.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_qicon = QtGui.QIcon()
    tmp_icon = icon_module.TokenIcon(
        icon=tmp_qicon,
        size=roles_module.IconSize.Large,
    )

    # Assert
    assert tmp_icon.icon() == tmp_qicon
    assert tmp_icon.size_preset() == roles_module.IconSize.Large


def test_token_icon_setters(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify properties can be dynamically updated via setters.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_icon = icon_module.TokenIcon("test_icon")

    # Act
    tmp_new_pixmap = QtGui.QPixmap()
    tmp_icon.set_icon(tmp_new_pixmap)
    tmp_icon.set_size_preset(roles_module.IconSize.Small)

    # Assert
    assert tmp_icon.icon() == tmp_new_pixmap
    assert tmp_icon.size_preset() == roles_module.IconSize.Small


def test_token_icon_fallback_no_provider(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify TokenIcon fallback when no provider is registered.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_old_provider = factory_module.get_icon_provider()
    factory_module._state.provider = None

    try:
        # Act
        tmp_icon = icon_module.TokenIcon("test_icon")

        # Assert
        assert tmp_icon.pixmap() is not None
        assert tmp_icon.pixmap().isNull() is True
    finally:
        # Clean up
        factory_module._state.provider = tmp_old_provider


def test_token_icon_with_provider(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify TokenIcon uses registered provider.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_called_name = None

    def tmp_mock_provider(name: str) -> QtGui.QIcon:
        nonlocal tmp_called_name
        tmp_called_name = name
        tmp_pix = QtGui.QPixmap(10, 10)
        tmp_pix.fill(QtGui.QColor("red"))
        return QtGui.QIcon(tmp_pix)

    tmp_old_provider = factory_module.get_icon_provider()
    factory_module.register_icon_provider(tmp_mock_provider)

    try:
        # Act
        tmp_icon = icon_module.TokenIcon("home_icon")

        # Assert
        assert tmp_called_name == "home_icon"
        assert tmp_icon.pixmap() is not None
        assert tmp_icon.pixmap().isNull() is False
    finally:
        # Clean up
        factory_module._state.provider = tmp_old_provider


def test_token_icon_dpi_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify style and icon scale are re-applied on screen scale changes.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_icon = icon_module.TokenIcon("test_icon")

    tmp_apply_called = False

    def tmp_apply_tokens_spy() -> None:
        nonlocal tmp_apply_called
        tmp_apply_called = True

    tmp_icon._apply_tokens = tmp_apply_tokens_spy

    # Act
    dp_module.notifier.scale_changed.emit(2.0)

    # Assert
    assert tmp_apply_called is True

    # Clean up / reset scale notifier
    dp_module.notifier.scale_changed.emit(1.0)
