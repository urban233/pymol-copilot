"""A styled text label primitive."""

from __future__ import annotations

import dataclasses
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.core.stylesheet as stylesheet_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles_module


@dataclasses.dataclass(frozen=True)
class _LabelGeometry:
    """Label geometry settings in physical pixels.

    Attributes:
        font_size_px: Font size in physical pixels.
        font_size_dp: Font size in dp (for make_font).
        font_weight: Font weight (e.g. QFont.Weight).
        font_family: Font family name string.
    """

    font_size_px: int
    font_size_dp: int
    font_weight: QtGui.QFont.Weight
    font_family: str


@dataclasses.dataclass(frozen=True)
class _LabelColors:
    """Label color settings.

    Attributes:
        color: Text color.
    """

    color: QtGui.QColor


class TokenLabel(tokens_module.TokenConsumer, QtWidgets.QLabel):
    """A WinUI3-faithful styled text label primitive.

    This label uses design tokens to adapt its styling (color and typography)
    based on the current theme mode and DPI scaling.
    """

    def __init__(
        self,
        text: str = "",
        role: roles_module.TextRole = roles_module.TextRole.Primary,
        style: roles_module.TypeStyle = roles_module.TypeStyle.Body,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the TokenLabel.

        Args:
            text: The text to display on the label.
            role: The semantic text role determining the color.
            style: The typography style determining font configuration.
            parent: Optional parent widget.
        """
        self._role = role
        self._style = style

        # Cooperative multiple inheritance initialization
        super().__init__(text, parent=parent)

        # Connect to DPI scaling changes
        dp_module.notifier.scale_changed.connect(self._handle_scale_changed)

    def role(self) -> roles_module.TextRole:
        """Get the current text role.

        Returns:
            The active TextRole.
        """
        return self._role

    def set_role(self, role: roles_module.TextRole) -> None:
        """Set the text role and refresh the style.

        Args:
            role: The new TextRole.
        """
        if self._role == role:
            return
        self._role = role
        self._apply_tokens()

    def style(self) -> roles_module.TypeStyle:
        """Get the current type style.

        Returns:
            The active TypeStyle.
        """
        return self._style

    def set_style(self, style: roles_module.TypeStyle) -> None:
        """Set the typography style and refresh the style.

        Args:
            style: The new TypeStyle.
        """
        if self._style == style:
            return
        self._style = style
        self._apply_tokens()

    def _compute_geometry(self) -> _LabelGeometry:
        """Compute the DPI-scaled geometry values in physical pixels.

        Returns:
            A new _LabelGeometry instance containing scaled dimensions.
        """
        tmp_tok = tokens_module.tokens()
        tmp_size_field = self._style.size_token()
        tmp_weight_field = self._style.weight_token()

        tmp_size_dp = getattr(tmp_tok, tmp_size_field)
        tmp_weight = getattr(tmp_tok, tmp_weight_field)

        tmp_size_px = dp_module.dp(tmp_size_dp)

        tmp_font = tokens_module.make_font(tmp_size_dp, tmp_weight)
        tmp_family = tmp_font.family()

        return _LabelGeometry(
            font_size_px=tmp_size_px,
            font_size_dp=tmp_size_dp,
            font_weight=tmp_weight,
            font_family=tmp_family,
        )

    def _compute_colors(self) -> _LabelColors:
        """Resolve semantic roles to QColor instances based on current tokens.

        Returns:
            A new _LabelColors instance containing resolved colors.
        """
        tmp_tok = tokens_module.tokens()
        tmp_color = getattr(tmp_tok, self._role.value)
        return _LabelColors(color=tmp_color)

    @override
    def _apply_tokens(self) -> None:
        """Apply current tokens to geometry, colors, and font.

        This method is called on theme changes or manual properties updates.
        """
        self._colors = self._compute_colors()
        self._geometry = self._compute_geometry()

        tmp_font = tokens_module.make_font(
            self._geometry.font_size_dp,
            self._geometry.font_weight,
        )
        self.setFont(tmp_font)

        self._refresh_stylesheet()

    def _refresh_stylesheet(self) -> None:
        """Generate and apply the QSS stylesheet based on cached styles."""
        if not hasattr(self, "_colors") or not hasattr(self, "_geometry"):
            return

        tmp_qss = stylesheet_module.build_label_style(
            color=self._colors.color,
            font_size_px=self._geometry.font_size_px,
            font_weight=int(self._geometry.font_weight),
            font_family=self._geometry.font_family,
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
        """Return the size hint of the label.

        Returns:
            The size hint QSize.
        """
        return super().sizeHint()
