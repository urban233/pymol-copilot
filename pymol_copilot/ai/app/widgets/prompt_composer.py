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

"""Auto-expanding prompt composer for the home view."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets


class PromptComposer(QtWidgets.QFrame):
    """Large Junie-style prompt card with integrated toolbar."""

    submitted = QtCore.pyqtSignal(str, str, bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the home prompt composer widget.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("promptCard")
        self._min_height = 80
        self._max_height = 200
        self._build_ui()
        self._wire_events()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable user input.

        Args:
          enabled: Whether the composer accepts input.
        """
        self._input.setEnabled(enabled)
        self._submit.setEnabled(
            enabled and bool(self._input.toPlainText().strip())
        )
        self._attach.setEnabled(enabled)
        self._visualize_btn.setEnabled(enabled)
        self._ask_btn.setEnabled(enabled)
        self._dry_run.setEnabled(enabled)

    def clear_input(self) -> None:
        """Clear the prompt text field."""
        self._input.clear()
        self._resize_input()

    def _build_ui(self) -> None:
        """Construct child widgets."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._input = QtWidgets.QTextEdit(self)
        self._input.setObjectName("promptInput")
        self._input.setPlaceholderText(
            "Describe the PyMOL visualization you want…"
        )
        self._input.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self._input)

        toolbar = QtWidgets.QHBoxLayout()
        self._attach = QtWidgets.QPushButton("+", self)
        self._attach.setEnabled(False)
        self._attach.setToolTip("Attachments (Phase 4)")

        self._visualize_btn = QtWidgets.QPushButton("Visualize", self)
        self._visualize_btn.setObjectName("modeButton")
        self._visualize_btn.setCheckable(True)
        self._visualize_btn.setChecked(True)

        self._ask_btn = QtWidgets.QPushButton("Ask", self)
        self._ask_btn.setObjectName("modeButton")
        self._ask_btn.setCheckable(True)

        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.addButton(self._visualize_btn)
        mode_group.addButton(self._ask_btn)

        self._dry_run = QtWidgets.QCheckBox("Dry Run", self)

        self._submit = QtWidgets.QPushButton("→", self)
        self._submit.setObjectName("submitButton")
        self._submit.setEnabled(False)

        toolbar.addWidget(self._attach)
        toolbar.addWidget(self._visualize_btn)
        toolbar.addWidget(self._ask_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self._dry_run)
        toolbar.addWidget(self._submit)
        layout.addLayout(toolbar)

    def _wire_events(self) -> None:
        """Connect internal signals."""
        self._input.textChanged.connect(self._on_text_changed)
        self._input.installEventFilter(self)
        self._submit.clicked.connect(self._emit_submit)

    def _on_text_changed(self) -> None:
        """Resize the input and toggle submit availability."""
        self._resize_input()
        has_text = bool(self._input.toPlainText().strip())
        self._submit.setEnabled(self._input.isEnabled() and has_text)

    def _resize_input(self) -> None:
        """Adjust input height based on document layout."""
        doc = self._input.document()
        layout = doc.documentLayout()
        if layout is None:
            return
        height = int(layout.documentSize().height()) + 16
        height = max(self._min_height, min(self._max_height, height))
        self._input.setFixedHeight(height)

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
        """Emit the submitted signal with mode and dry-run flag."""
        text = self._input.toPlainText().strip()
        if not text:
            return
        mode = "ask" if self._ask_btn.isChecked() else "visualize"
        self.submitted.emit(text, mode, self._dry_run.isChecked())
