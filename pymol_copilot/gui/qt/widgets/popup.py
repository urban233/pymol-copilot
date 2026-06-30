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
"""Popup dialog blocks for frameless popup windows.

This module provides PopupBlock, a base QDialog configured with
the Qt.WindowType.Popup flag so it behaves like a dropdown; it closes
automatically when the user clicks outside it.

Subclass PopupBlock to build application-specific popup panels (for example,
an import menu, a scene list) while inheriting the shared popup behavior and
window title handling.
"""

from __future__ import annotations

from typing import Optional

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets

__docformat__: str = "google"


class PopupBlock(QtWidgets.QDialog):
    """A base popup dialog that closes when the user clicks outside it.

    Configures QDialog with Qt.WindowType.Popup so the window
    behaves as a transient dropdown rather than a normal modal or modeless
    dialog. Subclasses should call super().__init__ with the desired
    title, then add their own layout and widgets.

    Example:
        >>> popup = PopupBlock("Options")
        >>> popup.setLayout(my_layout)
        >>> popup.exec()
    """

    def __init__(
        self,
        window_title: str,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the popup dialog with a title.

        Args:
            window_title: The title string shown in the window title bar
                (may not be visible depending on the platform and window
                manager, but is useful for accessibility).
            parent: Optional parent widget. Defaults to None.
        """
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        self.setWindowTitle(window_title)
