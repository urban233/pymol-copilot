"""Contains the reusable elevated container widget."""

from __future__ import annotations

import typing

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets


def dp(value: int | float) -> int:
    """Convert a density-independent pixel value to physical pixels.

    Sizes are defined at 96 DPI (100% / 1× scaling) and scaled up at
    runtime to match the user's OS display-scaling setting.  Always call
    this *after* ``QApplication`` has been created.

    Args:
        value: The size in density-independent pixels (96 DPI baseline).

    Returns:
        The equivalent size in physical pixels for the primary screen.
    """
    screen = QtWidgets.QApplication.primaryScreen()
    if screen is None:
        return round(value)
    scale = screen.logicalDotsPerInch() / 96.0
    return round(value * scale)


def _natural_control_height() -> int:
    """Return a comfortable single-row control height derived from the system font.

    Basing height on ``QFontMetrics`` (rather than a magic number) ensures
    the container looks correct even when the user has changed the OS font
    size — the same strategy used by Office and WinUI controls.

    Returns:
        An integer pixel height equal to the font's line height plus
        comfortable vertical padding.
    """
    fm = QtGui.QFontMetrics(QtWidgets.QApplication.font())
    # line height  +  16dp top/bottom padding  (matches content_layout V margins × 2)
    return fm.height() + dp(16)


class ElevatedContainer(QtWidgets.QWidget):
    """Base widget for rounded, shadowed composite UI components.

    All size parameters are expressed in **density-independent pixels**
    (96 DPI baseline).  The widget scales them automatically to physical
    pixels at construction time using the primary screen's logical DPI,
    so callers never need to think about the display's scale factor.

    Default values follow the Windows 11 Fluent Design / WinUI 2 system
    rather than web conventions:

    * Margins sit on an 8 dp grid.
    * ``border_radius=8`` matches the Fluent card radius (not the rounder
      12 dp typical of mobile / web cards).
    * The shadow uses a tight blur + small offset consistent with WinUI
      *Elevation 2* — visible enough to convey depth without looking like
      a floating CSS card.
    """

    def __init__(
            self,
            parent: QtWidgets.QWidget | None = None,
            *,
            height: int | None = None,
            bg_color: str = "#FFFFFF",
            border_radius: int = 8,
            shadow_blur: int = 12,
            shadow_offset: tuple[int, int] = (0, 2),
            shadow_alpha: int = 40,
            orientation: typing.Literal["horizontal", "vertical"] = "horizontal",
    ) -> None:
        """Initialise the shared elevated container structure.

        All pixel arguments (``height``, ``border_radius``, ``shadow_blur``,
        ``shadow_offset``) are in density-independent pixels and are converted
        to physical pixels internally — do **not** pre-scale them at the call
        site.

        Args:
            parent: The parent widget for this component.
            height: Optional fixed height for the visual container frame.
                When omitted the height is derived from the system font
                metrics so it adapts to the user's font-size setting.
            bg_color: The frame background color as a QSS-compatible value.
            border_radius: Card corner radius in dp.  Default ``8`` matches
                the Windows 11 Fluent card radius.
            shadow_blur: Drop-shadow blur radius in dp.  Default ``12``
                produces a tight, desktop-appropriate shadow (WinUI Elevation 2).
            shadow_offset: Horizontal and vertical shadow offset in dp.
                Default ``(0, 2)`` keeps the ratio ≈ blur / 6, matching
                Fluent's downward-only cast.
            shadow_alpha: Alpha (0–255) of the shadow colour.  Default ``40``
                is visible at blur 12 / offset 2 without looking heavy.
            orientation: Direction of the inner content layout.

        Raises:
            ValueError: If the supplied orientation is unsupported.
            NotImplementedError: If a subclass does not implement ``setup_ui``.
        """
        super().__init__(parent)

        # ------------------------------------------------------------------
        # Scale all caller-supplied dp values to physical pixels once.
        # Callers always work in dp; this class owns the conversion.
        # ------------------------------------------------------------------
        scaled_radius = dp(border_radius)
        scaled_blur = dp(shadow_blur)
        scaled_offset = (dp(shadow_offset[0]), dp(shadow_offset[1]))

        # Outer layout — 8 dp margin keeps the shadow visible and aligns to
        # the 8 dp grid used by Fluent Design and macOS HIG.
        self.outer_layout = QtWidgets.QHBoxLayout(self)
        self.outer_layout.setContentsMargins(dp(8), dp(8), dp(8), dp(8))

        self.container_frame = QtWidgets.QFrame()
        self.container_frame.setObjectName("ElevatedContainerFrame")

        # Prefer font-metric height so the row scales with the system font;
        # fall back to the caller-supplied value (still scaled to physical px).
        if height is not None:
            self.container_frame.setFixedHeight(dp(height))
        else:
            self.container_frame.setFixedHeight(_natural_control_height())

        self.container_frame.setStyleSheet(
            self._build_frame_style(bg_color, scaled_radius)
        )

        self.shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(scaled_blur)
        self.shadow.setOffset(scaled_offset[0], scaled_offset[1])
        self.shadow.setColor(QtGui.QColor(0, 0, 0, shadow_alpha))
        self.container_frame.setGraphicsEffect(self.shadow)

        self.content_layout: QtWidgets.QBoxLayout
        if orientation == "horizontal":
            self.content_layout = QtWidgets.QHBoxLayout(self.container_frame)
        elif orientation == "vertical":
            self.content_layout = QtWidgets.QVBoxLayout(self.container_frame)
        else:
            tmp_message = f"Unsupported orientation: {orientation}"
            raise ValueError(tmp_message)

        # 16 dp horizontal inset is the standard Fluent content margin.
        # 8 dp vertical keeps single-line rows compact, matching Office toolbars.
        # 8 dp spacing sits on the base grid unit; 12 dp is a web convention.
        self.content_layout.setContentsMargins(dp(16), dp(8), dp(16), dp(8))
        self.content_layout.setSpacing(dp(8))
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
                (already scaled by the caller).

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
