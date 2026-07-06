# cBioMOL - open C++ and Python platform for BioMOLecular visualization and
# analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban
# (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
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
"""Viewer widget for embedding PyMOL and handling custom overlays."""

from __future__ import annotations

from pmg_qt import pymol_gl_widget

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.widgets import convex_hull_overlay


class Viewer(QtWidgets.QWidget):
    """PyMOL Viewer widget."""

    # <editor-fold desc="Class attributes">
    viewportsignal: QtCore.pyqtSignal = QtCore.pyqtSignal(int, int)
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
        # self.cmd.color("yellow", "1DPX")

    def _init_widget(self) -> None:
        """Initialize child widgets and set layout margins."""
        self._layout.addWidget(self.pymolwidget)
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self.setLayout(self._layout)

    def _connect_signals(self) -> None:
        """Connect signal handlers to their destinations."""
        self.viewportsignal.connect(self.pymolviewport)

    def pymolviewport(self, w: int, h: int) -> None:
        """Updates the PyMOL viewport size based on the widget dimensions.

        Args:
            w: The target width.
            h: The target height.
        """
        tmp_cw, tmp_ch = self.cmd.get_viewport()
        tmp_pw = self.pymolwidget
        tmp_scale = tmp_pw.fb_scale

        # maintain aspect ratio
        if h < 1:
            if w < 1:
                tmp_pw.pymol.reshape(
                    int(tmp_scale * tmp_pw.width()),
                    int(tmp_scale * tmp_pw.height()),
                    True,
                )
                return
            h = (w * tmp_ch) / tmp_cw
        if w < 1:
            w = (h * tmp_cw) / tmp_ch

        tmp_win_size = self.size()
        tmp_delta = QtCore.QSize(w - tmp_cw, h - tmp_ch) / tmp_scale

        # window resize
        self.resize(tmp_delta + tmp_win_size)

    def highlight_selection(self, selection_name: str) -> None:
        """Highlights the specified PyMOL selection using a 2D convex hull.

        Args:
            selection_name: The name of the PyMOL selection.
        """
        self.overlay.set_selection(selection_name)
