"""Main window module for the PyMOL Copilot application."""

from __future__ import annotations

import pathlib
import sys
import webbrowser
from typing import TYPE_CHECKING, override

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt import icons
from pymol_copilot.gui.qt.model import list_model
from pymol_copilot.gui.qt.model import table_model
from pymol_copilot.gui.qt.widgets import color_grid, pml_command_line, panel
from pymol_copilot.gui.qt.widgets import command_bar
from pymol_copilot.gui.qt.widgets import flyout
from pymol_copilot.gui.qt.widgets import input_bar
from pymol_copilot.gui.qt.widgets import list_view
from pymol_copilot.gui.qt.widgets import table_view
from pymol_copilot.gui.qt.widgets import viewer
from pymol_copilot.gui.qt.widgets import pml_menu_bar
from pymol_copilot.ai.app.chat_controller import ChatController
from pymol_copilot.ai.backend.config import InferenceConfig
from pymol_copilot.ai.execution.execution_worker import ExecutionWorker
from pymol_copilot.ai.execution.pymol_session import InjectedPyMOLSession


class MainWindow(QtWidgets.QMainWindow):
    """Main window for the PyMOL Copilot application."""

    def __init__(self) -> None:
        """Initializes the main window and sets up the user interface."""
        super().__init__()

        # # <editor-fold desc="Core App Logic and AI Initialization">
        self.viewer = viewer.Viewer()
        self._pymol_session = InjectedPyMOLSession(self.viewer)
        self._execution_worker = ExecutionWorker(self._pymol_session, self)

        tmp_model_path = (
            pathlib.Path(__file__).parent.parent.parent
            / "ai"
            / "training"
            / "models"
            / "cbiomol-pymol-assistant-Q4_K_M.gguf"
        )
        self._ai_config = InferenceConfig(
            model_path=tmp_model_path,
            n_ctx=8192,
            mock=False,
        )

        self._conversation_panel = panel.PmlCopilotPanel()
        self._chat_controller = ChatController(
            panel=self._conversation_panel,
            config=self._ai_config,
            execution_worker=self._execution_worker,
            parent=self,
        )
        # </editor-fold>

        # # <editor-fold desc="Menu Builder and Data Model Instantiation">
        self._menu_builder = PyMOLMenuBuilder(self.viewer.cmd)
        # </editor-fold>

        # # <editor-fold desc="Command Bar Widget Configuration">
        # 1. Dedicated Open Dropdown Operations
        self._open_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "open"),
            text="Open",
            style=command_bar.CommandBarButtonStyle.ICON_ONLY,
        )
        self._open_menu_obj = QtWidgets.QMenu(self._open_cmd_button)
        self._menu_builder.add_action(
            self._open_menu_obj, "Open...", "cmd_string", "file_open"
        )
        self._open_menu_obj.addMenu("Open Recent")
        self._menu_builder.add_action(
            self._open_menu_obj, "Get PDB...", "cmd_string", "fetch"
        )
        self._open_menu_obj.addSeparator()
        self._menu_builder.add_action(
            self._open_menu_obj, "Run Script...", "cmd_string", "run"
        )
        self._open_cmd_button.set_menu(self._open_menu_obj)

        # 2. Dedicated Save Dropdown Operations
        self._save_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "save"),
            text="Save",
            style=command_bar.CommandBarButtonStyle.ICON_ONLY,
        )
        self._save_menu_obj = QtWidgets.QMenu(self._save_cmd_button)
        self._menu_builder.add_action(
            self._save_menu_obj, "Save Session", "cmd_string", "save"
        )
        self._menu_builder.add_action(
            self._save_menu_obj, "Save Session As...", "cmd_string", "save"
        )
        self._save_cmd_button.set_menu(self._save_menu_obj)

        # 3. Dedicated Export Dropdown Operations
        self._export_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "export"),
            text="Export",
            style=command_bar.CommandBarButtonStyle.ICON_ONLY,
        )
        self._export_menu_obj = QtWidgets.QMenu(self._export_cmd_button)
        self._menu_builder.add_action(
            self._export_menu_obj,
            "Export Molecule...",
            "cmd_string",
            "save",
        )
        self._menu_builder.add_action(
            self._export_menu_obj,
            "Export Map...",
            "cmd_string",
            "save",
        )
        self._menu_builder.add_action(
            self._export_menu_obj,
            "Export Alignment...",
            "cmd_string",
            "save",
        )

        # Export Submenus
        tmp_export_img = self._export_menu_obj.addMenu("Export Image As")
        self._menu_builder.add_action(
            tmp_export_img,
            "Draw / Raytrace Frame View Panel...",
            "cmd_string",
            "ray",
        )
        tmp_export_img.addSeparator()
        self._menu_builder.add_action(
            tmp_export_img, "VRML 2...", "cmd_string", "save view.wrl"
        )
        self._menu_builder.add_action(
            tmp_export_img, "COLLADA...", "cmd_string", "save view.dae"
        )
        self._menu_builder.add_action(
            tmp_export_img, "GLTF...", "cmd_string", "save view.gltf"
        )
        self._menu_builder.add_action(
            tmp_export_img, "POV-Ray...", "cmd_string", "save view.pov"
        )
        self._menu_builder.add_action(
            tmp_export_img, "STL...", "cmd_string", "save view.stl"
        )

        tmp_export_movie = self._export_menu_obj.addMenu("Export Movie As")
        self._menu_builder.add_action(
            tmp_export_movie,
            "MPEG...",
            "cmd_string",
            "movie.produce output.mpg",
        )
        self._menu_builder.add_action(
            tmp_export_movie,
            "Quicktime...",
            "cmd_string",
            "movie.produce output.mov",
        )
        tmp_export_movie.addSeparator()
        self._menu_builder.add_action(
            tmp_export_movie, "PNG Images...", "cmd_string", "mpng"
        )
        self._export_cmd_button.set_menu(self._export_menu_obj)

        self._ai_cmd_button = command_bar.CommandBarActionButton(
            icons.icon("pymol_copilot.gui.qt", "ai"),
        )

        # Dropdown Buttons with Associated Popups
        self._build_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "build"),
        )
        self._build_menu_obj = QtWidgets.QMenu(self._build_cmd_button)
        self._build_menu_obj.setProperty("cmd", self.viewer.cmd)
        self._menu_builder.build_build_menu(self._build_menu_obj)
        self._build_cmd_button.set_menu(self._build_menu_obj)

        self._movie_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "movie"),
        )
        self._movie_menu_obj = QtWidgets.QMenu(self._movie_cmd_button)
        self._movie_menu_obj.setProperty("cmd", self.viewer.cmd)
        self._menu_builder.build_movie_menu(self._movie_menu_obj)
        self._movie_cmd_button.set_menu(self._movie_menu_obj)

        self._settings_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "settings"),
        )
        self._settings_menu_obj = QtWidgets.QMenu(self._settings_cmd_button)
        self._settings_menu_obj.setProperty("cmd", self.viewer.cmd)
        self._menu_builder.build_setting_menu(self._settings_menu_obj)
        self._settings_cmd_button.set_menu(self._settings_menu_obj)

        self._mouse_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "mouse"),
        )
        self._mouse_menu_obj = QtWidgets.QMenu(self._mouse_cmd_button)
        self._mouse_menu_obj.setProperty("cmd", self.viewer.cmd)
        self._menu_builder.build_mouse_menu(self._mouse_menu_obj)
        self._mouse_cmd_button.set_menu(self._mouse_menu_obj)

        self._wizard_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "wizard"),
        )
        self._wizard_menu_obj = QtWidgets.QMenu(self._wizard_cmd_button)
        self._wizard_menu_obj.setProperty("cmd", self.viewer.cmd)
        self._menu_builder.build_wizard_menu(self._wizard_menu_obj)
        self._wizard_cmd_button.set_menu(self._wizard_menu_obj)

        self._help_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "help"),
        )
        self._help_menu_obj = QtWidgets.QMenu(self._help_cmd_button)
        self._help_menu_obj.setProperty("cmd", self.viewer.cmd)
        self._menu_builder.build_help_menu(self._help_menu_obj)
        self._help_cmd_button.set_menu(self._help_menu_obj)

        self._more_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "more_vertical"),
        )
        self._more_menu_obj = QtWidgets.QMenu(self._more_cmd_button)
        self._more_menu_obj.setProperty("cmd", self.viewer.cmd)
        self._menu_builder.build_more_menu(self._more_menu_obj)
        self._more_cmd_button.set_menu(self._more_menu_obj)

        # Assemble Main Layout Strip
        # self._command_bar = command_bar.CommandBar(
        #     [
        #         self._open_cmd_button,
        #         self._save_cmd_button,
        #         self._export_cmd_button,
        #         self._build_cmd_button,
        #         self._movie_cmd_button,
        #         self._settings_cmd_button,
        #         self._mouse_cmd_button,
        #         self._wizard_cmd_button,
        #         self._ai_cmd_button,
        #     ]
        # )
        # self._command_bar.append_command_button(self._more_cmd_button)
        # self._command_bar.append_command_button(self._help_cmd_button)
        self._sele_mode_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "left_click"),
        )
        self._zoom_cmd_button = command_bar.CommandBarActionButton(
            icons.icon("pymol_copilot.gui.qt", "zoom"),
        )
        self._scene_cmd_button = command_bar.CommandBarActionButton(
            icons.icon("pymol_copilot.gui.qt", "scene"),
        )
        self._camera_cmd_button = command_bar.CommandBarDropdownButton(
            icons.icon("pymol_copilot.gui.qt", "photo_camera"),
        )

        self._sele_mode_menu_obj = QtWidgets.QMenu(self._sele_mode_cmd_button)
        self._sele_mode_menu_obj.setProperty("cmd", self.viewer.cmd)
        self._menu_builder.build_selection_mode_menu(self._sele_mode_menu_obj)
        self._sele_mode_cmd_button.set_menu(self._sele_mode_menu_obj)

        self._camera_flyout = flyout.FlyoutFrame(self._camera_cmd_button)
        tmp_camera_content = QtWidgets.QWidget()
        self._camera_flyout.set_content(tmp_camera_content)
        self._camera_cmd_button.set_flyout(self._camera_flyout)

        self._command_bar = command_bar.TabbedCommandBar(
            [
                (
                    "Home",
                    [
                        self._open_cmd_button,
                        self._save_cmd_button,
                        self._export_cmd_button,
                        self._build_cmd_button,
                        self._movie_cmd_button,
                        self._settings_cmd_button,
                        self._mouse_cmd_button,
                        self._wizard_cmd_button,
                        self._ai_cmd_button,
                    ],
                ),
                (
                    "Display",
                    [
                        self._sele_mode_cmd_button,
                        self._zoom_cmd_button,
                        self._scene_cmd_button,
                        self._camera_cmd_button,
                    ],
                ),
            ]
        )
        self._command_bar.append_command_button(0, self._more_cmd_button)
        self._command_bar.append_command_button(0, self._help_cmd_button)
        # </editor-fold>

        # # <editor-fold desc="Console Inputs and Layout Shell Declarations">
        self._side_panel_stack = panel.SidePanelStack()
        self._input_bar = input_bar.InputBar()
        self._command_line = pml_command_line.PmlCommandLine(self.viewer.cmd)

        self._setup_ui()
        self.setMinimumSize(600, 400)
        self.setWindowIcon(icons.icon("pymol_copilot.gui.qt", "logo_icon"))
        self.setWindowTitle("Open-Source PyMOL Copilot")
        self.resize(800, 600)

        # </editor-fold>

    def _setup_ui(self) -> None:
        # # <editor-fold desc="General central layout">
        tmp_central_widget = QtWidgets.QWidget()
        self.setCentralWidget(tmp_central_widget)
        tmp_layout = QtWidgets.QVBoxLayout()
        tmp_layout.setContentsMargins(*ui_defaults.default_contents_margins())
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_central_widget.setLayout(tmp_layout)
        # </editor-fold>

        # # <editor-fold desc="Main Application Panel Packing and Display Layout">
        # self.setMenuBar(self._menu_bar)

        tmp_main_content_layout = QtWidgets.QVBoxLayout()
        tmp_main_content_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        tmp_main_content_layout.setSpacing(ui_defaults.EMPTY_SPACING)

        tmp_input_bar_wrapper_layout = QtWidgets.QHBoxLayout()
        tmp_input_bar_wrapper_layout.setContentsMargins(120, 0, 120, 0)
        tmp_input_bar_wrapper_layout.addWidget(self._input_bar)
        tmp_main_content_layout.addLayout(tmp_input_bar_wrapper_layout)
        tmp_main_content_layout.addWidget(self.viewer)
        tmp_main_content_layout.addWidget(self._command_line)

        tmp_main_content_widget = QtWidgets.QWidget()
        tmp_main_content_widget.setLayout(tmp_main_content_layout)

        self._side_panel_stack.add_panel(
            "PyMOL Copilot",
            icons.icon("pymol_copilot.gui.qt", "ai"),
            self._conversation_panel,
        )

        self._content_splitter = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Horizontal
        )
        self._content_splitter.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._content_splitter.addWidget(tmp_main_content_widget)
        self._content_splitter.addWidget(self._side_panel_stack)
        self._content_splitter.setStretchFactor(0, 1)
        self._content_splitter.setStretchFactor(1, 0)
        self._content_splitter.setChildrenCollapsible(False)
        self._side_panel_stack.hide()

        self._ai_cmd_button.clicked.connect(self._toggle_side_panel)
        self._conversation_panel.panelClosed.connect(
            self._side_panel_stack.collapse
        )
        self._side_panel_stack.panelToggled.connect(
            lambda _idx, expanded: self._input_bar.setVisible(not expanded)
        )
        self._input_bar.submitted.connect(self._on_main_input_submitted)

        tmp_layout.addWidget(self._command_bar)
        tmp_layout.addWidget(self._content_splitter)
        # </editor-fold>

    def _toggle_side_panel(self) -> None:
        """Toggle the side panel: show it if hidden, collapse it if visible."""
        if self._side_panel_stack.isVisible():
            self._side_panel_stack.collapse()
        else:
            self._side_panel_stack.set_active(0)

    def _on_main_input_submitted(self, text: str) -> None:
        """Forward text from the main input bar into the AI panel.

        Opens the panel first if it is currently hidden.

        Args:
            text: The submitted message text.
        """
        if not self._side_panel_stack.isVisible():
            self._side_panel_stack.set_active(0)
        self._input_bar.set_processing(False)
        self._conversation_panel.submit_text(text)


# # <editor-fold desc="Memory-Safe Data-Driven Menu Engine">
class PyMOLMenuBuilder:
    """Builds and dispatches menus dynamically via unified meta-data tracking."""

    def __init__(self, cmd) -> None:
        self.cmd = cmd

    def add_action(
        self, menu, text, action_type: str, data: any = None
    ) -> QtWidgets.QAction:
        """Single bottleneck builder tracking arguments as pure properties."""
        action = menu.addAction(text)
        action.setProperty("action_type", action_type)
        if data is not None:
            action.setData(data)
        action.triggered.connect(self._dispatch_action)
        return action

    def add_check_action(
        self, menu, text, setting_name: str, on_val=1, off_val=0
    ) -> QtWidgets.QAction:
        action = QtWidgets.QAction(text, menu)
        action.setCheckable(True)
        action.setProperty("action_type", "setting_toggle")
        action.setProperty("setting_meta", (setting_name, on_val, off_val))
        action.triggered.connect(self._dispatch_action)
        menu.addAction(action)
        return action

    def add_radio_group(
        self, menu, options, setting_name: str
    ) -> QtGui.QActionGroup:
        group = QtGui.QActionGroup(menu)
        group.setExclusive(True)
        for label, val in options:
            action = QtWidgets.QAction(label, menu)
            action.setCheckable(True)
            action.setProperty("action_type", "setting_radio")
            action.setProperty("setting_meta", (setting_name, val))
            action.triggered.connect(self._dispatch_action)
            group.addAction(action)
            menu.addAction(action)
        return group

    def _dispatch_action(self) -> None:
        """Universal, single-point handler decoding properties on the triggered action."""
        action: QtWidgets.QAction = self.sender()
        action_type = action.property("action_type")

        if action_type == "cmd_string":
            self.cmd.do(action.data())
        elif action_type == "remove":
            self.cmd.remove(action.data())
        elif action_type == "alter":
            target, expression = action.data()
            self.cmd.alter(target, expression)
        elif action_type == "url":
            webbrowser.open(action.data())
        elif action_type == "help_topic":
            webbrowser.open(f"http://pymol.org/d/{action.data()}")
        elif action_type == "wizard":
            self.cmd.wizard(action.data())
        elif action_type == "wizard_demo":
            self.cmd.wizard("demo", action.data())
        elif action_type == "wizard_demo_finish":
            self.cmd.replace_wizard("demo", "finish")
        elif action_type == "movie_blank":
            self.cmd.movie.add_blank(action.data())
        elif action_type == "zoom_sphere":
            self.cmd.zoom("center", action.data(), animate=-1)
        elif action_type == "clip_slab":
            self.cmd.clip("slab", action.data())
        elif action_type == "scene_action":
            key, val = action.data()
            self.cmd.scene(key, val)
        elif action_type == "scene_cache":
            self.cmd.cache(action.data())
        elif action_type == "mouse_config":
            m = action.data()
            self.cmd.config_mouse(m) if (
                "config" in m or "two_button" in m
            ) else self.cmd.mouse(m)
        elif action_type == "attach_fragment":
            f, a, m = action.data()
            self.cmd.editor.attach_fragment("pk1", f, a, m)
        elif action_type == "attach_amino_acid":
            self.cmd.editor.attach_amino_acid("pk1", action.data())
        elif action_type == "replace_element":
            e, g, v = action.data()
            self.cmd.replace(e, g, v)
        elif action_type == "modernize_rendering":
            self.cmd.util.modernize_rendering(1, self.cmd)
        elif action_type == "ray_shadows":
            self.cmd.util.ray_shadows(action.data())
        elif action_type == "transparency_combo":
            v = action.data()
            self.cmd.set("transparency_mode", v[0], quiet=0)
            self.cmd.set("backface_cull", v[1], quiet=0)
            self.cmd.set("two_sided_lighting", v[2], quiet=0)
        elif action_type == "setting_toggle":
            setting_name, on_val, off_val = action.property("setting_meta")
            self.cmd.set(
                setting_name,
                str(on_val if action.isChecked() else off_val),
                quiet=0,
            )
        elif action_type == "setting_radio":
            if action.isChecked():
                setting_name, val = action.property("setting_meta")
                self.cmd.set(setting_name, str(val), quiet=0)

    # --- Structural Hierarchy Gen ---
    def build_more_menu(self, parent_menu):
        sys_browser_cmd = (
            "explorer ."
            if sys.platform == "win32"
            else "open ."
            if sys.platform == "darwin"
            else "xdg-open ."
        )
        new_window_menu = parent_menu.addMenu("New PyMOL Window")
        self.add_action(new_window_menu, "Default", "cmd_string", "new_window")
        self.add_action(
            new_window_menu,
            "Ignore .pymolrc and plugins (-k)",
            "cmd_string",
            "new_window -k",
        )

        parent_menu.addSeparator()
        self.add_action(parent_menu, "Undo", "cmd_string", "undo")
        self.add_action(parent_menu, "Redo", "cmd_string", "redo")

        parent_menu.addSeparator()
        log_menu = parent_menu.addMenu("Log File")
        self.add_action(log_menu, "Open...", "cmd_string", "log_open")
        self.add_action(log_menu, "Resume...", "cmd_string", "log_open mode=r")
        self.add_action(log_menu, "Append...", "cmd_string", "log_open mode=a")
        self.add_action(log_menu, "Close", "cmd_string", "log_close")

        wd_menu = parent_menu.addMenu("Working Directory")
        self.add_action(wd_menu, "Change...", "cmd_string", "cd")
        self.add_action(
            wd_menu, "File Browser", "cmd_string", f"system {sys_browser_cmd}"
        )

        parent_menu.addSeparator()
        self.add_action(
            parent_menu, "Edit pymolrc", "cmd_string", "edit_pymolrc"
        )
        parent_menu.addSeparator()

        reinit_menu = parent_menu.addMenu("Reinitialize")
        self.add_action(reinit_menu, "Everything", "cmd_string", "reinitialize")
        self.add_action(
            reinit_menu,
            "Original Settings",
            "cmd_string",
            "reinitialize original_settings",
        )
        self.add_action(
            reinit_menu,
            "Stored Settings",
            "cmd_string",
            "reinitialize settings",
        )
        reinit_menu.addSeparator()
        self.add_action(
            reinit_menu,
            "Store Current Settings",
            "cmd_string",
            "reinitialize store_defaults",
        )

        self.add_action(parent_menu, "Quit", "cmd_string", "quit")

    def build_build_menu(self, parent_menu):
        self._build_fragments_layout(parent_menu.addMenu("Fragment"))
        self._build_residues_layout(parent_menu.addMenu("Residue"))
        parent_menu.addSeparator()
        self._build_sculpting_layout(parent_menu.addMenu("Sculpting"))
        parent_menu.addSeparator()
        self.add_action(
            parent_menu,
            "Cycle Bond Valence [Ctrl-Shift-W]",
            "cmd_string",
            "cycle_valence",
        )
        self.add_action(
            parent_menu,
            "Fill Hydrogens on (pk1) [Ctrl-Shift-R]",
            "cmd_string",
            "h_fill",
        )
        self.add_action(
            parent_menu,
            "Invert (pk2)-(pk1)-(pk3) [Ctrl-Shift-E]",
            "cmd_string",
            "invert",
        )
        self.add_action(
            parent_menu,
            "Create Bond (pk1)-(pk2) [Ctrl-Shift-T]",
            "cmd_string",
            "bond",
        )
        parent_menu.addSeparator()
        self.add_action(
            parent_menu, "Remove (pk1) [Ctrl-Shift-D]", "remove", "pk1"
        )
        parent_menu.addSeparator()
        self.add_action(
            parent_menu,
            "Make (pk1) Positive [Ctrl-Shift-K]",
            "alter",
            ("pk1", "formal_charge=1"),
        )
        self.add_action(
            parent_menu,
            "Make (pk1) Negative [Ctrl-Shift-J]",
            "alter",
            ("pk1", "formal_charge=-1"),
        )
        self.add_action(
            parent_menu,
            "Make (pk1) Neutral [Ctrl-Shift-U]",
            "alter",
            ("pk1", "formal_charge=0"),
        )

    def build_movie_menu(self, parent_menu):
        durations = [0.25, 0.5, 1, 2, 3, 4, 6, 8, 12, 18, 24, 30, 48, 60]
        fps_modes = [
            ("30 FPS", 30.0),
            ("15 FPS", 15.0),
            ("5 FPS", 5.0),
            ("1 FPS", 1.0),
            ("0.3 FPS", 0.3),
        ]
        append_menu = parent_menu.addMenu("Append")
        for i in durations:
            self.add_action(append_menu, f"{i} second", "movie_blank", i)
        parent_menu.addSeparator()
        self._build_movie_programs_layout(parent_menu.addMenu("Program"))
        self.add_action(
            parent_menu, "Update Last Program", "cmd_string", "mvprg"
        )
        self.add_action(
            parent_menu,
            "Remove Last Program",
            "cmd_string",
            "mvprg_remove_last",
        )
        parent_menu.addSeparator()
        self.add_action(parent_menu, "Reset", "cmd_string", "mset;rewind")
        parent_menu.addSeparator()
        fps_menu = parent_menu.addMenu("Frame Rate")
        self.add_radio_group(fps_menu, fps_modes, "movie_fps")
        fps_menu.addSeparator()
        self.add_check_action(fps_menu, "Show Frame Rate", "show_frame_rate")
        self.add_action(fps_menu, "Reset Meter", "cmd_string", "meter_reset")
        parent_menu.addSeparator()
        self.add_check_action(
            parent_menu, "Auto Interpolate", "movie_auto_interpolate"
        )
        self.add_check_action(parent_menu, "Show Panel", "movie_panel")
        self.add_check_action(parent_menu, "Loop Frames", "movie_loop")
        self.add_check_action(parent_menu, "Draw Frames", "draw_frames")
        self.add_check_action(
            parent_menu, "Ray Trace Frames", "ray_trace_frames"
        )
        self.add_check_action(parent_menu, "Cache Frame Images", "cache_frames")
        self.add_action(
            parent_menu, "Clear Image Cache", "cmd_string", "mclear"
        )
        parent_menu.addSeparator()
        self.add_check_action(
            parent_menu, "Static Singletons", "static_singletons", 1
        )
        self.add_check_action(parent_menu, "Show All States", "all_states", 1)

    def build_display_menu(self, parent_menu):
        seq_formats = [
            ("Residue Codes", 0),
            ("Residue Names", 1),
            ("Chain Identifiers", 3),
            ("Atom Names", 2),
            ("States", 4),
        ]
        seq_labels = [
            ("All Residue Numbers", 2),
            ("Top Sequence Only", 1),
            ("Object Names Only", 0),
            ("No Labels", 3),
        ]
        seq_gaps = [("No Gaps", 0), ("All Gaps", 1), ("Single Gap", 2)]
        bg_colors = [
            ("White", 0),
            ("Light Grey", 134),
            ("Grey", 104),
            ("Black", 1),
        ]
        grid_modes = [
            ("By Object", 1),
            ("By State", 2),
            ("By Object-State", 3),
            ("Disable", 0),
        ]

        self.add_check_action(parent_menu, "Sequence", "seq_view", 1)
        seq_menu = parent_menu.addMenu("Sequence Mode")
        self.add_radio_group(seq_menu, seq_formats, "seq_view_format")
        seq_menu.addSeparator()
        self.add_radio_group(seq_menu, seq_labels, "seq_view_label_mode")
        seq_menu.addSeparator()
        self.add_radio_group(seq_menu, seq_gaps, "seq_view_gap_mode")

        parent_menu.addSeparator()
        self.add_check_action(parent_menu, "Internal GUI", "internal_gui", 1)
        self.add_check_action(
            parent_menu, "Internal Prompt", "internal_prompt", 1
        )
        self.add_radio_group(
            parent_menu.addMenu("Internal Feedback"),
            [("0", 0), ("1", 1), ("3", 3), ("5", 5)],
            "internal_feedback",
        )
        self.add_radio_group(
            parent_menu.addMenu("Overlay"),
            [("0", 0), ("1", 1), ("3", 3), ("5", 5)],
            "overlay",
        )

        parent_menu.addSeparator()
        self.add_check_action(parent_menu, "Stereo", "stereo", 1)
        stereo_menu = parent_menu.addMenu("Stereo Mode")
        for lab, s_cmd in [
            ("Anaglyph Stereo", "stereo anaglyph"),
            ("Cross-Eye Stereo", "stereo crosseye"),
            ("Wall-Eye Stereo", "stereo walleye"),
            ("Quad-Buffered Stereo", "stereo quadbuffer"),
            ("Zalman Stereo", "stereo byrow"),
            ("OpenVR", "stereo openvr"),
        ]:
            self.add_action(stereo_menu, lab, "cmd_string", s_cmd)
        stereo_menu.addSeparator()
        self.add_action(stereo_menu, "Swap Sides", "cmd_string", "stereo swap")
        stereo_menu.addSeparator()
        self.add_action(
            stereo_menu, "Chromadepth", "cmd_string", "stereo chromadepth"
        )
        self.add_action(stereo_menu, "off", "cmd_string", "stereo off")

        parent_menu.addSeparator()
        zoom_menu = parent_menu.addMenu("Zoom")
        for ang in [4, 6, 8, 12, 20]:
            self.add_action(
                zoom_menu, f"{ang} Angstrom Sphere", "zoom_sphere", ang
            )
        self.add_action(zoom_menu, "All", "cmd_string", "zoom animate=-1")
        self.add_action(
            zoom_menu, "Complete", "cmd_string", "zoom animate=-1, complete=1"
        )

        clip_menu = parent_menu.addMenu("Clip")
        self.add_action(
            clip_menu, "Nothing", "cmd_string", "clip atoms, 5, all"
        )
        for slab in [8, 12, 16, 20, 30]:
            self.add_action(
                clip_menu, f"{slab} Angstrom Slab", "clip_slab", slab
            )

        parent_menu.addSeparator()
        bg_menu = parent_menu.addMenu("Background")
        self.add_check_action(bg_menu, "Opaque", "opaque_background", 1)
        self.add_check_action(bg_menu, "Alpha Checker", "show_alpha_checker", 1)
        bg_menu.addSeparator()
        self.add_radio_group(bg_menu, bg_colors, "bg_rgb")

        cspace_menu = parent_menu.addMenu("Color Space")
        for lab, cs_cmd in [
            ("CMYK (for publications)", "space cmyk"),
            ("PyMOL (for video + web)", "space pymol"),
            ("RGB (default)", "space rgb"),
        ]:
            self.add_action(cspace_menu, lab, "cmd_string", cs_cmd)
        qual_menu = parent_menu.addMenu("Quality")
        for lab, pq_cmd in [
            ("Maximum Performance", "util.performance(100)"),
            ("Reasonable Performance", "util.performance(66)"),
            ("Reasonable Quality", "util.performance(33)"),
            ("Maximum Quality", "util.performance(0)"),
        ]:
            self.add_action(qual_menu, lab, "cmd_string", pq_cmd)

        self.add_radio_group(
            parent_menu.addMenu("Grid"), grid_modes, "grid_mode"
        )
        parent_menu.addSeparator()
        self.add_check_action(parent_menu, "Orthoscopic View", "orthoscopic", 1)
        self.add_check_action(parent_menu, "Show Valences", "valence", 1)
        self.add_check_action(parent_menu, "Smooth Lines", "line_smooth", 1)
        self.add_check_action(
            parent_menu, "Depth Cue (Fogging)", "depth_cue", 1
        )
        self.add_check_action(
            parent_menu, "Two Sided Lighting", "two_sided_lighting", 1
        )
        self.add_check_action(
            parent_menu, "Specular Reflections", "specular", 1.0
        )
        self.add_check_action(parent_menu, "Animation", "animation", 1)
        self.add_check_action(parent_menu, "Roving Detail", "roving_detail", 1)

    def build_setting_menu(self, parent_menu):
        label_fonts = [
            ("Sans", 5),
            ("Sans Oblique", 6),
            ("Sans Bold", 7),
            ("Sans Bold Oblique", 8),
            ("Serif", 9),
            ("Serif Oblique", 17),
            ("Serif Bold", 10),
            ("Serif Bold Oblique", 18),
            ("Mono", 11),
            ("Mono Oblique", 12),
            ("Mono Bold", 13),
            ("Mono Bold Oblique", 14),
            ("Gentium Roman", 15),
            ("Gentium Italic", 16),
        ]
        self.add_action(
            parent_menu, "Edit All...", "cmd_string", "edit_settings"
        )
        self.add_action(
            parent_menu, "Keyboard Shortcuts...", "cmd_string", "edit_shortcuts"
        )
        self.add_action(parent_menu, "Colors...", "cmd_string", "edit_colors")
        parent_menu.addSeparator()

        lbl_menu = parent_menu.addMenu("Label")
        size_menu = lbl_menu.addMenu("Size")
        self.add_radio_group(
            size_menu,
            [(f"{v} Point", v) for v in [10, 14, 18, 24, 36, 48, 72]],
            "label_size",
        )
        size_menu.addSeparator()
        self.add_radio_group(
            size_menu,
            [(f"{v} Angstrom", -v) for v in [0.3, 0.5, 1, 2, 4]],
            "label_size",
        )
        self.add_radio_group(
            lbl_menu.addMenu("Font"), label_fonts, "label_font_id"
        )
        self.add_radio_group(
            lbl_menu.addMenu("Color"),
            [("Front", -6), ("Back", -7)],
            "label_color",
        )
        self.add_check_action(lbl_menu, "Show Connectors", "label_connector")
        self.add_radio_group(
            lbl_menu.addMenu("Background Color"),
            [("None", -1), ("Back", -7), ("Front", -6)],
            "label_bg_color",
        )

        self._build_lines_sticks_layout(parent_menu.addMenu("Lines & Sticks"))
        self._build_cartoon_layout(parent_menu.addMenu("Cartoon"))
        self._build_ribbon_layout(parent_menu.addMenu("Ribbon"))
        self._build_surface_layout(parent_menu.addMenu("Surface"))

        vol_menu = parent_menu.addMenu("Volume")
        self.add_check_action(
            vol_menu, "Pre-integrated Rendering", "volume_mode"
        )
        self.add_radio_group(
            vol_menu.addMenu("Number of Layers"),
            [(f"{v:.0f}", v) for v in [100.0, 256.0, 500.0, 1000.0]],
            "volume_layers",
        )

        trans_menu = parent_menu.addMenu("Transparency")
        t_opts = [
            ("Off", 0.0),
            ("20%", 0.2),
            ("40%", 0.4),
            ("50%", 0.5),
            ("60%", 0.6),
            ("80%", 0.8),
        ]
        self.add_radio_group(
            trans_menu.addMenu("Surface"), t_opts, "transparency"
        )
        self.add_radio_group(
            trans_menu.addMenu("Sphere"), t_opts, "sphere_transparency"
        )
        self.add_radio_group(
            trans_menu.addMenu("Cartoon"), t_opts, "cartoon_transparency"
        )
        self.add_radio_group(
            trans_menu.addMenu("Stick"), t_opts, "stick_transparency"
        )
        trans_menu.addSeparator()
        for lab, values in [
            ("Uni-Layer", (2, 1, 0)),
            ("Multi-Layer", (1, 0, 1)),
            ("Multi-Layer (Real-time OIT)", (3, 0, -1)),
            ("Fast and Ugly", (0, 1, 0)),
        ]:
            self.add_action(trans_menu, lab, "transparency_combo", values)
        trans_menu.addSeparator()
        self.add_check_action(
            trans_menu, "Angle-dependent", "ray_transparency_oblique", 1.0
        )

        self._build_rendering_layout(parent_menu.addMenu("Rendering"))
        parent_menu.addSeparator()
        self.add_check_action(
            parent_menu.addMenu("PDB File Loading"),
            "Ignore PDB Segment Identifier",
            "ignore_pdb_segi",
            1,
        )

        cif_menu = parent_menu.addMenu("mmCIF File Loading")
        self.add_check_action(
            cif_menu, 'Use "auth" Identifiers', "cif_use_auth", 1
        )
        self.add_check_action(
            cif_menu, "Load Assembly (Biological Unit)", "assembly", "1", ""
        )
        self.add_check_action(
            cif_menu,
            'Bonding by "Chemical Component Dictionary"',
            "connect_mode",
            4,
            0,
        )

        map_menu = parent_menu.addMenu("Map File Loading")
        self.add_check_action(
            map_menu, "Normalize CCP4 Maps", "normalize_ccp4_maps", 1
        )
        self.add_check_action(
            map_menu, "Normalize O Maps", "normalize_o_maps", 1
        )

        parent_menu.addSeparator()
        auto_menu = parent_menu.addMenu("Auto-Show ...")
        self.add_check_action(
            auto_menu,
            "Cartoon/Sticks/Spheres by Classification",
            "auto_show_classified",
            -1,
            0,
        )
        auto_menu.addSeparator()
        self.add_check_action(
            auto_menu, "Auto-Show Lines", "auto_show_lines", 1
        )
        self.add_check_action(
            auto_menu, "Auto-Show Spheres", "auto_show_spheres", 1
        )
        self.add_check_action(
            auto_menu, "Auto-Show Nonbonded", "auto_show_nonbonded", 1
        )
        auto_menu.addSeparator()
        self.add_check_action(
            auto_menu, "Auto-Show New Selections", "auto_show_selections", 1
        )
        self.add_check_action(
            auto_menu, "Auto-Hide Selections", "auto_hide_selections", 1
        )

        self.add_check_action(
            parent_menu, "Auto-Zoom New Objects", "auto_zoom", 1
        )
        self.add_check_action(
            parent_menu, "Auto-Remove Hydrogens", "auto_remove_hydrogens", 1
        )
        parent_menu.addSeparator()
        self.add_check_action(parent_menu, "Show Text (Esc)", "text")
        self.add_check_action(parent_menu, "Overlay Text", "overlay")

    def build_scene_menu(self, parent_menu):
        self.add_action(parent_menu, "Scenes...", "cmd_string", "scene_panel")
        parent_menu.addSeparator()
        self.add_action(
            parent_menu, "Next [PgDn]", "scene_action", ("", "next")
        )
        self.add_action(
            parent_menu, "Previous [PgUp]", "scene_action", ("", "previous")
        )
        parent_menu.addSeparator()
        self.add_action(parent_menu, "Append", "scene_action", ("new", "store"))

        app_menu = parent_menu.addMenu("Append...")
        for lab, param in [
            ("Camera", "scene new, store, color=0, rep=0"),
            ("Color", "scene new, store, view=0, rep=0"),
            ("Reps", "scene new, store, view=0, color=0"),
            ("Reps + Color", "scene new, store, view=0"),
        ]:
            self.add_action(app_menu, lab, "cmd_string", param)
        self.add_action(
            parent_menu, "Insert Before", "scene_action", ("", "insert_before")
        )
        self.add_action(
            parent_menu, "Insert After", "scene_action", ("", "insert_after")
        )
        self.add_action(
            parent_menu, "Update", "scene_action", ("auto", "update")
        )
        parent_menu.addSeparator()
        self.add_action(
            parent_menu, "Delete", "scene_action", ("auto", "clear")
        )
        parent_menu.addSeparator()

        self._build_fkeys_scene_menu(parent_menu.addMenu("Recall"), "recall")
        self._build_fkeys_scene_menu(parent_menu.addMenu("Store"), "store")
        self._build_fkeys_scene_menu(parent_menu.addMenu("Clear"), "clear")
        parent_menu.addSeparator()
        self.add_check_action(parent_menu, "Buttons", "scene_buttons", 1)

        cache_menu = parent_menu.addMenu("Cache")
        for lab, mode in [
            ("Enable", "enable"),
            ("Optimize", "optimize"),
            ("Read Only", "read_only"),
            ("Disable", "disable"),
        ]:
            self.add_action(cache_menu, lab, "scene_cache", mode)

    def build_selection_mode_menu(self, parent_menu: QtWidgets.QMenu) -> None:
        """Build the Selection Mode sub-menu options.

        Args:
            parent_menu: The menu to add selection mode options to.
        """
        self.add_radio_group(
            parent_menu,
            [
                ("Atoms", 0),
                ("Residues", 1),
                ("Chains", 2),
                ("Segments", 3),
                ("Objects", 4),
                ("Molecules", 5),
                ("C-alphas", 6),
            ],
            "mouse_selection_mode",
        )

    def build_mouse_menu(self, parent_menu: QtWidgets.QMenu) -> None:
        """Build the complete Mouse menu.

        Args:
            parent_menu: The parent menu to populate.
        """
        tmp_selection_menu = parent_menu.addMenu("Selection Mode")
        self.build_selection_mode_menu(tmp_selection_menu)
        parent_menu.addSeparator()
        for tmp_lab, tmp_mode in [
            ("3 Button Motions", "three_button_motions"),
            ("3 Button Editing", "three_button_editing"),
            ("3 Button Viewing", "three_button_viewing"),
            ("3 Button Lights", "three_button_lights"),
            ("3 Button All Modes", "three_button_all_modes"),
            ("2 Button Editing", "two_button_editing"),
            ("2 Button Viewing", "two_button"),
            ("1 Button Viewing Mode", "one_button_viewing"),
            ("Emulate Maestro", "three_button_maestro"),
        ]:
            self.add_action(parent_menu, tmp_lab, "mouse_config", tmp_mode)
        parent_menu.addSeparator()
        self.add_check_action(
            parent_menu, "Virtual Trackball", "virtual_trackball"
        )
        self.add_check_action(parent_menu, "Show Mouse Grid", "mouse_grid")
        self.add_check_action(parent_menu, "Roving Origin", "roving_origin")

    def build_wizard_menu(self, parent_menu):
        self.add_action(parent_menu, "Appearance", "wizard", "appearance")
        self.add_action(parent_menu, "Measurement", "wizard", "measurement")
        mut_menu = parent_menu.addMenu("Mutagenesis")
        self.add_action(mut_menu, "Protein", "wizard", "mutagenesis")
        self.add_action(mut_menu, "Nucleic Acids", "wizard", "nucmutagenesis")
        self.add_action(parent_menu, "Pair Fitting", "wizard", "pair_fit")
        parent_menu.addSeparator()
        self.add_action(parent_menu, "Density", "wizard", "density")
        self.add_action(parent_menu, "Filter", "wizard", "filter")
        self.add_action(parent_menu, "Sculpting", "wizard", "sculpting")
        parent_menu.addSeparator()
        self.add_action(parent_menu, "Label", "wizard", "label")
        self.add_action(parent_menu, "Charge", "wizard", "charge")
        parent_menu.addSeparator()

        demo_menu = parent_menu.addMenu("Demo")
        for lab, val in [
            ("Representations", "reps"),
            ("Cartoon Ribbons", "cartoon"),
            ("Roving Detail", "roving"),
            ("Roving Density", "roving_density"),
            ("Transparency", "trans"),
            ("Ray Tracing", "ray"),
            ("Sculpting", "sculpt"),
            ("Scripted Animation", "anime"),
            ("Electrostatics", "elec"),
            ("Compiled Graphics Objects", "cgo"),
            ("Molscript/Raster3D Input", "raster3d"),
        ]:
            self.add_action(demo_menu, lab, "wizard_demo", val)
        demo_menu.addSeparator()
        self.add_action(demo_menu, "End Demonstration", "wizard_demo_finish")

    def build_help_menu(self, parent_menu):
        self.add_action(
            parent_menu,
            "PyMOL Command Reference",
            "url",
            "http://pymol.org/pymol-command-ref.html",
        )
        parent_menu.addSeparator()
        self.add_action(
            parent_menu, "Online Documentation", "url", "http://pymol.org/d/"
        )
        topics_menu = parent_menu.addMenu("Topics")
        for lab, topic in [
            ("Introductory Screencasts", "media:intro"),
            ("Core Commands", "command:core_set"),
            ("Settings", "setting"),
            ("Atom Selections", "selection"),
            ("Commands", "command"),
            ("Launching", "launch"),
            ("Concepts", "concept"),
            ("A.P.I. Methods", "api"),
        ]:
            self.add_action(topics_menu, lab, "help_topic", topic)
        parent_menu.addSeparator()
        for lab, target_url in [
            ("PyMOL Community Wiki", "http://www.pymolwiki.org"),
            (
                "PyMOL Mailing List",
                "https://lists.sourceforge.net/lists/listinfo/pymol-users",
            ),
            ("PyMOL Home Page", "http://www.pymol.org"),
        ]:
            self.add_action(parent_menu, lab, "url", target_url)
        parent_menu.addSeparator()
        self.add_action(parent_menu, "About PyMOL", "cmd_string", "about")
        self.add_action(
            parent_menu,
            "Sponsorship Information",
            "url",
            "http://pymol.org/funding.html",
        )
        self.add_action(
            parent_menu, "How to Cite PyMOL", "url", "http://pymol.org/citing"
        )

    def _build_fragments_layout(self, menu):
        for lab, f_name, atom, mode in [
            ("Acetylene [Alt-J]", "acetylene", 2, 0),
            ("Amide N->C [Alt-1]", "formamide", 3, 1),
            ("Amide C->N [Alt-2]", "formamide", 5, 0),
            ("Carbonyl [Alt-0]", "formaldehyde", 2, 0),
            ("Cyclobutyl [Alt-4]", "cyclobutane", 4, 0),
            ("Cyclopentyl [Alt-5]", "cyclopentane", 5, 0),
            ("Cyclopentadiene [Alt-8]", "cyclopentadiene", 5, 0),
            ("Cyclohexyl [Alt-6]", "cyclohexane", 7, 0),
            ("Cycloheptyl [Alt-7]", "cycloheptane", 8, 0),
            ("Methane [Ctrl-Shift-M]", "methane", 1, 0),
            ("Sulfonyl [Alt-3]", "sulfone", 3, 1),
        ]:
            self.add_action(menu, lab, "attach_fragment", (f_name, atom, mode))
        menu.addSeparator()
        for lab, elem, geom, val in [
            ("Bromine [Ctrl-Shift-B]", "Br", 1, 1),
            ("Carbon [Ctrl-Shift-C]", "C", 4, 4),
            ("Chlorine [Ctrl-Shift-L]", "Cl", 1, 1),
            ("Fluorine [Ctrl-Shift-F]", "F", 1, 1),
            ("Iodine [Ctrl-Shift-I]", "I", 1, 1),
            ("Nitrogen [Ctrl-Shift-N]", "N", 4, 3),
            ("Oxygen [Ctrl-Shift-O]", "O", 4, 2),
            ("Sulfer [Ctrl-Shift-S]", "S", 2, 2),
            ("Phosphorus [Ctrl-Shift-P]", "P", 4, 3),
        ]:
            self.add_action(menu, lab, "replace_element", (elem, geom, val))

    def _build_residues_layout(self, menu):
        for lab, r_name in [
            ("Acetyl [Alt-B]", "ace"),
            ("Alanine [Alt-A]", "ala"),
            ("Amine", "nhh"),
            ("Aspartate [Alt-D]", "asp"),
            ("Asparagine [Alt-N]", "asn"),
            ("Arginine [Alt-R]", "arg"),
            ("Cysteine [Alt-C]", "cys"),
            ("Glutamate [Alt-E]", "glu"),
            ("Glutamine [Alt-Q]", "gln"),
            ("Glycine [Alt-G]", "gly"),
            ("Histidine [Alt-H]", "his"),
            ("Isoleucine [Alt-I]", "ile"),
            ("Leucine [Alt-L]", "leu"),
            ("Lysine [Alt-K]", "lys"),
            ("Methionine [Alt-M]", "met"),
            ("N-Methyl [Alt-Z]", "nme"),
            ("Phenylalanine [Alt-F]", "phe"),
            ("Proline [Alt-P]", "pro"),
            ("Serine [Alt-S]", "ser"),
            ("Threonine [Alt-T]", "thr"),
            ("Tryptophan [Alt-W]", "trp"),
            ("Tyrosine [Alt-Y]", "tyr"),
            ("Valine [Alt-V]", "val"),
        ]:
            self.add_action(menu, lab, "attach_amino_acid", r_name)
        menu.addSeparator()
        self.add_radio_group(
            menu,
            [
                ("Helix", 1),
                ("Antiparallel Beta Sheet", 2),
                ("Parallel Beta Sheet", 3),
            ],
            "secondary_structure",
        )

    def _build_sculpting_layout(self, menu):
        self.add_check_action(menu, "Auto-Sculpting", "auto_sculpt")
        self.add_check_action(menu, "Sculpting", "sculpting")
        menu.addSeparator()
        self.add_action(menu, "Activate", "cmd_string", "sculpt_activate all")
        self.add_action(
            menu, "Deactivate", "cmd_string", "sculpt_deactivate all"
        )
        self.add_action(menu, "Clear Memory", "cmd_string", "sculpt_purge")
        menu.addSeparator()
        self.add_radio_group(
            menu,
            [("1 Cycle per Update", 1)]
            + [
                (f"{v} Cycles per Update", v)
                for v in [3, 10, 33, 100, 333, 1000]
            ],
            "sculpting_cycles",
        )
        menu.addSeparator()
        self.add_radio_group(
            menu,
            [
                ("Bonds Only", 0x01),
                ("Bonds and Angles Only", 0x01 | 0x02),
                ("Local Geometry Only", 0x20 - 1),
                ("All Except VDW", ~(0x20 | 0x40)),
                ("All Except 1-4 VDW and Torsions", ~(0x40 | 0x80)),
                ("All Terms", 0xFF),
            ],
            "sculpt_field_mask",
        )

    def _build_movie_programs_layout(self, menu):
        cam_loop = menu.addMenu("Camera Loop")
        nutate_menu = cam_loop.addMenu("Nutate")
        for lab, s_expr in [
            ("15 deg. over 4 sec.", "movie.add_nutate(4,15,start=%d)"),
            ("15 deg. over 8 sec.", "movie.add_nutate(8,15,start=%d)"),
            ("15 deg. over 12 sec.", "movie.add_nutate(12,15,start=%d)"),
            ("30 deg. over 4 sec.", "movie.add_nutate(4,30,start=%d)"),
            ("30 deg. over 8 sec.", "movie.add_nutate(8,30,start=%d)"),
            ("30 deg. over 12 sec.", "movie.add_nutate(12,30,start=%d)"),
            ("30 deg. over 16 sec.", "movie.add_nutate(16,30,start=%d)"),
            ("60 deg. over 8 sec.", "movie.add_nutate(8,60,start=%d)"),
            ("60 deg. over 16 sec.", "movie.add_nutate(16,60,start=%d)"),
            ("60 deg. over 24 sec.", "movie.add_nutate(24,60,start=%d)"),
            ("60 deg. over 32 sec.", "movie.add_nutate(32,60,start=%d)"),
        ]:
            self.add_action(nutate_menu, lab, "cmd_string", s_expr)
        for axis in ["x", "y"]:
            rock_m = cam_loop.addMenu(f"{axis.upper()}-Rock")
            for deg, seconds in [
                (30, (2, 4, 8)),
                (60, (4, 8, 16)),
                (90, (6, 12, 24)),
                (120, (8, 16, 32)),
                (180, (12, 24, 48)),
            ]:
                for s in seconds:
                    val = 179.99 if deg == 180 else deg
                    self.add_action(
                        rock_m,
                        f"{deg} deg. over {s} sec.",
                        "cmd_string",
                        f"movie.add_rock({s},{val},axis='{axis}',start=%d)",
                    )
            roll_m = cam_loop.addMenu(f"{axis.upper()}-Roll")
            for s in [4, 8, 16, 32]:
                self.add_action(
                    roll_m,
                    f"{s} seconds",
                    "cmd_string",
                    f"movie.add_roll({s}.0,axis='{axis}',start=%d)",
                )
        menu.addSeparator()
        scene_loop = menu.addMenu("Scene Loop")
        for type_lab, r_val in [("Nutate", 4), ("X-Rock", 2), ("Y-Rock", 1)]:
            sl_m = scene_loop.addMenu(type_lab)
            for angle, seconds in (
                (30, (2, 4, 8)),
                (60, (4, 8, 16)),
                (90, (6, 12, 24)),
                (120, (8, 16, 32)),
            ):
                for sec in seconds:
                    self.add_action(
                        sl_m,
                        f"{angle} deg. over {sec} sec.",
                        "cmd_string",
                        f"set sweep_angle,{angle};cmd.movie.add_scenes(None, {sec}, rock={r_val}, start=%d)",
                    )
        steady_m = scene_loop.addMenu("Steady")
        for val in [1, 2, 4, 8, 12, 16, 24]:
            self.add_action(
                steady_m,
                f"{val} seconds each",
                "cmd_string",
                f"movie.add_scenes(None,{val:.1f},rock=0,start=%d)",
            )
        menu.addSeparator()
        for loop_lab, fmt in [
            ("State Loop", "movie.add_state_loop(%d, %d"),
            ("State Sweep", "movie.add_state_sweep(%d, %d"),
        ]:
            l_menu = menu.addMenu(loop_lab)
            for speed in [1, 2, 3, 4, 8, 16]:
                sp_m = l_menu.addMenu(
                    "Full Speed" if speed == 1 else f"1/{speed} Speed"
                )
                for pause in [0, 1, 2, 4]:
                    self.add_action(
                        sp_m,
                        f"{pause} second pause" if pause else "no pause",
                        "cmd_string",
                        (fmt % (speed, pause)) + ", start=%d)",
                    )

    def _build_lines_sticks_layout(self, menu):
        self.add_check_action(menu, "Ball and Stick", "stick_ball", 1)
        self.add_radio_group(
            menu.addMenu("Ball and Stick Ratio"),
            [("1.0", 1.0), ("1.5", 1.5), ("VDW", -1.0)],
            "stick_ball_ratio",
        )
        menu.addSeparator()
        self.add_radio_group(
            menu.addMenu("Zero Order Bonds"),
            [("Hide", 0), ("Dashed", 1), ("Solid", 2)],
            "valence_zero_mode",
        )
        self.add_radio_group(
            menu.addMenu("Zero Order Stick Scale"),
            [("0.1", 0.1), ("0.2", 0.2), ("0.3", 0.3), ("1.0", 1.0)],
            "valence_zero_scale",
        )
        menu.addSeparator()
        self.add_radio_group(
            menu.addMenu("Stick Radius"),
            [("0.1", 0.1), ("0.2", 0.2), ("0.25", 0.25)],
            "stick_radius",
        )
        self.add_radio_group(
            menu.addMenu("Stick Hydrogen Scale"),
            [("0.4", 0.4), ("1.0", 1.0)],
            "stick_h_scale",
        )
        menu.addSeparator()
        self.add_radio_group(
            menu.addMenu("Line Width"),
            [("1.0", 1.0), ("1.49", 1.49), ("3.0", 3.0)],
            "line_width",
        )
        self.add_check_action(
            menu, "Lines As Cylinders", "line_as_cylinders", 1
        )

    def _build_cartoon_layout(self, menu):
        r_menu = menu.addMenu("Rings and Bases")
        self.add_radio_group(
            r_menu,
            [
                ("Filled Rings (Round Edges)", 1),
                ("Filled Rings (Flat Edges)", 2),
                ("Filled Rings (with Border)", 3),
                ("Spheres", 4),
                ("Base Ladders", 0),
            ],
            "cartoon_ring_mode",
        )
        r_menu.addSeparator()
        self.add_radio_group(
            r_menu,
            [
                ("Bases and Sugars", 1),
                ("Bases Only", 2),
                ("Non-protein Rings", 3),
                ("All Rings", 4),
            ],
            "cartoon_ring_finder",
        )
        r_menu.addSeparator()
        self.add_radio_group(
            r_menu,
            [("Transparent Rings", 0.5), ("Default", -1)],
            "cartoon_ring_transparency",
        )
        self.add_check_action(
            menu, "Side Chain Helper", "cartoon_side_chain_helper", 1
        )
        self.add_check_action(menu, "Round Helices", "cartoon_round_helices", 1)
        self.add_check_action(menu, "Fancy Helices", "cartoon_fancy_helices", 1)
        self.add_check_action(
            menu, "Cylindrical Helices", "cartoon_cylindrical_helices", 1
        )
        self.add_check_action(menu, "Flat Sheets", "cartoon_flat_sheets", 1)
        self.add_check_action(menu, "Fancy Sheets", "cartoon_fancy_sheets", 1)
        self.add_check_action(menu, "Smooth Loops", "cartoon_smooth_loops", 1)
        self.add_check_action(
            menu, "Discrete Colors", "cartoon_discrete_colors", 1
        )
        self.add_check_action(
            menu, "Highlight Color", "cartoon_highlight_color", 104, -1
        )
        self.add_radio_group(
            menu.addMenu("Sampling"),
            [("Atom count dependent", -1), ("2", 2), ("7", 7), ("14", 14)],
            "cartoon_sampling",
        )
        self.add_radio_group(
            menu.addMenu("Gap Cutoff"),
            [("0", 0), ("5", 5), ("10", 10), ("20", 20)],
            "cartoon_gap_cutoff",
        )

    def _build_ribbon_layout(self, menu):
        self.add_check_action(
            menu, "Side Chain Helper", "ribbon_side_chain_helper", 1
        )
        self.add_check_action(menu, "Trace Atoms", "ribbon_trace_atoms", 1)
        menu.addSeparator()
        self.add_radio_group(
            menu, [("As Lines", 0), ("As Cylinders", 1)], "ribbon_as_cylinders"
        )
        self.add_radio_group(
            menu.addMenu("Cylinder Radius"),
            [
                ("Match Line Width", 0.0),
                ("0.2 Angstrom", 0.2),
                ("0.5 Angstrom", 0.5),
                ("1.0 Angstrom", 1.0),
            ],
            "ribbon_radius",
        )

    def _build_surface_layout(self, menu):
        self.add_radio_group(
            menu.addMenu("Color"),
            [
                ("White", 0),
                ("Light Gray", 4236),
                ("Gray", 25),
                ("Default (Atomic)", -1),
            ],
            "surface_color",
        )
        self.add_radio_group(
            menu, [("Dot", 1), ("Wireframe", 2), ("Solid", 0)], "surface_type"
        )
        menu.addSeparator()
        self.add_radio_group(
            menu,
            [
                ("Cavities and Pockets Only", 1),
                ("Cavities and Pockets (Culled)", 2),
            ],
            "surface_cavity_mode",
        )
        self.add_radio_group(
            menu.addMenu("Cavity Detection Radius"),
            [("7 Angstrom", 7)]
            + [(f"{v} Solvent Radii", -v) for v in [3, 4, 5, 6, 8, 10, 20]],
            "surface_cavity_radius",
        )
        self.add_radio_group(
            menu.addMenu("Cavity Detection Cutoff"),
            [(f"{v} Solvent Radii", -v) for v in [1, 2, 3, 4, 5]],
            "surface_cavity_cutoff",
        )
        self.add_radio_group(
            menu, [("Exterior (Normal)", 0)], "surface_cavity_mode"
        )
        menu.addSeparator()
        self.add_check_action(menu, "Solvent Accessible", "surface_solvent", 1)
        menu.addSeparator()
        self.add_check_action(menu, "Smooth Edges", "surface_smooth_edges", 1)
        self.add_check_action(menu, "Edge Proximity", "surface_proximity", 1)
        menu.addSeparator()
        self.add_radio_group(
            menu,
            [
                ("Ignore None", 1),
                ("Ignore HETATMs", 0),
                ("Ignore Hydrogens", 2),
                ("Ignore Unsurfaced", 3),
            ],
            "surface_mode",
        )

    def _build_rendering_layout(self, menu):
        self.add_check_action(menu, "OpenGL 2.0 Shaders", "use_shaders", 1)
        menu.addSeparator()
        self.add_check_action(menu, "Antialias (Ray Tracing)", "antialias", 1)
        self.add_radio_group(
            menu.addMenu("Antialias (Real Time)"),
            [("off", 0), ("FXAA", 1), ("SMAA", 2)],
            "antialias_shader",
        )
        menu.addSeparator()
        self.add_action(menu, "Modernize", "modernize_rendering")
        menu.addSeparator()
        shd_menu = menu.addMenu("Shadows")
        for val in [
            "none",
            "light",
            "medium",
            "heavy",
            "black",
            "matte",
            "soft",
            "occlusion",
            "occlusion2",
        ]:
            self.add_action(shd_menu, val.title(), "ray_shadows", val)
        tex_opts = [
            ("None", 0),
            ("Matte 1", 1),
            ("Matte 2", 4),
            ("Swirl 1", 2),
            ("Swirl 2", 3),
            ("Fiber", 5),
        ]
        self.add_radio_group(menu.addMenu("Texture"), tex_opts, "ray_texture")
        self.add_radio_group(
            menu.addMenu("Interior Texture"), tex_opts, "ray_interior_texture"
        )
        self.add_radio_group(
            menu.addMenu("Memory"),
            [
                ("Use Less (slower)", 70),
                ("Use Standard Amount", 100),
                ("Use More (faster)", 170),
                ("Use Even More", 230),
                ("Use Most", 300),
            ],
            "hash_max",
        )
        menu.addSeparator()
        self.add_check_action(menu, "Cull Backfaces", "backface_cull", 1)
        self.add_check_action(
            menu, "Opaque Interiors", "ray_interior_color", 74, -1
        )

    def _build_fkeys_scene_menu(self, menu, action_name):
        for i in range(1, 13):
            self.add_action(
                menu, f"F{i}", "scene_action", (f"F{i}", action_name)
            )


# </editor-fold>


# from __future__ import annotations
#
# import pathlib
#
# from pymol_copilot.gui.qt import QtGui
# from pymol_copilot.gui.qt import QtWidgets
# from pymol_copilot.gui.qt import ui_defaults
# from pymol_copilot.gui.qt import icons
# from pymol_copilot.gui.qt.model import list_model
# from pymol_copilot.gui.qt.model import table_model
# from pymol_copilot.gui.qt.widgets import color_grid, pml_command_line, panel
# from pymol_copilot.gui.qt.widgets import command_bar
# from pymol_copilot.gui.qt.widgets import flyout
# from pymol_copilot.gui.qt.widgets import input_bar
# from pymol_copilot.gui.qt.widgets import list_view
# from pymol_copilot.gui.qt.widgets import table_view
# from pymol_copilot.gui.qt.widgets import viewer
# from pymol_copilot.gui.qt.widgets import pml_menu_bar
# from pymol_copilot.ai.app.chat_controller import ChatController
# from pymol_copilot.ai.backend.config import InferenceConfig
# from pymol_copilot.ai.execution.execution_worker import ExecutionWorker
# from pymol_copilot.ai.execution.pymol_session import InjectedPyMOLSession
#
#
# class MainWindow(QtWidgets.QMainWindow):
#     """Main window for the PyMOL Copilot application."""
#
#     def __init__(self) -> None:
#         """Initializes the main window and sets up the user interface."""
#         super().__init__()
#         self.viewer = viewer.Viewer()
#         self._menu_bar = pml_menu_bar.PyMOLMenuBar(self, self.viewer.cmd)
#
#         # --- Command buttons
#         self._open_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "open"),
#         )
#         self._save_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "save"),
#         )
#         self._undo_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "undo"),
#         )
#         self._redo_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "redo"),
#         )
#         self._build_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "build"),
#         )
#         self._movie_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "movie"),
#         )
#         self._settings_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "settings"),
#         )
#         self._mouse_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "mouse"),
#         )
#         self._wizard_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "wizard"),
#         )
#         self._help_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "help"),
#         )
#         self._ai_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "ai"),
#         )
#
#         self._command_bar = command_bar.CommandBar(
#             [
#                 self._open_cmd_button,
#                 self._save_cmd_button,
#                 self._undo_cmd_button,
#                 self._redo_cmd_button,
#                 self._build_cmd_button,
#                 self._movie_cmd_button,
#                 self._settings_cmd_button,
#                 self._mouse_cmd_button,
#                 self._wizard_cmd_button,
#                 self._ai_cmd_button,
#             ]
#         )
#         self._more_cmd_button = command_bar.CommandBarActionButton(
#             icons.icon("pymol_copilot.gui.qt", "more_vertical"),
#         )
#         self._command_bar.append_command_button(self._more_cmd_button)
#         self._command_bar.append_command_button(self._help_cmd_button)
#
#         self._content_layout = QtWidgets.QHBoxLayout()
#
#         self._conversation_panel = panel.PmlCopilotPanel()
#
#         tmp_model_path = (
#             pathlib.Path(__file__).parent.parent.parent
#             / "ai"
#             / "training"
#             / "models"
#             / "cbiomol-pymol-assistant-Q4_K_M.gguf"
#         )
#         self._ai_config = InferenceConfig(
#             model_path=tmp_model_path,
#             n_ctx=8192,
#             mock=False,
#         )
#         self._pymol_session = InjectedPyMOLSession(self.viewer)
#         self._execution_worker = ExecutionWorker(self._pymol_session, self)
#
#         self._chat_controller = ChatController(
#             panel=self._conversation_panel,
#             config=self._ai_config,
#             execution_worker=self._execution_worker,
#             parent=self,
#         )
#
#         self._input_bar = input_bar.InputBar()
#         self._command_line = pml_command_line.PmlCommandLine(self.viewer.cmd)
#
#         self._setup_ui()
#         self.setMinimumSize(600, 400)
#         self.setWindowIcon(icons.icon("pymol_copilot.gui.qt", "logo_icon"))
#         self.setWindowTitle("Open-Source PyMOL Copilot")
#         self.resize(800, 600)
#         # self._setup_ui_mock()
#
#     def _setup_ui(self) -> None:
#         # <editor-fold desc="General central layout">
#         tmp_central_widget = QtWidgets.QWidget()
#         self.setCentralWidget(tmp_central_widget)
#         tmp_layout = QtWidgets.QVBoxLayout()
#         tmp_layout.setContentsMargins(*ui_defaults.default_contents_margins())
#         tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
#         tmp_central_widget.setLayout(tmp_layout)
#         # </editor-fold>
#         self._content_layout.setContentsMargins(
#             *ui_defaults.EMPTY_CONTENTS_MARGINS
#         )
#         self._content_layout.setSpacing(ui_defaults.EMPTY_SPACING)
#
#         self.setMenuBar(self._menu_bar)
#
#         tmp_main_content_layout = QtWidgets.QVBoxLayout()
#         tmp_main_content_layout.setContentsMargins(
#             *ui_defaults.EMPTY_CONTENTS_MARGINS
#         )
#         tmp_main_content_layout.setSpacing(ui_defaults.EMPTY_SPACING)
#
#         tmp_layout.addWidget(self._command_bar)
#         tmp_input_bar_wrapper_layout = QtWidgets.QHBoxLayout()
#         tmp_input_bar_wrapper_layout.setContentsMargins(120, 0, 120, 0)
#         tmp_input_bar_wrapper_layout.addWidget(self._input_bar)
#         tmp_main_content_layout.addLayout(tmp_input_bar_wrapper_layout)
#         tmp_main_content_layout.addWidget(self.viewer)
#         tmp_main_content_layout.addWidget(self._command_line)
#         self._content_layout.addLayout(tmp_main_content_layout)
#         self._content_layout.addWidget(self._conversation_panel)
#         tmp_layout.addLayout(self._content_layout)
#
#         # tmp_highlight_btn = command_bar.CommandBarActionButton(
#         #     icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
#         #     "Highlight",
#         # )
#         # tmp_highlight_btn.clicked.connect(self.highlight_sele)
#         # tmp_layout.addWidget(tmp_highlight_btn)
#
#         # self.input = input_bar.InputBar()
#         # tmp_layout.addWidget(self.input)
#
#     def highlight_sele(self) -> None:
#         """Highlights the selected molecule residue region."""
#         # self.viewer.highlight_selection("/1DPX//A/20-25")
#         # self.viewer.cmd.select("highlighted", "/1DPX//A/20-25")
#         self.viewer.highlight_selection("/1DPX//A/20-25+40-42")
#         self.viewer.cmd.select("highlighted", "/1DPX//A/20-25+40-42")
#
#     def _setup_ui_mock(self) -> None:
#         """Creates and arranges the GUI components."""
#         self._setup_menus()
#
#         tmp_central_widget = QtWidgets.QWidget()
#         self.setCentralWidget(tmp_central_widget)
#
#         tmp_layout = QtWidgets.QVBoxLayout()
#         tmp_central_widget.setLayout(tmp_layout)
#
#         tmp_split_btn = command_bar.CommandBarSplitButton(
#             icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"), "Home"
#         )
#         menu = QtWidgets.QMenu(tmp_split_btn)
#         menu.addAction("First action")
#         menu.addAction("Second action")
#         menu.addSeparator()
#         menu.addAction("Third action")
#         tmp_split_btn.set_menu(menu)
#
#         # --- Flyout example ---
#         tmp_flyout_btn = command_bar.CommandBarSplitButton(
#             icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"), "Options"
#         )
#         tmp_flyout = flyout.FlyoutFrame(shadow=False)
#         tmp_flyout_content = QtWidgets.QWidget()
#         tmp_flyout_layout = QtWidgets.QVBoxLayout(tmp_flyout_content)
#         tmp_flyout_layout.setSpacing(4)
#         tmp_flyout_layout.setContentsMargins(0, 0, 0, 0)
#         tmp_flyout_layout.addWidget(QtWidgets.QLabel("Display options"))
#         tmp_flyout_layout.addWidget(QtWidgets.QCheckBox("Show hydrogen atoms"))
#         tmp_flyout_layout.addWidget(QtWidgets.QCheckBox("Show surface"))
#         tmp_flyout_layout.addWidget(QtWidgets.QCheckBox("Show labels"))
#         tmp_flyout.set_content(tmp_flyout_content)
#         tmp_flyout_btn.set_flyout(tmp_flyout)
#
#         tmp_flyout_plus_btn = command_bar.CommandToggleSplitButton(
#             icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
#             "Options+",
#         )
#         tmp_flyout_plus_btn.set_flyout(tmp_flyout)
#         # ----------------------
#
#         tmp_dropdown_menu_btn = command_bar.CommandBarDropdownButton(
#             icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
#             "Export",
#             command_bar.CommandBarButtonStyle.TEXT_BESIDE,
#         )
#         tmp_export_menu = QtWidgets.QMenu(tmp_dropdown_menu_btn)
#         tmp_export_menu.addAction("Export as PNG")
#         tmp_export_menu.addAction("Export as SVG")
#         tmp_export_menu.addSeparator()
#         tmp_export_menu.addAction("Export session...")
#         tmp_dropdown_menu_btn.set_menu(tmp_export_menu)
#
#         tmp_dropdown_flyout_btn = command_bar.CommandBarDropdownButton(
#             icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
#             "View",
#             command_bar.CommandBarButtonStyle.TEXT_BESIDE,
#         )
#         tmp_list_flyout = flyout.FlyoutFrame(shadow=False)
#         tmp_dropdown_flyout_content = QtWidgets.QWidget()
#         tmp_dropdown_flyout_layout = QtWidgets.QVBoxLayout(
#             tmp_dropdown_flyout_content
#         )
#         tmp_dropdown_flyout_layout.setSpacing(4)
#         tmp_dropdown_flyout_layout.setContentsMargins(0, 0, 0, 0)
#         tmp_dropdown_flyout_layout.addWidget(QtWidgets.QLabel("View options"))
#         tmp_dropdown_flyout_layout.addWidget(
#             QtWidgets.QCheckBox("Cartoon representation")
#         )
#         tmp_dropdown_flyout_layout.addWidget(
#             QtWidgets.QCheckBox("Stick representation")
#         )
#         tmp_list_flyout.set_content(tmp_dropdown_flyout_content)
#         tmp_dropdown_flyout_btn.set_flyout(tmp_list_flyout)
#
#         tmp_toggle_btn = command_bar.CommandBarToggleButton(
#             icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
#             "Labels",
#             command_bar.CommandBarButtonStyle.TEXT_BESIDE,
#         )
#
#         tmp_highlight_btn = command_bar.CommandBarDropdownButton(
#             icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
#             "Highlight",
#             command_bar.CommandBarButtonStyle.ICON_ONLY,
#         )
#         tmp_list_flyout = flyout.FlyoutFrame(shadow=False)
#         tmp_list_flyout_content = QtWidgets.QWidget()
#         tmp_list_flyout_layout = QtWidgets.QVBoxLayout(tmp_list_flyout_content)
#         tmp_list_flyout_layout.setSpacing(4)
#         tmp_list_flyout_layout.setContentsMargins(0, 0, 0, 0)
#
#         model = list_model.ListModel(initial_data=["Alice", "Bob", "Carol"])
#         # List view with search:
#         search_view = list_view.ListViewWithSearch()
#         search_view.set_model(model)
#         search_view.set_checkboxes_enabled(True)
#         tmp_list_flyout_layout.addWidget(search_view)
#         tmp_list_flyout.set_content(tmp_list_flyout_content)
#         tmp_highlight_btn.set_flyout(tmp_list_flyout)
#
#         tmp_highlight_color_btn = command_bar.CommandBarDropdownButton(
#             icons.icon("pymol_copilot.gui.qt", "add_photo_alternate"),
#             "Color",
#             command_bar.CommandBarButtonStyle.ICON_ONLY,
#         )
#         tmp_color = color_grid.ColorFlyout()
#         tmp_highlight_color_btn.set_flyout(tmp_color)
#
#         tmp_command_bar = command_bar.CommandBar(
#             [
#                 tmp_highlight_btn,
#                 tmp_highlight_color_btn,
#                 tmp_split_btn,
#                 tmp_flyout_btn,
#                 tmp_dropdown_menu_btn,
#                 tmp_dropdown_flyout_btn,
#                 tmp_toggle_btn,
#                 tmp_flyout_plus_btn,
#             ],
#             tmp_central_widget,
#         )
#         tmp_layout.addWidget(tmp_command_bar)
#         # --- Begin content
#         tmp_input_box = input_bar.InputBar()
#         tmp_layout.addWidget(tmp_input_box)
#
#         class Job:
#             """Represent a mock job for the table view demo."""
#
#             def __init__(self, name: str, status: str, project: str) -> None:
#                 """Initialize the job.
#
#                 Args:
#                     name: The job name.
#                     status: The job status.
#                     project: The project name.
#                 """
#                 self.name = name
#                 self.status = status
#                 self.project = project
#
#         class JobTableModel(table_model.TableModel):
#             """Table model for mock jobs."""
#
#             def _cell_data(self, item: object, column: int) -> object:
#                 """Return display data for a cell.
#
#                 Args:
#                     item: The job item.
#                     column: The column index.
#
#                 Returns:
#                     The display string.
#                 """
#                 if isinstance(item, Job):
#                     return [item.name, item.status, item.project][column]
#                 return ""
#
#         tmp_job_model = JobTableModel(
#             column_headers=["Name", "Status", "Project"]
#         )
#         tmp_job_items: list[object] = [
#             Job("Home", "Running", "PyMOL"),
#             Job("Align", "Queued", "cBioMOL"),
#             Job("Render", "Completed", "Copilot"),
#         ]
#         tmp_job_model.add_rows(tmp_job_items)
#         tmp_table_view = table_view.TableView()
#         tmp_table_view.set_model(tmp_job_model)
#         tmp_table_view.set_checkboxes_enabled(True)
#         tmp_layout.addWidget(tmp_table_view)
#
#         # --- End content
#         tmp_layout.addStretch(1)
#         # tmp_label = QtWidgets.QLabel("PyMOL Copilot")
#         # tmp_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         # tmp_font = QtGui.QFont("Segoe UI", 24, QtGui.QFont.Weight.Bold)
#         # tmp_label.setFont(tmp_font)
#         # tmp_layout.addWidget(tmp_label)
#         #
#         # tmp_description = QtWidgets.QLabel(
#         #     "A professional AI assistant for PyMOL."
#         # )
#         # tmp_description.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         # tmp_layout.addWidget(tmp_description)
#         #
#         # tmp_input_bar = input_bar.InputBar()
#         # tmp_layout.addWidget(tmp_input_bar)
#         #
#         # tmp_status_bar = self.statusBar()
#         # if tmp_status_bar is not None:
#         #     tmp_status_bar.showMessage("Application Loaded")
#
#     def _setup_menus(self) -> None:
#         """Sets up the application menu bar."""
#         tmp_menu_bar = self.menuBar()
#
#         if tmp_menu_bar is None:
#             return
#
#         # File Menu
#         tmp_file_menu = tmp_menu_bar.addMenu("&File")
#
#         if tmp_file_menu is None:
#             return
#
#         tmp_exit_action = QtGui.QAction("&Exit", self)
#         tmp_exit_action.setShortcut("Ctrl+Q")
#         tmp_exit_action.triggered.connect(self.close)
#         tmp_file_menu.addAction(tmp_exit_action)
