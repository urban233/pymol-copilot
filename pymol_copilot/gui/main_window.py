"""Main window module for the PyMOL Copilot application."""
from __future__ import annotations

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets


class MainWindow(QtWidgets.QMainWindow):
    """Main window for the PyMOL Copilot application."""

    def __init__(self) -> None:
        """Initializes the main window and sets up the user interface."""
        super().__init__()

        self.setWindowTitle("PyMOL Copilot")
        self.resize(800, 600)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Creates and arranges the GUI components."""
        self._setup_menus()

        tmp_central_widget = QtWidgets.QWidget()
        self.setCentralWidget(tmp_central_widget)

        tmp_layout = QtWidgets.QVBoxLayout()
        tmp_central_widget.setLayout(tmp_layout)

        tmp_label = QtWidgets.QLabel("PyMOL Copilot")
        tmp_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        tmp_font = QtGui.QFont("Segoe UI", 24, QtGui.QFont.Weight.Bold)
        tmp_label.setFont(tmp_font)
        tmp_layout.addWidget(tmp_label)

        tmp_description = QtWidgets.QLabel(
            "A professional AI assistant for PyMOL."
        )
        tmp_description.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        tmp_layout.addWidget(tmp_description)

        tmp_status_bar = self.statusBar()
        if tmp_status_bar is not None:
            tmp_status_bar.showMessage("Application Loaded")

    def _setup_menus(self) -> None:
        """Sets up the application menu bar."""
        tmp_menu_bar = self.menuBar()

        if tmp_menu_bar is None:
            return

        # File Menu
        tmp_file_menu = tmp_menu_bar.addMenu("&File")

        if tmp_file_menu is None:
            return

        tmp_exit_action = QtGui.QAction("&Exit", self)
        tmp_exit_action.setShortcut("Ctrl+Q")
        tmp_exit_action.triggered.connect(self.close)
        tmp_file_menu.addAction(tmp_exit_action)
