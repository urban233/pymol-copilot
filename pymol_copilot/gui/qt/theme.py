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
"""Design system colors, sizing tokens, and QSS compilation helper."""

from __future__ import annotations

from typing import override
import contextlib
import enum
import re

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets


def dp(value: int | float, screen: QtGui.QScreen | None = None) -> int:
    """Convert a density-independent pixel value to physical pixels.

    All dimension tokens in Win11Tokens and ElevationLevel are expressed in
    dp at a 96 DPI baseline. Widgets call this function whenever they pass a
    token value to a Qt API that expects physical pixels.

    Always call after QApplication has been created.

    Args:
        value: Size in density-independent pixels (96 DPI = 1x baseline).
        screen: Optional QScreen to use for calculating DPI scaling. If
            None, the primary screen is used.

    Returns:
        The equivalent size in physical pixels for the chosen screen,
        rounded to the nearest integer.
    """
    tmp_app = QtWidgets.QApplication.instance()
    if isinstance(tmp_app, QtWidgets.QApplication):
        get_notifier().install_event_filter(tmp_app)

    if screen is None and isinstance(tmp_app, QtWidgets.QApplication):
        screen = tmp_app.primaryScreen()

    if screen is None:
        return round(value)

    tmp_scale = screen.logicalDotsPerInch() / 96.0
    return round(value * tmp_scale)


class _NotifierQObject(QtCore.QObject):
    """Internal QObject subclass for emitting Qt signals."""

    scale_changed = QtCore.pyqtSignal(float)

    def __init__(self, outer: ScreenChangeNotifier) -> None:
        """Initialize the _NotifierQObject.

        Args:
            outer: The ScreenChangeNotifier instance.
        """
        super().__init__()
        self._outer = outer

    @override
    def eventFilter(
        self, a0: QtCore.QObject | None, a1: QtCore.QEvent | None
    ) -> bool:
        """Filter events on QApplication.

        Args:
            a0: The QObject receiving the event.
            a1: The QEvent being sent.

        Returns:
            Always False to allow the event to propagate.
        """
        return self._outer._handle_event(a0, a1)

    @override
    def connectNotify(self, signal: QtCore.QMetaMethod) -> None:
        """Ensure the event filter is installed when a connection is made.

        Args:
            signal: The signal being connected.
        """
        super().connectNotify(signal)
        tmp_app = QtWidgets.QApplication.instance()
        if isinstance(tmp_app, QtWidgets.QApplication):
            self._outer.install_event_filter(tmp_app)


class ScreenChangeNotifier:
    """Notifier for screen scale factor changes.

    This class monitors for device pixel ratio changes and emits the
    scale_changed signal when a change is detected, allowing widgets
    to dynamically adapt their scaling.
    """

    def __init__(self) -> None:
        """Initialize the ScreenChangeNotifier wrapper."""
        self._qobject: _NotifierQObject | None = None
        self._last_scale: float = 1.0
        self._current_screen: QtGui.QScreen | None = None
        self._installed: bool = False

        tmp_app = QtWidgets.QApplication.instance()
        if isinstance(tmp_app, QtWidgets.QApplication):
            self.install_event_filter(tmp_app)

    def _get_qobject(self) -> _NotifierQObject:
        """Get the active QObject instance, recreating it if deleted.

        Returns:
            The active _NotifierQObject instance.
        """
        from PyQt6 import sip

        if self._qobject is None:
            self._qobject = _NotifierQObject(self)
            self._installed = False
            tmp_app = QtWidgets.QApplication.instance()
            if isinstance(tmp_app, QtWidgets.QApplication):
                self.install_event_filter(tmp_app)
        elif sip.isdeleted(self._qobject):
            # The C++ QObject was unexpectedly freed (e.g., during teardown).
            # We cannot call removeEventFilter on a deleted object, so the
            # old filter entry is already gone from Qt's side.  Log a warning
            # so developers can investigate the unexpected deletion path.
            import logging

            logging.getLogger(__name__).warning(
                "_NotifierQObject was unexpectedly deleted by Qt. "
                "Recreating it."
            )
            self._qobject = _NotifierQObject(self)
            self._installed = False
            tmp_app = QtWidgets.QApplication.instance()
            if isinstance(tmp_app, QtWidgets.QApplication):
                self.install_event_filter(tmp_app)
        return self._qobject

    @property
    def scale_changed(self) -> QtCore.pyqtBoundSignal:
        """The scale_changed signal bound to the internal QObject.

        Returns:
            The scale_changed signal.
        """
        return self._get_qobject().scale_changed

    def install_event_filter(self, app: QtWidgets.QApplication) -> None:
        """Install the event filter and connect signals.

        Args:
            app: The QApplication instance.
        """
        if self._installed:
            return

        tmp_qobj = self._get_qobject()
        app.installEventFilter(tmp_qobj)
        app.primaryScreenChanged.connect(self._handle_primary_screen_change)
        self._connect_primary_screen_signals()

        tmp_screen = app.primaryScreen()
        if tmp_screen is not None:
            self._last_scale = tmp_screen.logicalDotsPerInch() / 96.0

        self._installed = True

    def _connect_primary_screen_signals(self) -> None:
        """Connect to the primary screen's logical DPI change signal."""
        from pymol_copilot.gui.qt import sip

        if self._current_screen is not None:
            if sip.isdeleted(self._current_screen):
                self._current_screen = None
            else:
                try:
                    if (
                        self._current_screen
                        not in QtWidgets.QApplication.screens()
                    ):
                        self._current_screen = None
                except (TypeError, RuntimeError):
                    self._current_screen = None

        tmp_screen = QtWidgets.QApplication.primaryScreen()
        if tmp_screen == self._current_screen:
            return

        if self._current_screen is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._current_screen.logicalDotsPerInchChanged.disconnect(
                    self._handle_dpi_change
                )

        self._current_screen = tmp_screen
        if tmp_screen is not None:
            tmp_screen.logicalDotsPerInchChanged.connect(
                self._handle_dpi_change,
                QtCore.Qt.ConnectionType.UniqueConnection,  # type: ignore[call-arg]
            )

    def _handle_primary_screen_change(self, screen: QtGui.QScreen) -> None:
        """Handle change of primary screen.

        Args:
            screen: The new primary QScreen.
        """
        self._connect_primary_screen_signals()
        self._handle_dpi_change(screen.logicalDotsPerInch())

    def _handle_dpi_change(self, dpi: float) -> None:
        """Handle logical DPI change and emit signal if scale changed.

        Args:
            dpi: The new logical DPI.
        """
        tmp_scale = dpi / 96.0
        if tmp_scale != self._last_scale:
            self._last_scale = tmp_scale
            self.scale_changed.emit(tmp_scale)

    def _handle_event(
        self, a0: QtCore.QObject | None, a1: QtCore.QEvent | None
    ) -> bool:
        """Process event filter event.

        Args:
            a0: The watched QObject.
            a1: The QEvent to filter.

        Returns:
            Always False to allow the event to propagate.
        """
        if (
            a1 is not None
            and a1.type() == QtCore.QEvent.Type.DevicePixelRatioChange
        ):
            tmp_screen = None
            if isinstance(a0, QtWidgets.QWidget):
                tmp_window = a0.window()
                if tmp_window is not None:
                    tmp_handle = tmp_window.windowHandle()
                    if tmp_handle is not None:
                        tmp_screen = tmp_handle.screen()

            if tmp_screen is None:
                tmp_screen = QtWidgets.QApplication.primaryScreen()

            if tmp_screen is not None:
                self._handle_dpi_change(tmp_screen.logicalDotsPerInch())

        return False


_notifier: ScreenChangeNotifier | None = None


def get_notifier() -> ScreenChangeNotifier:
    """Return the module-level ScreenChangeNotifier, creating it lazily.

    The singleton is not created until this function is first called,
    ensuring no QObject is allocated before QApplication exists.

    Returns:
        The singleton ScreenChangeNotifier instance.
    """
    global _notifier  # noqa: PLW0603
    if _notifier is None:
        _notifier = ScreenChangeNotifier()
    return _notifier


class ColorToken:
    """Value object representing a design system color."""

    def __init__(self, hex_value: str) -> None:
        """Initialize the color token.

        Args:
            hex_value: The hex color code.
        """
        self._hex = hex_value

    def to_hex(self) -> str:
        """Get the hex color string.

        Returns:
            The hex color code.
        """
        return self._hex

    def to_qcolor(self) -> QtGui.QColor:
        """Create a QColor instance.

        Returns:
            A QColor instance representing this color.
        """
        return QtGui.QColor(self._hex)


class SizeToken:
    """Value object representing a sizing token with DPI scaling support."""

    def __init__(self, dp_value: int) -> None:
        """Initialize the sizing token.

        Args:
            dp_value: Logical size in density-independent pixels.
        """
        self._dp = dp_value

    @property
    def px(self) -> int:
        """Get the DPI-scaled physical pixel value.

        Returns:
            The scaled physical pixels.
        """
        return dp(self._dp)

    def to_qss(self) -> str:
        """Get the QSS representation of this size.

        Returns:
            The size string formatted for QSS (e.g., "8px").
        """
        return f"{self.px}px"


class ThemeColors:
    """Static namespace for application colors."""

    SURFACE = ColorToken("#ffffff")
    HOVER = ColorToken("#f5f5f5")
    PRESSED = ColorToken("#e0e0e0")
    BORDER_COLOR = ColorToken("#ebecf0")
    BORDER_ACTIVE = ColorToken("#616161")
    BORDER_HOVER = ColorToken("#c7c7c7")
    DIVIDER = ColorToken("#dcdcdc")
    ACCENT = ColorToken("#009AE5")
    ACCENT_HOVER = ColorToken("#4b91f7")
    ACCENT_PRESSED = ColorToken("#256cf0")
    TEXT_ON_ACCENT = ColorToken("#ffffff")
    TEXT_PRIMARY = ColorToken("#242424")
    PRESSED_SHARED = ColorToken("#ebebeb")
    CUI_CARD_SURFACE = ColorToken("#f7f8f9")
    CUI_CARD_BORDER = ColorToken("#e9eaee")
    CUI_USER_CARD_SURFACE = ColorToken("#e9eaee")


class ThemeMetrics:
    """Static namespace for layout sizes."""

    CORNER_RADIUS = SizeToken(6)
    BORDER_WIDTH = SizeToken(1)
    PADDING_SMALL = SizeToken(4)
    PADDING_MEDIUM = SizeToken(8)
    FONT_SIZE_BASE = SizeToken(12)
    CLOSE_BUTTON_SIZE = SizeToken(36)
    CLOSE_BUTTON_HOVER_SIZE = SizeToken(40)
    FONT_SIZE_HEADER = SizeToken(16)
    MARGIN_LEFT = SizeToken(8)
    FONT_SIZE_MENU_ITEM = SizeToken(13)


class StyleId(enum.StrEnum):
    """Typesafe identifier names for QSS object names."""

    BASIC_BUTTON = "BasicButton"
    ACCENT_BUTTON = "AccentButton"
    COMMAND_BAR = "CommandBar"
    COMMAND_BAR_OUTER = "CommandBarOuter"
    SPLIT_BUTTON_MAIN = "SplitButtonMain"
    SPLIT_BUTTON_ARROW = "SplitButtonArrow"
    TOGGLE_BUTTON = "ToggleButton"
    DROPDOWN_BUTTON_UNDER = "DropdownButtonTextUnder"
    DROPDOWN_BUTTON_BESIDE = "DropdownButtonTextBeside"
    FLYOUT_FRAME = "FlyoutFrame"
    PANEL_CLOSE_BUTTON = "PanelCloseButton"
    PANEL_HEADER_LABEL = "PanelHeaderLabel"
    PANEL_SURFACE = "PanelSurface"
    INPUT_BAR_TEXT_BOX = "InputBarTextBox"
    INPUT_BAR = "InputBar"
    MINIMAL_TEXT_BOX = "MinimalTextBox"
    CUI_CARD_SURFACE = "CuiCardSurface"
    """Base card surface for the conversational user interface (CUI)."""
    CUI_USER_CARD_SURFACE = "CuiUserCardSurface"
    SIDE_TAB_BUTTON = "SideTabButton"
    # Maybe outdated
    SPLITTER_HANDLE = "SplitterHandle"
    MENU_BLOCK = "MenuBlock"
    TOOLBAR_BLOCK = "ToolbarBlock"
    TABBED_COMMAND_BAR = "TabbedCommandBar"
    TABBED_COMMAND_BAR_OUTER = "TabbedCommandBarOuter"
    TABBED_COMMAND_BAR_TAB = "TabbedCommandBarTab"
    TABBED_COMMAND_BAR_DIVIDER = "TabbedCommandBarDivider"


GLOBAL_STYLESHEET_TEMPLATE = f"""
QPushButton#{StyleId.BASIC_BUTTON} {{
    background-color: ${{surface}};
    border: 1px solid ${{border_color}};
    border-radius: ${{padding_small}};
    min-height: 22px;
    min-width: 80px;
    max-width: 80px;
}}
QPushButton#{StyleId.BASIC_BUTTON}:hover {{
    background-color: ${{hover}};
    border: 1px solid ${{border_hover}};
}}
QPushButton#{StyleId.BASIC_BUTTON}:pressed {{
    background-color: ${{pressed}};
    border: 1px solid ${{border_active}};
}}

QPushButton#{StyleId.ACCENT_BUTTON} {{
    background-color: ${{accent}};
    border: 1px solid ${{accent}};
    border-radius: ${{padding_small}};
    min-height: 22px;
    min-width: 80px;
    max-width: 80px;
    color: ${{text_on_accent}};
}}
QPushButton#{StyleId.ACCENT_BUTTON}:hover {{
    background-color: ${{accent_hover}};
    border: 1px solid ${{accent_hover}};
}}
QPushButton#{StyleId.ACCENT_BUTTON}:pressed {{
    background-color: ${{accent_pressed}};
    border: 1px solid ${{accent_pressed}};
}}


QPushButton#{StyleId.PANEL_CLOSE_BUTTON} {{
    background-color: rgba(220, 219, 227, 0.01);
    border: none;
    border-radius: ${{padding_small}};
    min-width: ${{close_button_size}};
    max-width: ${{close_button_size}};
    min-height: ${{close_button_size}};
    max-height: ${{close_button_size}};
}}
QPushButton#{StyleId.PANEL_CLOSE_BUTTON}:hover {{
    background-color: rgba(220, 219, 227, 0.5);
    border: none;
    min-width: ${{close_button_hover_size}};
    max-width: ${{close_button_hover_size}};
    min-height: ${{close_button_hover_size}};
    max-height: ${{close_button_hover_size}};
}}

QLabel#{StyleId.PANEL_HEADER_LABEL} {{
    font-size: ${{font_size_header}};
    margin-left: ${{margin_left}};
}}

QFrame#{StyleId.PANEL_SURFACE} {{
    border: ${{border_width}} solid ${{border_color}};
    background-color: ${{surface}};
    border-radius: ${{corner_radius}};
}}

QSplitter::handle {{
    background-color: ${{border_color}};
    margin: 1px;
}}

QFrame#{StyleId.COMMAND_BAR_OUTER} {{
    border: ${{border_width}} solid ${{border_color}};
    background-color: ${{surface}};
    border-radius: ${{corner_radius}};
    padding: ${{padding_small}};
}}

#{StyleId.COMMAND_BAR} QToolButton {{
    font-size: ${{font_size_base}};
    background-color: ${{surface}};
    border: none;
    border-radius: ${{corner_radius}};
    padding: 4px 6px;
}}
#{StyleId.COMMAND_BAR} QToolButton:hover {{
    background-color: ${{hover}};
}}

#{StyleId.TABBED_COMMAND_BAR} QToolButton {{
    font-size: ${{font_size_base}};
    background-color: ${{surface}};
    border: none;
    border-radius: ${{corner_radius}};
    padding: 4px 6px;
}}
#{StyleId.TABBED_COMMAND_BAR} QToolButton:hover {{
    background-color: ${{hover}};
}}

QToolButton#{StyleId.TOGGLE_BUTTON} {{
    font-size: ${{font_size_base}};
    background-color: ${{surface}};
    border: 1px solid transparent;
    border-radius: ${{corner_radius}};
    padding: 3px 5px;
}}
QToolButton#{StyleId.TOGGLE_BUTTON}:hover {{
    background-color: ${{hover}};
    border-color: ${{border_hover}};
}}
QToolButton#{StyleId.TOGGLE_BUTTON}:checked {{
    background-color: ${{pressed_shared}};
    border-color: ${{border_active}};
}}
QToolButton#{StyleId.TOGGLE_BUTTON}:checked:hover {{
    background-color: ${{pressed}};
    border-color: ${{border_active}};
}}
QToolButton#{StyleId.TOGGLE_BUTTON}:pressed {{
    background-color: ${{pressed}};
    border-color: ${{border_active}};
}}
QToolButton#{StyleId.TOGGLE_BUTTON}:focus {{
    outline: none;
}}

QToolButton#{StyleId.SPLIT_BUTTON_MAIN} {{
    font-size: ${{font_size_base}};
    background: transparent;
    border: none;
    padding: 4px 6px;
}}
QToolButton#{StyleId.SPLIT_BUTTON_MAIN}:hover,
QToolButton#{StyleId.SPLIT_BUTTON_MAIN}:pressed,
QToolButton#{StyleId.SPLIT_BUTTON_MAIN}:focus {{
    background: transparent;
    border: none;
    outline: none;
}}

QToolButton#{StyleId.SPLIT_BUTTON_ARROW} {{
    font-size: ${{font_size_base}};
    background: transparent;
    border: none;
    min-width: 14px;
    max-width: 14px;
    padding: 4px 3px;
}}
QToolButton#{StyleId.SPLIT_BUTTON_ARROW}:hover,
QToolButton#{StyleId.SPLIT_BUTTON_ARROW}:pressed,
QToolButton#{StyleId.SPLIT_BUTTON_ARROW}:focus {{
    background: transparent;
    border: none;
    outline: none;
}}
QToolButton#{StyleId.SPLIT_BUTTON_ARROW}::menu-indicator {{
    image: none;
}}

QToolButton#{StyleId.DROPDOWN_BUTTON_UNDER} {{
    font-size: ${{font_size_base}};
    background-color: ${{surface}};
    border: 1px solid transparent;
    border-radius: ${{corner_radius}};
    padding: 3px 5px;
    padding-bottom: 13px;
}}
QToolButton#{StyleId.DROPDOWN_BUTTON_UNDER}:hover {{
    background-color: ${{hover}};
}}
QToolButton#{StyleId.DROPDOWN_BUTTON_UNDER}:pressed,
QToolButton#{StyleId.DROPDOWN_BUTTON_UNDER}:open,
QToolButton#{StyleId.DROPDOWN_BUTTON_UNDER}[flyoutOpen="true"] {{
    background-color: ${{pressed_shared}};
    border-color: ${{border_active}};
}}
QToolButton#{StyleId.DROPDOWN_BUTTON_UNDER}::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: bottom center;
    width: 8px;
    height: 8px;
    bottom: 2px;
}}

QToolButton#{StyleId.DROPDOWN_BUTTON_BESIDE} {{
    font-size: ${{font_size_base}};
    background-color: ${{surface}};
    border: 1px solid transparent;
    border-radius: ${{corner_radius}};
    padding: 3px 5px;
    padding-right: 13px;
}}
QToolButton#{StyleId.DROPDOWN_BUTTON_BESIDE}:hover {{
    background-color: ${{hover}};
}}
QToolButton#{StyleId.DROPDOWN_BUTTON_BESIDE}:pressed,
QToolButton#{StyleId.DROPDOWN_BUTTON_BESIDE}:open,
QToolButton#{StyleId.DROPDOWN_BUTTON_BESIDE}[flyoutOpen="true"] {{
    background-color: ${{pressed_shared}};
    border-color: ${{border_active}};
}}
QToolButton#{StyleId.DROPDOWN_BUTTON_BESIDE}::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 8px;
    height: 8px;
    right: 2px;
}}

QFrame#{StyleId.FLYOUT_FRAME} {{
    border: ${{border_width}} solid ${{border_color}};
    background-color: ${{surface}};
    border-radius: ${{corner_radius}};
    padding: 4px;
}}

QMenu {{
    background-color: ${{surface}};
    margin: 2px;
}}
QMenu::item {{
    padding-top: 5px;
    padding-bottom: 5px;
    padding-left: 7px;
    padding-right: 15px;
    font-size: ${{font_size_menu_item}};
}}
QMenu::item:selected {{
    background-color: ${{hover}};
    border-width: 2px;
    border-radius: 4px;
    border-color: ${{surface}};
}}
QMenu::icon {{
    padding-left: 15px;
}}
QMenu::separator {{
    height: 1px;
    background-color: ${{border_color}};
    margin-left: 0px;
    margin-right: 0px;
}}
QMenu QLabel {{
    padding-top: 5px;
    padding-bottom: 5px;
    padding-right: 10px;
    margin-left: 10px;
    font: bold;
    font-size: ${{font_size_base}};
    color: ${{text_primary}};
}}

#{StyleId.TOOLBAR_BLOCK} QToolButton {{
    font-size: 8pt;
    background-color: ${{surface}};
    padding: 4px;
    border: none;
    border-radius: ${{corner_radius}};
}}
#{StyleId.TOOLBAR_BLOCK} QToolButton::hover {{
    background-color: ${{hover}};
    color: ${{text_primary}};
}}

QPlainTextEdit#{StyleId.INPUT_BAR_TEXT_BOX} {{
border: none;
    background-color: transparent;
    color: #1f1f1f;
    padding: 0px;
}}

QPlainTextEdit#{StyleId.INPUT_BAR_TEXT_BOX}:focus {{
border: none;
    outline: none;
}}

QPlainTextEdit#{StyleId.INPUT_BAR_TEXT_BOX} QScrollBar:horizontal {{
height: 0px;
    background: transparent;
}}

QFrame#{StyleId.INPUT_BAR} {{
    border: ${{border_width}} solid ${{border_color}};
    background-color: ${{surface}};
    border-radius: 17px;
    padding: ${{padding_small}};
}}

QLineEdit#{StyleId.MINIMAL_TEXT_BOX} {{
border: none;
    background-color: transparent;
    color: #1f1f1f;
    padding: 0px;
}}

QLineEdit#{StyleId.MINIMAL_TEXT_BOX}:focus {{
border: none;
    outline: none;
}}

QLineEdit#{StyleId.MINIMAL_TEXT_BOX} QScrollBar:horizontal {{
height: 0px;
    background: transparent;
}}

QTableView {{
    background-color: ${{surface}};
    gridline-color: ${{border_color}};
    border: 1px solid ${{border_color}};
    border-radius: ${{corner_radius}};
    alternate-background-color: ${{hover}};
}}

QTableView::item {{
    padding: 6px;
    border-bottom: 1px solid ${{border_color}};
}}

QTableView::item:hover {{
    background-color: ${{hover}};
}}

QTableView::item:selected {{
    background-color: rgba(54, 122, 246, 0.15);
    color: ${{text_primary}};
}}

QHeaderView::section {{
    background-color: ${{hover}};
    color: ${{text_primary}};
    padding: 5px;
    border: 1px solid ${{border_color}};
    font-weight: bold;
    font-size: ${{font_size_base}};
}}

QHeaderView::section:checked {{
    background-color: ${{pressed_shared}};
    color: #107c41;
}}

QFrame#{StyleId.CUI_CARD_SURFACE} {{
    border: ${{border_width}} solid ${{cui_card_border}};
    background-color: ${{cui_card_surface}};
    border-radius: ${{corner_radius}};
    padding: ${{padding_small}};
}}

QFrame#{StyleId.CUI_USER_CARD_SURFACE} {{
    border: ${{border_width}} solid ${{cui_card_border}};
    background-color: ${{cui_user_card_surface}};
    border-radius: ${{corner_radius}};
    padding: ${{padding_small}};
}}

QPushButton#{StyleId.SIDE_TAB_BUTTON} {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: ${{corner_radius}};
    padding: 0px;
}}
QPushButton#{StyleId.SIDE_TAB_BUTTON}:hover {{
    background-color: ${{hover}};
}}
QPushButton#{StyleId.SIDE_TAB_BUTTON}:checked {{
    background-color: ${{pressed_shared}};
    border-color: ${{border_active}};
}}
QPushButton#{StyleId.SIDE_TAB_BUTTON}:checked:hover {{
    background-color: ${{pressed}};
    border-color: ${{border_active}};
}}
QPushButton#{StyleId.SIDE_TAB_BUTTON}:pressed {{
    background-color: ${{pressed}};
    border-color: ${{border_active}};
}}
QPushButton#{StyleId.SIDE_TAB_BUTTON}:focus {{
    outline: none;
}}

QFrame#{StyleId.TABBED_COMMAND_BAR_OUTER} {{
    border: ${{border_width}} solid ${{border_color}};
    background-color: ${{surface}};
    border-radius: ${{corner_radius}};
    padding: 0px;
}}

QPushButton#{StyleId.TABBED_COMMAND_BAR_TAB} {{
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    padding: 4px 10px;
    font-size: ${{font_size_base}};
    color: ${{text_primary}};
}}
QPushButton#{StyleId.TABBED_COMMAND_BAR_TAB}:hover {{
    background-color: ${{hover}};
}}
QPushButton#{StyleId.TABBED_COMMAND_BAR_TAB}:checked {{
    background-color: transparent;
    border-bottom: 2px solid ${{accent}};
    font-weight: bold;
}}
QPushButton#{StyleId.TABBED_COMMAND_BAR_TAB}:pressed {{
    background-color: ${{pressed}};
}}

QFrame#{StyleId.TABBED_COMMAND_BAR_DIVIDER} {{
    background-color: ${{border_color}};
    border: none;
}}
"""
# QFrame#{StyleId.CUI_CARD_SURFACE} {{
# background-color: ${{surface}};
# border-top: ${{border_width}} solid ${{border_color}};
# border-right: ${{border_width}} solid ${{border_color}};
# border-bottom: ${{border_width}} solid ${{border_color}};
# /* Left-accented stroke mimicking Microsoft's focus paradigm */
# border-left: 4px solid ${{accent}};
# border-radius: ${{corner_radius}};
# }}
#
# /* State Flattening: Strip outer visual weight when item lifecycle ends */
#                                                                    QFrame#{StyleId.CUI_CARD_SURFACE}[state="historic"] {{
# background-color: transparent;
# border-top: ${{border_width}} solid transparent;
# border-right: ${{border_width}} solid transparent;
# border-bottom: ${{border_width}} solid transparent;
# /* Keeps timeline context without attracting structural attention */
#                                                         border-left: 4px solid ${{divider}};
# }}
#
# /* Default text color inside an active agent card */
#                                              QFrame#{StyleId.CUI_CARD_SURFACE} QLabel {{
# color: ${{text_primary}};
# }}
#
# /* Cascading dimming effect applied automatically to child elements */
#                                                            QFrame#{StyleId.CUI_CARD_SURFACE}[state="historic"] QLabel {{
# color: ${{border_hover}};
# }}

# Pre-built colour-token binding map.  Colour tokens are defined as
# class attributes on ThemeColors and never change at runtime, so
# this dict is computed exactly once at import time rather than on
# every compile_stylesheet() call (which fires on every DPI change).
_COLOR_BINDINGS: dict[str, str] = {
    tmp_name.lower(): tmp_attr.to_hex()
    for tmp_name, tmp_attr in vars(ThemeColors).items()
    if not tmp_name.startswith("_") and isinstance(tmp_attr, ColorToken)
}


def compile_stylesheet(template: str) -> str:
    """Formats a QSS template using static ThemeColors and ThemeMetrics.

    Placeholders should be in the format ${token_name} (e.g., ${surface}).
    Colour bindings are taken from the module-level ``_COLOR_BINDINGS`` dict
    (built once at import time).  Size bindings are recomputed on each call
    because they are DPI-dependent.

    Args:
        template: QSS template containing token placeholders.

    Returns:
        The formatted QSS stylesheet string.

    Raises:
        KeyError: If an invalid placeholder is specified in the template.
    """
    # Start from the cached colour bindings and overlay DPI-sensitive sizes.
    tmp_bindings: dict[str, str] = dict(_COLOR_BINDINGS)

    for tmp_name, tmp_attr in vars(ThemeMetrics).items():
        if not tmp_name.startswith("_") and isinstance(tmp_attr, SizeToken):
            tmp_bindings[tmp_name.lower()] = tmp_attr.to_qss()

    # Find all ${key} pattern occurrences
    tmp_matches = re.findall(r"\$\{(\w+)\}", template)
    for tmp_key in tmp_matches:
        if tmp_key not in tmp_bindings:
            raise KeyError(
                "Invalid theme token placeholder referenced in template: "
                f"{tmp_key}"
            )

    def _replacer(tmp_match: re.Match[str]) -> str:
        """Return the token binding for a matched placeholder.

        Args:
            tmp_match: The regex match object containing the token name
                in group 1.

        Returns:
            The replacement string for the matched token.
        """
        return tmp_bindings[tmp_match.group(1)]

    return re.sub(r"\$\{(\w+)\}", _replacer, template)


def apply_global_theme(scale: float | None = None) -> None:  # noqa: ARG001
    """Compiles and sets the global stylesheet on the QApplication instance.

    Args:
        scale: Optional scale factor passed when called from scale_changed.
    """
    tmp_app = QtWidgets.QApplication.instance()
    if isinstance(tmp_app, QtWidgets.QApplication):
        tmp_qss = compile_stylesheet(GLOBAL_STYLESHEET_TEMPLATE)
        tmp_app.setStyleSheet(tmp_qss)


def refresh_widget_style(widget: QtWidgets.QWidget) -> None:
    """Forces Qt to re-evaluate the global stylesheet on a widget.

    Required when updating object names or dynamic properties after the
    widget is already rendered.

    Args:
        widget: The target widget.
    """
    tmp_style = widget.style()
    if isinstance(tmp_style, QtWidgets.QStyle):
        tmp_style.unpolish(widget)
        tmp_style.polish(widget)
        widget.update()
