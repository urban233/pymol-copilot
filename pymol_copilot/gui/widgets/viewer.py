from pmg_qt import pymol_gl_widget

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets


class Viewer(QtWidgets.QWidget):
    """PyMOL Viewer widget."""

    # <editor-fold desc="Class attributes">
    viewportsignal = QtCore.Signal(int, int)
    """A signal for thread-safe viewport command."""
    # </editor-fold>

    def __init__(self) -> None:
        super().__init__()
        self._layout = QtWidgets.QVBoxLayout()
        self.pymolwidget = pymol_gl_widget.PyMOLGLWidget(self)
        self.cmd = self.pymolwidget.cmd

        self._init_widget()
        self._connect_signals()
        # Only for demonstration purposes.
        self.cmd.fetch("1DPX")

    def _init_widget(self) -> None:
        self._layout.addWidget(self.pymolwidget)
        self.setLayout(self._layout)

    def _connect_signals(self) -> None:
        self.viewportsignal.connect(self.pymolviewport)

    def pymolviewport(self, w, h):
        cw, ch = self.cmd.get_viewport()
        pw = self.pymolwidget
        scale = pw.fb_scale

        # maintain aspect ratio
        if h < 1:
            if w < 1:
                pw.pymol.reshape(int(scale * pw.width()), int(scale * pw.height()), True)
                return
            h = (w * ch) / cw
        if w < 1:
            w = (h * cw) / ch

        win_size = self.size()
        delta = QtCore.QSize(w - cw, h - ch) / scale

        # window resize
        self.resize(delta + win_size)
