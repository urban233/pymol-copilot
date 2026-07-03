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
"""Styled buttons for the user interface."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import styles
from pymol_copilot.gui.qt import theme


class Button(QtWidgets.QPushButton):
    """Base class for styled push buttons.

    Delegates initialization and style configuration to abstract subclass methods.
    """

    def __init__(
        self,
        text: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the Button.

        Args:
            text: The text label for the button.
            parent: Optional parent widget.
        """
        super().__init__(text, parent)
        self._init_widget()
        self._set_styles()

    def _init_widget(self) -> None:
        """Initialize the widget.

        Raises:
            NotImplementedError: Always raised to enforce subclass override.
        """
        raise NotImplementedError

    def _set_styles(self) -> None:
        """Apply styles to the widget.

        Raises:
            NotImplementedError: Always raised to enforce subclass override.
        """
        raise NotImplementedError


class BasicButton(Button):
    """A standard, non-accented button with basic styling."""

    def _init_widget(self) -> None:
        """Initialize the widget."""

    def _set_styles(self) -> None:
        """Apply basic button styles."""
        self.setObjectName(theme.StyleId.BASIC_BUTTON)


class AccentButton(Button):
    """An accented button with the primary theme color highlight."""

    def _init_widget(self) -> None:
        """Initialize the widget."""

    def _set_styles(self) -> None:
        """Apply accented button styles."""
        self.setObjectName(theme.StyleId.ACCENT_BUTTON)


class CircleIconButton(Button):
    """A circular button widget that displays an icon instead of text.

    Attributes:
        _icon: The QIcon rendered inside the button.
        _size_dp: The diameter of the button in logical pixels.
    """

    def __init__(
        self,
        icon: QtGui.QIcon,
        size_dp: int = 24,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the CircleIconButton.

        Args:
            icon: The QIcon to display.
            size_dp: The diameter of the button in logical pixels. Defaults to 24.
            parent: Optional parent widget.
        """
        self._icon = icon
        self._size_dp = size_dp
        super().__init__("", parent)

    def _init_widget(self) -> None:
        """Initialize the widget properties, applying the icon."""
        self.setIcon(self._icon)
        styles.notifier.scale_changed.connect(self._handle_scale_changed)
        self.destroyed.connect(self._cleanup_connections)

    def _set_styles(self) -> None:
        """Set the QSS stylesheet for the circular button."""
        tmp_size_px = theme.SizeToken(self._size_dp).px
        tmp_radius_px = tmp_size_px // 2
        tmp_surface = theme.ThemeColors.SURFACE.to_hex()
        tmp_border = theme.ThemeColors.BORDER_COLOR.to_hex()
        tmp_hover = theme.ThemeColors.HOVER.to_hex()
        tmp_border_hover = theme.ThemeColors.BORDER_HOVER.to_hex()
        tmp_pressed = theme.ThemeColors.PRESSED.to_hex()
        tmp_border_active = theme.ThemeColors.BORDER_ACTIVE.to_hex()

        tmp_qss = f"""
            QPushButton {{
                background-color: {tmp_surface};
                border: 1px solid {tmp_border};
                border-radius: {tmp_radius_px}px;
                min-width: {tmp_size_px}px;
                max-width: {tmp_size_px}px;
                min-height: {tmp_size_px}px;
                max-height: {tmp_size_px}px;
            }}
            QPushButton:hover {{
                background-color: {tmp_hover};
                border: 1px solid {tmp_border_hover};
            }}
            QPushButton:pressed {{
                background-color: {tmp_pressed};
                border: 1px solid {tmp_border_active};
            }}
        """
        self.setStyleSheet(tmp_qss)

    def _handle_scale_changed(self, scale: float) -> None:
        """Handle screen DPI scaling updates to recalculate circle dimensions.

        Args:
            scale: The new screen scaling factor.
        """
        _ = scale
        self._set_styles()

    def _cleanup_connections(self, obj: QtCore.QObject | None = None) -> None:
        """Clean up scale changed signal connection to prevent memory leaks.

        Args:
            obj: The QObject being destroyed (optional).
        """
        _ = obj
        try:
            styles.notifier.scale_changed.disconnect(self._handle_scale_changed)
        except (TypeError, RuntimeError):
            pass
