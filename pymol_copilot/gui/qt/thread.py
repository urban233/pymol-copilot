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
# Martin Urban
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================
#
"""PyQt6 Background Job API for non-blocking task execution.

Provides a decorator and a job container to safely offload
heavy functions to background threads without freezing the UI.
"""

from __future__ import annotations

import functools
import logging
import traceback

from typing import Any
from typing import Callable
from typing import ParamSpec

from pymol_copilot.gui.qt import QtCore

_ParameterSpecification = ParamSpec("_ParameterSpecification")

__docformat__ = "google"

LOGGER = logging.getLogger(__name__)


class WorkerSignals(QtCore.QObject):
    """Defines the signals available from a running background worker.

    Attributes:
        success: Emitted when the task completes successfully.
        error: Emitted when the task raises an exception.
        finished: Emitted unconditionally when the task finishes.
        progress: Emitted to report task progress percentage and message.
    """

    # <editor-fold desc="Class attributes">
    success = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(Exception, str)
    finished = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int, str)
    # </editor-fold>


class Worker(QtCore.QRunnable):
    """Executes a target function in a background thread.

    Catches all exceptions to prevent silent thread death and safely
    emits signals back to the main UI thread.

    Attributes:
        signals: The WorkerSignals instance for this worker.
    """

    def __init__(
        self,
        target_function: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the Worker.

        Args:
            target_function: The function to execute in the background.
            *args: Positional arguments for the target function.
            **kwargs: Keyword arguments for the target function.
        """
        super().__init__()
        # <editor-fold desc="Instance attributes">
        self.setAutoDelete(True)
        self._target_function = target_function
        self._args = args
        self._kwargs = kwargs
        self.signals = WorkerSignals()
        # </editor-fold>

    # <editor-fold desc="Public methods">
    def run(self) -> None:
        """Execute the target function and emit corresponding signals."""
        try:
            # Provide a progress callback to the function.
            def progress_callback(percentage: int, message: str) -> None:
                """Emit progress percentage and message to the UI thread.

                Args:
                    percentage: The current progress percentage.
                    message: An accompanying status message.
                """
                self.signals.progress.emit(percentage, message)

            self._kwargs["progress_callback"] = progress_callback

            tmp_result = self._target_function(*self._args, **self._kwargs)
            self.signals.success.emit(tmp_result)
        except Exception as tmp_exception:
            LOGGER.exception("Background task failed.")
            tmp_traceback_string = traceback.format_exc()
            self.signals.error.emit(tmp_exception, tmp_traceback_string)
        finally:
            self.signals.finished.emit()

    # </editor-fold>


class BackgroundJob:
    """Chainable job container for configuring and starting tasks.

    Allows the developer to attach callbacks to the worker's signals before
    submitting it to the thread pool.
    """

    def __init__(self, worker_obj: Worker) -> None:
        """Initialize the BackgroundJob.

        Args:
            worker_obj: The Worker instance to control.
        """
        # <editor-fold desc="Instance attributes">
        self._worker = worker_obj
        # </editor-fold>

    # <editor-fold desc="Public methods">
    def on_success(self, callback: Callable[[Any], None]) -> "BackgroundJob":
        """Attach a callback for successful completion.

        Args:
            callback: The function to call with the result.

        Returns:
            The BackgroundJob instance for chaining.
        """
        self._worker.signals.success.connect(callback)
        return self

    def on_error(
        self,
        callback: Callable[[Exception, str], None],
    ) -> "BackgroundJob":
        """Attach a callback for error handling.

        Args:
            callback: The function to call with the exception and traceback.

        Returns:
            The BackgroundJob instance for chaining.
        """
        self._worker.signals.error.connect(callback)
        return self

    def on_finally(self, callback: Callable[[], None]) -> "BackgroundJob":
        """Attach a callback for unconditional completion.

        Args:
            callback: The function to call when the task finishes.

        Returns:
            The BackgroundJob instance for chaining.
        """
        self._worker.signals.finished.connect(callback)
        return self

    def on_progress(
        self,
        callback: Callable[[int, str], None],
    ) -> "BackgroundJob":
        """Attach a callback for progress updates.

        Args:
            callback: The function to call with progress percentage and message.

        Returns:
            The BackgroundJob instance for chaining.
        """
        self._worker.signals.progress.connect(callback)
        return self

    def start(self) -> None:
        """Submit the worker to the global thread pool for execution."""
        tmp_thread_pool = QtCore.QThreadPool.globalInstance()
        tmp_thread_pool.start(self._worker)

    # </editor-fold>


# <editor-fold desc="Decorator">
def background_task(
    target_function: Callable[_ParameterSpecification, Any],
) -> Callable[_ParameterSpecification, "BackgroundJob"]:
    """Decorator to convert a synchronous function into a background job.

    Args:
        target_function: The function to execute in the background.

    Returns:
        A wrapper function that returns a BackgroundJob upon invocation.
    """

    @functools.wraps(
        target_function,
        assigned=("__module__", "__name__", "__qualname__", "__doc__"),
    )
    def wrapper(
        *args: _ParameterSpecification.args,
        **kwargs: _ParameterSpecification.kwargs,
    ) -> "BackgroundJob":
        """Wrap the target function in a Worker and return a BackgroundJob.

        Args:
            *args: Positional arguments for the target function.
            **kwargs: Keyword arguments for the target function.

        Returns:
            The created BackgroundJob instance.
        """
        tmp_worker = Worker(target_function, *args, **kwargs)
        return BackgroundJob(tmp_worker)

    return wrapper


# </editor-fold>
