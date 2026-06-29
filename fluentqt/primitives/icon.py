"""A styled icon label widget."""

from __future__ import annotations

import dataclasses
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles_module


@dataclasses.dataclass(frozen=True)
class _IconGeometry:
    """Icon geometry settings in physical pixels.

    Attributes:
        size_px: Height and width in physical pixels.
    """

    size_px: int


@dataclasses.dataclass(frozen=True)
class _IconColors:
    """Icon color settings."""


class TokenIcon(tokens_module.TokenConsumer, QtWidgets.QLabel):
    """A WinUI3-faithful styled icon primitive.

    This widget displays an icon from a name string (loaded via a registered
    global provider), a QIcon, or a QPixmap, scaling it automatically with
    DPI scaling changes.
    """

    _STYLESHEET = "TokenIcon { background-color: transparent; border: none; }"

    def __init__(
        self,
        icon: str | QtGui.QIcon | QtGui.QPixmap,
        size: roles_module.IconSize = roles_module.IconSize.Medium,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the TokenIcon.

        Args:
            icon: The icon identifier string, QIcon, or QPixmap to display.
            size: The semantic size of the icon.
            parent: Optional parent widget.
        """
        self._icon = icon
        self._size = size
        self._geometry = _IconGeometry(size_px=0)
        self._colors = _IconColors()

        # Cooperative multiple inheritance initialization
        super().__init__(parent=parent)

        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Connect to DPI scaling changes
        dp_module.notifier.scale_changed.connect(self._handle_scale_changed)

    def icon(self) -> str | QtGui.QIcon | QtGui.QPixmap:
        """Get the current icon source.

        Returns:
            The active icon identifier string, QIcon, or QPixmap.
        """
        return self._icon

    def set_icon(self, icon: str | QtGui.QIcon | QtGui.QPixmap) -> None:
        """Set the icon source and refresh the widget style.

        Args:
            icon: The new icon identifier string, QIcon, or QPixmap.
        """
        if self._icon == icon:
            return
        self._icon = icon
        self._apply_tokens()

    def size_preset(self) -> roles_module.IconSize:
        """Get the current size preset.

        Returns:
            The active IconSize preset.
        """
        return self._size

    def set_size_preset(self, size: roles_module.IconSize) -> None:
        """Set the size preset and refresh the widget style.

        Args:
            size: The new IconSize preset.
        """
        if self._size == size:
            return
        self._size = size
        self._apply_tokens()

    def _compute_geometry(self) -> _IconGeometry:
        """Compute the DPI-scaled geometry values in physical pixels.

        Returns:
            A new _IconGeometry instance containing scaled dimensions.
        """
        tmp_size_px = dp_module.dp(self._size.value)
        return _IconGeometry(size_px=tmp_size_px)

    def _compute_colors(self) -> _IconColors:
        """Resolve semantic roles to colors.

        Returns:
            A new _IconColors instance.
        """
        return _IconColors()

    @override
    def _apply_tokens(self) -> None:
        """Apply current tokens to geometry, colors, and the displayed pixmap.

        This method is called on theme changes or manual properties updates.
        """
        self._colors = self._compute_colors()
        self._geometry = self._compute_geometry()

        tmp_size_px = self._geometry.size_px
        self.setFixedSize(tmp_size_px, tmp_size_px)

        if isinstance(self._icon, str):
            from fluentqt.core import factory as factory_module

            tmp_provider = factory_module.get_icon_provider()
            if tmp_provider is not None:
                tmp_qicon = tmp_provider(self._icon)
                tmp_pixmap = tmp_qicon.pixmap(tmp_size_px, tmp_size_px)
            else:
                tmp_pixmap = QtGui.QPixmap()
        elif isinstance(self._icon, QtGui.QIcon):
            tmp_pixmap = self._icon.pixmap(tmp_size_px, tmp_size_px)
        elif isinstance(self._icon, QtGui.QPixmap):
            tmp_pixmap = self._icon.scaled(
                tmp_size_px,
                tmp_size_px,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        else:
            tmp_pixmap = QtGui.QPixmap()

        self.setPixmap(tmp_pixmap)
        self._refresh_stylesheet()

    def _refresh_stylesheet(self) -> None:
        """Generate and apply the QSS stylesheet based on cached styles."""
        self.setStyleSheet(self._STYLESHEET)

    def _handle_scale_changed(self, scale: float) -> None:
        """Handle screen scale change events.

        Args:
            scale: The new display scale factor.
        """
        _ = scale
        self._apply_tokens()

    @override
    def sizeHint(self) -> QtCore.QSize:
        """Return the size hint of the icon.

        Returns:
            The size hint QSize.
        """
        return QtCore.QSize(self._geometry.size_px, self._geometry.size_px)
