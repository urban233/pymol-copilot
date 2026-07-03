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

import enum
import re

from PyQt6 import QtGui
from PyQt6 import QtWidgets

from pymol_copilot.gui.qt import styles


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
        return styles.dp(self._dp)

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
    ACCENT = ColorToken("#367af6")
    ACCENT_HOVER = ColorToken("#4b91f7")
    ACCENT_PRESSED = ColorToken("#256cf0")
    TEXT_ON_ACCENT = ColorToken("#ffffff")
    TEXT_PRIMARY = ColorToken("#242424")
    PRESSED_SHARED = ColorToken("#ebebeb")


class ThemeMetrics:
    """Static namespace for layout sizes."""

    CORNER_RADIUS = SizeToken(6)
    BORDER_WIDTH = SizeToken(1)
    PADDING_SMALL = SizeToken(4)
    PADDING_MEDIUM = SizeToken(8)
    FONT_SIZE_BASE = SizeToken(12)
    CLOSE_BUTTON_SIZE = SizeToken(36)
    CLOSE_BUTTON_HOVER_SIZE = SizeToken(40)
    FONT_SIZE_HEADER = SizeToken(20)
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
    # Maybe outdated
    SPLITTER_HANDLE = "SplitterHandle"
    MENU_BLOCK = "MenuBlock"
    TOOLBAR_BLOCK = "ToolbarBlock"


GLOBAL_STYLESHEET_TEMPLATE = f"""
QPushButton#{StyleId.BASIC_BUTTON} {{
    background-color: ${{surface}};
    border: 1px solid ${{border_color}};
    border-radius: ${{padding_small}};
    min-height: 22px;
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
    border-radius: 20px;
    padding: ${{padding_medium}};
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
"""


def compile_stylesheet(template: str) -> str:
    """Formats a QSS template using static ThemeColors and ThemeMetrics.

    Placeholders should be in the format ${token_name} (e.g., ${surface}).

    Args:
        template: QSS template containing token placeholders.

    Returns:
        The formatted QSS stylesheet string.

    Raises:
        KeyError: If an invalid placeholder is specified in the template.
    """
    tmp_bindings: dict[str, str] = {}

    for tmp_name in dir(ThemeColors):
        if tmp_name.startswith("_"):
            continue
        tmp_attr = getattr(ThemeColors, tmp_name)
        if isinstance(tmp_attr, ColorToken):
            tmp_bindings[tmp_name.lower()] = tmp_attr.to_hex()

    for tmp_name in dir(ThemeMetrics):
        if tmp_name.startswith("_"):
            continue
        tmp_attr = getattr(ThemeMetrics, tmp_name)
        if isinstance(tmp_attr, SizeToken):
            tmp_bindings[tmp_name.lower()] = tmp_attr.to_qss()

    # Find all ${key} pattern occurrences
    tmp_matches = re.findall(r"\$\{(\w+)\}", template)
    for tmp_key in tmp_matches:
        if tmp_key not in tmp_bindings:
            raise KeyError(
                f"Invalid theme token placeholder referenced in template: {tmp_key}"
            )

    tmp_result = template
    for tmp_key, tmp_val in tmp_bindings.items():
        tmp_result = tmp_result.replace(f"${{{tmp_key}}}", tmp_val)
    return tmp_result


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
