"""
PyMOL Native QMenuBar System - 100% Self-Contained MVC Architecture for PyQt6
Provides direct drop-in implementation via `self.setMenuBar(PyMOLMenuBar(self, cmd))`.
"""

import sys
import os
import re
import pathlib
import tempfile
import webbrowser
from collections import defaultdict

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QAction, QActionGroup


# ==============================================================================
# FALLBACK UTILITIES & GUARDS (Ensures Standalone Decoupled Execution)
# ==============================================================================


class UpdateLock:
    """Prevents circular update triggers during fast sequential GUI modifications."""

    def __init__(self, exceptions=()):
        self.exceptions = exceptions
        self.locked = False

    def skipIfCircular(self, func):
        def wrapper(*args, **kwargs):
            if self.locked:
                return
            self.locked = True
            try:
                return func(*args, **kwargs)
            except tuple(self.exceptions):
                pass
            finally:
                self.locked = False

        return wrapper


class PopupOnException:
    """Context manager and decorator to capture framework runtime execution exceptions."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            print(f"[PyMOLMenuBar Exception Trap]: {exc_val}")
            return True

    @staticmethod
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"[PyMOLMenuBar Exception Loop]: {e}")

        return wrapper


# ==============================================================================
# 1. MODEL LAYER (Application State & Configuration Indexes)
# ==============================================================================


class PyMOLMenuBarModel:
    """Manages tracking states, operational directories, history caches, and data configurations."""

    def __init__(self, cmd, desktop_gui=None):
        self.cmd = cmd
        self.desktop_gui = desktop_gui
        self._initialdir = ""

        # Action/Signal Map Caches
        self.history = [""]
        self.history_cur = 0
        self.movie_start = 0
        self.movie_command = None
        self._recent_filenames_db = None

    @property
    def initialdir(self):
        """Keeps current local working files targeted relative to user environment updates."""
        return self._initialdir or os.getcwd()

    @initialdir.setter
    def initialdir(self, value):
        self._initialdir = value

    def lazy_init_recent_db(self):
        """Safely initializes embedded recent file tracking storage index configuration schemas."""
        if self._recent_filenames_db is not None:
            return self._recent_filenames_db is not False

        db_directory = os.path.expanduser("~/.pymol")
        db_filepath = os.path.join(db_directory, "recent.db")

        try:
            os.makedirs(db_directory, exist_ok=True)
            import sqlite3

            db = sqlite3.connect(db_filepath)
            db.cursor().execute(
                "CREATE TABLE IF NOT EXISTS recent (filename text unique, timestamp integer)"
            )
            self._recent_filenames_db = db
            return True
        except BaseException as e:
            print(" Warning: failed to connect to recent DB:", e)
            self._recent_filenames_db = False
            return False


# ==============================================================================
# 2. CONTROLLER LAYER (Business Logic Transactions & Operations Routing)
# ==============================================================================


class PyMOLMenuBarController:
    """Processes operational slots, system commands, input events, and form updates."""

    def __init__(self, model):
        self.model = model
        self.view = None

        # State indicators for dynamically held modal components
        self.active_color_dialog = None
        self.active_render_dialog = None

    def set_view(self, view):
        self.view = view

    # --- Session Windows Management ---
    def new_window(self, extra_argv=()):
        import pymol

        python = sys.executable
        if os.path.isfile(python + "w"):
            python += "w"
        args = [
            python,
            pymol.__file__,
            "-N",
            pymol.invocation.options.gui,
        ] + list(extra_argv)
        os.spawnv(os.P_NOWAITO, args[0], args)

    def confirm_quit(self):
        QtWidgets.QApplication.instance().quit()

    # --- Disk Workspace Actions ---
    def file_open(self):
        fnames = QtWidgets.QFileDialog.getOpenFileNames(
            self.model.desktop_gui, "Open file", self.model.initialdir
        )[0]
        partial = 0
        for fname in fnames:
            if self.model.desktop_gui and hasattr(
                self.model.desktop_gui, "load_dialog"
            ):
                if not self.model.desktop_gui.load_dialog(
                    fname, partial=partial
                ):
                    break
            else:
                self.model.cmd.load(fname, partial=partial)
            partial = 1

    def file_fetch_pdb(self):
        if self.model.desktop_gui and hasattr(
            self.model.desktop_gui, "file_fetch_pdb"
        ):
            self.model.desktop_gui.file_fetch_pdb()
        else:
            self.model.cmd.do("wizard measurement")

    def session_save(self):
        fname = self.model.cmd.get("session_file")
        fname = self.model.cmd.as_pathstr(fname)
        self.session_save_as(fname)

    def session_save_as(self, fname=""):
        formats = "PyMOL Session File (*.pse *.pze *.pse.gz);;PyMOL Show File (*.psw *.pzw *.psw.gz)"
        if not fname:
            fname = QtWidgets.QFileDialog.getSaveFileName(
                self.model.desktop_gui,
                "Save Session As...",
                self.model.initialdir,
                filter=formats,
            )[0]
        if fname:
            self.model.initialdir = os.path.dirname(fname)
            self.model.cmd.save(fname, format="pse", quiet=0)
            self.recent_filenames_add(fname)

    def _generic_file_save(self, caption, filter_str, format_ext):
        fname = QtWidgets.QFileDialog.getSaveFileName(
            self.model.desktop_gui,
            caption,
            self.model.initialdir,
            filter=filter_str,
        )[0]
        if fname:
            self.model.cmd.save(fname, format=format_ext, quiet=0)

    # --- Workspace Commands Logging Operations ---
    def log_open(self, fname="", mode="w"):
        formats = "PyMOL Script (*.pml);;Python Script (*.py *.pym);;All (*)"
        if not fname:
            fname = QtWidgets.QFileDialog.getSaveFileName(
                self.model.desktop_gui,
                "Open Logfile...",
                self.model.initialdir,
                filter=formats,
            )[0]
        if fname:
            self.model.initialdir = os.path.dirname(fname)
            self.model.cmd.log_open(fname, mode)

    def log_resume(self):
        formats = "PyMOL Script (*.pml);;Python Script (*.py *.pym);;All (*)"
        fname = QtWidgets.QFileDialog.getSaveFileName(
            self.model.desktop_gui,
            "Open Logfile...",
            self.model.initialdir,
            filter=formats,
        )[0]
        if fname:
            self.model.initialdir = os.path.dirname(fname)
            self.model.cmd.resume(fname)

    def file_run(self):
        formats = "All Runnable (*.pml *.py *.pym);;PyMOL Command Script (*.pml);;Python Script (*.py *.pym);;All Files(*)"
        fnames, selectedfilter = QtWidgets.QFileDialog.getOpenFileNames(
            self.model.desktop_gui,
            "Open file",
            self.model.initialdir,
            filter=formats,
        )
        is_py = selectedfilter.startswith("Python")
        for fname in fnames:
            self.model.initialdir = os.path.dirname(fname)
            self.model.cmd.cd(self.model.initialdir, quiet=0)
            if is_py or re.search(r"\.py(|m|c|o|\.txt)$", fname, re.IGNORECASE):
                self.model.cmd.run(fname)
            else:
                self.model.cmd.do("@" + fname)

    def cd_dialog(self):
        dname = QtWidgets.QFileDialog.getExistingDirectory(
            self.model.desktop_gui,
            "Change Working Directory",
            self.model.initialdir,
        )
        if dname:
            self.model.cmd.cd(dname, quiet=0)

    # --- Clipboard Matrix Serialization Tool ---
    def get_view(self):
        self.model.cmd.get_view(2, quiet=0)
        QtWidgets.QApplication.clipboard().setText(self.model.cmd.get_view(3))
        print(" get_view: matrix copied to clipboard.")

    # --- Integrated Specialized Modals & Modifiers Managers ---
    def open_settings_all_dialog(self):
        try:
            from pymol_qt.advanced_settings_gui import PyMOLAdvancedSettings

            dialog = PyMOLAdvancedSettings(
                self.model.desktop_gui, self.model.cmd
            )
            dialog.show()
        except ImportError:
            self.model.cmd.do("config_mouse")

    def open_shortcut_menu_dialog(self):
        try:
            from pymol_qt.shortcut_menu_gui import PyMOLShortcutMenu

            shortcuts = getattr(self.model.desktop_gui, "saved_shortcuts", {})
            dialog = PyMOLShortcutMenu(
                self.model.desktop_gui, shortcuts, self.model.cmd
            )
            dialog.show()
        except ImportError:
            print("PyMOL Shortcuts editing interface module unavailable.")

    def open_scene_panel_dialog(self):
        try:
            from pymol_qt.scene_bin_gui import ScenePanel

            dialog = ScenePanel(self.model.desktop_gui)
            dialog.show()
        except ImportError:
            self.model.cmd.do("wizard density")

    def show_about(self):
        msg = [
            "The PyMOL Molecular Graphics System",
            f"Version {self.model.cmd.get_version()[0]}",
            "Copyright (C) Schrödinger, LLC.",
            "All rights reserved.\n",
            "Open-Source PyQt6 Decoupled Interface",
            "\nFor more information:",
            "https://pymol.org",
        ]
        QtWidgets.QMessageBox.about(
            self.model.desktop_gui, "About PyMOL", "\n".join(msg)
        )

    # --- 100% Standalone Form Inflator: Custom Colors Modifier ---
    def open_colors_dialog(self):
        parent_widget = self.model.desktop_gui or self.view
        self.active_color_dialog = QtWidgets.QDialog(parent_widget)
        self.active_color_dialog.setWindowTitle("Colors configuration")

        main_layout = QtWidgets.QVBoxLayout(self.active_color_dialog)

        # UI controls setup
        list_colors = QtWidgets.QListWidget()
        list_colors.setSortingEnabled(True)
        for index_tuple in self.model.cmd.get_color_indices():
            list_colors.addItem(index_tuple[0])

        form_layout = QtWidgets.QFormLayout()
        input_name = QtWidgets.QLineEdit()
        input_R = QtWidgets.QDoubleSpinBox()
        input_R.setRange(0.0, 1.0)
        input_R.setSingleStep(0.05)
        input_G = QtWidgets.QDoubleSpinBox()
        input_G.setRange(0.0, 1.0)
        input_G.setSingleStep(0.05)
        input_B = QtWidgets.QDoubleSpinBox()
        input_B.setRange(0.0, 1.0)
        input_B.setSingleStep(0.05)

        slider_R = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider_R.setRange(0, 100)
        slider_G = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider_G.setRange(0, 100)
        slider_B = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider_B.setRange(0, 100)

        frame_color = QtWidgets.QFrame()
        frame_color.setMinimumSize(60, 60)
        frame_color.setStyleSheet(
            "background-color: rgb(255,255,255); border: 1px solid black;"
        )

        form_layout.addRow("Color Name:", input_name)
        form_layout.addRow("Red Factor:", input_R)
        form_layout.addRow("", slider_R)
        form_layout.addRow("Green Factor:", input_G)
        form_layout.addRow("", slider_G)
        form_layout.addRow("Blue Factor:", input_B)
        form_layout.addRow("", slider_B)
        form_layout.addRow("Preview Box:", frame_color)

        main_layout.addWidget(list_colors)
        main_layout.addLayout(form_layout)

        apply_btn = QtWidgets.QPushButton("Apply Changes")
        main_layout.addWidget(apply_btn)

        spinbox_lock = [False]

        def update_sliders_and_preview():
            spinbox_lock[0] = True
            r_val, g_val, b_val = (
                input_R.value(),
                input_G.value(),
                input_B.value(),
            )
            slider_R.setValue(round(r_val * 100))
            slider_G.setValue(round(g_val * 100))
            slider_B.setValue(round(b_val * 100))
            frame_color.setStyleSheet(
                f"background-color: rgb({int(r_val * 255)}, {int(g_val * 255)}, {int(b_val * 255)}); border: 1px solid black;"
            )
            spinbox_lock[0] = False

        def on_slider_change(spinbox, value):
            if not spinbox_lock[0]:
                spinbox.setValue(value / 100.0)

        def load_named_color(name):
            idx = self.model.cmd.get_color_index(name)
            if idx == -1:
                return
            rgb_tuple = self.model.cmd.get_color_tuple(idx)
            input_R.setValue(rgb_tuple[0])
            input_G.setValue(rgb_tuple[1])
            input_B.setValue(rgb_tuple[2])

        def execute_color_modification():
            c_name = input_name.text().strip()
            if c_name:
                self.model.cmd.do(
                    f"set_color {c_name}, [{input_R.value():.2f}, {input_G.value():.2f}, {input_B.value():.2f}]\nrecolor"
                )
                if not list_colors.findItems(
                    c_name, QtCore.Qt.MatchFlag.MatchExactly
                ):
                    list_colors.addItem(c_name)

        slider_R.valueChanged.connect(lambda v: on_slider_change(input_R, v))
        slider_G.valueChanged.connect(lambda v: on_slider_change(input_G, v))
        slider_B.valueChanged.connect(lambda v: on_slider_change(input_B, v))
        input_R.valueChanged.connect(update_sliders_and_preview)
        input_G.valueChanged.connect(update_sliders_and_preview)
        input_B.valueChanged.connect(update_sliders_and_preview)
        input_name.textChanged.connect(load_named_color)
        list_colors.currentTextChanged.connect(input_name.setText)
        apply_btn.clicked.connect(execute_color_modification)

        self.active_color_dialog.show()

    # --- 100% Standalone Form Inflator: Raytrace & Resolution Matrix Render ---
    def open_render_dialog(self):
        parent_widget = self.model.desktop_gui or self.view
        self.active_render_dialog = QtWidgets.QDialog(parent_widget)
        self.active_render_dialog.setWindowTitle(
            "Draw / Raytrace Graphics View"
        )

        layout = QtWidgets.QVBoxLayout(self.active_render_dialog)
        form = QtWidgets.QFormLayout()

        width_box = QtWidgets.QSpinBox()
        width_box.setRange(10, 8192)
        width_box.setValue(640)
        height_box = QtWidgets.QSpinBox()
        height_box.setRange(10, 8192)
        height_box.setValue(480)
        dpi_combo = QtWidgets.QComboBox()
        dpi_combo.addItems(["72", "150", "300", "600"])
        dpi_combo.setEditable(True)
        transparent_check = QtWidgets.QCheckBox(
            "Enable Opaque Background Alpha Transparency"
        )

        form.addRow("Width (Pixels):", width_box)
        form.addRow("Height (Pixels):", height_box)
        form.addRow("Dots Per Inch (DPI):", dpi_combo)
        form.addRow(transparent_check)

        layout.addLayout(form)

        btn_layout = QtWidgets.QHBoxLayout()
        draw_btn = QtWidgets.QPushButton("Draw (Fast)")
        ray_btn = QtWidgets.QPushButton("Raytrace (Quality)")
        save_btn = QtWidgets.QPushButton("Save Image Snapshot")

        btn_layout.addWidget(draw_btn)
        btn_layout.addWidget(ray_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        def get_dim():
            return width_box.value(), height_box.value()

        def trigger_fast_draw():
            w, h = get_dim()
            self.model.cmd.do(f"draw {w}, {h}")

        def trigger_raytrace():
            w, h = get_dim()
            self.model.cmd.set(
                "opaque_background", 0 if transparent_check.isChecked() else 1
            )
            self.model.cmd.do(f"ray {w}, {h}, async=1")

        def trigger_save():
            fname = QtWidgets.QFileDialog.getSaveFileName(
                self.active_render_dialog,
                "Save Rendered Image Snapshot",
                self.model.initialdir,
                filter="PNG Image File (*.png)",
            )[0]
            if fname:
                self.model.initialdir = os.path.dirname(fname)
                self.model.cmd.png(
                    fname, prior=1, dpi=int(dpi_combo.currentText())
                )

        draw_btn.clicked.connect(trigger_fast_draw)
        ray_btn.clicked.connect(trigger_raytrace)
        save_btn.clicked.connect(trigger_save)

        self.active_render_dialog.show()

    # --- History Framework Parsing Shell Controllers ---
    def complete(self, text_getter, text_setter, cursor_setter):
        st = self.model.cmd._parser.complete(text_getter())
        if st:
            text_setter(st)
            cursor_setter(len(st))
        return "break"

    def doTypedCommand(self, cmmd):
        if len(self.model.history) < 2 or self.model.history[1] != cmmd:
            self.model.history[0] = cmmd
            self.model.history.insert(0, "")
            if len(self.model.history) > 255:
                self.model.history.pop()
        self.model.history_cur = 0
        self.model.cmd.do(cmmd)

    def back_search(self, text_getter, text_setter, cursor_setter, set0=False):
        if not self.model.history_cur or set0:
            self.model.history[0] = text_getter()
        for i in range(self.model.history_cur + 1, len(self.model.history)):
            if self.model.history[i].startswith(self.model.history[0]):
                self._jump_history(i, text_setter, cursor_setter)
                break

    def back(self, text_getter, text_setter, cursor_setter):
        if not self.model.history_cur:
            self.model.history[0] = text_getter()
        self._jump_history(
            self.model.history_cur + 1, text_setter, cursor_setter
        )

    def forward(self, text_setter, cursor_setter):
        if not self.model.history_cur:
            return
        self._jump_history(
            self.model.history_cur - 1, text_setter, cursor_setter
        )

    def _jump_history(self, i, text_setter, cursor_setter):
        self.model.history_cur = min(i, len(self.model.history) - 1)
        target_text = self.model.history[self.model.history_cur]
        text_setter(target_text)
        cursor_setter(len(target_text))

    # --- Movie Timeline Controllers ---
    def mvprg_remove_last(self):
        if self.model.movie_start > 0:
            self.model.cmd.mdelete(-1, self.model.movie_start)

    def mvprg(self, command=None):
        if command is not None:
            self.model.movie_start = self.model.cmd.get_movie_length() + 1
            self.model.movie_command = command % self.model.movie_start
        elif self.model.movie_command is None:
            return
        self.model.cmd.do(self.model.movie_command)

    # --- Cache Layers Queries Engine ---
    def get_recent_filenames(self):
        if not self.model.lazy_init_recent_db():
            return []
        c = self.model._recent_filenames_db.cursor()
        return [
            row[0]
            for row in c.execute(
                "SELECT filename FROM recent ORDER BY timestamp DESC"
            )
        ]

    def recent_filenames_add(self, filename):
        if not self.model.lazy_init_recent_db():
            return
        c = self.model._recent_filenames_db.cursor()
        c.execute(
            "REPLACE INTO recent VALUES (?, datetime('now'))", (filename,)
        )
        if c.execute("SELECT COUNT(*) FROM recent").fetchone()[0] > 20:
            c.execute(
                "DELETE FROM recent WHERE timestamp < ?",
                c.execute(
                    "SELECT timestamp from recent ORDER BY timestamp DESC LIMIT 1 OFFSET 15"
                ).fetchone(),
            )
        self.model._recent_filenames_db.commit()

    def export_molecule(self):
        if self.model.desktop_gui and hasattr(self.model.desktop_gui, 'file_save') and self.model.desktop_gui.file_save:
            self.model.desktop_gui.file_save()

    def export_map(self):
        if self.model.desktop_gui and hasattr(self.model.desktop_gui, 'file_save_map') and self.model.desktop_gui.file_save_map:
            self.model.desktop_gui.file_save_map()

    def export_alignment(self):
        if self.model.desktop_gui and hasattr(self.model.desktop_gui, 'file_save_aln') and self.model.desktop_gui.file_save_aln:
            self.model.desktop_gui.file_save_aln()

    def export_image_wrl(self):
        self._generic_file_save("Save VRML Image", "VRML 2 WRL File (*.wrl)", "wrl")

    def export_image_dae(self):
        self._generic_file_save("Save COLLADA Image", "COLLADA File (*.dae)", "dae")

    def export_image_gltf(self):
        self._generic_file_save("Save GLTF Image", "GLTF File (*.gltf)", "gltf")

    def export_image_pov(self):
        self._generic_file_save("Save POV Image", "POV File (*.pov)", "pov")

    def export_image_stl(self):
        self._generic_file_save("Save STL Image", "STL File (*.stl)", "stl")

    def export_movie_mpeg(self):
        if self.model.desktop_gui and hasattr(self.model.desktop_gui, 'file_save_mpeg') and self.model.desktop_gui.file_save_mpeg:
            self.model.desktop_gui.file_save_mpeg()
        else:
            self._generic_file_save("Save MPEG Movie", "MPEG Movie (*.mpeg *.mpg)", "mpeg")

    def export_movie_mov(self):
        if self.model.desktop_gui and hasattr(self.model.desktop_gui, 'file_save_mov') and self.model.desktop_gui.file_save_mov:
            self.model.desktop_gui.file_save_mov()
        else:
            self._generic_file_save("Save Quicktime Movie", "Quicktime Movie (*.mov)", "mov")

    def export_movie_mpng(self):
        if self.model.desktop_gui and hasattr(self.model.desktop_gui, 'file_save_mpng') and self.model.desktop_gui.file_save_mpng:
            self.model.desktop_gui.file_save_mpng()
        else:
            self._generic_file_save("Save PNG Movie Frames", "PNG Images (*.png)", "png")

    def edit_pymolrc(self):
        if self.model.desktop_gui and hasattr(self.model.desktop_gui, 'edit_pymolrc') and self.model.desktop_gui.edit_pymolrc:
            self.model.desktop_gui.edit_pymolrc()
        else:
            home = pathlib.Path.home()
            paths = [home / ".pymolrc", home / "pymolrc", home / ".pymolrc.py"]
            target = next((p for p in paths if p.exists()), paths[0])
            if not target.exists():
                target.touch()
            webbrowser.open(target.as_uri())

    def initialize_plugins(self):
        """Initializes PyMOL's legacy plugin architecture and hooks it to this menu bar."""
        from pymol import plugins
        import pymol.gui

        # Retrieve the native QMenu object from the active view menu tracking dict
        plugin_menu = self.view.menu_bar.menudict["Plugin"]
        plugin_menu.clear()

        # Wire the legacy application bridge callback directly to this class instance
        pymol.gui.createlegacypmgapp = self.createlegacypmgapp

        app = plugins.get_pmgapp()
        plugins.legacysupport.addPluginManagerMenuItem()

        # Re-route the active dictionary tracks to safely isolate legacy Tkinter-wrapped items
        self.view.menu_bar.menudict["PluginQt"] = plugin_menu
        self.view.menu_bar.menudict["Plugin"] = plugin_menu.addMenu("Legacy Plugins")
        self.view.menu_bar.menudict["Plugin"].setTearOffEnabled(True)
        self.view.menu_bar.menudict["PluginQt"].addSeparator()

        plugins.HAVE_QT = True
        plugins.initialize(app)

# ==============================================================================
# 3. VIEW LAYER (Qt Architecture Blueprint Mappings & Tree Inflation)
# ==============================================================================


class PyMOLMenuBarView:
    """Calculates entire application layout topologies and translates them to native Qt nodes."""

    def __init__(self, controller: "PyMOLMenuBarController", menu_bar_instance):
        self.controller: "PyMOLMenuBarController" = controller
        self.menu_bar = menu_bar_instance

    def inflate_ui(self):
        """Constructs and registers menus explicitly onto targeted native container bar object."""
        cmd = self.controller.model.cmd
        layout_tree = [
            ("menu", "File", self._build_file_menu(cmd)),
            ("menu", "Edit", self._build_edit_menu(cmd)),
            ("menu", "Build", self._build_build_menu(cmd)),
            ("menu", "Movie", self._build_movie_menu(cmd)),
            ("menu", "Display", self._build_display_menu(cmd)),
            ("menu", "Setting", self._build_setting_menu(cmd)),
            ("menu", "Scene", self._build_scene_menu(cmd)),
            ("menu", "Mouse", self._build_mouse_menu(cmd)),
            ("menu", "Wizard", self._build_wizard_menu(cmd)),
            ("menu", "Plugin", [("command", "Initialize Plugin System", self.controller.initialize_plugins)]),
            ("menu", "Help", self._build_help_menu(cmd)),
        ]

        for _, label, data in layout_tree:
            native_menu = self.menu_bar.addMenu(label)
            self.menu_bar.menudict[label] = native_menu
            self._render_menu_recursive(data, native_menu)

    def _render_menu_recursive(self, data, target_menu):
        target_menu.setTearOffEnabled(True)
        target_menu.setWindowTitle(target_menu.title())
        cmd = self.controller.model.cmd

        for item in data:
            if item[0] == "separator":
                target_menu.addSeparator()
            elif item[0] == "menu":
                sub_menu = target_menu.addMenu(item[1].replace("&", "&&"))
                self._render_menu_recursive(item[2], sub_menu)
            elif item[0] == "command":
                label, command = item[1], item[2]
                if command is not None:
                    if isinstance(command, str):
                        target_menu.addAction(
                            label, lambda c=command: cmd.do(c)
                        )
                    else:
                        target_menu.addAction(label, command)
            elif item[0] == "check":
                if len(item) > 4:
                    action = self._create_setting_action(
                        item[2], item[1], item[3], item[4]
                    )
                else:
                    action = self._create_setting_action(item[2], item[1])
                target_menu.addAction(action)
            elif item[0] == "radio":
                label, name, value = item[1], item[2], item[3]
                try:
                    group, type_, values = self.menu_bar.actiongroups[name]
                except KeyError:
                    group = QActionGroup(self.menu_bar)
                    type_, values = cmd.get_setting_tuple(name)
                    self.menu_bar.actiongroups[name] = (group, type_, values)

                action = QAction(label, self.menu_bar)
                action.setCheckable(True)
                action.triggered.connect(
                    lambda _=0, n=name, v=value: cmd.set(n, v, log=1, quiet=0)
                )

                index = cmd.setting._get_index(name)
                self.menu_bar.setting_callbacks[index].append(
                    lambda v, V=value, a=action: a.setChecked(v == V)
                )

                group.addAction(action)
                target_menu.addAction(action)
                if values[0] == value:
                    action.setChecked(True)
            elif item[0] == "open_recent_menu":
                self.menu_bar.open_recent_menu = target_menu.addMenu(
                    "Open Recent..."
                )

    def _create_setting_action(
        self, name, label="", true_value=1, false_value=0, command=None
    ):
        cmd = self.controller.model.cmd
        if not label:
            label = name
        index = cmd.setting._get_index(name)
        type_, values = cmd.get_setting_tuple(index)
        action = QAction(label, self.menu_bar)

        if not command:
            command = lambda: cmd.set(
                index,
                true_value if action.isChecked() else false_value,
                log=1,
                quiet=0,
            )

        self.menu_bar.setting_callbacks[index].append(
            lambda v: action.setChecked(v != false_value)
        )

        if type_ in (1, 2, 3, 5, 6):
            action.setCheckable(True)
            if values[0] == true_value:
                action.setChecked(True)
        action.triggered.connect(command)
        return action

    # --------------------------------------------------------------------------
    # COMPLETELY EXPANDED BLUEPRINT COMPONENT SUBMENUS
    # --------------------------------------------------------------------------

    def _build_file_menu(self, cmd):
        sys_browser_cmd = (
            "explorer ."
            if sys.platform == "win32"
            else "open ."
            if sys.platform == "darwin"
            else "xdg-open ."
        )
        return [
            (
                "menu",
                "New PyMOL Window",
                [
                    ("command", "Default", self.controller.new_window),
                    (
                        "command",
                        "Ignore .pymolrc and plugins (-k)",
                        lambda: self.controller.new_window(("-k",)),
                    ),
                ],
            ),
            ("separator",),
            ("command", "Open...", self.controller.file_open),
            ("open_recent_menu",),
            ("command", "Get PDB...", self.controller.file_fetch_pdb),
            ("separator",),
            ("command", "Save Session", self.controller.session_save),
            ("command", "Save Session As...", self.controller.session_save_as),
            ("separator",),
            ("command", "Export Molecule...", self.controller.export_molecule),
            ("command", "Export Map...", self.controller.export_map),
            (
                "command",
                "Export Alignment...",
                self.controller.export_alignment,
            ),
            (
                "menu",
                "Export Image As",
                [
                    (
                        "command",
                        "Draw / Raytrace Frame View Panel...",
                        self.controller.open_render_dialog,
                    ),
                    ("separator",),
                    ("command", "VRML 2...", self.controller.export_image_wrl),
                    ("command", "COLLADA...", self.controller.export_image_dae),
                    ("command", "GLTF...", self.controller.export_image_gltf),
                    ("command", "POV-Ray...", self.controller.export_image_pov),
                    ("command", "STL...", self.controller.export_image_stl),
                ],
            ),
            (
                "menu",
                "Export Movie As",
                [
                    ("command", "MPEG...", self.controller.export_movie_mpeg),
                    (
                        "command",
                        "Quicktime...",
                        self.controller.export_movie_mov,
                    ),
                    ("separator",),
                    (
                        "command",
                        "PNG Images...",
                        self.controller.export_movie_mpng,
                    ),
                ],
            ),
            ("separator",),
            (
                "menu",
                "Log File",
                [
                    ("command", "Open...", self.controller.log_open),
                    ("command", "Resume...", self.controller.log_resume),
                    (
                        "command",
                        "Append...",
                        lambda: self.controller.log_open(mode="a"),
                    ),
                    ("command", "Close", cmd.log_close),
                ],
            ),
            ("command", "Run Script...", self.controller.file_run),
            (
                "menu",
                "Working Directory",
                [
                    ("command", "Change...", self.controller.cd_dialog),
                    (
                        "command",
                        "File Browser",
                        lambda: cmd.system(sys_browser_cmd),
                    ),
                ],
            ),
            ("separator",),
            ("command", "Edit pymolrc", self.controller.edit_pymolrc),
            ("separator",),
            (
                "menu",
                "Reinitialize",
                [
                    ("command", "Everything", cmd.reinitialize),
                    (
                        "command",
                        "Original Settings",
                        "reinitialize original_settings",
                    ),
                    ("command", "Stored Settings", "reinitialize settings"),
                    ("separator",),
                    (
                        "command",
                        "Store Current Settings",
                        "reinitialize store_defaults",
                    ),
                ],
            ),
            ("command", "Quit", self.controller.confirm_quit),
        ]

    def _build_edit_menu(self, cmd):
        return [
            ("command", "Undo [Ctrl-Z]", cmd.undo),
            ("command", "Redo [Ctrl-Y]", cmd.redo),
        ]

    def _build_build_menu(self, cmd):
        return [
            ("menu", "Fragment", self._extract_fragments_layout()),
            ("menu", "Residue", self._extract_residues_layout(cmd)),
            ("separator",),
            ("menu", "Sculpting", self._extract_sculpting_layout(cmd)),
            ("separator",),
            ("command", "Cycle Bond Valence [Ctrl-Shift-W]", "cycle_valence"),
            ("command", "Fill Hydrogens on (pk1) [Ctrl-Shift-R]", "h_fill"),
            ("command", "Invert (pk2)-(pk1)-(pk3) [Ctrl-Shift-E]", "invert"),
            ("command", "Create Bond (pk1)-(pk2) [Ctrl-Shift-T]", "bond"),
            ("separator",),
            ("command", "Remove (pk1) [Ctrl-Shift-D]", "remove pk1"),
            ("separator",),
            (
                "command",
                "Make (pk1) Positive [Ctrl-Shift-K]",
                "alter pk1, formal_charge=1",
            ),
            (
                "command",
                "Make (pk1) Negative [Ctrl-Shift-J]",
                "alter pk1, formal_charge=-1",
            ),
            (
                "command",
                "Make (pk1) Neutral [Ctrl-Shift-U]",
                "alter pk1, formal_charge=0",
            ),
        ]

    def _build_movie_menu(self, cmd):
        durations = [0.25, 0.5, 1, 2, 3, 4, 6, 8, 12, 18, 24, 30, 48, 60]
        fps_modes = [
            ("30 FPS", 30.0),
            ("15 FPS", 15.0),
            ("5 FPS", 5.0),
            ("1 FPS", 1.0),
            ("0.3 FPS", 0.3),
        ]
        return [
            (
                "menu",
                "Append",
                [
                    (
                        "command",
                        f"{i} second",
                        lambda i=i: cmd.movie.add_blank(i),
                    )
                    for i in durations
                ],
            ),
            ("separator",),
            ("menu", "Program", self._extract_movie_programs_layout()),
            ("command", "Update Last Program", self.controller.mvprg),
            (
                "command",
                "Remove Last Program",
                self.controller.mvprg_remove_last,
            ),
            ("separator",),
            ("command", "Reset", "mset;rewind"),
            ("separator",),
            (
                "menu",
                "Frame Rate",
                [("radio", lab, "movie_fps", val) for lab, val in fps_modes]
                + [
                    ("separator",),
                    ("check", "Show Frame Rate", "show_frame_rate"),
                    ("command", "Reset Meter", cmd.meter_reset),
                ],
            ),
            ("separator",),
            ("check", "Auto Interpolate", "movie_auto_interpolate"),
            ("check", "Show Panel", "movie_panel"),
            ("check", "Loop Frames", "movie_loop"),
            ("check", "Draw Frames", "draw_frames"),
            ("check", "Ray Trace Frames", "ray_trace_frames"),
            ("check", "Cache Frame Images", "cache_frames"),
            ("command", "Clear Image Cache", cmd.mclear),
            ("separator",),
            ("check", "Static Singletons", "static_singletons", 1),
            ("check", "Show All States", "all_states", 1),
        ]

    def _build_display_menu(self, cmd):
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
        stereo_modes = [
            ("Anaglyph Stereo", "stereo anaglyph"),
            ("Cross-Eye Stereo", "stereo crosseye"),
            ("Wall-Eye Stereo", "stereo walleye"),
            ("Quad-Buffered Stereo", "stereo quadbuffer"),
            ("Zalman Stereo", "stereo byrow"),
            ("OpenVR", "stereo openvr"),
            ("separator", None),
            ("Swap Sides", "stereo swap"),
            ("separator", None),
            ("Chromadepth", "stereo chromadepth"),
            ("off", "stereo off"),
        ]
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
        perf_qualities = [
            ("Maximum Performance", "util.performance(100)"),
            ("Reasonable Performance", "util.performance(66)"),
            ("Reasonable Quality", "util.performance(33)"),
            ("Maximum Quality", "util.performance(0)"),
        ]
        return [
            ("check", "Sequence", "seq_view", 1),
            (
                "menu",
                "Sequence Mode",
                [
                    ("radio", lab, "seq_view_format", val)
                    for lab, val in seq_formats
                ]
                + [("separator",)]
                + [
                    ("radio", lab, "seq_view_label_mode", val)
                    for lab, val in seq_labels
                ]
                + [("separator",)]
                + [
                    ("radio", lab, "seq_view_gap_mode", val)
                    for lab, val in seq_gaps
                ],
            ),
            ("separator",),
            ("check", "Internal GUI", "internal_gui", 1),
            ("check", "Internal Prompt", "internal_prompt", 1),
            (
                "menu",
                "Internal Feedback",
                [
                    ("radio", str(val), "internal_feedback", val)
                    for val in [0, 1, 3, 5]
                ],
            ),
            (
                "menu",
                "Overlay",
                [("radio", str(val), "overlay", val) for val in [0, 1, 3, 5]],
            ),
            ("separator",),
            ("check", "Stereo", "stereo", 1),
            (
                "menu",
                "Stereo Mode",
                [
                    ("separator",)
                    if m[0] == "separator"
                    else ("command", m[0], m[1])
                    for m in stereo_modes
                ],
            ),
            ("separator",),
            (
                "menu",
                "Zoom",
                [
                    (
                        "command",
                        f"{i} Angstrom Sphere",
                        lambda i=i: cmd.zoom("center", i, animate=-1),
                    )
                    for i in [4, 6, 8, 12, 20]
                ]
                + [
                    ("command", "All", "zoom animate=-1"),
                    ("command", "Complete", "zoom animate=-1, complete=1"),
                ],
            ),
            (
                "menu",
                "Clip",
                [("command", "Nothing", "clip atoms, 5, all")]
                + [
                    (
                        "command",
                        f"{i} Angstrom Slab",
                        lambda i=i: cmd.clip("slab", i),
                    )
                    for i in [8, 12, 16, 20, 30]
                ],
            ),
            ("separator",),
            (
                "menu",
                "Background",
                [
                    ("check", "Opaque", "opaque_background", 1),
                    ("check", "Alpha Checker", "show_alpha_checker", 1),
                    ("separator",),
                ]
                + [("radio", lab, "bg_rgb", val) for lab, val in bg_colors],
            ),
            (
                "menu",
                "Color Space",
                [
                    ("command", "CMYK (for publications)", "space cmyk"),
                    ("command", "PyMOL (for video + web)", "space pymol"),
                    ("command", "RGB (default)", "space rgb"),
                ],
            ),
            (
                "menu",
                "Quality",
                [("command", lab, target) for lab, target in perf_qualities],
            ),
            (
                "menu",
                "Grid",
                [("radio", lab, "grid_mode", val) for lab, val in grid_modes],
            ),
            ("separator",),
            ("check", "Orthoscopic View", "orthoscopic", 1),
            ("check", "Show Valences", "valence", 1),
            ("check", "Smooth Lines", "line_smooth", 1),
            ("check", "Depth Cue (Fogging)", "depth_cue", 1),
            ("check", "Two Sided Lighting", "two_sided_lighting", 1),
            ("check", "Specular Reflections", "specular", 1.0),
            ("check", "Animation", "animation", 1),
            ("check", "Roving Detail", "roving_detail", 1),
        ]

    def _build_setting_menu(self, cmd):
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
        return [
            (
                "command",
                "Edit All...",
                self.controller.open_settings_all_dialog,
            ),
            (
                "command",
                "Keyboard Shortcuts...",
                self.controller.open_shortcut_menu_dialog,
            ),
            ("command", "Colors...", self.controller.open_colors_dialog),
            ("separator",),
            (
                "menu",
                "Label",
                [
                    (
                        "menu",
                        "Size",
                        [
                            ("radio", f"{val} Point", "label_size", val)
                            for val in [10, 14, 18, 24, 36, 48, 72]
                        ]
                        + [("separator",)]
                        + [
                            ("radio", f"{val} Angstrom", "label_size", -val)
                            for val in [0.3, 0.5, 1, 2, 4]
                        ],
                    ),
                    (
                        "menu",
                        "Font",
                        [
                            ("radio", label, "label_font_id", val)
                            for label, val in label_fonts
                        ],
                    ),
                    (
                        "menu",
                        "Color",
                        [
                            ("radio", lab, "label_color", val)
                            for lab, val in [("Front", -6), ("Back", -7)]
                        ],
                    ),
                    ("check", "Show Connectors", "label_connector"),
                    (
                        "menu",
                        "Background Color",
                        [
                            ("radio", lab, "label_bg_color", val)
                            for lab, val in [
                                ("None", -1),
                                ("Back", -7),
                                ("Front", -6),
                            ]
                        ],
                    ),
                ],
            ),
            ("menu", "Lines & Sticks", self._extract_lines_sticks_layout()),
            ("menu", "Cartoon", self._extract_cartoon_layout()),
            ("menu", "Ribbon", self._extract_ribbon_layout()),
            ("menu", "Surface", self._extract_surface_layout()),
            (
                "menu",
                "Volume",
                [
                    ("check", "Pre-integrated Rendering", "volume_mode"),
                    (
                        "menu",
                        "Number of Layers",
                        [
                            ("radio", f"{val:.0f}", "volume_layers", val)
                            for val in [100.0, 256.0, 500.0, 1000.0]
                        ],
                    ),
                ],
            ),
            (
                "menu",
                "Transparency",
                [
                    (
                        "menu",
                        "Surface",
                        self._generate_transparency_array("transparency"),
                    ),
                    (
                        "menu",
                        "Sphere",
                        self._generate_transparency_array(
                            "sphere_transparency"
                        ),
                    ),
                    (
                        "menu",
                        "Cartoon",
                        self._generate_transparency_array(
                            "cartoon_transparency"
                        ),
                    ),
                    (
                        "menu",
                        "Stick",
                        self._generate_transparency_array("stick_transparency"),
                    ),
                    ("separator",),
                ]
                + [
                    (
                        "command",
                        lab,
                        lambda v=val: (
                            cmd.set("transparency_mode", v[0], quiet=0),
                            cmd.set("backface_cull", v[1], quiet=0),
                            cmd.set("two_sided_lighting", v[2], quiet=0),
                        ),
                    )
                    for lab, val in [
                        ("Uni-Layer", (2, 1, 0)),
                        ("Multi-Layer", (1, 0, 1)),
                        ("Multi-Layer (Real-time OIT)", (3, 0, -1)),
                        ("Fast and Ugly", (0, 1, 0)),
                    ]
                ]
                + [
                    ("separator",),
                    (
                        "check",
                        "Angle-dependent",
                        "ray_transparency_oblique",
                        1.0,
                    ),
                ],
            ),
            ("menu", "Rendering", self._extract_rendering_layout(cmd)),
            ("separator",),
            (
                "menu",
                "PDB File Loading",
                [
                    (
                        "check",
                        "Ignore PDB Segment Identifier",
                        "ignore_pdb_segi",
                        1,
                    )
                ],
            ),
            (
                "menu",
                "mmCIF File Loading",
                [
                    ("check", 'Use "auth" Identifiers', "cif_use_auth", 1),
                    (
                        "check",
                        "Load Assembly (Biological Unit)",
                        "assembly",
                        "1",
                        "",
                    ),
                    (
                        "check",
                        'Bonding by "Chemical Component Dictionary"',
                        "connect_mode",
                        4,
                        0,
                    ),
                ],
            ),
            (
                "menu",
                "Map File Loading",
                [
                    ("check", "Normalize CCP4 Maps", "normalize_ccp4_maps", 1),
                    ("check", "Normalize O Maps", "normalize_o_maps", 1),
                ],
            ),
            ("separator",),
            (
                "menu",
                "Auto-Show ...",
                [
                    (
                        "check",
                        "Cartoon/Sticks/Spheres by Classification",
                        "auto_show_classified",
                        -1,
                        0,
                    ),
                    ("separator",),
                    ("check", "Auto-Show Lines", "auto_show_lines", 1),
                    ("check", "Auto-Show Spheres", "auto_show_spheres", 1),
                    ("check", "Auto-Show Nonbonded", "auto_show_nonbonded", 1),
                    ("separator",),
                    (
                        "check",
                        "Auto-Show New Selections",
                        "auto_show_selections",
                        1,
                    ),
                    (
                        "check",
                        "Auto-Hide Selections",
                        "auto_hide_selections",
                        1,
                    ),
                ],
            ),
            ("check", "Auto-Zoom New Objects", "auto_zoom", 1),
            ("check", "Auto-Remove Hydrogens", "auto_remove_hydrogens", 1),
            ("separator",),
            ("check", "Show Text (Esc)", "text"),
            ("check", "Overlay Text", "overlay"),
        ]

    def _build_scene_menu(self, cmd):
        def parse_f_keys(action):
            return [
                ("command", k, lambda k=k, a=action: cmd.scene(k, a))
                for k in [f"F{i}" for i in range(1, 13)]
            ]

        return [
            ("command", "Scenes...", self.controller.open_scene_panel_dialog),
            ("separator",),
            ("command", "Next [PgDn]", lambda: cmd.scene("", "next")),
            ("command", "Previous [PgUp]", lambda: cmd.scene("", "previous")),
            ("separator",),
            ("command", "Append", "scene new, store"),
            (
                "menu",
                "Append...",
                [
                    ("command", "Camera", "scene new, store, color=0, rep=0"),
                    ("command", "Color", "scene new, store, view=0, rep=0"),
                    ("command", "Reps", "scene new, store, view=0, color=0"),
                    ("command", "Reps + Color", "scene new, store, view=0"),
                ],
            ),
            (
                "command",
                "Insert Before",
                lambda: cmd.scene("", "insert_before"),
            ),
            ("command", "Insert After", lambda: cmd.scene("", "insert_after")),
            ("command", "Update", lambda: cmd.scene("auto", "update")),
            ("separator",),
            ("command", "Delete", lambda: cmd.scene("auto", "clear")),
            ("separator",),
            ("menu", "Recall", parse_f_keys("recall")),
            ("menu", "Store", parse_f_keys("store")),
            ("menu", "Clear", parse_f_keys("clear")),
            ("separator",),
            ("check", "Buttons", "scene_buttons", 1),
            (
                "menu",
                "Cache",
                [
                    ("command", "Enable", lambda: cmd.cache("enable")),
                    ("command", "Optimize", lambda: cmd.cache("optimize")),
                    ("command", "Read Only", lambda: cmd.cache("read_only")),
                    ("command", "Disable", lambda: cmd.cache("disable")),
                ],
            ),
        ]

    def _build_mouse_menu(self, cmd):
        return [
            (
                "menu",
                "Selection Mode",
                [
                    ("radio", lab, "mouse_selection_mode", val)
                    for lab, val in [
                        ("Atoms", 0),
                        ("Residues", 1),
                        ("Chains", 2),
                        ("Segments", 3),
                        ("Objects", 4),
                        ("Molecules", 5),
                        ("C-alphas", 6),
                    ]
                ],
            ),
            ("separator",),
            (
                "command",
                "3 Button Motions",
                lambda: cmd.config_mouse("three_button_motions"),
            ),
            (
                "command",
                "3 Button Editing",
                lambda: cmd.config_mouse("three_button_editing"),
            ),
            (
                "command",
                "3 Button Viewing",
                lambda: cmd.mouse("three_button_viewing"),
            ),
            (
                "command",
                "3 Button Lights",
                lambda: cmd.mouse("three_button_lights"),
            ),
            (
                "command",
                "3 Button All Modes",
                lambda: cmd.config_mouse("three_button_all_modes"),
            ),
            (
                "command",
                "2 Button Editing",
                lambda: cmd.config_mouse("two_button_editing"),
            ),
            (
                "command",
                "2 Button Viewing",
                lambda: cmd.config_mouse("two_button"),
            ),
            (
                "command",
                "1 Button Viewing Mode",
                lambda: cmd.mouse("one_button_viewing"),
            ),
            (
                "command",
                "Emulate Maestro",
                lambda: cmd.mouse("three_button_maestro"),
            ),
            ("separator",),
            ("check", "Virtual Trackball", "virtual_trackball"),
            ("check", "Show Mouse Grid", "mouse_grid"),
            ("check", "Roving Origin", "roving_origin"),
        ]

    def _build_wizard_menu(self, cmd):
        demos = [
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
        ]
        return [
            ("command", "Appearance", "wizard appearance"),
            ("command", "Measurement", "wizard measurement"),
            (
                "menu",
                "Mutagenesis",
                [
                    ("command", "Protein", "wizard mutagenesis"),
                    ("command", "Nucleic Acids", "wizard nucmutagenesis"),
                ],
            ),
            ("command", "Pair Fitting", "wizard pair_fit"),
            ("separator",),
            ("command", "Density", "wizard density"),
            ("command", "Filter", "wizard filter"),
            ("command", "Sculpting", "wizard sculpting"),
            ("separator",),
            ("command", "Label", "wizard label"),
            ("command", "Charge", "wizard charge"),
            ("separator",),
            (
                "menu",
                "Demo",
                [
                    ("command", lab, lambda val=val: cmd.wizard("demo", val))
                    for lab, val in demos
                ]
                + [
                    ("separator",),
                    (
                        "command",
                        "End Demonstration",
                        lambda: cmd.replace_wizard("demo", "finish"),
                    ),
                ],
            ),
        ]

    def _build_help_menu(self, cmd):
        topics = [
            ("Introductory Screencasts", "media:intro"),
            ("Core Commands", "command:core_set"),
            ("Settings", "setting"),
            ("Atom Selections", "selection"),
            ("Commands", "command"),
            ("Launching", "launch"),
            ("Concepts", "concept"),
            ("A.P.I. Methods", "api"),
        ]
        return [
            (
                "command",
                "PyMOL Command Reference",
                lambda: webbrowser.open(
                    "http://pymol.org/pymol-command-ref.html"
                ),
            ),
            ("separator",),
            (
                "command",
                "Online Documentation",
                lambda: webbrowser.open("http://pymol.org/d/"),
            ),
            (
                "menu",
                "Topics",
                [
                    (
                        "command",
                        lab,
                        lambda val=val: webbrowser.open(
                            f"http://pymol.org/d/{val}"
                        ),
                    )
                    for lab, val in topics
                ],
            ),
            ("separator",),
            (
                "command",
                "PyMOL Community Wiki",
                lambda: webbrowser.open("http://www.pymolwiki.org"),
            ),
            (
                "command",
                "PyMOL Mailing List",
                lambda: webbrowser.open(
                    "https://lists.sourceforge.net/lists/listinfo/pymol-users"
                ),
            ),
            (
                "command",
                "PyMOL Home Page",
                lambda: webbrowser.open("http://www.pymol.org"),
            ),
            ("separator",),
            ("command", "About PyMOL", self.controller.show_about),
            (
                "command",
                "Sponsorship Information",
                lambda: webbrowser.open("http://pymol.org/funding.html"),
            ),
            (
                "command",
                "How to Cite PyMOL",
                lambda: webbrowser.open("http://pymol.org/citing"),
            ),
        ]

    # --- Static Mapped Internal Layout Extraction Blueprints ---
    def _extract_fragments_layout(self):
        fragments = [
            (
                "Acetylene [Alt-J]",
                "editor.attach_fragment('pk1','acetylene',2,0)",
            ),
            (
                "Amide N->C [Alt-1]",
                "editor.attach_fragment('pk1','formamide',3,1)",
            ),
            (
                "Amide C->N [Alt-2]",
                "editor.attach_fragment('pk1','formamide',5,0)",
            ),
            ("Bromine [Ctrl-Shift-B]", "replace Br,1,1"),
            ("Carbon [Ctrl-Shift-C]", "replace C,4,4"),
            (
                "Carbonyl [Alt-0]",
                "editor.attach_fragment('pk1','formaldehyde',2,0)",
            ),
            ("Chlorine [Ctrl-Shift-L]", "replace Cl,1,1"),
            (
                "Cyclobutyl [Alt-4]",
                "editor.attach_fragment('pk1','cyclobutane',4,0)",
            ),
            (
                "Cyclopentyl [Alt-5]",
                "editor.attach_fragment('pk1','cyclopentane',5,0)",
            ),
            (
                "Cyclopentadiene [Alt-8]",
                "editor.attach_fragment('pk1','cyclopentadiene',5,0)",
            ),
            (
                "Cyclohexyl [Alt-6]",
                "editor.attach_fragment('pk1','cyclohexane',7,0)",
            ),
            (
                "Cycloheptyl [Alt-7]",
                "editor.attach_fragment('pk1','cycloheptane',8,0)",
            ),
            ("Fluorine [Ctrl-Shift-F]", "replace F,1,1"),
            ("Iodine [Ctrl-Shift-I]", "replace I,1,1"),
            (
                "Methane [Ctrl-Shift-M]",
                "editor.attach_fragment('pk1','methane',1,0)",
            ),
            ("Nitrogen [Ctrl-Shift-N]", "replace N,4,3"),
            ("Oxygen [Ctrl-Shift-O]", "replace O,4,2"),
            ("Sulfer [Ctrl-Shift-S]", "replace S,2,2"),
            ("Sulfonyl [Alt-3]", "editor.attach_fragment('pk1','sulfone',3,1)"),
            ("Phosphorus [Ctrl-Shift-P]", "replace P,4,3"),
        ]
        return [("command", lab, target) for lab, target in fragments]

    def _extract_residues_layout(self, cmd):
        residues = [
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
        ]
        return [
            (
                "command",
                lab,
                lambda v=val: cmd.editor.attach_amino_acid("pk1", v),
            )
            for lab, val in residues
        ] + [
            ("separator",),
            ("radio", "Helix", "secondary_structure", 1),
            ("radio", "Antiparallel Beta Sheet", "secondary_structure", 2),
            ("radio", "Parallel Beta Sheet", "secondary_structure", 3),
        ]

    def _extract_sculpting_layout(self, cmd):
        return (
            [
                ("check", "Auto-Sculpting", "auto_sculpt"),
                ("check", "Sculpting", "sculpting"),
                ("separator",),
                ("command", "Activate", "sculpt_activate all"),
                ("command", "Deactivate", "sculpt_deactivate all"),
                ("command", "Clear Memory", cmd.sculpt_purge),
                ("separator",),
                ("radio", "1 Cycle per Update", "sculpting_cycles", 1),
            ]
            + [
                ("radio", f"{v} Cycles per Update", "sculpting_cycles", v)
                for v in [3, 10, 33, 100, 333, 1000]
            ]
            + [("separator",)]
            + [
                ("radio", lab, "sculpt_field_mask", val)
                for lab, val in [
                    ("Bonds Only", 0x01),
                    ("Bonds and Angles Only", 0x01 | 0x02),
                    ("Local Geometry Only", 0x20 - 1),
                    ("All Except VDW", ~(0x20 | 0x40)),
                    ("All Except 1-4 VDW and Torsions", ~(0x40 | 0x80)),
                    ("All Terms", 0xFF),
                ]
            ]
        )

    def _extract_movie_programs_layout(self):
        speeds = [1, 2, 3, 4, 8, 16]
        return [
            (
                "menu",
                "Camera Loop",
                [
                    (
                        "menu",
                        "Nutate",
                        [
                            (
                                "command",
                                "15 deg. over 4 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(4,15,start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "15 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(8,15,start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "15 deg. over 12 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(12,15,start=%d)"
                                ),
                            ),
                            ("separator", ""),
                            (
                                "command",
                                "30 deg. over 4 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(4,30,start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "30 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(8,30,start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "30 deg. over 12 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(12,30,start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "30 deg. over 16 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(16,30,start=%d)"
                                ),
                            ),
                            ("separator", ""),
                            (
                                "command",
                                "60 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(8,60,start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "60 deg. over 16 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(16,60,start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "60 deg. over 24 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(24,60,start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "60 deg. over 32 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_nutate(32,60,start=%d)"
                                ),
                            ),
                        ],
                    ),
                    ("separator",),
                    (
                        "menu",
                        "X-Rock",
                        [
                            (
                                "command",
                                "30 deg. over 2 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(2,30,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "30 deg. over 4 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(4,30,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "30 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(8,30,axis='x',start=%d)"
                                ),
                            ),
                            ("separator",),
                            (
                                "command",
                                "60 deg. over 4 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(4,60,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "60 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(8,60,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "60 deg. over 16 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(16,60,axis='x',start=%d)"
                                ),
                            ),
                            ("separator",),
                            (
                                "command",
                                "90 deg. over 6 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(6,90,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "90 deg. over 12 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(12,90,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "90 deg. over 24 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(24,90,axis='x',start=%d)"
                                ),
                            ),
                            ("separator",),
                            (
                                "command",
                                "120 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(8,120,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "120 deg. over 16 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(16,120,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "120 deg. over 32 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(32,120,axis='x',start=%d)"
                                ),
                            ),
                            ("separator",),
                            (
                                "command",
                                "180 deg. over 12 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(12,179.99,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "180 deg. over 24 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(24,179.99,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "180 deg. over 48 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(48,179.99,axis='x',start=%d)"
                                ),
                            ),
                        ],
                    ),
                    (
                        "menu",
                        "X-Roll",
                        [
                            (
                                "command",
                                "4 seconds",
                                lambda: self.controller.mvprg(
                                    "movie.add_roll(4.0,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "8 seconds",
                                lambda: self.controller.mvprg(
                                    "movie.add_roll(8.0,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "16 seconds",
                                lambda: self.controller.mvprg(
                                    "movie.add_roll(16.0,axis='x',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "32 seconds",
                                lambda: self.controller.mvprg(
                                    "movie.add_roll(32.0,axis='x',start=%d)"
                                ),
                            ),
                        ],
                    ),
                    ("separator",),
                    (
                        "menu",
                        "Y-Rock",
                        [
                            (
                                "command",
                                "30 deg. over 2 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(2,30,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "30 deg. over 4 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(4,30,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "30 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(8,30,axis='y',start=%d)"
                                ),
                            ),
                            ("separator",),
                            (
                                "command",
                                "60 deg. over 4 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(4,60,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "60 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(8,60,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "60 deg. over 16 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(16,60,axis='y',start=%d)"
                                ),
                            ),
                            ("separator",),
                            (
                                "command",
                                "90 deg. over 6 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(6,90,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "90 deg. over 12 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(12,90,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "90 deg. over 24 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(24,90,axis='y',start=%d)"
                                ),
                            ),
                            ("separator",),
                            (
                                "command",
                                "120 deg. over 8 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(8,120,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "120 deg. over 16 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(16,120,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "120 deg. over 32 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(32,120,axis='y',start=%d)"
                                ),
                            ),
                            ("separator",),
                            (
                                "command",
                                "180 deg. over 12 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(12,179.99,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "180 deg. over 24 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(24,179.99,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "180 deg. over 48 sec.",
                                lambda: self.controller.mvprg(
                                    "movie.add_rock(48,179.99,axis='y',start=%d)"
                                ),
                            ),
                        ],
                    ),
                    (
                        "menu",
                        "Y-Roll",
                        [
                            (
                                "command",
                                "4 seconds",
                                lambda: self.controller.mvprg(
                                    "movie.add_roll(4.0,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "8 seconds",
                                lambda: self.controller.mvprg(
                                    "movie.add_roll(8.0,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "16 seconds",
                                lambda: self.controller.mvprg(
                                    "movie.add_roll(16.0,axis='y',start=%d)"
                                ),
                            ),
                            (
                                "command",
                                "32 seconds",
                                lambda: self.controller.mvprg(
                                    "movie.add_roll(32.0,axis='y',start=%d)"
                                ),
                            ),
                        ],
                    ),
                ],
            ),
            ("separator",),
            (
                "menu",
                "Scene Loop",
                [
                    (
                        "menu",
                        lab,
                        [
                            (
                                "command",
                                f"{angle} deg. over {sec} sec.",
                                lambda s=f"set sweep_angle,{angle};cmd.movie.add_scenes(None, {sec}, rock={rock}, start=%d)": (
                                    self.controller.mvprg(s)
                                ),
                            )
                            for angle, seconds in (
                                (30, (2, 4, 8)),
                                (60, (4, 8, 16)),
                                (90, (6, 12, 24)),
                                (120, (8, 16, 32)),
                            )
                            for sec in seconds
                        ],
                    )
                    for lab, rock in [
                        ("Nutate", 4),
                        ("X-Rock", 2),
                        ("Y-Rock", 1),
                    ]
                ]
                + [
                    (
                        "menu",
                        "Steady",
                        [
                            (
                                "command",
                                f"{val} seconds each",
                                lambda s=f"movie.add_scenes(None,{val:.1f},rock=0,start=%d)": (
                                    self.controller.mvprg(s)
                                ),
                            )
                            for val in [1, 2, 4, 8, 12, 16, 24]
                        ],
                    )
                ],
            ),
            ("separator",),
        ] + [
            (
                "menu",
                lab,
                [
                    (
                        "menu",
                        "Full Speed" if speed == 1 else f"1/{speed} Speed",
                        [
                            (
                                "command",
                                f"{pause} second pause"
                                if pause
                                else "no pause",
                                lambda s=fmt % (speed, pause): (
                                    self.controller.mvprg(s + ", start=%d)")
                                ),
                            )
                            for pause in [0, 1, 2, 4]
                        ],
                    )
                    for speed in speeds
                ],
            )
            for lab, fmt in [
                ("State Loop", "movie.add_state_loop(%d, %d"),
                ("State Sweep", "movie.add_state_sweep(%d, %d"),
            ]
        ]

    def _extract_lines_sticks_layout(self):
        return [
            ("check", "Ball and Stick", "stick_ball", 1),
            (
                "menu",
                "Ball and Stick Ratio",
                [
                    ("radio", lab, "stick_ball_ratio", val)
                    for lab, val in [("1.0", 1.0), ("1.5", 1.5), ("VDW", -1.0)]
                ],
            ),
            ("separator",),
            (
                "menu",
                "Zero Order Bonds",
                [
                    ("radio", lab, "valence_zero_mode", val)
                    for lab, val in [("Hide", 0), ("Dashed", 1), ("Solid", 2)]
                ],
            ),
            (
                "menu",
                "Zero Order Stick Scale",
                [
                    ("radio", str(val), "valence_zero_scale", val)
                    for val in [0.1, 0.2, 0.3, 1.0]
                ],
            ),
            ("separator",),
            (
                "menu",
                "Stick Radius",
                [
                    ("radio", str(val), "stick_radius", val)
                    for val in [0.1, 0.2, 0.25]
                ],
            ),
            (
                "menu",
                "Stick Hydrogen Scale",
                [
                    ("radio", str(val), "stick_h_scale", val)
                    for val in [0.4, 1.0]
                ],
            ),
            ("separator",),
            (
                "menu",
                "Line Width",
                [
                    ("radio", str(val), "line_width", val)
                    for val in [1.0, 1.49, 3.0]
                ],
            ),
            ("check", "Lines As Cylinders", "line_as_cylinders", 1),
        ]

    def _extract_cartoon_layout(self):
        return [
            (
                "menu",
                "Rings and Bases",
                [
                    (
                        "radio",
                        "Filled Rings (Round Edges)",
                        "cartoon_ring_mode",
                        1,
                    ),
                    (
                        "radio",
                        "Filled Rings (Flat Edges)",
                        "cartoon_ring_mode",
                        2,
                    ),
                    (
                        "radio",
                        "Filled Rings (with Border)",
                        "cartoon_ring_mode",
                        3,
                    ),
                    ("radio", "Spheres", "cartoon_ring_mode", 4),
                    ("radio", "Base Ladders", "cartoon_ring_mode", 0),
                    ("separator",),
                    ("radio", "Bases and Sugars", "cartoon_ring_finder", 1),
                    ("radio", "Bases Only", "cartoon_ring_finder", 2),
                    ("radio", "Non-protein Rings", "cartoon_ring_finder", 3),
                    ("radio", "All Rings", "cartoon_ring_finder", 4),
                    ("separator",),
                    (
                        "radio",
                        "Transparent Rings",
                        "cartoon_ring_transparency",
                        0.5,
                    ),
                    ("radio", "Default", "cartoon_ring_transparency", -1),
                ],
            ),
            ("check", "Side Chain Helper", "cartoon_side_chain_helper", 1),
            ("check", "Round Helices", "cartoon_round_helices", 1),
            ("check", "Fancy Helices", "cartoon_fancy_helices", 1),
            ("check", "Cylindrical Helices", "cartoon_cylindrical_helices", 1),
            ("check", "Flat Sheets", "cartoon_flat_sheets", 1),
            ("check", "Fancy Sheets", "cartoon_fancy_sheets", 1),
            ("check", "Smooth Loops", "cartoon_smooth_loops", 1),
            ("check", "Discrete Colors", "cartoon_discrete_colors", 1),
            ("check", "Highlight Color", "cartoon_highlight_color", 104, -1),
            (
                "menu",
                "Sampling",
                [("radio", "Atom count dependent", "cartoon_sampling", -1)]
                + [
                    ("radio", str(val), "cartoon_sampling", val)
                    for val in [2, 7, 14]
                ],
            ),
            (
                "menu",
                "Gap Cutoff",
                [
                    ("radio", str(val), "cartoon_gap_cutoff", val)
                    for val in [0, 5, 10, 20]
                ],
            ),
        ]

    def _extract_ribbon_layout(self):
        return [
            ("check", "Side Chain Helper", "ribbon_side_chain_helper", 1),
            ("check", "Trace Atoms", "ribbon_trace_atoms", 1),
            ("separator",),
            ("radio", "As Lines", "ribbon_as_cylinders", 0),
            ("radio", "As Cylinders", "ribbon_as_cylinders", 1),
            (
                "menu",
                "Cylinder Radius",
                [("radio", "Match Line Width", "ribbon_radius", 0.0)]
                + [
                    ("radio", f"{val:.1f} Angstrom", "ribbon_radius", val)
                    for val in [0.2, 0.5, 1.0]
                ],
            ),
        ]

    def _extract_surface_layout(self):
        return [
            (
                "menu",
                "Color",
                [
                    ("radio", lab, "surface_color", val)
                    for lab, val in [
                        ("White", 0),
                        ("Light Gray", 4236),
                        ("Gray", 25),
                        ("Default (Atomic)", -1),
                    ]
                ],
            ),
            ("radio", "Dot", "surface_type", 1),
            ("radio", "Wireframe", "surface_type", 2),
            ("radio", "Solid", "surface_type", 0),
            ("separator",),
            ("radio", "Cavities and Pockets Only", "surface_cavity_mode", 1),
            (
                "radio",
                "Cavities and Pockets (Culled)",
                "surface_cavity_mode",
                2,
            ),
            (
                "menu",
                "Cavity Detection Radius",
                [("radio", "7 Angstrom", "surface_cavity_radius", 7)]
                + [
                    (
                        "radio",
                        f"{val} Solvent Radii",
                        "surface_cavity_radius",
                        -val,
                    )
                    for val in [3, 4, 5, 6, 8, 10, 20]
                ],
            ),
            (
                "menu",
                "Cavity Detection Cutoff",
                [
                    (
                        "radio",
                        f"{val} Solvent Radii",
                        "surface_cavity_cutoff",
                        -val,
                    )
                    for val in [1, 2, 3, 4, 5]
                ],
            ),
            ("radio", "Exterior (Normal)", "surface_cavity_mode", 0),
            ("separator",),
            ("check", "Solvent Accessible", "surface_solvent", 1),
            ("separator",),
            ("check", "Smooth Edges", "surface_smooth_edges", 1),
            ("check", "Edge Proximity", "surface_proximity", 1),
            ("separator",),
            ("radio", "Ignore None", "surface_mode", 1),
            ("radio", "Ignore HETATMs", "surface_mode", 0),
            ("radio", "Ignore Hydrogens", "surface_mode", 2),
            ("radio", "Ignore Unsurfaced", "surface_mode", 3),
        ]

    def _extract_rendering_layout(self, cmd):
        return [
            ("check", "OpenGL 2.0 Shaders", "use_shaders", 1),
            ("separator",),
            ("check", "Antialias (Ray Tracing)", "antialias", 1),
            (
                "menu",
                "Antialias (Real Time)",
                [
                    ("radio", lab, "antialias_shader", val)
                    for lab, val in [("off", 0), ("FXAA", 1), ("SMAA", 2)]
                ],
            ),
            ("separator",),
            (
                "command",
                "Modernize",
                lambda: cmd.util.modernize_rendering(1, cmd),
            ),
            ("separator",),
            (
                "menu",
                "Shadows",
                [
                    (
                        "command",
                        val.title(),
                        lambda v=val: cmd.util.ray_shadows(v),
                    )
                    for val in ["none", "light", "medium", "heavy", "black"]
                ]
                + [("separator",)]
                + [
                    (
                        "command",
                        val.title(),
                        lambda v=val: cmd.util.ray_shadows(v),
                    )
                    for val in ["matte", "soft", "occlusion", "occlusion2"]
                ],
            ),
            (
                "menu",
                "Texture",
                [
                    ("radio", lab, "ray_texture", val)
                    for lab, val in [
                        ("None", 0),
                        ("Matte 1", 1),
                        ("Matte 2", 4),
                        ("Swirl 1", 2),
                        ("Swirl 2", 3),
                        ("Fiber", 5),
                    ]
                ],
            ),
            (
                "menu",
                "Interior Texture",
                [
                    ("radio", lab, "ray_interior_texture", val)
                    for lab, val in [
                        ("None", 0),
                        ("Matte 1", 1),
                        ("Matte 2", 4),
                        ("Swirl 1", 2),
                        ("Swirl 2", 3),
                        ("Fiber", 5),
                    ]
                ],
            ),
            (
                "menu",
                "Memory",
                [
                    ("radio", lab, "hash_max", val)
                    for lab, val in [
                        ("Use Less (slower)", 70),
                        ("Use Standard Amount", 100),
                        ("Use More (faster)", 170),
                        ("Use Even More", 230),
                        ("Use Most", 300),
                    ]
                ],
            ),
            ("separator",),
            ("check", "Cull Backfaces", "backface_cull", 1),
            ("check", "Opaque Interiors", "ray_interior_color", 74, -1),
        ]

    def _generate_transparency_array(self, setting_name):
        return [
            ("radio", lab, setting_name, val)
            for lab, val in [
                ("Off", 0.0),
                ("20%", 0.2),
                ("40%", 0.4),
                ("50%", 0.5),
                ("60%", 0.6),
                ("80%", 0.8),
            ]
        ]


# ==============================================================================
# 4. UNIFIED NATIVE INTERFACE (Unified QMenuBar Control Core)
# ==============================================================================


class PyMOLMenuBar(QtWidgets.QMenuBar):
    """
    Native PyQt6 QMenuBar implementation running an isolated MVC loop.
    Use directly downstream via `self.setMenuBar(PyMOLMenuBar(self, cmd))`.
    """

    def __init__(self, parent, cmd):
        super().__init__(parent)

        # Native internal state collections matching engine targets
        self.menudict = {"": self}
        self.actiongroups = {}
        self.setting_callbacks = defaultdict(list)
        self.open_recent_menu = None

        # Instantiate structural system pipeline
        self.model = PyMOLMenuBarModel(cmd, desktop_gui=parent)
        self.controller = PyMOLMenuBarController(self.model)
        self.view = PyMOLMenuBarView(self.controller, self)

        self.controller.set_view(self.view)

        # Inflate tree layout components onto native widget nodes
        self.view.inflate_ui()

        # Setup modern Recent Files dynamically when the menu drops down
        if self.open_recent_menu:
            self.open_recent_menu.aboutToShow.connect(
                self._dynamic_refresh_recent_files
            )

    def _dynamic_refresh_recent_files(self):
        """Re-populates the recent items list dynamically when clicked."""
        self.open_recent_menu.clear()
        recent_list = self.controller.get_recent_filenames()
        if not recent_list:
            no_item_action = self.open_recent_menu.addAction(
                "No Recent Files Found"
            )
            no_item_action.setEnabled(False)
            return

        for fname in recent_list:
            display_label = fname if len(fname) < 128 else "..." + fname[-120:]
            # Safe runtime closure mapping string parameter safely to dynamic command callbacks
            self.open_recent_menu.addAction(
                display_label, lambda f=fname: self._load_file_fallback(f)
            )

    def _load_file_fallback(self, target_file):
        if self.model.desktop_gui and hasattr(
            self.model.desktop_gui, "load_dialog"
        ):
            self.model.desktop_gui.load_dialog(target_file)
        else:
            self.model.cmd.load(target_file)

    def update_menu_settings(self):
        """
        Call periodically or attach to update loops to synchronize check/radio
        menu states with internal PyMOL setting updates.
        """
        updates = self.model.cmd.get_setting_updates() or ()
        for setting_idx in updates:
            if setting_idx in self.setting_callbacks:
                current_val = self.model.cmd.get_setting_tuple(setting_idx)[1][
                    0
                ]
                for callback in self.setting_callbacks[setting_idx]:
                    callback(current_val)

    # --- Proxy Passthroughs for Command Interceptions ---
    def complete(self, getter, setter, cursor):
        return self.controller.complete(getter, setter, cursor)

    def doTypedCommand(self, command_str):
        self.controller.doTypedCommand(command_str)

    def back_search(self, getter, setter, cursor, set0=False):
        self.controller.back_search(getter, setter, cursor, set0)

    def back(self, getter, setter, cursor):
        self.controller.back(getter, setter, cursor)

    def forward(self, setter, cursor):
        self.controller.forward(setter, cursor)

    def recent_filenames_add(self, filename):
        self.controller.recent_filenames_add(filename)
