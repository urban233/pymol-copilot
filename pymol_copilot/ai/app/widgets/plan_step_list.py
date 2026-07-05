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

"""Numbered plan checklist widget."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtWidgets

import pymol_copilot.ai.app.models.session as session_module
import pymol_copilot.ai.app.widgets.plan_step_row as plan_step_row_module


class PlanStepList(QtWidgets.QWidget):
    """Vertical list of plan steps with optional evaluating placeholder."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the plan step list widget.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._rows: list[plan_step_row_module.PlanStepRow] = []
        self._steps: dict[int, session_module.PlanStep] = {}
        self._evaluating: QtWidgets.QLabel | None = None

    def clear_steps(self) -> None:
        """Remove all rows and placeholders."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = []
        self._steps = {}
        self._evaluating = None

    def show_evaluating(self) -> None:
        """Show a placeholder row while waiting for tool calls."""
        self.clear_steps()
        self._evaluating = QtWidgets.QLabel("Evaluating request…", self)
        self._evaluating.setObjectName("secondaryLabel")
        self._layout.addWidget(self._evaluating)

    def hide_evaluating(self) -> None:
        """Remove the evaluating placeholder if present."""
        if self._evaluating is not None:
            self._layout.removeWidget(self._evaluating)
            self._evaluating.deleteLater()
            self._evaluating = None

    def set_steps(self, steps: list[session_module.PlanStep]) -> None:
        """Replace the visible plan steps.

        Args:
          steps: Ordered plan steps to render.
        """
        self.clear_steps()
        if not steps:
            self.show_evaluating()
            return
        for step in steps:
            self.add_step(step)

    def add_step(self, step: session_module.PlanStep) -> None:
        """Append or update one plan step row.

        Args:
          step: Plan step to display.
        """
        self.hide_evaluating()
        self._steps[step.index] = step
        index = step.index - 1
        while len(self._rows) <= index:
            row = plan_step_row_module.PlanStepRow(self)
            self._rows.append(row)
            self._layout.addWidget(row)
        self._rows[index].set_step(step)

    def set_step_state(
        self,
        index: int,
        state: session_module.StepState,
    ) -> None:
        """Update the state of an existing step row.

        Args:
          index: One-based step index.
          state: New step state.
        """
        row_index = index - 1
        if index not in self._steps:
            return
        updated = session_module.PlanStep(
            index=self._steps[index].index,
            name=self._steps[index].name,
            arguments=self._steps[index].arguments,
            state=state,
            warning=self._steps[index].warning,
            display_label=self._steps[index].display_label,
            error=self._steps[index].error,
        )
        self._steps[index] = updated
        if row_index < len(self._rows):
            self._rows[row_index].set_step(updated)

    def set_step_error(self, index: int, message: str) -> None:
        """Attach an error message to a plan step row.

        Args:
          index: One-based step index.
          message: Error text to display under the row.
        """
        if index not in self._steps:
            return
        current = self._steps[index]
        updated = session_module.PlanStep(
            index=current.index,
            name=current.name,
            arguments=current.arguments,
            state=current.state,
            warning=current.warning,
            display_label=current.display_label,
            error=message,
        )
        self._steps[index] = updated
        row_index = index - 1
        if row_index < len(self._rows):
            self._rows[row_index].set_step(updated)
