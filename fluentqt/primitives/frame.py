"""A styled content container frame."""

from __future__ import annotations

import dataclasses
from typing import override

from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.core.stylesheet as stylesheet_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles_module


@dataclasses.dataclass(frozen=True)
class _FrameGeometry:
    """Frame visual dimensions in physical pixels.

    Attributes:
        radius_px: Corner radius in physical pixels.
        border_width_px: Border line width in physical pixels.
    """

    radius_px: int
    border_width_px: int


@dataclasses.dataclass(frozen=True)
class _FrameColors:
    """Frame color settings.

    Attributes:
        background: Background fill color.
        border: Border line color, or None if border_width is 0.
    """

    background: QtGui.QColor
    border: QtGui.QColor | None


class TokenFrame(tokens_module.TokenConsumer, QtWidgets.QFrame):
    """A WinUI3-faithful styled frame container.

    This frame uses design tokens to dynamically adapt its styling (background,
    border, and drop shadow) based on the current theme mode and DPI scaling.
    """

    def __init__(
        self,
        elevation: roles_module.ElevationPreset = (
            roles_module.ElevationPreset.Flat
        ),
        fill_role: roles_module.FillRole = roles_module.FillRole.Transparent,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the TokenFrame.

        Args:
            elevation: The semantic elevation preset determining shadow and
                radius.
            fill_role: The semantic fill role for the background color.
            parent: Optional parent widget.
        """
        self._elevation = elevation
        self._fill_role = fill_role
        self._shadow_effect = None

        # Cooperative multiple inheritance initialization
        super().__init__(parent=parent)

        # Now create self._shadow_effect (safe because C++ object exists)
        self._shadow_effect = QtWidgets.QGraphicsDropShadowEffect(self)
        self.setGraphicsEffect(self._shadow_effect)

        # Configure shadow parameters using the already computed and cached values
        tmp_level = self._elevation.elevation_level
        if tmp_level is None:
            self._shadow_effect.setEnabled(False)
        else:
            self._shadow_effect.setEnabled(True)
            self._shadow_effect.setBlurRadius(
                float(dp_module.dp(tmp_level.shadow_radius))
            )
            self._shadow_effect.setOffset(
                0.0, float(dp_module.dp(tmp_level.shadow_offset_y))
            )
            tmp_mode = tokens_module.current_mode()
            tmp_hex = (
                tmp_level.shadow_color_light
                if tmp_mode == tokens_module.ThemeMode.Light
                else tmp_level.shadow_color_dark
            )
            self._shadow_effect.setColor(
                tokens_module.hex_color_to_qcolor(tmp_hex)
            )

        # Connect to DPI scaling changes
        dp_module.notifier.scale_changed.connect(self._handle_scale_changed)

    def elevation(self) -> roles_module.ElevationPreset:
        """Get the current elevation preset.

        Returns:
            The active ElevationPreset.
        """
        return self._elevation

    def set_elevation(self, elevation: roles_module.ElevationPreset) -> None:
        """Set the elevation preset and refresh the widget style.

        Args:
            elevation: The new ElevationPreset.
        """
        if self._elevation == elevation:
            return
        self._elevation = elevation
        self._apply_tokens()

    def fill_role(self) -> roles_module.FillRole:
        """Get the current fill role.

        Returns:
            The active FillRole.
        """
        return self._fill_role

    def set_fill_role(self, fill_role: roles_module.FillRole) -> None:
        """Set the fill role and refresh the widget style.

        Args:
            fill_role: The new FillRole.
        """
        if self._fill_role == fill_role:
            return
        self._fill_role = fill_role
        self._apply_tokens()

    def _compute_geometry(self) -> _FrameGeometry:
        """Compute the DPI-scaled geometry values in physical pixels.

        Returns:
            A new _FrameGeometry instance containing scaled dimensions.
        """
        tmp_tokens = tokens_module.tokens()

        # Map ElevationPreset to corresponding radius token
        if self._elevation == roles_module.ElevationPreset.Flat:
            tmp_radius_dp = tmp_tokens.radius_none
        elif self._elevation in (
            roles_module.ElevationPreset.Layer,
            roles_module.ElevationPreset.Control,
        ):
            tmp_radius_dp = tmp_tokens.radius_control
        else:
            tmp_radius_dp = tmp_tokens.radius_overlay

        tmp_radius_px = dp_module.dp(tmp_radius_dp)

        # Border width is 1 physical pixel (or 1 dp scaled)
        if self._elevation != roles_module.ElevationPreset.Flat:
            tmp_border_width_px = dp_module.dp(1)
        else:
            tmp_border_width_px = 0

        return _FrameGeometry(
            radius_px=tmp_radius_px,
            border_width_px=tmp_border_width_px,
        )

    def _compute_colors(self) -> _FrameColors:
        """Resolve semantic roles to QColor instances based on current tokens.

        Returns:
            A new _FrameColors instance containing resolved colors.
        """
        tmp_tokens = tokens_module.tokens()

        # Resolve background color
        if self._fill_role == roles_module.FillRole.Transparent:
            tmp_background = QtGui.QColor(0, 0, 0, 0)
        else:
            tmp_background = getattr(tmp_tokens, self._fill_role.value)

        # Border color
        tmp_border = tmp_tokens.stroke_default

        return _FrameColors(background=tmp_background, border=tmp_border)

    @override
    def _apply_tokens(self) -> None:
        """Apply current tokens to geometry, colors, and shadow effect.

        This method is called on theme changes or manual properties updates.
        """
        self._colors = self._compute_colors()
        self._geometry = self._compute_geometry()

        # Apply shadow effect parameters
        if self._shadow_effect is not None:
            tmp_level = self._elevation.elevation_level
            if tmp_level is None:
                self._shadow_effect.setEnabled(False)
            else:
                self._shadow_effect.setEnabled(True)
                self._shadow_effect.setBlurRadius(
                    float(dp_module.dp(tmp_level.shadow_radius))
                )
                self._shadow_effect.setOffset(
                    0.0, float(dp_module.dp(tmp_level.shadow_offset_y))
                )

                tmp_mode = tokens_module.current_mode()
                tmp_hex = (
                    tmp_level.shadow_color_light
                    if tmp_mode == tokens_module.ThemeMode.Light
                    else tmp_level.shadow_color_dark
                )
                self._shadow_effect.setColor(
                    tokens_module.hex_color_to_qcolor(tmp_hex)
                )

        self._refresh_stylesheet()

    def _refresh_stylesheet(self) -> None:
        """Generate and apply the QSS stylesheet based on cached styles."""
        tmp_qss = stylesheet_module.build_frame_style(
            background=self._colors.background,
            radius_px=self._geometry.radius_px,
            border=self._colors.border,
            border_width_px=self._geometry.border_width_px,
        )
        self.setStyleSheet(tmp_qss)

    def _handle_scale_changed(self, scale: float) -> None:
        """Handle screen scale change events.

        Args:
            scale: The new display scale factor.
        """
        _ = scale
        self._apply_tokens()
