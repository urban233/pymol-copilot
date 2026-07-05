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

"""Prompt recap card for the task plan view."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtWidgets


class PromptRecap(QtWidgets.QFrame):
    """Displays the original user request during plan execution."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the recap card widget.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("recapCard")
        layout = QtWidgets.QVBoxLayout(self)

        heading = QtWidgets.QLabel("Request", self)
        heading.setObjectName("secondaryLabel")

        self._text = QtWidgets.QLabel("", self)
        self._text.setObjectName("recapText")
        self._text.setWordWrap(True)

        layout.addWidget(heading)
        layout.addWidget(self._text)

    def set_text(self, text: str) -> None:
        """Update the recap body text.

        Args:
          text: Original user prompt.
        """
        self._text.setText(text)
