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
DEFAULT_CONTENTS_MARGINS = [
    theme.dp(4),
    theme.dp(4),
    theme.dp(4),
    theme.dp(4),
]
"""Contents margins with default extra padding."""
SMALL_CONTENTS_MARGINS = [theme.dp(2), theme.dp(2), theme.dp(2), 2]
"""Contents margins with small extra padding."""
RIBBON_CONTENTS_MARGINS = [theme.dp(3), 0, theme.dp(3), 0]
"""Contents margins for the ribbon widget."""
RIBBON_PANEL_CONTENTS_MARGINS = [theme.dp(2), 0, theme.dp(2), 0]
"""Contents margins for ribbon panels."""

EMPTY_SPACING = 0
"""Spacing without extra padding."""

DEFAULT_SPACING = theme.dp(4)
"""Default layout spacing between widgets."""


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
        COMMAND_BAR_BUTTON_SIZE: Default size of command bar buttons.
    """

    # <editor-fold desc="Class attributes">
    LEFT_PANEL_WIDTH = 200
    RIGHT_PANEL_WIDTH = 250
    BOTTOM_PANEL_HEIGHT = 200
    COMMAND_BAR_BUTTON_SIZE = (theme.dp(24), theme.dp(24))

    # </editor-fold>
