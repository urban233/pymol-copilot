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
"""Main content area widget.

Provides a wrapper for the central display area of the application window,
which can host visualizers or other main panels with an optional toolbar.
"""

from __future__ import annotations

from typing import Optional

from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.widgets import toolbar

__docformat__ = "google"


class MainContentAreaBlock(QtWidgets.QWidget):
    """A widget representing the main content area with an optional toolbar.

    This class manages a central content widget and provides access to an
    associated toolbar block.

    Attributes:
        _toolbar: The associated ToolbarBlock instance.
        _content: The current content widget.
        _main_content_frame: The QFrame containing the main content.
        _main_content_layout: The QVBoxLayout for the main content area.
    """

    def __init__(
        self,
        toolbar_block: "toolbar.ToolbarBlock",
        content: QtWidgets.QWidget,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the MainContentAreaBlock.

        Args:
            toolbar_block: The toolbar associated with this content area.
            content: The initial content widget to display.
            parent: The optional parent widget. Defaults to None.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._toolbar = toolbar_block
        self._content = content
        self._main_content_frame = QtWidgets.QFrame()
        self._main_content_layout = QtWidgets.QVBoxLayout(
            self._main_content_frame
        )
        # </editor-fold>
        self._init_widget()

    # <editor-fold desc="Public methods">
    def set_content_widget(self, widget: QtWidgets.QWidget) -> None:
        """Set the main content widget, replacing any existing content.

        Args:
            widget: The new content widget to display.
        """
        while self._main_content_layout.count():
            if (tmp_item := self._main_content_layout.takeAt(0)) is None:
                raise RuntimeError("tmp_item is None")
            if (tmp_widget := tmp_item.widget()) is None:
                raise RuntimeError("tmp_widget is None")
            tmp_widget.deleteLater()

        self._main_content_layout.addWidget(widget)

    @property
    def toolbar(self) -> "toolbar.ToolbarBlock":
        """Return the toolbar associated with this content area.

        Returns:
            The toolbar block.
        """
        return self._toolbar

    # </editor-fold>

    # <editor-fold desc="Public static methods">
    @staticmethod
    def create_with_toolbar(
        toolbar_block: "toolbar.ToolbarBlock",
        content: QtWidgets.QWidget,
    ) -> "MainContentAreaBlock":
        """Create a MainContentAreaBlock with a specific toolbar and content.

        Args:
            toolbar_block: The toolbar to associate with the content area.
            content: The initial content widget.

        Returns:
            A new instance of MainContentAreaBlock.
        """
        return MainContentAreaBlock(toolbar_block, content)

    @staticmethod
    def create_content_area(
        content: QtWidgets.QWidget,
    ) -> "MainContentAreaBlock":
        """Create a MainContentAreaBlock with a default (empty) toolbar.

        Args:
            content: The initial content widget.

        Returns:
            A new instance of MainContentAreaBlock.
        """
        tmp_toolbar = toolbar.ToolbarBlock([QtGui.QAction()])
        return MainContentAreaBlock(tmp_toolbar, content)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the layout and add the initial content widget."""
        self._main_content_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._main_content_layout.addWidget(self._content)
        self.setLayout(self._main_content_layout)

    # </editor-fold>
