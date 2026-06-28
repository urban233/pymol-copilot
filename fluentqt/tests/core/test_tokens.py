"""Tests for design tokens and TokenConsumer mixin."""

from __future__ import annotations

from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.tokens as tokens


def test_token_consumer_apply_tokens(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify that _apply_tokens is called during init and palette change.

    Args:
        q_app: Session-scoped QApplication instance.
    """

    class MockConsumer(tokens.TokenConsumer, QtWidgets.QWidget):
        """Mock class that implements TokenConsumer and inherits from QWidget."""

        def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
            """Initialize the mock widget.

            Args:
                parent: Optional parent widget.
            """
            self.apply_count: int = 0
            super().__init__(parent)

        @override
        def _apply_tokens(self) -> None:
            """Increment the application counter on theme update."""
            self.apply_count += 1

    # Arrange & Act
    tmp_widget = MockConsumer()

    # Assert
    assert tmp_widget.apply_count == 1

    # Act: Simulate ApplicationPaletteChange
    tmp_event = QtCore.QEvent(QtCore.QEvent.Type.ApplicationPaletteChange)
    QtWidgets.QApplication.sendEvent(q_app, tmp_event)

    # Assert
    assert tmp_widget.apply_count == 2


def test_register_accent() -> None:
    """Verify register_accent updates accent tokens and fires callbacks."""
    # Arrange
    tmp_original_light_tokens = tokens._LIGHT_TOKENS
    tmp_original_dark_tokens = tokens._DARK_TOKENS
    tmp_new_color = QtGui.QColor(255, 0, 0)  # Red

    tmp_callback_called = False

    def tmp_callback() -> None:
        """Set callback called flag."""
        nonlocal tmp_callback_called
        tmp_callback_called = True

    tokens.on_mode_changed(tmp_callback)

    try:
        # Act
        tokens.register_accent(tmp_new_color)

        # Assert
        assert tokens._LIGHT_TOKENS.accent_default == tmp_new_color
        assert tokens._DARK_TOKENS.accent_default == tmp_new_color
        assert tmp_callback_called is True
    finally:
        # Restore the original tokens to maintain test isolation
        tokens._LIGHT_TOKENS = tmp_original_light_tokens
        tokens._DARK_TOKENS = tmp_original_dark_tokens
        # Clear the callback to avoid side effects in other tests
        if tmp_callback in tokens._callbacks:
            tokens._callbacks.remove(tmp_callback)
