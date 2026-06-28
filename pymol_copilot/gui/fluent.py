"""Windows 11 Fluent design token system for PyMOL Copilot.

Single, authoritative source of every visual constant used across the
application: colors, radii, elevation, typography, motion, and spacing,
faithfully translated from the Windows 11 design guidelines into PyQt6.

No widget ever hardcodes a color, radius, font weight, spacing value,
shadow, or animation duration.  Every such value originates here.

HiDPI contract
--------------
All dimension tokens (spacing, radius, typography size, shadow parameters)
are stored as **density-independent pixels (dp)** at a 96 DPI baseline.
Widgets must pass them through :func:`dp` before using them in any Qt API
that expects physical pixels.  ``QColor`` and ``QEasingCurve`` fields are
DPI-agnostic and need no conversion.

The single exception is :func:`make_font`, which applies ``dp()``
internally — callers pass raw ``Win11Tokens.type_*_size`` values directly.

Typical import pattern::

    from pymol_copilot.gui import fluent

    tok = fluent.tokens()
    color = tok.layer_base
    font  = fluent.make_font(tok.type_body_size, tok.type_body_weight)

    # Dimension tokens require dp() at the call site:
    layout.setSpacing(fluent.dp(tok.spacing_m))
    frame.setStyleSheet(f"border-radius: {fluent.dp(tok.radius_control)}px;")

OS mode is detected automatically on first use and updated whenever the
platform fires an ``ApplicationPaletteChange`` event.
"""

from __future__ import annotations

import dataclasses
import enum
import sys
from typing import Callable
from typing import Final
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

__docformat__ = "google"


# ---------------------------------------------------------------------------
# dp — density-independent pixel helper
# ---------------------------------------------------------------------------


def dp(value: int | float) -> int:
    """Convert a density-independent pixel value to physical pixels.

    All dimension tokens in :class:`Win11Tokens` and :class:`ElevationLevel`
    are expressed in dp at a 96 DPI baseline.  Widgets call this function
    whenever they pass a token value to a Qt API that expects physical pixels.

    Always call *after* ``QApplication`` has been created.

    Args:
        value: Size in density-independent pixels (96 DPI = 1x baseline).

    Returns:
        The equivalent size in physical pixels for the primary screen,
        rounded to the nearest integer.
    """
    screen = QtWidgets.QApplication.primaryScreen()
    if screen is None:
        return round(value)
    scale = screen.logicalDotsPerInch() / 96.0
    return round(value * scale)


# ---------------------------------------------------------------------------
# ThemeMode
# ---------------------------------------------------------------------------


class ThemeMode(enum.Enum):
    """OS colour-scheme preference.

    Attributes:
        Light: Light mode (default fallback when detection fails).
        Dark: Dark mode.
    """

    Light = "light"
    Dark = "dark"


# ---------------------------------------------------------------------------
# Elevation
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _ElevationSpec:
    """Raw shadow parameters for one elevation level.

    All pixel values are in **density-independent pixels** and must be
    passed through :func:`dp` before being given to any Qt API.

    Attributes:
        shadow_radius: Gaussian blur radius in dp.
        shadow_offset_y: Vertical drop-shadow offset in dp.
        shadow_color_light: RRGGBBAA hex shadow colour for light mode.
        shadow_color_dark: RRGGBBAA hex shadow colour for dark mode.
    """

    shadow_radius: int
    shadow_offset_y: int
    shadow_color_light: str
    shadow_color_dark: str


class ElevationLevel(enum.Enum):
    """Windows 11 elevation levels mapping depth to shadow parameters.

    Each member wraps an ``_ElevationSpec`` whose pixel values are in **dp**
    and must be scaled via :func:`dp` before use in Qt APIs.

    Attributes:
        LAYER: Flat in-page surface layer (shadow_radius=1 dp).
        CONTROL: Resting buttons and inputs (shadow_radius=2 dp).
        CARD: Content cards (shadow_radius=4 dp).
        FLYOUT: Menus, flyouts, and dropdowns (shadow_radius=8 dp).
        DIALOG: Modal dialogs (shadow_radius=16 dp).
    """

    LAYER = _ElevationSpec(1, 1, "#0000000d", "#0000004d")
    CONTROL = _ElevationSpec(2, 1, "#00000012", "#00000052")
    CARD = _ElevationSpec(4, 2, "#0000001a", "#0000005c")
    FLYOUT = _ElevationSpec(8, 4, "#00000026", "#00000066")
    DIALOG = _ElevationSpec(16, 8, "#00000033", "#00000080")

    @property
    def shadow_radius(self) -> int:
        """Gaussian blur radius in dp.

        Returns:
            Integer dp value.  Pass through :func:`dp` before use.
        """
        return self.value.shadow_radius

    @property
    def shadow_offset_y(self) -> int:
        """Vertical drop-shadow offset in dp.

        Returns:
            Integer dp value.  Pass through :func:`dp` before use.
        """
        return self.value.shadow_offset_y

    @property
    def shadow_color_light(self) -> str:
        """RRGGBBAA hex shadow colour string for light mode.

        Returns:
            Eight-character hex string, e.g. ``"#0000001a"``.
        """
        return self.value.shadow_color_light

    @property
    def shadow_color_dark(self) -> str:
        """RRGGBBAA hex shadow colour string for dark mode.

        Returns:
            Eight-character hex string, e.g. ``"#0000005c"``.
        """
        return self.value.shadow_color_dark

    def scaled_radius(self) -> int:
        """Return ``shadow_radius`` converted to physical pixels via :func:`dp`.

        Convenience wrapper so callers do not need to write
        ``dp(level.shadow_radius)`` everywhere.

        Returns:
            Physical pixel blur radius for the current display scale.
        """
        return dp(self.shadow_radius)

    def scaled_offset_y(self) -> int:
        """Return ``shadow_offset_y`` converted to physical pixels via :func:`dp`.

        Returns:
            Physical pixel vertical offset for the current display scale.
        """
        return dp(self.shadow_offset_y)


# ---------------------------------------------------------------------------
# Win11Tokens
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Win11Tokens:
    """Resolved design tokens for one OS colour-scheme mode.

    This is the only type the rest of the codebase ever touches.
    Obtain an instance via ``fluent.tokens()``; never construct directly.

    **DPI contract for each field group:**

    * ``QColor`` fields — DPI-agnostic, use directly.
    * ``type_*_size`` fields — dp values; pass through :func:`dp` only
      when calling ``setFixedSize`` or similar physical-pixel APIs.
      :func:`make_font` handles the conversion internally.
    * ``type_*_weight`` fields — ``QtGui.QFont.Weight`` enum, use directly.
    * ``type_*_line_height`` fields — dp values; pass through :func:`dp`.
    * ``radius_*`` fields — dp values; pass through :func:`dp` before
      embedding in a QSS ``border-radius: Npx`` rule or calling
      ``setFixedSize``.
    * ``spacing_*`` fields — dp values; pass through :func:`dp` before
      any layout or geometry call.
    * ``motion_*_ms`` fields — milliseconds, not pixels; use directly.
    * ``motion_*_curve`` fields — ``QEasingCurve``, use directly.
    """

    # ── Neutral layers ────────────────────────────────────────────────────
    layer_base: QtGui.QColor
    layer_content: QtGui.QColor
    layer_card: QtGui.QColor
    layer_flyout: QtGui.QColor
    layer_dialog: QtGui.QColor

    # ── Strokes ───────────────────────────────────────────────────────────
    stroke_default: QtGui.QColor
    stroke_control: QtGui.QColor
    stroke_focus: QtGui.QColor
    stroke_focus_inner: QtGui.QColor

    # ── Text ──────────────────────────────────────────────────────────────
    text_primary: QtGui.QColor
    text_secondary: QtGui.QColor
    text_tertiary: QtGui.QColor
    text_disabled: QtGui.QColor
    text_on_accent: QtGui.QColor

    # ── Control fills ─────────────────────────────────────────────────────
    fill_control_default: QtGui.QColor
    fill_control_hover: QtGui.QColor
    fill_control_pressed: QtGui.QColor
    fill_control_disabled: QtGui.QColor
    fill_subtle_hover: QtGui.QColor
    fill_subtle_pressed: QtGui.QColor

    # ── Accent ────────────────────────────────────────────────────────────
    accent_default: QtGui.QColor
    accent_hover: QtGui.QColor
    accent_pressed: QtGui.QColor
    accent_disabled: QtGui.QColor
    accent_text_light: QtGui.QColor

    # ── Status colours ────────────────────────────────────────────────────
    status_info_background: QtGui.QColor
    status_info_text: QtGui.QColor
    status_info_border: QtGui.QColor

    status_success_background: QtGui.QColor
    status_success_text: QtGui.QColor
    status_success_border: QtGui.QColor

    status_warning_background: QtGui.QColor
    status_warning_text: QtGui.QColor
    status_warning_border: QtGui.QColor

    status_error_background: QtGui.QColor
    status_error_text: QtGui.QColor
    status_error_border: QtGui.QColor

    # ── Geometry — corner radii (dp) ──────────────────────────────────────
    # Pass through dp() before use in QSS or geometry APIs.
    # Do NOT round when a control edge touches a container edge.
    # Do NOT round when two sibling controls share a straight boundary.
    radius_control: int  # 4 dp — buttons, inputs, checkboxes, InfoBar
    radius_overlay: int  # 8 dp — flyouts, dialogs, menus, cards
    radius_tooltip: int  # 4 dp — tooltip exception (small surface)
    radius_none: int  # 0 dp — snapped/maximised windows, shared edges

    # ── Typography — Windows 11 type ramp (sizes in dp) ──────────────────
    # Only Regular (400) and Semibold (600) weights are permitted.
    # All *_size values are in dp; make_font() applies dp() internally.
    # All *_line_height values are in dp; callers must apply dp().
    type_caption_size: int
    type_caption_weight: QtGui.QFont.Weight
    type_caption_line_height: int

    type_body_size: int
    type_body_weight: QtGui.QFont.Weight
    type_body_line_height: int

    type_body_strong_size: int
    type_body_strong_weight: QtGui.QFont.Weight
    type_body_strong_line_height: int

    type_body_large_size: int
    type_body_large_weight: QtGui.QFont.Weight
    type_body_large_line_height: int

    type_body_large_strong_size: int
    type_body_large_strong_weight: QtGui.QFont.Weight
    type_body_large_strong_line_height: int

    type_subtitle_size: int
    type_subtitle_weight: QtGui.QFont.Weight
    type_subtitle_line_height: int

    type_title_size: int
    type_title_weight: QtGui.QFont.Weight
    type_title_line_height: int

    type_title_large_size: int
    type_title_large_weight: QtGui.QFont.Weight
    type_title_large_line_height: int

    type_display_size: int
    type_display_weight: QtGui.QFont.Weight
    type_display_line_height: int

    # ── Motion (milliseconds — not pixels, no dp() needed) ────────────────
    motion_fast_ms: int
    motion_fast_curve: QtCore.QEasingCurve = dataclasses.field(
        hash=False, compare=False
    )
    motion_normal_ms: int = dataclasses.field(hash=True, compare=True)
    motion_normal_curve: QtCore.QEasingCurve = dataclasses.field(
        hash=False, compare=False
    )
    motion_exit_ms: int = dataclasses.field(hash=True, compare=True)
    motion_exit_curve: QtCore.QEasingCurve = dataclasses.field(
        hash=False, compare=False
    )
    motion_gentle_exit_ms: int = dataclasses.field(hash=True, compare=True)
    motion_gentle_exit_curve: QtCore.QEasingCurve = dataclasses.field(
        hash=False, compare=False
    )
    motion_fade_ms: int = dataclasses.field(hash=True, compare=True)
    motion_fade_curve: QtCore.QEasingCurve = dataclasses.field(
        hash=False, compare=False
    )

    # ── Spacing — WinUI3 4 dp base grid (all values in dp) ───────────────
    # Pass through dp() before any layout or geometry call.
    spacing_xxs: int  # 2 dp  — icon-to-text gap within a control
    spacing_xs: int  # 4 dp  — tight internal padding (badge, chip)
    spacing_s: int  # 8 dp  — control internal padding (button, input)
    spacing_m: int  # 12 dp — gap between sibling controls
    spacing_l: int  # 16 dp — section padding; card content margin
    spacing_xl: int  # 20 dp — gap between card and page edge
    spacing_xxl: int  # 24 dp — vertical spacing between sections
    spacing_xxxl: int  # 32 dp — page-level margins


# ---------------------------------------------------------------------------
# Private constants and module state
# ---------------------------------------------------------------------------

_ELEVATION_MAP: Final[dict[int, ElevationLevel]] = {
    1: ElevationLevel.LAYER,
    2: ElevationLevel.CONTROL,
    3: ElevationLevel.CARD,
    4: ElevationLevel.FLYOUT,
    5: ElevationLevel.DIALOG,
}

_callbacks: list[Callable[[], None]] = []
_current_mode: ThemeMode | None = None
_filter_obj: "_AppModeFilter | None" = None
_filter_installed: bool = False
_platform_font_family: str | None = None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _hex_to_qcolor(hex_str: str) -> QtGui.QColor:
    """Parse a RRGGBB or RRGGBBAA hex string into a ``QColor``.

    Qt's built-in ``QColor("#RRGGBBAA")`` constructor interprets eight-digit
    strings as AARRGGBB, which is the opposite of the CSS/WinUI convention.
    This helper handles both formats correctly.

    Args:
        hex_str: Hex colour string, e.g. ``"#f3f3f3"`` or ``"#000000e3"``.

    Returns:
        A valid ``QColor``.
    """
    raw = hex_str.lstrip("#")
    if len(raw) == 8:
        r = int(raw[0:2], 16)
        g = int(raw[2:4], 16)
        b = int(raw[4:6], 16)
        a = int(raw[6:8], 16)
        return QtGui.QColor(r, g, b, a)
    return QtGui.QColor(hex_str)


def _c(
    light_hex: str,
    dark_hex: str,
    mode: ThemeMode,
) -> QtGui.QColor:
    """Select and parse the correct hex colour for the given mode.

    Args:
        light_hex: RRGGBB or RRGGBBAA hex string for light mode.
        dark_hex: RRGGBB or RRGGBBAA hex string for dark mode.
        mode: The target colour-scheme mode.

    Returns:
        A ``QColor`` resolved for ``mode``.
    """
    return _hex_to_qcolor(light_hex if mode == ThemeMode.Light else dark_hex)


def _bezier(
    p1x: float,
    p1y: float,
    p2x: float,
    p2y: float,
) -> QtCore.QEasingCurve:
    """Construct a cubic-bezier ``QEasingCurve`` from CSS control points.

    Args:
        p1x: X coordinate of the first control point (0 to 1).
        p1y: Y coordinate of the first control point (0 to 1).
        p2x: X coordinate of the second control point (0 to 1).
        p2y: Y coordinate of the second control point (0 to 1).

    Returns:
        A configured ``QEasingCurve`` with ``BezierSpline`` type.
    """
    curve = QtCore.QEasingCurve(QtCore.QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(
        QtCore.QPointF(p1x, p1y),
        QtCore.QPointF(p2x, p2y),
        QtCore.QPointF(1.0, 1.0),
    )
    return curve


def _build_tokens(mode: ThemeMode) -> Win11Tokens:
    """Construct a fully-populated ``Win11Tokens`` for ``mode``.

    Args:
        mode: The colour-scheme mode to build tokens for.

    Returns:
        A frozen ``Win11Tokens`` instance.
    """
    _reg = QtGui.QFont.Weight.Normal
    _semi = QtGui.QFont.Weight.DemiBold
    _lin = QtCore.QEasingCurve(QtCore.QEasingCurve.Type.Linear)

    return Win11Tokens(
        # ── Neutral layers ────────────────────────────────────────────
        layer_base=_c("#f3f3f3", "#202020", mode),
        layer_content=_c("#ffffff", "#2c2c2c", mode),
        layer_card=_c("#ffffff", "#333333", mode),
        layer_flyout=_c("#f9f9f9", "#272727", mode),
        layer_dialog=_c("#f3f3f3", "#202020", mode),
        # ── Strokes ───────────────────────────────────────────────────
        stroke_default=_c("#e5e5e5", "#3d3d3d", mode),
        stroke_control=_c("#0000001a", "#ffffff1a", mode),
        stroke_focus=_c("#000000", "#ffffff", mode),
        stroke_focus_inner=_c("#ffffff", "#000000", mode),
        # ── Text ──────────────────────────────────────────────────────
        text_primary=_c("#000000e3", "#ffffffE3", mode),
        text_secondary=_c("#00000099", "#ffffff99", mode),
        text_tertiary=_c("#00000072", "#ffffff72", mode),
        text_disabled=_c("#0000005c", "#ffffff5c", mode),
        text_on_accent=_c("#ffffff", "#000000", mode),
        # ── Control fills ─────────────────────────────────────────────
        fill_control_default=_c("#ffffffb3", "#ffffff0d", mode),
        fill_control_hover=_c("#f9f9f9b3", "#ffffff15", mode),
        fill_control_pressed=_c("#f3f3f3b3", "#ffffff08", mode),
        fill_control_disabled=_c("#f3f3f34c", "#ffffff0a", mode),
        fill_subtle_hover=_c("#0000000f", "#ffffff0f", mode),
        fill_subtle_pressed=_c("#0000000a", "#ffffff0a", mode),
        # ── Accent ────────────────────────────────────────────────────
        accent_default=_c("#0067c0", "#60cdff", mode),
        accent_hover=_c("#1975c4", "#78d2ff", mode),
        accent_pressed=_c("#005aa3", "#3dc9ff", mode),
        accent_disabled=_c("#0000005c", "#ffffff5c", mode),
        accent_text_light=_c("#003e92", "#60cdff", mode),
        # ── Status: info ──────────────────────────────────────────────
        status_info_background=_c("#ebf3fc", "#00213d", mode),
        status_info_text=_c("#0f6cbd", "#479ef5", mode),
        status_info_border=_c("#0f6cbd", "#1a6ab1", mode),
        # ── Status: success ───────────────────────────────────────────
        status_success_background=_c("#f1faf1", "#052505", mode),
        status_success_text=_c("#107c10", "#6bb700", mode),
        status_success_border=_c("#6bb700", "#3d6b00", mode),
        # ── Status: warning ───────────────────────────────────────────
        status_warning_background=_c("#fff9f0", "#2c1a00", mode),
        status_warning_text=_c("#835d00", "#f9c860", mode),
        status_warning_border=_c("#f9c860", "#835d00", mode),
        # ── Status: error ─────────────────────────────────────────────
        status_error_background=_c("#fdf3f4", "#3b0509", mode),
        status_error_text=_c("#bc2f32", "#f75f61", mode),
        status_error_border=_c("#eeaaaa", "#6e1e1e", mode),
        # ── Geometry (dp — callers must apply dp()) ───────────────────
        radius_control=4,
        radius_overlay=8,
        radius_tooltip=4,
        radius_none=0,
        # ── Typography (sizes in dp — make_font applies dp() internally)
        type_caption_size=12,
        type_caption_weight=_reg,
        type_caption_line_height=16,
        type_body_size=14,
        type_body_weight=_reg,
        type_body_line_height=20,
        type_body_strong_size=14,
        type_body_strong_weight=_semi,
        type_body_strong_line_height=20,
        type_body_large_size=18,
        type_body_large_weight=_reg,
        type_body_large_line_height=24,
        type_body_large_strong_size=18,
        type_body_large_strong_weight=_semi,
        type_body_large_strong_line_height=24,
        type_subtitle_size=20,
        type_subtitle_weight=_semi,
        type_subtitle_line_height=28,
        type_title_size=28,
        type_title_weight=_semi,
        type_title_line_height=36,
        type_title_large_size=40,
        type_title_large_weight=_semi,
        type_title_large_line_height=52,
        type_display_size=68,
        type_display_weight=_semi,
        type_display_line_height=92,
        # ── Motion (milliseconds — no dp() needed) ────────────────────
        motion_fast_ms=167,
        motion_fast_curve=_bezier(0.0, 0.0, 0.0, 1.0),
        motion_normal_ms=250,
        motion_normal_curve=_bezier(0.55, 0.55, 0.0, 1.0),
        motion_exit_ms=167,
        motion_exit_curve=_bezier(0.0, 0.0, 0.0, 1.0),
        motion_gentle_exit_ms=167,
        motion_gentle_exit_curve=_bezier(1.0, 0.0, 1.0, 1.0),
        motion_fade_ms=83,
        motion_fade_curve=_lin,
        # ── Spacing (dp — callers must apply dp()) ────────────────────
        spacing_xxs=2,
        spacing_xs=4,
        spacing_s=8,
        spacing_m=12,
        spacing_l=16,
        spacing_xl=20,
        spacing_xxl=24,
        spacing_xxxl=32,
    )


_LIGHT_TOKENS: Final[Win11Tokens] = _build_tokens(ThemeMode.Light)
_DARK_TOKENS: Final[Win11Tokens] = _build_tokens(ThemeMode.Dark)


# ---------------------------------------------------------------------------
# OS mode detection
# ---------------------------------------------------------------------------


def _detect_mode() -> ThemeMode:
    """Infer the current OS colour scheme from the application palette.

    Args:  (none)

    Returns:
        ``ThemeMode.Dark`` when the OS is in dark mode, otherwise
        ``ThemeMode.Light``.
    """
    app = QtWidgets.QApplication.instance()
    if not isinstance(app, QtWidgets.QApplication):
        return ThemeMode.Light
    window_color = app.palette().color(QtGui.QPalette.ColorRole.Window)
    if window_color.lightness() < 128:
        return ThemeMode.Dark
    return ThemeMode.Light


def _resolve_platform_font() -> str:
    """Return the best available typeface name for the current platform.

    Resolution order:
    - **Windows**: ``"Segoe UI Variable"`` → ``"Segoe UI"``
    - **macOS**: ``".AppleSystemUIFont"`` (San Francisco)
    - **Linux**: ``"Roboto"`` → ``"DejaVu Sans"`` → ``"sans-serif"``

    Returns:
        The resolved font family name as a string.
    """
    if sys.platform == "darwin":
        return ".AppleSystemUIFont"
    families = set(QtGui.QFontDatabase.families())
    if sys.platform == "win32":
        if "Segoe UI Variable" in families:
            return "Segoe UI Variable"
        return "Segoe UI"
    for candidate in ("Roboto", "DejaVu Sans"):
        if candidate in families:
            return candidate
    return "sans-serif"


# ---------------------------------------------------------------------------
# App-mode event filter
# ---------------------------------------------------------------------------


class _AppModeFilter(QtCore.QObject):
    """Internal event filter watching for OS theme changes."""

    @override
    def eventFilter(
        self,
        a0: QtCore.QObject | None,
        a1: QtCore.QEvent | None,
    ) -> bool:
        """Intercept ``ApplicationPaletteChange`` and fire callbacks.

        Returns:
            Always ``False`` so the event continues normal processing.
        """
        global _current_mode  # noqa: PLW0603
        if (
            a1 is not None
            and a1.type() == QtCore.QEvent.Type.ApplicationPaletteChange
        ):
            _current_mode = _detect_mode()
            for cb in list(_callbacks):
                cb()
        return False


def _ensure_initialized() -> None:
    """Install the event filter and detect the initial OS mode.  Idempotent."""
    global _current_mode, _filter_obj, _filter_installed  # noqa: PLW0603
    if _filter_installed:
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    _current_mode = _detect_mode()
    _filter_obj = _AppModeFilter()
    app.installEventFilter(_filter_obj)
    _filter_installed = True


# ---------------------------------------------------------------------------
# Surface painting helper
# ---------------------------------------------------------------------------


def _paint_shape(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    background: QtGui.QColor,
    radius: int,
    border_color: QtGui.QColor | None,
) -> None:
    """Paint a rounded rectangle onto ``painter`` without a shadow.

    Args:
        painter: Active ``QPainter`` to draw onto.
        rect: Bounding rectangle in the painter's coordinate system.
        background: Fill colour for the surface interior.
        radius: Corner radius in **physical pixels** (already dp-scaled).
        border_color: Optional 1 px border colour.  Pass ``None`` for no border.
    """
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    path = QtGui.QPainterPath()
    path.addRoundedRect(rect, float(radius), float(radius))
    painter.fillPath(path, background)
    if border_color is not None:
        saved_pen = painter.pen()
        pen = QtGui.QPen(border_color)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.setPen(saved_pen)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def tokens() -> Win11Tokens:
    """Return the cached ``Win11Tokens`` for the current OS mode.

    Returns:
        The ``Win11Tokens`` instance for the current colour scheme.
    """
    _ensure_initialized()
    if _current_mode == ThemeMode.Dark:
        return _DARK_TOKENS
    return _LIGHT_TOKENS


def current_mode() -> ThemeMode:
    """Return the currently active ``ThemeMode``.

    Returns:
        ``ThemeMode.Light`` or ``ThemeMode.Dark``.  Falls back to
        ``ThemeMode.Light`` when no ``QApplication`` exists yet.
    """
    _ensure_initialized()
    if _current_mode is None:
        return ThemeMode.Light
    return _current_mode


def on_mode_changed(callback: Callable[[], None]) -> None:
    """Register a callback to be invoked on every OS theme change.

    Args:
        callback: Zero-argument callable to invoke on theme change.
    """
    _ensure_initialized()
    _callbacks.append(callback)


def make_font(
    size: int,
    weight: QtGui.QFont.Weight,
) -> QtGui.QFont:
    """Construct a ``QFont`` using the platform-resolved typeface.

    Applies :func:`dp` to ``size`` internally so callers always pass the
    raw dp value from a ``Win11Tokens.type_*_size`` field.

    Args:
        size: Type size in dp from a ``Win11Tokens.type_*_size`` field.
            dp() is applied here; do not pre-scale.
        weight: Font weight from a ``Win11Tokens.type_*_weight`` field.

    Returns:
        A ``QFont`` configured with the correct family, pixel size, and weight.
    """
    global _platform_font_family  # noqa: PLW0603
    if _platform_font_family is None:
        _platform_font_family = _resolve_platform_font()
    font = QtGui.QFont(_platform_font_family)
    # setPixelSize expects physical pixels. dp() converts the dp token value.
    font.setPixelSize(dp(size))
    font.setWeight(weight)
    return font


def paint_win11_surface(
    painter: QtGui.QPainter,
    rect: QtCore.QRect,
    *,
    background: QtGui.QColor,
    radius: int,
    border_color: QtGui.QColor | None = None,
    shadow_elevation: int = 0,
) -> None:
    """Paint a Windows 11 surface onto an active ``QPainter``.

    All shadow pixel values are converted from dp to physical pixels
    internally via :func:`dp`.  Callers pass ``radius`` in dp.

    Elevation mapping: 1=LAYER, 2=CONTROL, 3=CARD, 4=FLYOUT, 5=DIALOG.

    Args:
        painter: Active ``QPainter`` — must already be opened.
        rect: Bounding rectangle in widget coordinates.
        background: Surface fill colour (use a ``tokens().*`` field).
        radius: Corner radius in dp (e.g. ``tokens().radius_overlay``).
            Converted to physical pixels internally.
        border_color: Optional 1 px border colour.  ``None`` = no border.
        shadow_elevation: Integer 0 to 5 selecting the elevation level.
            0 = no shadow.

    Raises:
        RuntimeError: If ``painter`` is not active.
    """
    if not painter.isActive():
        raise RuntimeError("paint_win11_surface: painter must be active.")

    # Convert the caller-supplied dp radius to physical pixels once.
    scaled_radius = dp(radius)

    if shadow_elevation < 1 or shadow_elevation not in _ELEVATION_MAP:
        _paint_shape(
            painter,
            QtCore.QRectF(rect),
            background,
            scaled_radius,
            border_color,
        )
        return

    level = _ELEVATION_MAP[shadow_elevation]
    # Convert all shadow dp values to physical pixels here, not at the
    # ElevationLevel definition site (which stores dp, not physical px).
    blur = level.scaled_radius()
    offset_y = level.scaled_offset_y()
    margin = blur * 2 + offset_y + 2

    device = painter.device()
    dpr = device.devicePixelRatio() if device is not None else 1.0

    surf = QtGui.QPixmap(int(rect.width() * dpr), int(rect.height() * dpr))
    surf.setDevicePixelRatio(dpr)
    surf.fill(QtCore.Qt.GlobalColor.transparent)
    sp = QtGui.QPainter(surf)
    _paint_shape(
        sp,
        QtCore.QRectF(surf.rect()),
        background,
        scaled_radius,
        border_color,
    )
    sp.end()

    scene = QtWidgets.QGraphicsScene()
    item = scene.addPixmap(surf)
    if item is not None:
        item.setPos(float(margin), float(margin))

    effect = QtWidgets.QGraphicsDropShadowEffect()
    effect.setBlurRadius(float(blur))
    effect.setOffset(QtCore.QPointF(0.0, float(offset_y)))
    mode = current_mode()
    shadow_hex = (
        level.shadow_color_light
        if mode == ThemeMode.Light
        else level.shadow_color_dark
    )
    effect.setColor(_hex_to_qcolor(shadow_hex))
    if item is not None:
        item.setGraphicsEffect(effect)

    total_w = rect.width() + margin * 2
    total_h = rect.height() + margin * 2
    result = QtGui.QPixmap(int(total_w * dpr), int(total_h * dpr))
    result.setDevicePixelRatio(dpr)
    result.fill(QtCore.Qt.GlobalColor.transparent)
    rp = QtGui.QPainter(result)
    scene.render(
        rp,
        QtCore.QRectF(result.rect()),
        QtCore.QRectF(0.0, 0.0, float(total_w), float(total_h)),
    )
    rp.end()

    painter.drawPixmap(rect.x() - margin, rect.y() - margin, result)
