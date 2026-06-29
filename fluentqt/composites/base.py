"""Base class for composite widgets."""

from __future__ import annotations

from typing import Literal
from typing import override

from PyQt6 import QtWidgets

from fluentqt.core import dp as dp_module
from fluentqt.core import state as state_module
from fluentqt.core import tokens as tokens_module
from fluentqt.enums import roles as roles_module
from fluentqt.primitives import frame as frame_module


class CompositeWidget(state_module.StatefulWidget):
    """A container widget for grouping other widgets with WinUI3 styling.

    This widget acts as an elevated surface containing other widgets arranged
    either horizontally or vertically, handling design tokens and layout margins.
    """

    def __init__(
        self,
        elevation: roles_module.ElevationPreset = (
            roles_module.ElevationPreset.Flat
        ),
        orientation: Literal["horizontal", "vertical"] = "horizontal",
        border_radius: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the CompositeWidget.

        Args:
            elevation: The semantic elevation preset determining shadow and
                border radius.
            orientation: The layout orientation of the composite's content.
            border_radius: Optional custom corner radius in dp.
            parent: Optional parent widget.
        """
        self._elevation = elevation
        self._orientation = orientation
        self._border_radius = border_radius

        self.frame: frame_module.TokenFrame | None = None
        """The internal frame. Subclasses must not replace/re-parent this."""

        self.content_layout: QtWidgets.QBoxLayout | None = None
        """The content layout. Subclasses must only add child widgets here."""

        self._outer_layout: QtWidgets.QVBoxLayout | None = None

        super().__init__(parent=parent)

        tmp_outer_layout = QtWidgets.QVBoxLayout(self)
        tmp_outer_layout.setSpacing(0)
        self._outer_layout = tmp_outer_layout

        tmp_frame = frame_module.TokenFrame(
            elevation=self._elevation,
            fill_role=roles_module.FillRole.Transparent,
            border_radius=self._border_radius,
            parent=self,
        )
        self.frame = tmp_frame
        tmp_outer_layout.addWidget(tmp_frame)

        if self._orientation == "horizontal":
            tmp_content_layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout(
                tmp_frame
            )
        else:
            tmp_content_layout = QtWidgets.QVBoxLayout(tmp_frame)
        self.content_layout = tmp_content_layout

        self._build_content()
        self._apply_tokens()

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
        if self.frame is not None:
            self.frame.set_elevation(elevation)
        self._apply_tokens()

    def border_radius(self) -> int | None:
        """Get the custom border radius of the composite in dp.

        Returns:
            The custom border radius in dp, or None if using default.
        """
        return self._border_radius

    def set_border_radius(self, border_radius: int | None) -> None:
        """Set the custom border radius and refresh style.

        Args:
            border_radius: The new border radius in dp.
        """
        if self._border_radius == border_radius:
            return
        self._border_radius = border_radius
        if self.frame is not None:
            self.frame.set_border_radius(border_radius)
        self._apply_tokens()

    def orientation(self) -> Literal["horizontal", "vertical"]:
        """Get the layout orientation of the composite content.

        Returns:
            The layout orientation.
        """
        return self._orientation

    @override
    def _apply_tokens(self) -> None:
        """Apply current design tokens to the widget and its frame.

        This method updates layout margins, spacing, and explicit tokens on the
        inner frame.
        """
        # Call superclass method to satisfy the StatefulWidget contract.
        # Visual styling is entirely delegated to self.frame.
        super()._apply_tokens()

        if self.frame is not None:
            tmp_tok = tokens_module.tokens()

            if self._outer_layout is not None:
                tmp_outer_margin = dp_module.dp(tmp_tok.spacing_s)
                self._outer_layout.setContentsMargins(
                    tmp_outer_margin,
                    tmp_outer_margin,
                    tmp_outer_margin,
                    tmp_outer_margin,
                )

            if self.content_layout is not None:
                tmp_h_margin = dp_module.dp(tmp_tok.spacing_l)
                tmp_v_margin = dp_module.dp(tmp_tok.spacing_xs)
                self.content_layout.setContentsMargins(
                    tmp_h_margin,
                    tmp_v_margin,
                    tmp_h_margin,
                    tmp_v_margin,
                )
                self.content_layout.setSpacing(dp_module.dp(tmp_tok.spacing_s))

    @override
    def _refresh_stylesheet(self) -> None:
        """Refresh the stylesheet of the composite widget.

        Since composite styling is managed by the internal TokenFrame, this
        method is a no-op.
        """
        return

    def _build_content(self) -> None:
        """Build and populate the content layout.

        Subclasses override this method to add child widgets to the
        content layout. The base implementation does nothing.
        """
        return

    def _handle_scale_changed(self, scale: float) -> None:
        """Handle screen scale change events.

        Args:
            scale: The new display scale factor.
        """
        _ = scale
        self._apply_tokens()
