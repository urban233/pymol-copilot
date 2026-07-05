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

"""Single numbered row in the plan checklist."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtWidgets

import pymol_copilot.ai.app.models.session as session_module


class PlanStepRow(QtWidgets.QFrame):
    """Visual row for one plan step."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build an empty plan step row.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("planStepRow")
        layout = QtWidgets.QHBoxLayout(self)

        self._index = QtWidgets.QLabel("", self)
        self._index.setObjectName("secondaryLabel")
        self._index.setFixedWidth(24)

        self._icon = QtWidgets.QLabel("○", self)
        self._icon.setFixedWidth(20)

        self._label = QtWidgets.QLabel("", self)
        self._label.setWordWrap(True)

        self._error = QtWidgets.QLabel("", self)
        self._error.setObjectName("stepError")
        self._error.setWordWrap(True)
        self._error.hide()

        layout.addWidget(self._index)
        layout.addWidget(self._icon)
        text_col = QtWidgets.QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.addWidget(self._label)
        text_col.addWidget(self._error)
        layout.addLayout(text_col, stretch=1)

    def set_step(self, step: session_module.PlanStep) -> None:
        """Render a plan step.

        Args:
          step: Plan step model to display.
        """
        self._index.setText(f"{step.index}.")
        label_text = step.display_label or step.compact_label()
        self._label.setText(label_text)
        if step.warning:
            self._label.setToolTip(step.warning)
        else:
            self._label.setToolTip("")

        if step.error:
            self._error.setText(step.error)
            self._error.show()
        else:
            self._error.clear()
            self._error.hide()

        if step.state == session_module.StepState.PENDING:
            self._icon.setText("○")
            self._label.setObjectName("stepPending")
        elif step.state == session_module.StepState.ACTIVE:
            self._icon.setText("▶")
            self._label.setObjectName("stepActive")
        elif step.state == session_module.StepState.DONE:
            self._icon.setText("✓")
            self._label.setObjectName("stepDone")
        else:
            self._icon.setText("—")
            self._label.setObjectName("stepPending")
