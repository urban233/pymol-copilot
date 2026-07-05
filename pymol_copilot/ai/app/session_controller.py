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

"""State machine orchestrating views, sessions, and inference."""

from __future__ import annotations

import dataclasses
import pathlib

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets

import pymol_copilot.ai.app.models.plan_parser as plan_parser_module
import pymol_copilot.ai.app.models.session as session_module
import pymol_copilot.ai.app.widgets.follow_up_composer as follow_up_composer_module
import pymol_copilot.ai.app.widgets.plan_step_list as plan_step_list_module
import pymol_copilot.ai.app.widgets.prompt_composer as prompt_composer_module
import pymol_copilot.ai.app.widgets.prompt_recap as prompt_recap_module
import pymol_copilot.ai.app.widgets.result_summary as result_summary_module
import pymol_copilot.ai.app.widgets.session_list as session_list_module
import pymol_copilot.ai.app.widgets.task_header as task_header_module
import pymol_copilot.ai.app.widgets.verification_bar as verification_bar_module
import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.backend.inference_worker as inference_worker_module
import pymol_copilot.ai.execution.execution_worker as execution_worker_module
import pymol_copilot.ai.execution.pymol_session as pymol_session_module
import pymol_copilot.ai.execution.session_context as session_context_module
import pymol_copilot.ai.explanations as explanations_module
import pymol_copilot.ai.pymol_wrapper as pymol_wrapper_module


@dataclasses.dataclass
class ViewRefs:
    """Handles to widgets owned by the main window."""

    stack: QtWidgets.QStackedWidget
    prompt_composer: prompt_composer_module.PromptComposer
    session_list: session_list_module.SessionList
    task_header: task_header_module.TaskHeader
    prompt_recap: prompt_recap_module.PromptRecap
    plan_steps: plan_step_list_module.PlanStepList
    verification_bar: verification_bar_module.VerificationBar
    follow_up: follow_up_composer_module.FollowUpComposer
    result_summary: result_summary_module.ResultSummary
    cancel_banner: QtWidgets.QLabel


class SessionController(QtCore.QObject):
    """Connects UI events to the inference worker and view stack."""

    VIEW_HOME = 0
    VIEW_PLAN = 1
    VIEW_RESULT = 2

    def __init__(
        self,
        config: config_module.InferenceConfig,
        views: ViewRefs,
        pymol_session: pymol_session_module.PyMOLSessionProvider | None = None,
        execution_enabled: bool = False,
        parent: QtWidgets.QObject | None = None,
    ) -> None:
        """Initialise the session controller.

        Args:
          config: Inference configuration.
          views: Main-window widget references.
          pymol_session: Optional injectable PyMOL session provider.
          execution_enabled: Whether Run Actions may dispatch to PyMOL.
          parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._config = config
        self._views = views
        self._sessions: list[session_module.Session] = []
        self._current: session_module.Session | None = None
        self._parser = plan_parser_module.PlanParser()
        self._worker = inference_worker_module.InferenceWorker(config, self)
        self._pymol_session = pymol_session
        self._execution_enabled = execution_enabled
        self._execution_worker: (
            execution_worker_module.ExecutionWorker | None
        ) = None
        if pymol_session is not None:
            self._execution_worker = execution_worker_module.ExecutionWorker(
                pymol_session,
                self,
            )
        self._wire_ui()
        self._wire_worker()
        self._views.result_summary.set_save_session_enabled(
            self._execution_enabled and self._pymol_session is not None
        )
        if self._execution_worker is not None:
            self._wire_execution_worker()

    def shutdown(self) -> None:
        """Stop worker threads and unload backends."""
        self._worker.request_stop()
        self._worker.unload_backend()
        if self._execution_worker is not None:
            self._execution_worker.request_stop()
        if self._pymol_session is not None:
            self._pymol_session.shutdown()

    def update_model_path(self, path: str) -> None:
        """Update model path and reload backend on next run.

        Args:
          path: Filesystem path to a GGUF model file.
        """
        self._config = dataclasses.replace(
            self._config,
            model_path=pathlib.Path(path),
            prompt_family=config_module.detect_prompt_family(
                pathlib.Path(path)
            ),
            mock=False,
        )
        self._worker.update_config(self._config)

    def _wire_ui(self) -> None:
        """Connect view signals."""
        views = self._views
        views.prompt_composer.submitted.connect(self._on_home_submit)
        views.session_list.session_selected.connect(self._on_session_selected)
        views.task_header.back_clicked.connect(self._go_home)
        views.task_header.stop_clicked.connect(self._on_stop)
        views.follow_up.submitted.connect(self._on_follow_up)
        views.result_summary.retry_clicked.connect(self._on_retry)
        views.result_summary.back_clicked.connect(self._go_home)
        views.result_summary.run_actions_clicked.connect(self._on_run_actions)
        views.result_summary.save_session_clicked.connect(self._on_save_session)
        views.verification_bar.cancel_clicked.connect(
            self._on_verification_cancel
        )
        views.verification_bar.run_actions_clicked.connect(self._on_run_actions)

    def _wire_worker(self) -> None:
        """Connect inference worker signals."""
        signals = self._worker.signals
        signals.generation_started.connect(self._on_generation_started)
        signals.token_received.connect(self._on_token_received)
        signals.generation_finished.connect(self._on_generation_finished)
        signals.generation_error.connect(self._on_generation_error)
        signals.generation_cancelled.connect(self._on_generation_cancelled)

    def _wire_execution_worker(self) -> None:
        """Connect execution worker signals."""
        if self._execution_worker is None:
            return
        signals = self._execution_worker.signals
        signals.execution_started.connect(self._on_execution_started)
        signals.step_started.connect(self._on_execution_step_started)
        signals.step_finished.connect(self._on_execution_step_finished)
        signals.execution_finished.connect(self._on_execution_finished)
        signals.execution_failed.connect(self._on_execution_failed)

    def _on_home_submit(
        self,
        prompt: str,
        mode: str,
        dry_run: bool,
    ) -> None:
        """Start a new task from the home prompt composer.

        Args:
          prompt: User natural-language request.
          mode: Selected interaction mode.
          dry_run: Whether dry-run mode is enabled.
        """
        self._worker.conversation.clear()
        self._config = dataclasses.replace(self._config, dry_run=dry_run)
        self._worker.update_config(self._config)
        session = session_module.Session(
            prompt=prompt,
            mode=mode,
            dry_run=dry_run,
            state=session_module.TaskState.GENERATING,
        )
        self._begin_session(session)
        self._worker.submit(prompt)

    def _on_follow_up(self, prompt: str) -> None:
        """Submit a follow-up prompt in an existing session.

        Args:
          prompt: Follow-up user text.
        """
        if self._current is None:
            return
        self._current.state = session_module.TaskState.GENERATING
        self._views.cancel_banner.hide()
        self._views.verification_bar.hide()
        self._views.stack.setCurrentIndex(self.VIEW_PLAN)
        self._prepare_plan_view(self._current)
        self._worker.submit(prompt)

    def _on_retry(self) -> None:
        """Re-run inference for the current session prompt."""
        if self._current is None:
            return
        self._worker.conversation.clear()
        self._current.state = session_module.TaskState.GENERATING
        self._views.stack.setCurrentIndex(self.VIEW_PLAN)
        self._prepare_plan_view(self._current)
        self._worker.submit(self._current.prompt)

    def _on_stop(self) -> None:
        """Cancel the active generation."""
        self._worker.request_cancel()

    def _go_home(self) -> None:
        """Return to the prompt home view."""
        if (
            self._current is not None
            and self._current.state == session_module.TaskState.GENERATING
        ):
            reply = QtWidgets.QMessageBox.question(
                self._views.stack,
                "Stop task?",
                "Generation is still running. Stop and go back?",
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            self._worker.request_cancel()
        self._views.stack.setCurrentIndex(self.VIEW_HOME)
        self._refresh_session_list()

    def _on_session_selected(self, session_id: str) -> None:
        """Open a past session result summary.

        Args:
          session_id: Selected session identifier.
        """
        session = next(
            (item for item in self._sessions if item.id == session_id),
            None,
        )
        if session is None:
            return
        self._current = session
        self._views.result_summary.set_session(session)
        self._views.stack.setCurrentIndex(self.VIEW_RESULT)

    def _begin_session(self, session: session_module.Session) -> None:
        """Switch UI to plan view for a new session.

        Args:
          session: Newly created session record.
        """
        self._current = session
        self._sessions.insert(0, session)
        self._parser.reset()
        self._views.stack.setCurrentIndex(self.VIEW_PLAN)
        self._prepare_plan_view(session)
        self._views.prompt_composer.clear_input()
        self._views.prompt_composer.set_enabled(True)
        self._views.follow_up.set_enabled(False)

    def _prepare_plan_view(self, session: session_module.Session) -> None:
        """Populate plan view widgets for a session.

        Args:
          session: Active session record.
        """
        title = session_module.Session.title_from_prompt(session.prompt)
        self._views.task_header.set_title(title)
        self._views.task_header.set_stop_visible(True)
        self._views.prompt_recap.set_text(session.prompt)
        self._views.plan_steps.show_evaluating()
        self._views.cancel_banner.hide()
        self._views.verification_bar.hide()
        self._update_verification_bar()

    def _update_verification_bar(self) -> None:
        """Show or hide verification controls based on session state."""
        bar = self._views.verification_bar
        if self._current is None:
            bar.hide()
            return

        show_bar = (
            self._current.state
            in (
                session_module.TaskState.PLAN_READY,
                session_module.TaskState.EXECUTION_FAILED,
            )
            and len(self._current.steps) > 0
        )
        if show_bar:
            bar.set_busy(False)
            bar.set_run_enabled(self._execution_enabled)
            bar.show()
        else:
            bar.hide()

    def _on_generation_started(self) -> None:
        """Handle generation start."""
        if self._current is not None:
            self._current.state = session_module.TaskState.GENERATING
        self._parser.reset()
        self._views.plan_steps.show_evaluating()
        self._views.verification_bar.hide()
        self._views.prompt_composer.set_enabled(False)
        self._views.follow_up.set_enabled(False)
        self._views.task_header.set_stop_visible(True)

    def _on_token_received(self, delta: str) -> None:
        """Update plan steps while tokens stream in.

        Args:
          delta: Incremental assistant output fragment.
        """
        if self._current is None:
            return
        self._current.raw_assistant_output += delta
        new_steps = self._parser.feed(delta)
        for step in new_steps:
            self._views.plan_steps.add_step(step)
            if step.index > 1:
                self._views.plan_steps.set_step_state(
                    step.index - 1,
                    session_module.StepState.DONE,
                )

    def _on_generation_finished(self, text: str) -> None:
        """Finalize session and enter verification or result view.

        Args:
          text: Full assistant output text.
        """
        if self._current is None:
            return

        steps, prose = self._parser.finalize()
        explained = explanations_module.explain_plan(steps)
        self._current.steps = explained
        self._current.summary_prose = prose
        self._current.raw_assistant_output = text
        self._current.execution_log = []

        self._views.task_header.set_stop_visible(False)
        self._views.prompt_composer.set_enabled(True)
        self._views.follow_up.set_enabled(True)

        if not explained:
            self._current.state = session_module.TaskState.DONE
            self._views.result_summary.set_session(self._current)
            self._views.stack.setCurrentIndex(self.VIEW_RESULT)
            self._refresh_session_list()
            return

        pending_steps = [
            session_module.PlanStep(
                index=step.index,
                name=step.name,
                arguments=step.arguments,
                state=session_module.StepState.PENDING,
                warning=step.warning,
                display_label=step.display_label,
                error="",
            )
            for step in explained
        ]
        self._current.steps = pending_steps
        self._current.state = session_module.TaskState.PLAN_READY
        self._views.plan_steps.set_steps(pending_steps)
        self._update_verification_bar()
        self._views.stack.setCurrentIndex(self.VIEW_PLAN)
        self._refresh_session_list()

    def _on_verification_cancel(self) -> None:
        """Cancel the plan without mutating PyMOL."""
        if self._current is None:
            return
        self._current.state = session_module.TaskState.CANCELLED
        self._views.cancel_banner.setText(
            "Plan cancelled. No PyMOL actions were run."
        )
        self._views.cancel_banner.show()
        self._views.verification_bar.hide()
        self._views.stack.setCurrentIndex(self.VIEW_HOME)
        self._refresh_session_list()

    def _on_run_actions(self) -> None:
        """Dispatch the verified plan through the execution worker."""
        if self._current is None or self._execution_worker is None:
            return
        if not self._execution_enabled:
            self._views.cancel_banner.setText(
                "Execution disabled. Launch with --enable-execution.",
            )
            self._views.cancel_banner.show()
            return
        if self._current.state not in (
            session_module.TaskState.PLAN_READY,
            session_module.TaskState.EXECUTION_FAILED,
        ):
            return

        self._current.state = session_module.TaskState.EXECUTING
        self._current.execution_log = []
        for step in self._current.steps:
            step.error = ""
        self._views.verification_bar.set_busy(True)
        self._views.cancel_banner.hide()
        self._views.prompt_composer.set_enabled(False)
        self._views.follow_up.set_enabled(False)
        self._execution_worker.submit(self._current.steps)

    def _on_save_session(self) -> None:
        """Save the active PyMOL session to a user-selected .pse file."""
        if self._current is None:
            return
        if self._current.state != session_module.TaskState.EXECUTED:
            return
        if self._pymol_session is None or not self._pymol_session.is_ready():
            self._views.cancel_banner.setText(
                "PyMOL session not available. Launch with --enable-execution.",
            )
            self._views.cancel_banner.show()
            return

        default_name = session_module.Session.default_pse_filename(
            self._current.prompt,
        )
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self._views.stack,
            "Save PyMOL session",
            default_name,
            "PyMOL session (*.pse)",
        )
        if not path:
            return

        save_path = pathlib.Path(path)
        if save_path.suffix.lower() != ".pse":
            save_path = save_path.with_suffix(".pse")

        try:
            with session_context_module.use_cmd(self._pymol_session.get_cmd()):
                pymol_wrapper_module.save_session(str(save_path))
        except pymol_wrapper_module.WrapperError as exc:
            self._views.cancel_banner.setText(str(exc))
            self._views.cancel_banner.show()
            return

        saved_text = f"Saved session to {save_path}"
        self._current.saved_session_path = str(save_path)
        if saved_text not in self._current.execution_log:
            self._current.execution_log.append(saved_text)
        self._views.cancel_banner.hide()
        self._views.result_summary.set_session(self._current)

    def _on_execution_started(self) -> None:
        """Handle execution worker start."""
        if self._current is not None:
            self._current.state = session_module.TaskState.EXECUTING

    def _on_execution_step_started(self, index: int) -> None:
        """Mark a plan step active during execution.

        Args:
          index: One-based step index.
        """
        self._views.plan_steps.set_step_state(
            index,
            session_module.StepState.ACTIVE,
        )

    def _on_execution_step_finished(self, index: int) -> None:
        """Mark a plan step complete during execution.

        Args:
          index: One-based step index.
        """
        self._views.plan_steps.set_step_state(
            index,
            session_module.StepState.DONE,
        )

    def _on_execution_finished(self, log_lines: list) -> None:
        """Switch to the executed result summary.

        Args:
          log_lines: Per-step execution log lines.
        """
        if self._current is None:
            return
        self._current.state = session_module.TaskState.EXECUTED
        self._current.execution_log = list(log_lines)
        self._views.verification_bar.hide()
        self._views.prompt_composer.set_enabled(True)
        self._views.follow_up.set_enabled(True)
        self._views.result_summary.set_session(self._current)
        self._views.stack.setCurrentIndex(self.VIEW_RESULT)
        self._refresh_session_list()

    def _on_execution_failed(self, step_index: int, message: str) -> None:
        """Keep the plan view open and highlight the failed step.

        Args:
          step_index: One-based index of the failed step.
          message: Error description from the wrapper or dispatcher.
        """
        if self._current is None:
            return
        self._current.state = session_module.TaskState.EXECUTION_FAILED
        if step_index > 0:
            self._views.plan_steps.set_step_state(
                step_index,
                session_module.StepState.ACTIVE,
            )
            self._views.plan_steps.set_step_error(step_index, message)
            if step_index <= len(self._current.steps):
                self._current.steps[step_index - 1].error = message
        self._views.cancel_banner.setText(f"Execution failed: {message}")
        self._views.cancel_banner.show()
        self._views.prompt_composer.set_enabled(True)
        self._views.follow_up.set_enabled(True)
        self._update_verification_bar()

    def _on_generation_error(self, message: str) -> None:
        """Display an inference error banner.

        Args:
          message: Error description text.
        """
        self._views.cancel_banner.setText(f"Error: {message}")
        self._views.cancel_banner.show()
        self._views.task_header.set_stop_visible(False)
        self._views.prompt_composer.set_enabled(True)
        self._views.follow_up.set_enabled(True)
        if self._current is not None:
            self._current.state = session_module.TaskState.CANCELLED

    def _on_generation_cancelled(self) -> None:
        """Handle user-initiated cancellation."""
        self._views.cancel_banner.setText("Generation cancelled.")
        self._views.cancel_banner.show()
        self._views.task_header.set_stop_visible(False)
        self._views.prompt_composer.set_enabled(True)
        self._views.follow_up.set_enabled(True)
        if self._current is not None:
            self._current.state = session_module.TaskState.CANCELLED

    def _refresh_session_list(self) -> None:
        """Refresh the home session history list."""
        self._views.session_list.set_sessions(self._sessions)
