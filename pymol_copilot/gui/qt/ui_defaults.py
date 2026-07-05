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
"""Default configuration values and sizes for UI components."""

from pymol_copilot.gui.qt import theme

__docformat__ = "google"


EMPTY_CONTENTS_MARGINS = [0, 0, 0, 0]
"""Contents margins without extra padding."""

EMPTY_SPACING = 0
"""Spacing without extra padding."""


def default_contents_margins() -> list[int]:
    """Return DPI-scaled default content margins.

    Returns:
        A list of four equal margin values in physical pixels.
    """
    tmp_v = theme.dp(4)
    return [tmp_v, tmp_v, tmp_v, tmp_v]


def small_contents_margins() -> list[int]:
    """Return DPI-scaled small content margins.

    Returns:
        A list of four margin values in physical pixels.
    """
    tmp_v = theme.dp(2)
    return [tmp_v, tmp_v, tmp_v, 2]


def default_spacing() -> int:
    """Return DPI-scaled default layout spacing.

    Returns:
        Spacing in physical pixels.
    """
    return theme.dp(4)


class UISize:
    """Represents predefined sizes for UI components.

    This class defines default sizes for various UI elements of the
    application.

    Attributes:
        LEFT_PANEL_WIDTH: Default width of the left panel of a
            ToolWindowLayoutBlock.
        RIGHT_PANEL_WIDTH: Default width of the right panel of a
            ToolWindowLayoutBlock.
        BOTTOM_PANEL_HEIGHT: Default height of the bottom panel of a
            ToolWindowLayoutBlock.
    """

    # <editor-fold desc="Class attributes">
    LEFT_PANEL_WIDTH = 200
    RIGHT_PANEL_WIDTH = 250
    BOTTOM_PANEL_HEIGHT = 200

    # </editor-fold>

    @staticmethod
    def command_bar_button_size() -> tuple[int, int]:
        """Return DPI-scaled command bar button size.

        Returns:
            A tuple (width, height) in physical pixels.
        """
        # tmp_v = theme.dp(24)
        tmp_v = theme.dp(20)
        return tmp_v, tmp_v
