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

import enum

__docformat__ = "google"

from pymol_copilot.gui.qt import styles

EMPTY_CONTENTS_MARGINS = [0, 0, 0, 0]
"""Contents margins without extra padding."""
DEFAULT_CONTENTS_MARGINS = [styles.dp(4), styles.dp(4), styles.dp(4), styles.dp(4)]
"""Contents margins with default extra padding."""
SMALL_CONTENTS_MARGINS = [styles.dp(2), styles.dp(2), styles.dp(2), 2]
"""Contents margins with small extra padding."""
RIBBON_CONTENTS_MARGINS = [styles.dp(3), 0, styles.dp(3), 0]
"""Contents margins for the ribbon widget."""
RIBBON_PANEL_CONTENTS_MARGINS = [styles.dp(2), 0, styles.dp(2), 0]
"""Contents margins for ribbon panels."""

EMPTY_SPACING = 0
"""Spacing without extra padding."""

DEFAULT_SPACING = styles.dp(4)
"""Default layout spacing between widgets."""
RIBBON_PANEL_SPACING = 1
"""Layout spacing between elements in a ribbon panel."""


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
        TOOLBAR_BUTTON_SIZE: Default size of toolbar buttons.
        RIBBON_PANEL_STACKED_ICON_SIZE: Icon size for stacked panel.
        RIBBON_PANEL_SIDE_BY_SIDE_ICON_SIZE: Icon size for side-by-side panel.
        RIBBON_PANEL_STACKED_ITEM_ICON_SIZE: Icon size for stacked panel items.
        RIBBON_PANEL_SETTINGS_ICON_SIZE: Icon size for panel settings button.
        RIBBON_PANEL_SPACER_WIDTH: Width of the ribbon panel spacer.
        RIBBON_PANEL_SPACER_HEIGHT: Height of the ribbon panel spacer.
        RIBBON_BAR_SHADOW_BLUR_RADIUS: Blur radius for ribbon bar shadow.
        RIBBON_BAR_SHADOW_COLOR_ALPHA: Alpha value for ribbon bar shadow color.
        RIBBON_BAR_SHADOW_OFFSET_X: Horizontal offset for ribbon bar shadow.
        RIBBON_BAR_SHADOW_OFFSET_Y: Vertical offset for ribbon bar shadow.
        RIBBON_BAR_HIDDEN_TAB_INDEX: Index of the hidden ribbon tab.
    """

    # <editor-fold desc="Class attributes">
    LEFT_PANEL_WIDTH = 200
    RIGHT_PANEL_WIDTH = 250
    BOTTOM_PANEL_HEIGHT = 200
    TOOLBAR_BUTTON_SIZE = 30

    COMMAND_BAR_BUTTON_SIZE = (styles.dp(24), styles.dp(24))
    """Default size of command bar buttons."""

    RIBBON_PANEL_STACKED_ICON_SIZE = 20
    RIBBON_PANEL_SIDE_BY_SIDE_ICON_SIZE = 32
    RIBBON_PANEL_STACKED_ITEM_ICON_SIZE = 16
    RIBBON_PANEL_SETTINGS_ICON_SIZE = 12
    RIBBON_PANEL_SPACER_WIDTH = 2
    RIBBON_PANEL_SPACER_HEIGHT = 10
    RIBBON_BAR_SHADOW_BLUR_RADIUS = 10
    RIBBON_BAR_SHADOW_COLOR_ALPHA = 80
    RIBBON_BAR_SHADOW_OFFSET_X = 0
    RIBBON_BAR_SHADOW_OFFSET_Y = 2
    RIBBON_BAR_HIDDEN_TAB_INDEX = 5
    # </editor-fold>


class RibbonSize(enum.IntEnum):
    """Pixel dimensions for Fluent-style ribbon components.

    This enum centralises every size constant used by the new
    RibbonCommandBar / RibbonGroup stack so that layout state
    calculations reference a single source of truth.

    Attributes:
        LARGE_BUTTON_ICON: Edge length of a large (3-row-span) button icon.
        SMALL_BUTTON_ICON: Edge length of a small (1-row) button icon.
        SETTINGS_ICON: Edge length of the dialog-box-launcher icon.
        COLLAPSED_GROUP_WIDTH: Fixed pixel width a RibbonGroup occupies
            when it is in the COLLAPSED layout state.
        GROUP_LABEL_HEIGHT: Height of the label row painted at the bottom
            of every RibbonGroup.
        TAB_BAR_HEIGHT: Fixed height of the RibbonTabBar header row.
        ACCENT_LINE_HEIGHT: Thickness of the active-tab underline accent.
        CONTEXTUAL_BANNER_HEIGHT: Height of the colored contextual-tabset
            title band painted above the tab handles.
        LAUNCHER_BUTTON_SIZE: Edge length of the dialog-box-launcher button.
        SPLIT_BUTTON_ARROW_WIDTH: Width of the dropdown-arrow half of a
            RibbonSplitButton.
    """

    # <editor-fold desc="Class attributes">
    LARGE_BUTTON_ICON = 32
    SMALL_BUTTON_ICON = 16
    SETTINGS_ICON = 12
    COLLAPSED_GROUP_WIDTH = 48
    GROUP_LABEL_HEIGHT = 18
    TAB_BAR_HEIGHT = 28
    ACCENT_LINE_HEIGHT = 2
    CONTEXTUAL_BANNER_HEIGHT = 14
    LAUNCHER_BUTTON_SIZE = 10
    SPLIT_BUTTON_ARROW_WIDTH = 14
    # </editor-fold>
