"""Contains the reusable elevated container widget."""

from __future__ import annotations

import typing

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

from pymol_copilot.gui import fluent


def dp(value: int | float) -> int:
    """Thin re-export of :func:`fluent.dp` for use within this package.

    Widgets that import ``elevated_container`` can call ``elevated_container.dp``
    without a separate ``fluent`` import.

    Args:
        value: Size in density-independent pixels (96 DPI baseline).

    Returns:
        Physical pixel equivalent for the primary screen.
    """
    return fluent.dp(value)


def _natural_control_height() -> int:
    """Return a comfortable single-row control height derived from the system font.

    Basing height on ``QFontMetrics`` (rather than a magic number) ensures
    the container looks correct even when the user has changed the OS font
    size — the same strategy used by Office and WinUI controls.

    Returns:
        An integer pixel height equal to the font's line height plus
        comfortable vertical padding (8 dp top + 8 dp bottom).
    """
    fm = QtGui.QFontMetrics(QtWidgets.QApplication.font())
    return fm.height() + dp(16)


class ElevatedContainer(QtWidgets.QWidget):
    """Base widget for rounded, shadowed composite UI components.

    All size parameters are expressed in **density-independent pixels**
    (96 DPI baseline).  The widget scales them to physical pixels at
    construction time via :func:`fluent.dp`.

    Default shadow values are sourced from :data:`fluent.ElevationLevel.CARD`
    so they stay in sync with the token system rather than being duplicated.

    Default geometry values are sourced from the active ``Win11Tokens``
    instance (``radius_overlay = 8 dp``, ``spacing_l = 16 dp``,
    ``spacing_s = 8 dp``).
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        height: int | None = None,
        bg_color: str | None = None,
        border_radius: int | None = None,
        elevation: fluent.ElevationLevel = fluent.ElevationLevel.CARD,
        orientation: typing.Literal["horizontal", "vertical"] = "horizontal",
    ) -> None:
        """Initialise the shared elevated container structure.

        All pixel arguments (``height``, ``border_radius``) are in dp and
        are converted to physical pixels internally.  Do **not** pre-scale
        them at the call site.

        Shadow parameters are derived from ``elevation`` via the token system,
        so they are always consistent with every other elevated surface in the
        application.

        Args:
            parent: The parent widget for this component.
            height: Optional fixed height for the visual container frame in dp.
                When omitted the height is derived from the system font metrics.
            bg_color: The frame background color as a QSS-compatible string.
                Defaults to ``tokens().layer_card`` (white / #333333).
            border_radius: Card corner radius in dp.  Defaults to
                ``tokens().radius_overlay`` (8 dp), matching the Fluent card
                radius for overlay surfaces.
            elevation: The WinUI3 elevation level that controls shadow blur,
                offset, and colour.  Defaults to ``ElevationLevel.CARD``.
            orientation: Direction of the inner content layout.

        Raises:
            ValueError: If the supplied orientation is unsupported.
            NotImplementedError: If a subclass does not implement ``setup_ui``.
        """
        super().__init__(parent)

        tok = fluent.tokens()

        # Resolve defaults from tokens so every elevated surface in the app
        # shares a single source of truth.
        resolved_bg = bg_color or tok.layer_card.name(
            QtGui.QColor.NameFormat.HexRgb
        )
        resolved_radius = (
            border_radius if border_radius is not None else tok.radius_overlay
        )

        # Scale all dp values to physical pixels once at construction time.
        scaled_radius = dp(resolved_radius)

        # Outer layout — spacing_s (8 dp) keeps the shadow visible and aligns
        # to the 8 dp base grid used by Fluent Design.
        self.outer_layout = QtWidgets.QHBoxLayout(self)
        _m = dp(tok.spacing_s)
        self.outer_layout.setContentsMargins(_m, _m, _m, _m)

        self.container_frame = QtWidgets.QFrame()
        self.container_frame.setObjectName("ElevatedContainerFrame")

        # Prefer font-metric height; fall back to the caller-supplied dp value.
        if height is not None:
            self.container_frame.setFixedHeight(dp(height))
        else:
            self.container_frame.setFixedHeight(_natural_control_height())

        self.container_frame.setStyleSheet(
            self._build_frame_style(resolved_bg, scaled_radius)
        )

        # Shadow sourced entirely from the token-system elevation level.
        self.shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(elevation.scaled_radius())
        self.shadow.setOffset(0.0, float(elevation.scaled_offset_y()))
        shadow_hex = (
            elevation.shadow_color_light
            if fluent.current_mode() == fluent.ThemeMode.Light
            else elevation.shadow_color_dark
        )
        self.shadow.setColor(fluent._hex_to_qcolor(shadow_hex))
        self.container_frame.setGraphicsEffect(self.shadow)

        self.content_layout: QtWidgets.QBoxLayout
        if orientation == "horizontal":
            self.content_layout = QtWidgets.QHBoxLayout(self.container_frame)
        elif orientation == "vertical":
            self.content_layout = QtWidgets.QVBoxLayout(self.container_frame)
        else:
            tmp_message = f"Unsupported orientation: {orientation}"
            raise ValueError(tmp_message)

        # spacing_l (16 dp) horizontal inset — standard Fluent content margin.
        # spacing_xs (4 dp) vertical — compact padding inside a toolbar row.
        # spacing_s (8 dp) inter-control gap — base grid unit.
        self.content_layout.setContentsMargins(
            dp(tok.spacing_l),
            dp(tok.spacing_xs),
            dp(tok.spacing_l),
            dp(tok.spacing_xs),
        )
        self.content_layout.setSpacing(dp(tok.spacing_s))
        self.content_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.outer_layout.addWidget(self.container_frame)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Build subclass-specific controls inside the content layout.

        Raises:
            NotImplementedError: Always raised by the base implementation.
        """
        tmp_message = "Subclasses must implement setup_ui."
        raise NotImplementedError(tmp_message)

    def _build_frame_style(
        self,
        bg_color: str,
        border_radius: int,
    ) -> str:
        """Build the base QSS for the elevated container frame.

        Args:
            bg_color: The frame background color as a QSS-compatible value.
            border_radius: The frame border radius in **physical pixels**
                (already dp-scaled by the caller).

        Returns:
            A QSS string for the elevated container frame.
        """
        return (
            "QFrame#ElevatedContainerFrame {"
            f"background-color: {bg_color};"
            f"border-radius: {border_radius}px;"
            "border: none;"
            "}"
        )
