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
#
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================

"""Task header with back navigation and stop control."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets


class TaskHeader(QtWidgets.QWidget):
    """Header row for the task plan view."""

    back_clicked = QtCore.pyqtSignal()
    stop_clicked = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the task header widget.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._back = QtWidgets.QPushButton("←", self)
        self._back.setObjectName("footerButton")
        self._back.setToolTip("Back to home")

        self._title = QtWidgets.QLabel("", self)
        self._title.setObjectName("taskTitle")

        self._stop = QtWidgets.QPushButton("Stop", self)
        self._stop.setObjectName("stopButton")

        layout.addWidget(self._back)
        layout.addWidget(self._title, stretch=1)
        layout.addWidget(self._stop)

        self._back.clicked.connect(self.back_clicked.emit)
        self._stop.clicked.connect(self.stop_clicked.emit)

    def set_title(self, title: str) -> None:
        """Update the displayed task title.

        Args:
          title: Short task title text.
        """
        self._title.setText(title)

    def set_stop_visible(self, visible: bool) -> None:
        """Show or hide the stop button.

        Args:
          visible: Whether the stop button is visible.
        """
        self._stop.setVisible(visible)
