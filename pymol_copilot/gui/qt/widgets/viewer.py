"""Viewer widget for embedding PyMOL and handling custom overlays."""

from __future__ import annotations

from pmg_qt import pymol_gl_widget

from pymol_copilot.gui.qt import QtCore, ui_defaults
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.widgets import convex_hull_overlay


class Viewer(QtWidgets.QWidget):
    """PyMOL Viewer widget."""

    # <editor-fold desc="Class attributes">
    viewportsignal = QtCore.pyqtSignal(int, int)
    """A signal for thread-safe viewport command."""
    # </editor-fold>

    def __init__(self) -> None:
        """Initializes the Viewer widget and sets up the PyMOL GL widget."""
        super().__init__()
        self._layout = QtWidgets.QVBoxLayout()
        self.pymolwidget = pymol_gl_widget.PyMOLGLWidget(self)
        self.cmd = self.pymolwidget.cmd

        self._init_widget()
        self._connect_signals()

        # Instantiate overlay
        self.overlay = convex_hull_overlay.ConvexHullOverlay(
            self.pymolwidget, self.cmd
        )
        # Install event filter to keep overlay synced with viewport/camera
        self._filter = convex_hull_overlay.PyMOLWidgetEventFilter(self.overlay)
        self.pymolwidget.installEventFilter(self._filter)

        # Only for demonstration purposes.
        self.cmd.fetch("1DPX")
        self.cmd.remove("solvent")
        self.cmd.color("yellow", "1DPX")

    def _init_widget(self) -> None:
        self._layout.addWidget(self.pymolwidget)
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self.setLayout(self._layout)

    def _connect_signals(self) -> None:
        self.viewportsignal.connect(self.pymolviewport)

    def pymolviewport(self, w: int, h: int) -> None:
        """Updates the PyMOL viewport size based on the widget dimensions.

        Args:
            w: The target width.
            h: The target height.
        """
        cw, ch = self.cmd.get_viewport()
        pw = self.pymolwidget
        scale = pw.fb_scale

        # maintain aspect ratio
        if h < 1:
            if w < 1:
                pw.pymol.reshape(
                    int(scale * pw.width()), int(scale * pw.height()), True
                )
                return
            h = (w * ch) / cw
        if w < 1:
            w = (h * cw) / ch

        win_size = self.size()
        delta = QtCore.QSize(w - cw, h - ch) / scale

        # window resize
        self.resize(delta + win_size)

    def highlight_selection(self, selection_name: str) -> None:
        """Highlights the specified PyMOL selection using a 2D convex hull.

        Args:
            selection_name: The name of the PyMOL selection.
        """
        self.overlay.set_selection(selection_name)
