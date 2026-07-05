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

"""Verification bar with Cancel and Run Actions controls."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets


class VerificationBar(QtWidgets.QFrame):
    """Pinned verification controls shown before PyMOL mutation."""

    cancel_clicked = QtCore.pyqtSignal()
    run_actions_clicked = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the verification bar widget.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("verificationBar")
        layout = QtWidgets.QHBoxLayout(self)

        self._cancel = QtWidgets.QPushButton("✕ Cancel", self)
        self._cancel.setObjectName("cancelButton")

        self._run = QtWidgets.QPushButton("✔ Run Actions", self)
        self._run.setObjectName("runActionsButton")

        layout.addWidget(self._cancel)
        layout.addStretch(1)
        layout.addWidget(self._run)

        self._cancel.clicked.connect(self.cancel_clicked.emit)
        self._run.clicked.connect(self.run_actions_clicked.emit)
        self.hide()

    def set_run_enabled(self, enabled: bool) -> None:
        """Enable or disable the Run Actions button.

        Args:
          enabled: Whether execution is available.
        """
        self._run.setEnabled(enabled)

    def set_busy(self, busy: bool) -> None:
        """Disable both buttons while execution is in progress.

        Args:
          busy: True during execution.
        """
        self._cancel.setEnabled(not busy)
        self._run.setEnabled(not busy)
