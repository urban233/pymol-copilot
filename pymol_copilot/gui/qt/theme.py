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

import re

from PyQt6 import QtGui

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
    PRESSED_SHARED = ColorToken("#ebebeb")  # both-sections pressed (e.g. SplitButton arrow/menu-open)
    DIVIDER = ColorToken("#dcdcdc")         # intra-widget divider line
    BORDER_DEFAULT = ColorToken("#ebecf0")
    BORDER_HOVER = ColorToken("#c7c7c7")    # border shown on hover
    BORDER_ACTIVE = ColorToken("#616161")
    ACCENT = ColorToken("#367af6")
    TEXT_PRIMARY = ColorToken("#242424")


class ThemeMetrics:
    """Static namespace for layout sizes."""

    CORNER_RADIUS = SizeToken(6)
    CORNER_RADIUS_BUTTON = SizeToken(5)    # per-button border-radius
    BORDER_WIDTH = SizeToken(1)
    PADDING_FRAME = SizeToken(2)           # outer/flyout frame inner padding
    PADDING_XSMALL = SizeToken(3)          # arrow button horizontal padding
    PADDING_SMALL = SizeToken(4)           # button vertical padding
    PADDING_MEDIUM = SizeToken(8)
    PADDING_BUTTON_H = SizeToken(6)        # button horizontal padding
    ARROW_BUTTON_WIDTH = SizeToken(14)     # fixed width of the split-button arrow section
    FONT_SIZE_BASE = SizeToken(12)


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
