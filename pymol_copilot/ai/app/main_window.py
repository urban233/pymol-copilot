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

"""Main window hosting the Junie-style task workflow views."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets

import pymol_copilot.ai.app.session_controller as session_controller_module
import pymol_copilot.ai.app.widgets.follow_up_composer as follow_up_composer_module
import pymol_copilot.ai.app.widgets.plan_step_list as plan_step_list_module
import pymol_copilot.ai.app.widgets.prompt_composer as prompt_composer_module
import pymol_copilot.ai.app.widgets.prompt_recap as prompt_recap_module
import pymol_copilot.ai.app.widgets.result_summary as result_summary_module
import pymol_copilot.ai.app.widgets.session_list as session_list_module
import pymol_copilot.ai.app.widgets.task_header as task_header_module
import pymol_copilot.ai.app.widgets.verification_bar as verification_bar_module
import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.execution.pymol_session as pymol_session_module


class MainWindow(QtWidgets.QMainWindow):
    """Top-level window for the experimental AI assistant."""

    def __init__(
        self,
        config: config_module.InferenceConfig,
        pymol_session: pymol_session_module.PyMOLSessionProvider | None = None,
        execution_enabled: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Build the main window and session controller.

        Args:
          config: Inference configuration.
          pymol_session: Optional injectable PyMOL session provider.
          execution_enabled: Whether Run Actions may dispatch to PyMOL.
          parent: Optional parent widget.
        """
        super().__init__(parent)
        self._config = config
        self._pymol_session = pymol_session
        self._execution_enabled = execution_enabled
        self.setWindowTitle("cBioMOL AI Assistant")
        self.setMinimumSize(720, 560)
        self._build_ui()
        self._build_menu()
        self._controller = session_controller_module.SessionController(
            config,
            self._view_refs,
            pymol_session=pymol_session,
            execution_enabled=execution_enabled,
            parent=self,
        )

    @property
    def controller(self) -> session_controller_module.SessionController:
        """Return the session controller instance.

        Returns:
          Active session controller.
        """
        return self._controller

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Shut down the inference worker before closing.

        Args:
          event: Qt close event.
        """
        self._controller.shutdown()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        """Construct the stacked workflow views."""
        central = QtWidgets.QWidget(self)
        central.setObjectName("contentColumn")
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)

        self._stack = QtWidgets.QStackedWidget(central)

        home = self._build_home_view()
        plan = self._build_plan_view()
        result = self._build_result_view()

        self._stack.addWidget(home)
        self._stack.addWidget(plan)
        self._stack.addWidget(result)

        root.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self._view_refs = session_controller_module.ViewRefs(
            stack=self._stack,
            prompt_composer=self._prompt_composer,
            session_list=self._session_list,
            task_header=self._task_header,
            prompt_recap=self._prompt_recap,
            plan_steps=self._plan_steps,
            verification_bar=self._verification_bar,
            follow_up=self._follow_up,
            result_summary=self._result_summary,
            cancel_banner=self._cancel_banner,
        )

    def _build_home_view(self) -> QtWidgets.QWidget:
        """Create the prompt home page.

        Returns:
          Home view widget.
        """
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)

        self._session_list = session_list_module.SessionList(page)
        self._session_list.setMaximumWidth(220)

        center = QtWidgets.QWidget(page)
        center_layout = QtWidgets.QVBoxLayout(center)
        center_layout.addStretch(1)

        self._prompt_composer = prompt_composer_module.PromptComposer(center)
        self._prompt_composer.setMaximumWidth(680)
        composer_row = QtWidgets.QHBoxLayout()
        composer_row.addStretch(1)
        composer_row.addWidget(self._prompt_composer, stretch=0)
        composer_row.addStretch(1)
        center_layout.addLayout(composer_row)
        center_layout.addStretch(2)

        layout.addWidget(self._session_list)
        layout.addWidget(center, stretch=1)
        return page

    def _build_plan_view(self) -> QtWidgets.QWidget:
        """Create the task plan and progress page.

        Returns:
          Plan view widget.
        """
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)

        self._task_header = task_header_module.TaskHeader(page)
        self._prompt_recap = prompt_recap_module.PromptRecap(page)

        plan_title = QtWidgets.QLabel("Plan", page)
        plan_title.setObjectName("sectionTitle")

        self._plan_steps = plan_step_list_module.PlanStepList(page)
        self._cancel_banner = QtWidgets.QLabel("", page)
        self._cancel_banner.setObjectName("cancelBanner")
        self._cancel_banner.hide()

        scroll = QtWidgets.QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.addWidget(self._plan_steps)
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)

        self._follow_up = follow_up_composer_module.FollowUpComposer(page)
        self._verification_bar = verification_bar_module.VerificationBar(page)

        layout.addWidget(self._task_header)
        layout.addWidget(self._prompt_recap)
        layout.addWidget(plan_title)
        layout.addWidget(self._cancel_banner)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(self._verification_bar)
        layout.addWidget(self._follow_up)
        return page

    def _build_result_view(self) -> QtWidgets.QWidget:
        """Create the result summary page.

        Returns:
          Result view widget.
        """
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addStretch(1)

        self._result_summary = result_summary_module.ResultSummary(page)
        self._result_summary.setMaximumWidth(680)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._result_summary)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)
        return page

    def _build_menu(self) -> None:
        """Create application menus."""
        file_menu = self.menuBar().addMenu("File")
        quit_action = QtGui.QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        settings_menu = self.menuBar().addMenu("Settings")
        model_action = QtGui.QAction("Model Path…", self)
        model_action.triggered.connect(self._choose_model_path)
        settings_menu.addAction(model_action)

    def _choose_model_path(self) -> None:
        """Open a file dialog to select a GGUF model."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select GGUF model",
            str(self._config.model_path.parent),
            "GGUF models (*.gguf)",
        )
        if path:
            self._controller.update_model_path(path)
