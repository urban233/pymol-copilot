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

"""Background QThread worker for verified PyMOL plan execution."""

from __future__ import annotations

import pymol_copilot.ai.app.models.session as session_module
import pymol_copilot.ai.execution.dispatcher as dispatcher_module
import pymol_copilot.ai.execution.pymol_session as pymol_session_module
import pymol_copilot.ai.execution.session_context as session_context_module
import pymol_copilot.ai.pymol_wrapper as pymol_wrapper_module
from pymol_copilot.gui.qt import QtCore


class ExecutionSignals(QtCore.QObject):
    """Signals emitted by the execution worker thread."""

    execution_started = QtCore.pyqtSignal()
    step_started = QtCore.pyqtSignal(int)
    step_finished = QtCore.pyqtSignal(int)
    execution_finished = QtCore.pyqtSignal(list)
    execution_failed = QtCore.pyqtSignal(int, str)


class ExecutionWorker(QtCore.QThread):
    """Runs plan steps on a dedicated thread with stop-on-first-error."""

    def __init__(
        self,
        session_provider: pymol_session_module.PyMOLSessionProvider,
        parent: QtCore.QObject | None = None,
    ) -> None:
        """Initialise the execution worker.

        Args:
          session_provider: Injectable PyMOL session provider.
          parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._session_provider = session_provider
        self._pending_steps: list[session_module.PlanStep] | None = None
        self._signals = ExecutionSignals()

    @property
    def signals(self) -> ExecutionSignals:
        """Return the worker signal bus.

        Returns:
          Signal object for UI connections.
        """
        return self._signals

    def submit(self, steps: list[session_module.PlanStep]) -> None:
        """Queue plan steps for the next worker run.

        Args:
          steps: Ordered plan steps to execute.
        """
        self._pending_steps = list(steps)
        if not self.isRunning():
            self.start()

    def request_stop(self) -> None:
        """Wait for the worker thread to finish."""
        self.wait(3000)

    def run(self) -> None:
        """Execute queued plan steps on the worker thread."""
        if self._pending_steps is None:
            return

        steps = self._pending_steps
        self._pending_steps = None
        log_lines: list[str] = []

        if not self._session_provider.is_ready():
            self._signals.execution_failed.emit(
                0,
                "PyMOL session is not ready for execution.",
            )
            return

        self._signals.execution_started.emit()
        cmd = self._session_provider.get_cmd()

        try:
            with session_context_module.use_cmd(cmd):
                for step in steps:
                    self._signals.step_started.emit(step.index)
                    try:
                        result = dispatcher_module.dispatch_step(
                            step.name,
                            step.arguments,
                        )
                    except pymol_wrapper_module.WrapperError as exc:
                        self._signals.execution_failed.emit(
                            step.index, str(exc)
                        )
                        return
                    except dispatcher_module.DispatcherError as exc:
                        self._signals.execution_failed.emit(
                            step.index, str(exc)
                        )
                        return

                    label = step.display_label or step.compact_label()
                    if result is None:
                        log_lines.append(f"Step {step.index}: {label}")
                    else:
                        log_lines.append(
                            f"Step {step.index}: {label} -> {result!r}",
                        )
                    self._signals.step_finished.emit(step.index)
        except Exception as exc:
            self._signals.execution_failed.emit(0, str(exc))
            return

        self._signals.execution_finished.emit(log_lines)
