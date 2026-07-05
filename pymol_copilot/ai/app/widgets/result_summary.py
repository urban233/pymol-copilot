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

"""Result summary card shown after inference completes."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets

import pymol_copilot.ai.app.models.session as session_module


class ResultSummary(QtWidgets.QFrame):
    """Done card with planned actions and footer controls."""

    retry_clicked = QtCore.pyqtSignal()
    back_clicked = QtCore.pyqtSignal()
    run_actions_clicked = QtCore.pyqtSignal()
    save_session_clicked = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the result summary widget.

        Args:
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("summaryCard")
        self._save_session_enabled = False
        layout = QtWidgets.QVBoxLayout(self)

        self._status = QtWidgets.QLabel("Done", self)
        self._status.setObjectName("statusDone")

        actions_title = QtWidgets.QLabel("Planned Actions", self)
        actions_title.setObjectName("sectionTitle")

        self._actions = QtWidgets.QLabel("", self)
        self._actions.setObjectName("summaryText")
        self._actions.setWordWrap(True)

        log_title = QtWidgets.QLabel("Execution Log", self)
        log_title.setObjectName("sectionTitle")

        self._execution_log = QtWidgets.QLabel("", self)
        self._execution_log.setObjectName("summaryText")
        self._execution_log.setWordWrap(True)

        self._summary = QtWidgets.QLabel("", self)
        self._summary.setObjectName("summaryText")
        self._summary.setWordWrap(True)

        footer = QtWidgets.QHBoxLayout()
        self._retry = QtWidgets.QPushButton("↻", self)
        self._retry.setObjectName("footerButton")
        self._retry.setToolTip("Retry")

        self._back = QtWidgets.QPushButton("↩", self)
        self._back.setObjectName("footerButton")
        self._back.setToolTip("Back to home")

        self._save_session = QtWidgets.QPushButton("Save Session", self)
        self._save_session.setObjectName("saveSessionButton")
        self._save_session.setToolTip("Save PyMOL session as .pse")
        self._save_session.hide()

        self._run_actions = QtWidgets.QPushButton("Run Actions", self)
        self._run_actions.setObjectName("runActionsButton")
        self._run_actions.setEnabled(False)

        footer.addWidget(self._retry)
        footer.addWidget(self._back)
        footer.addWidget(self._save_session)
        footer.addStretch(1)
        footer.addWidget(self._run_actions)

        layout.addWidget(self._status)
        layout.addWidget(actions_title)
        layout.addWidget(self._actions)
        layout.addWidget(log_title)
        layout.addWidget(self._execution_log)
        layout.addWidget(self._summary)
        layout.addLayout(footer)

        self._retry.clicked.connect(self.retry_clicked.emit)
        self._back.clicked.connect(self.back_clicked.emit)
        self._save_session.clicked.connect(self.save_session_clicked.emit)
        self._run_actions.clicked.connect(self.run_actions_clicked.emit)

        self._log_title = log_title
        self._log_title.hide()
        self._execution_log.hide()

    def set_save_session_enabled(self, enabled: bool) -> None:
        """Configure whether Save Session may appear after execution.

        Args:
          enabled: True when a PyMOL session is available for export.
        """
        self._save_session_enabled = enabled

    def set_session(self, session: session_module.Session) -> None:
        """Populate the summary from a completed session.

        Args:
          session: Completed session record.
        """
        if session.state == session_module.TaskState.EXECUTED:
            self._status.setText("Executed")
            self._status.setObjectName("statusDone")
        elif session.state == session_module.TaskState.EXECUTION_FAILED:
            self._status.setText("Execution failed")
            self._status.setObjectName("statusFailed")
        elif session.steps:
            self._status.setText("Done")
            self._status.setObjectName("statusDone")
        else:
            self._status.setText("No actions")
            self._status.setObjectName("statusDone")

        if session.steps:
            lines = [
                step.display_label or step.compact_label()
                for step in session.steps
            ]
            self._actions.setText("\n".join(lines))
        else:
            self._actions.setText(
                "No PyMOL tool calls were generated for this request."
            )

        if session.execution_log:
            self._log_title.show()
            self._execution_log.setText("\n".join(session.execution_log))
            self._execution_log.show()
        else:
            self._log_title.hide()
            self._execution_log.clear()
            self._execution_log.hide()

        prose = session.summary_prose
        if not prose and session.raw_assistant_output:
            raw = session.raw_assistant_output
            if "<tool_call>" not in raw:
                prose = raw
        self._summary.setText(prose)

        can_run = session.state in (
            session_module.TaskState.PLAN_READY,
            session_module.TaskState.EXECUTION_FAILED,
        )
        self._run_actions.setEnabled(can_run and bool(session.steps))
        self._run_actions.setVisible(can_run)

        can_save = (
            self._save_session_enabled
            and session.state == session_module.TaskState.EXECUTED
        )
        self._save_session.setVisible(can_save)
        self._save_session.setEnabled(can_save)

    def set_run_enabled(self, enabled: bool) -> None:
        """Enable or disable the Run Actions button.

        Args:
          enabled: Whether PyMOL execution is available.
        """
        if not self._run_actions.isVisible():
            return
        self._run_actions.setEnabled(enabled)
