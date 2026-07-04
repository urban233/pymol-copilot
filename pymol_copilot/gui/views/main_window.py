"""Main window module for the PyMOL Copilot application."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt import icons
from pymol_copilot.gui.qt.model import list_model
from pymol_copilot.gui.qt.model import table_model
from pymol_copilot.gui.qt.widgets import color_grid, pml_command_line
from pymol_copilot.gui.qt.widgets import command_bar
from pymol_copilot.gui.qt.widgets import flyout
from pymol_copilot.gui.qt.widgets import input_bar
from pymol_copilot.gui.qt.widgets import list_view
from pymol_copilot.gui.qt.widgets import table_view
from pymol_copilot.gui.qt.widgets import viewer


class MainWindow(QtWidgets.QMainWindow):
    """Main window for the PyMOL Copilot application."""

    def __init__(self) -> None:
        """Initializes the main window and sets up the user interface."""
        super().__init__()
        self._menu_bar = QtWidgets.QMenuBar()
        self.viewer = viewer.Viewer()
        self._command_line = pml_command_line.PmlCommandLine(self.viewer.cmd)
        self.setWindowTitle("PyMOL Copilot")
        self.resize(800, 600)

        self._setup_ui()
        # self._setup_ui_mock()

    def _setup_ui(self) -> None:
        # <editor-fold desc="General central layout">
        tmp_central_widget = QtWidgets.QWidget()
        self.setCentralWidget(tmp_central_widget)
        tmp_layout = QtWidgets.QVBoxLayout()
        tmp_layout.setContentsMargins(*ui_defaults.default_contents_margins())
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_central_widget.setLayout(tmp_layout)
        # </editor-fold>
        self.setMenuBar(self._menu_bar)

        tmp_layout.addWidget(self.viewer)
        tmp_layout.addWidget(self._command_line)

        # tmp_highlight_btn = command_bar.CommandBarActionButton(
        #     icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
        #     "Highlight",
        # )
        # tmp_highlight_btn.clicked.connect(self.highlight_sele)
        # tmp_layout.addWidget(tmp_highlight_btn)

        # self.input = input_bar.InputBar()
        # tmp_layout.addWidget(self.input)

    def highlight_sele(self) -> None:
        """Highlights the selected molecule residue region."""
        # self.viewer.highlight_selection("/1DPX//A/20-25")
        # self.viewer.cmd.select("highlighted", "/1DPX//A/20-25")
        self.viewer.highlight_selection("/1DPX//A/20-25+40-42")
        self.viewer.cmd.select("highlighted", "/1DPX//A/20-25+40-42")

    def _setup_ui_mock(self) -> None:
        """Creates and arranges the GUI components."""
        self._setup_menus()

        tmp_central_widget = QtWidgets.QWidget()
        self.setCentralWidget(tmp_central_widget)

        tmp_layout = QtWidgets.QVBoxLayout()
        tmp_central_widget.setLayout(tmp_layout)

        tmp_split_btn = command_bar.CommandBarSplitButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"), "Home"
        )
        menu = QtWidgets.QMenu(tmp_split_btn)
        menu.addAction("First action")
        menu.addAction("Second action")
        menu.addSeparator()
        menu.addAction("Third action")
        tmp_split_btn.set_menu(menu)

        # --- Flyout example ---
        tmp_flyout_btn = command_bar.CommandBarSplitButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"), "Options"
        )
        tmp_flyout = flyout.FlyoutFrame(shadow=False)
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

        tmp_flyout_plus_btn = command_bar.CommandToggleSplitButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
            "Options+",
        )
        tmp_flyout_plus_btn.set_flyout(tmp_flyout)
        # ----------------------

        tmp_dropdown_menu_btn = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
            "Export",
            command_bar.CommandBarButtonStyle.TEXT_BESIDE,
        )
        tmp_export_menu = QtWidgets.QMenu(tmp_dropdown_menu_btn)
        tmp_export_menu.addAction("Export as PNG")
        tmp_export_menu.addAction("Export as SVG")
        tmp_export_menu.addSeparator()
        tmp_export_menu.addAction("Export session...")
        tmp_dropdown_menu_btn.set_menu(tmp_export_menu)

        tmp_dropdown_flyout_btn = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
            "View",
            command_bar.CommandBarButtonStyle.TEXT_BESIDE,
        )
        tmp_list_flyout = flyout.FlyoutFrame(shadow=False)
        tmp_dropdown_flyout_content = QtWidgets.QWidget()
        tmp_dropdown_flyout_layout = QtWidgets.QVBoxLayout(
            tmp_dropdown_flyout_content
        )
        tmp_dropdown_flyout_layout.setSpacing(4)
        tmp_dropdown_flyout_layout.setContentsMargins(0, 0, 0, 0)
        tmp_dropdown_flyout_layout.addWidget(QtWidgets.QLabel("View options"))
        tmp_dropdown_flyout_layout.addWidget(
            QtWidgets.QCheckBox("Cartoon representation")
        )
        tmp_dropdown_flyout_layout.addWidget(
            QtWidgets.QCheckBox("Stick representation")
        )
        tmp_list_flyout.set_content(tmp_dropdown_flyout_content)
        tmp_dropdown_flyout_btn.set_flyout(tmp_list_flyout)

        tmp_toggle_btn = command_bar.CommandBarToggleButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
            "Labels",
            command_bar.CommandBarButtonStyle.TEXT_BESIDE,
        )

        tmp_highlight_btn = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
            "Highlight",
            command_bar.CommandBarButtonStyle.ICON_ONLY,
        )
        tmp_list_flyout = flyout.FlyoutFrame(shadow=False)
        tmp_list_flyout_content = QtWidgets.QWidget()
        tmp_list_flyout_layout = QtWidgets.QVBoxLayout(tmp_list_flyout_content)
        tmp_list_flyout_layout.setSpacing(4)
        tmp_list_flyout_layout.setContentsMargins(0, 0, 0, 0)

        model = list_model.ListModel(initial_data=["Alice", "Bob", "Carol"])
        # List view with search:
        search_view = list_view.ListViewWithSearch()
        search_view.set_model(model)
        search_view.set_checkboxes_enabled(True)
        tmp_list_flyout_layout.addWidget(search_view)
        tmp_list_flyout.set_content(tmp_list_flyout_content)
        tmp_highlight_btn.set_flyout(tmp_list_flyout)

        tmp_highlight_color_btn = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
            "Color",
            command_bar.CommandBarButtonStyle.ICON_ONLY,
        )
        tmp_color = color_grid.ColorFlyout()
        tmp_highlight_color_btn.set_flyout(tmp_color)

        tmp_command_bar = command_bar.CommandBar(
            [
                tmp_highlight_btn,
                tmp_highlight_color_btn,
                tmp_split_btn,
                tmp_flyout_btn,
                tmp_dropdown_menu_btn,
                tmp_dropdown_flyout_btn,
                tmp_toggle_btn,
                tmp_flyout_plus_btn,
            ],
            tmp_central_widget,
        )
        tmp_layout.addWidget(tmp_command_bar)
        # --- Begin content
        tmp_input_box = input_bar.InputBar()
        tmp_layout.addWidget(tmp_input_box)

        class Job:
            """Represent a mock job for the table view demo."""

            def __init__(self, name: str, status: str, project: str) -> None:
                """Initialize the job.

                Args:
                    name: The job name.
                    status: The job status.
                    project: The project name.
                """
                self.name = name
                self.status = status
                self.project = project

        class JobTableModel(table_model.TableModel):
            """Table model for mock jobs."""

            def _cell_data(self, item: object, column: int) -> object:
                """Return display data for a cell.

                Args:
                    item: The job item.
                    column: The column index.

                Returns:
                    The display string.
                """
                if isinstance(item, Job):
                    return [item.name, item.status, item.project][column]
                return ""

        tmp_job_model = JobTableModel(
            column_headers=["Name", "Status", "Project"]
        )
        tmp_job_items: list[object] = [
            Job("Home", "Running", "PyMOL"),
            Job("Align", "Queued", "cBioMOL"),
            Job("Render", "Completed", "Copilot"),
        ]
        tmp_job_model.add_rows(tmp_job_items)
        tmp_table_view = table_view.TableView()
        tmp_table_view.set_model(tmp_job_model)
        tmp_table_view.set_checkboxes_enabled(True)
        tmp_layout.addWidget(tmp_table_view)

        # --- End content
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
