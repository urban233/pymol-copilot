"""Main entry point for the PyMOL Copilot application."""

from __future__ import annotations

import sys
import os

import pymol
from pymol.Qt.utils import MainThreadCaller

from pymol_copilot.gui import main_window
from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import styles
from pymol_copilot.gui.qt import theme


def main() -> int:
    """Entry point for the PyMOL Copilot application.

    Returns:
        The exit status code of the application.
    """
    # use QT_OPENGL=desktop (auto-detection may fail on Windows)
    if pymol.IS_WINDOWS:
        print("Handling AA_UseDesktopOpenGL")
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseDesktopOpenGL)

    # enable 4K scaling on Windows and Linux
    if hasattr(QtCore.Qt, "AA_EnableHighDpiScaling") and not any(
            v in os.environ for v in ["QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS"]
    ):
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)

    tmp_app = QtWidgets.QApplication(sys.argv)
    tmp_window = main_window.MainWindow()

    # <editor-fold desc="(Hopefully) one time initialization of the PyMOL library">
    pymol.cmd._call_in_gui_thread = MainThreadCaller()

    # Assume GUI thread, make OpenGL context current before calling func().
    def _call_with_opengl_context_gui_thread(func):
        # IMPORTANT: Here is a part where the explict PyMOL OpenGL widget is used!
        with tmp_window.viewer.pymolwidget:
            return func()

        # Dispatch to GUI thread and make OpenGL context current before calling func().
    pymol.cmd._call_with_opengl_context = lambda func: pymol.cmd._call_in_gui_thread(
        lambda: _call_with_opengl_context_gui_thread(func)
    )
    # </editor-fold>

    # Initialize and apply global stylesheet
    theme.apply_global_theme()

    # Hook screen DPI updates to re-apply the compiled stylesheet
    styles.notifier.scale_changed.connect(theme.apply_global_theme)


    tmp_window.show()
    return tmp_app.exec()


if __name__ == "__main__":
    sys.exit(main())
