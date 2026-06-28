"""Main entry point for the PyMOL Copilot application."""

from __future__ import annotations

import sys

from PyQt6 import QtWidgets

from fluentqt.core import factory
from pymol_copilot.gui import icons
from pymol_copilot.gui import main_window


def main() -> int:
    """Entry point for the PyMOL Copilot application.

    Returns:
        The exit status code of the application.
    """
    tmp_app = QtWidgets.QApplication(sys.argv)

    # Register the application's icon resolver as the fluentqt icon provider.
    factory.register_icon_provider(
        lambda tmp_name: icons.icon("pymol_copilot", tmp_name)
    )

    tmp_window = main_window.MainWindow()
    tmp_window.show()
    return tmp_app.exec()


if __name__ == "__main__":
    sys.exit(main())
