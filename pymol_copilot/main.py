"""Main entry point for the PyMOL Copilot application."""

from __future__ import annotations

import sys

from PyQt6 import QtWidgets

from pymol_copilot.gui import main_window
from pymol_copilot.gui.qt import styles
from pymol_copilot.gui.qt import theme


def main() -> int:
    """Entry point for the PyMOL Copilot application.

    Returns:
        The exit status code of the application.
    """
    tmp_app = QtWidgets.QApplication(sys.argv)

    # Initialize and apply global stylesheet
    theme.apply_global_theme()

    # Hook screen DPI updates to re-apply the compiled stylesheet
    styles.notifier.scale_changed.connect(theme.apply_global_theme)

    tmp_window = main_window.MainWindow()
    tmp_window.show()
    return tmp_app.exec()


if __name__ == "__main__":
    sys.exit(main())
