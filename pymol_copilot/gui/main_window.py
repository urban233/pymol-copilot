"""Main window module for the PyMOL Copilot application."""

from __future__ import annotations

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

from pymol_copilot.gui.qt import icons
from pymol_copilot.gui.qt.widgets import command_bar
from pymol_copilot.gui.qt.widgets.flyout import FlyoutFrame, FlyoutPlacement
from pymol_copilot.gui.widgets import input_bar


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

        tmp_split_btn = command_bar.CommandBarSplitButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
            "Home"
        )
        menu = QtWidgets.QMenu(tmp_split_btn)
        menu.addAction("First action")
        menu.addAction("Second action")
        menu.addSeparator()
        menu.addAction("Third action")
        tmp_split_btn.set_menu(menu)

        # --- Flyout example ---
        tmp_flyout_btn = command_bar.CommandBarSplitButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
            "Options"
        )
        tmp_flyout = FlyoutFrame(shadow=False)
        tmp_flyout_content = QtWidgets.QWidget()
        tmp_flyout_layout = QtWidgets.QVBoxLayout(tmp_flyout_content)
        tmp_flyout_layout.setSpacing(4)
        tmp_flyout_layout.setContentsMargins(0, 0, 0, 0)
        tmp_flyout_layout.addWidget(QtWidgets.QLabel("Display options"))
        tmp_flyout_layout.addWidget(QtWidgets.QCheckBox("Show hydrogen atoms"))
        tmp_flyout_layout.addWidget(QtWidgets.QCheckBox("Show surface"))
        tmp_flyout_layout.addWidget(QtWidgets.QCheckBox("Show labels"))
        tmp_flyout.set_content(tmp_flyout_content)
        tmp_flyout_btn.set_flyout(tmp_flyout)
        # ----------------------

        tmp_command_bar = command_bar.CommandBar(
            [
                command_bar.CommandBarActionButton(
                    icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
                    "Home"
                ),
                command_bar.CommandBarActionButton(
                    icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
                    "Home"
                ),
                tmp_split_btn,
                tmp_flyout_btn,
            ], tmp_central_widget
        )
        tmp_layout.addWidget(tmp_command_bar)
        tmp_layout.addStretch(1)
        # tmp_label = QtWidgets.QLabel("PyMOL Copilot")
        # tmp_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        # tmp_font = QtGui.QFont("Segoe UI", 24, QtGui.QFont.Weight.Bold)
        # tmp_label.setFont(tmp_font)
        # tmp_layout.addWidget(tmp_label)
        #
        # tmp_description = QtWidgets.QLabel(
        #     "A professional AI assistant for PyMOL."
        # )
        # tmp_description.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        # tmp_layout.addWidget(tmp_description)
        #
        # tmp_input_bar = input_bar.InputBar()
        # tmp_layout.addWidget(tmp_input_bar)
        #
        # tmp_status_bar = self.statusBar()
        # if tmp_status_bar is not None:
        #     tmp_status_bar.showMessage("Application Loaded")

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
