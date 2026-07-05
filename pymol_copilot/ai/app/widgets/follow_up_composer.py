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

"""Compact follow-up composer for plan and result views."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets


class FollowUpComposer(QtWidgets.QFrame):
    """Bottom follow-up input bar shown during task execution."""

    submitted = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the follow-up composer widget.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("promptCard")
        self._build_ui()
        self._wire_events()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable follow-up input.

        Args:
          enabled: Whether input is accepted.
        """
        self._input.setEnabled(enabled)
        self._submit.setEnabled(
            enabled and bool(self._input.toPlainText().strip())
        )

    def clear_input(self) -> None:
        """Clear the follow-up text field."""
        self._input.clear()

    def _build_ui(self) -> None:
        """Construct child widgets."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        row = QtWidgets.QHBoxLayout()
        self._input = QtWidgets.QTextEdit(self)
        self._input.setObjectName("followUpInput")
        self._input.setPlaceholderText("Write follow up here")
        self._input.setMaximumHeight(72)

        self._submit = QtWidgets.QPushButton("→", self)
        self._submit.setObjectName("submitButton")
        self._submit.setEnabled(False)

        row.addWidget(self._input, stretch=1)
        row.addWidget(self._submit)
        layout.addLayout(row)

    def _wire_events(self) -> None:
        """Connect internal signals."""
        self._input.textChanged.connect(self._on_text_changed)
        self._input.installEventFilter(self)
        self._submit.clicked.connect(self._emit_submit)

    def _on_text_changed(self) -> None:
        """Toggle submit availability."""
        has_text = bool(self._input.toPlainText().strip())
        self._submit.setEnabled(self._input.isEnabled() and has_text)

    def eventFilter(
        self,
        watched: QtCore.QObject,
        event: QtCore.QEvent,
    ) -> bool:
        """Submit on Enter without Shift.

        Args:
          watched: Event target object.
          event: Qt event instance.

        Returns:
          True if the event was consumed.
        """
        if (
            watched is self._input
            and event.type() == QtCore.QEvent.Type.KeyPress
        ):
            if isinstance(event, QtGui.QKeyEvent):
                if (
                    event.key()
                    in (
                        QtCore.Qt.Key.Key_Return,
                        QtCore.Qt.Key.Key_Enter,
                    )
                    and event.modifiers()
                    != QtCore.Qt.KeyboardModifier.ShiftModifier
                ):
                    if self._submit.isEnabled():
                        self._emit_submit()
                    return True
        return super().eventFilter(watched, event)

    def _emit_submit(self) -> None:
        """Emit the follow-up submitted signal."""
        text = self._input.toPlainText().strip()
        if not text:
            return
        self.submitted.emit(text)
        self.clear_input()
