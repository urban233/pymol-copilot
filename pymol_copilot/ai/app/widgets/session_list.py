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

"""Past session list shown on the prompt home view."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets

import pymol_copilot.ai.app.models.session as session_module


class SessionList(QtWidgets.QListWidget):
    """Displays prior in-memory task sessions."""

    session_selected = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the session list widget.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("sessionList")
        self.itemClicked.connect(self._on_item_clicked)
        self._sessions: dict[str, session_module.Session] = {}

    def set_sessions(self, sessions: list[session_module.Session]) -> None:
        """Refresh the list from session records.

        Args:
          sessions: Sessions to display, newest first.
        """
        self.clear()
        self._sessions = {session.id: session for session in sessions}
        for session in sessions:
            title = session_module.Session.title_from_prompt(session.prompt)
            item = QtWidgets.QListWidgetItem(title)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, session.id)
            self.addItem(item)

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """Emit the selected session identifier.

        Args:
          item: Clicked list item.
        """
        session_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(session_id, str):
            self.session_selected.emit(session_id)
