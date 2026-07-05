from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme


class SpinnerWidget(QtWidgets.QWidget):
    """Lightweight rotating-arc spinner drawn entirely with QPainter."""

    def __init__(
        self, size: int = 16, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._angle = 0
        self._size = size
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(size, size)

    def _tick(self) -> None:
        self._angle = (self._angle + 4) % 360
        self.update()

    def start(self) -> None:
        self._timer.start(16)

    def stop(self) -> None:
        self._timer.stop()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(theme.ThemeColors.ACCENT.to_hex()))
        pen.setWidthF(2.0)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        margin = pen.widthF() + 0.5
        rect = QtCore.QRectF(
            margin,
            margin,
            self._size - 2 * margin,
            self._size - 2 * margin,
        )
        # Qt arc angles are in 1/16°; arc starts from top (90°) and sweeps 270°
        painter.drawArc(rect, (90 - self._angle) * 16, 270 * 16)
        painter.end()
