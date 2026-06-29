"""A styled layout divider line."""

from __future__ import annotations

import dataclasses
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.core.stylesheet as stylesheet_module
import fluentqt.core.tokens as tokens_module


@dataclasses.dataclass(frozen=True)
class _DividerGeometry:
    """Divider geometry settings in physical pixels.

    Attributes:
        thickness_px: The line thickness in physical pixels.
    """

    thickness_px: int


@dataclasses.dataclass(frozen=True)
class _DividerColors:
    """Divider color settings.

    Attributes:
        color: The line color.
    """

    color: QtGui.QColor


class TokenDivider(tokens_module.TokenConsumer, QtWidgets.QFrame):
    """A WinUI3-faithful styled divider primitive.

    This divider displays a horizontal line that adapts its color and thickness
    based on the current theme mode and DPI scaling.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the TokenDivider.

        Args:
            parent: Optional parent widget.
        """
        self._geometry = _DividerGeometry(thickness_px=0)
        self._colors = _DividerColors(color=QtGui.QColor(0, 0, 0, 0))

        # Cooperative multiple inheritance initialization
        super().__init__(parent=parent)

        self.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)

        # Connect to DPI scaling changes
        dp_module.notifier.scale_changed.connect(self._handle_scale_changed)

    def _compute_geometry(self) -> _DividerGeometry:
        """Compute the DPI-scaled geometry values in physical pixels.

        Returns:
            A new _DividerGeometry instance containing scaled dimensions.
        """
        tmp_thickness_px = max(1, dp_module.dp(1))
        return _DividerGeometry(thickness_px=tmp_thickness_px)

    def _compute_colors(self) -> _DividerColors:
        """Resolve semantic roles to QColor instances based on current tokens.

        Returns:
            A new _DividerColors instance containing resolved colors.
        """
        tmp_tok = tokens_module.tokens()
        tmp_color = tmp_tok.stroke_default
        return _DividerColors(color=tmp_color)

    @override
    def _apply_tokens(self) -> None:
        """Apply current tokens to geometry and colors.

        This method is called on theme changes or manual properties updates.
        """
        self._colors = self._compute_colors()
        self._geometry = self._compute_geometry()
        self.setLineWidth(self._geometry.thickness_px)
        self._refresh_stylesheet()

    def _refresh_stylesheet(self) -> None:
        """Generate and apply the QSS stylesheet based on cached styles."""
        tmp_qss = stylesheet_module.build_divider_style(
            color=self._colors.color
        )
        self.setStyleSheet(tmp_qss)

    def _handle_scale_changed(self, scale: float) -> None:
        """Handle screen scale change events.

        Args:
            scale: The new display scale factor.
        """
        _ = scale
        self._apply_tokens()

    @override
    def sizeHint(self) -> QtCore.QSize:
        """Return the size hint of the divider.

        Returns:
            The size hint QSize.
        """
        tmp_hint = super().sizeHint()
        return QtCore.QSize(tmp_hint.width(), self._geometry.thickness_px)
