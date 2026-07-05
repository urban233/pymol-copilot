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

import contextlib

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults


class Button(QtWidgets.QPushButton):
    """Base class for styled push buttons.

    Delegates initialization and style configuration to abstract subclass
    methods.
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

    # <editor-fold desc="Private methods">
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

    # </editor-fold>


class BasicButton(Button):
    """A standard, non-accented button with basic styling."""

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget."""

    def _set_styles(self) -> None:
        """Apply basic button styles."""
        self.setObjectName(theme.StyleId.BASIC_BUTTON)

    # </editor-fold>


class AccentButton(Button):
    """An accented button with the primary theme color highlight."""

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget."""

    def _set_styles(self) -> None:
        """Apply accented button styles."""
        self.setObjectName(theme.StyleId.ACCENT_BUTTON)

    # </editor-fold>


class IconButton(Button):
    """A fully transparent, borderless button that centers an icon.

    No background or border is painted in any state. The button is fixed
    to a square hit area of ``size_dp`` logical pixels; the icon fills that
    area without padding.  Icon size can be changed at any time via
    :meth:`set_icon_size_dp`.

    Attributes:
        _icon: The QIcon rendered inside the button.
        _size_dp: The button (and icon) size in logical pixels.
    """

    def __init__(
        self,
        icon: QtGui.QIcon,
        size_dp: int = 24,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the GhostIconButton.

        Args:
            icon: The QIcon to display.
            size_dp: The button and icon size in logical pixels. Defaults to 24.
            parent: Optional parent widget.
        """
        # <editor-fold desc="Instance attributes">
        self._icon = icon
        self._size_dp = size_dp
        # </editor-fold>
        super().__init__("", parent)

    # <editor-fold desc="Public methods">
    def set_icon_size_dp(self, size_dp: int) -> None:
        """Change the icon and button size.

        Args:
            size_dp: New size in logical pixels.
        """
        self._size_dp = size_dp
        self.setIconSize(
            QtCore.QSize(
                theme.SizeToken(size_dp).px, theme.SizeToken(size_dp).px
            )
        )
        self._set_styles()

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Set the icon and connect to DPI-change notifications."""
        self.setIcon(self._icon)
        self._notifier_signal: QtCore.pyqtBoundSignal = (
            theme.get_notifier().scale_changed
        )
        self._notifier_signal.connect(self._handle_scale_changed)
        self.destroyed.connect(self._cleanup_connections)

    def _set_styles(self) -> None:
        """Apply a fully transparent, fixed-size stylesheet with hover highlight."""
        tmp_size_px = theme.SizeToken(self._size_dp).px
        self.setIconSize(QtCore.QSize(tmp_size_px, tmp_size_px))
        tmp_radius_px = tmp_size_px // 2
        tmp_qss = f"""
            QPushButton {{
                background: transparent;
                border: none;
                padding: 0px;
                border-radius: {tmp_radius_px}px;
                min-width: {tmp_size_px}px;
                max-width: {tmp_size_px}px;
                min-height: {tmp_size_px}px;
                max-height: {tmp_size_px}px;
            }}
            QPushButton:hover {{
                background-color: #efefef;
            }}
        """
        self.setStyleSheet(tmp_qss)

    def _handle_scale_changed(self, _scale: float) -> None:
        """Recalculate pixel dimensions when screen DPI changes.

        Args:
            _scale: The new screen scaling factor.
        """
        self._set_styles()

    def _cleanup_connections(self, _obj: QtCore.QObject | None = None) -> None:
        """Disconnect the scale-changed signal to prevent memory leaks.

        Args:
            _obj: The QObject being destroyed (optional).
        """
        if not hasattr(self, "_notifier_signal"):
            return
        with contextlib.suppress(TypeError, RuntimeError):
            self._notifier_signal.disconnect(self._handle_scale_changed)

    # </editor-fold>


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
            size_dp: The diameter of the button in logical pixels.
                Defaults to 24.
            parent: Optional parent widget.
        """
        # <editor-fold desc="Instance attributes">
        self._icon = icon
        self._size_dp = size_dp
        # </editor-fold>
        super().__init__("", parent)

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget properties, applying the icon."""
        self.setIcon(self._icon)
        # Store the exact signal instance so _cleanup_connections disconnects
        # from the same QObject the connection was made to, even if the
        # notifier's internal _NotifierQObject is ever recreated.
        self._notifier_signal: QtCore.pyqtBoundSignal = (
            theme.get_notifier().scale_changed
        )
        self._notifier_signal.connect(self._handle_scale_changed)
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

    def _handle_scale_changed(self, _scale: float) -> None:
        """Handle screen DPI scaling updates to recalculate circle dimensions.

        Args:
            _scale: The new screen scaling factor.
        """
        self._set_styles()

    def _cleanup_connections(self, _obj: QtCore.QObject | None = None) -> None:
        """Clean up scale changed signal connection to prevent memory leaks.

        Args:
            _obj: The QObject being destroyed (optional).
        """
        if not hasattr(self, "_notifier_signal"):
            return
        with contextlib.suppress(TypeError, RuntimeError):
            self._notifier_signal.disconnect(self._handle_scale_changed)

    # </editor-fold>


class ToggleButton(QtWidgets.QWidget):
    """A styled toggle button based on QToolButton.

    Provides a clean, checkable toggle button interface.
    """

    clicked = QtCore.pyqtSignal()
    toggled = QtCore.pyqtSignal(bool)

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the ToggleButton.

        Args:
            text: Label text.
            checked: Whether the button starts checked.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._text = text
        self._checked = checked
        self._button = QtWidgets.QToolButton()

        self._init_widget()
        self._set_styles()
        self._connect_signals()

    def _init_widget(self) -> None:
        """Initialize the widget."""
        if self._text:
            self._button.setText(self._text)
        self._button.setCheckable(True)
        self._button.setChecked(self._checked)
        self._button.setAutoRaise(False)
        self._button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        tmp_layout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_layout.addWidget(self._button)

    def _set_styles(self) -> None:
        """Apply styles to the widget."""
        self._button.setObjectName(theme.StyleId.TOGGLE_BUTTON)

    def _connect_signals(self) -> None:
        """Wire signal-slot connections."""
        self._button.clicked.connect(self._emit_clicked)
        self._button.toggled.connect(self._emit_toggled)

    def is_checked(self) -> bool:
        """Return whether the toggle is currently checked.

        Returns:
            True when the button is checked, otherwise False.
        """
        return self._button.isChecked()

    def set_checked(self, checked: bool) -> None:
        """Set the checked state.

        Args:
            checked: The new checked state.
        """
        self._button.setChecked(checked)

    def toggle(self) -> None:
        """Invert the checked state and emit toggled signal."""
        self._button.toggle()

    def _emit_clicked(self, checked: bool = False) -> None:
        """Emit clicked signal.

        Args:
            checked: Check status.
        """
        del checked
        self.clicked.emit()

    def _emit_toggled(self, checked: bool) -> None:
        """Emit toggled signal and refresh stylesheet state.

        Args:
            checked: The current checked state.
        """
        self.toggled.emit(checked)
        theme.refresh_widget_style(self._button)
