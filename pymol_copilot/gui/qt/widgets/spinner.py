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
"""Provides a rotating-arc spinner widget."""

from __future__ import annotations

from typing import override

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme


class SpinnerWidget(QtWidgets.QWidget):
    """Lightweight rotating-arc spinner drawn entirely with QPainter."""

    def __init__(
        self,
        size: int = 16,
        color: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the spinner widget.

        Args:
            size: Fixed height and width of the spinner in dp.
            color: Optional hex string color override.
            parent: Optional parent QWidget.
        """
        super().__init__(parent)
        self._angle = 0
        self._size = size
        self._color = color
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(size, size)

    def _tick(self) -> None:
        """Increment rotation angle and trigger repaint."""
        self._angle = (self._angle + 4) % 360
        self.update()

    def start(self) -> None:
        """Start the rotation animation timer."""
        self._timer.start(16)

    def stop(self) -> None:
        """Stop the rotation animation timer."""
        self._timer.stop()

    @override
    def paintEvent(
        self,
        event: QtGui.QPaintEvent,
    ) -> None:
        """Draw the rotating-arc spinner using QPainter.

        Args:
            event: The QPaintEvent object.
        """
        tmp_painter = QtGui.QPainter(self)
        tmp_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        tmp_pen = QtGui.QPen(
            QtGui.QColor(
                self._color
                if self._color
                else theme.ThemeColors.ACCENT.to_hex()
            )
        )
        tmp_pen.setWidthF(2.0)
        tmp_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        tmp_painter.setPen(tmp_pen)
        tmp_margin = tmp_pen.widthF() + 0.5
        tmp_rect = QtCore.QRectF(
            tmp_margin,
            tmp_margin,
            self._size - 2 * tmp_margin,
            self._size - 2 * tmp_margin,
        )
        # Qt arc angles are in 1/16°; arc starts from top (90°) and sweeps 270°
        tmp_painter.drawArc(tmp_rect, (90 - self._angle) * 16, 270 * 16)
        tmp_painter.end()
