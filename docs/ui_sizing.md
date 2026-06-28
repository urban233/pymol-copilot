# Desktop UI Sizing Reference — PyQt6 + WinUI3 Token System

A practical guide for writing pixel-perfect PyQt6 widgets that look at home
in a productivity desktop application (Word, Excel, VS Code tier) on any
display, including 4K HiDPI screens at 125 %, 150 %, or 200 % scaling.

---

## 1. The Core Concept: Density-Independent Pixels (dp)

All sizes in source code are written in **density-independent pixels (dp)**
at a **96 DPI baseline** (Windows 100 % / 1× scaling). At runtime `dp()`
converts them to physical pixels using the screen's actual logical DPI.

```
physical px = round(dp_value × (screen.logicalDotsPerInch() / 96.0))
```

| Scale factor | Logical DPI | 1 dp = |
|---|---|---|
| 100 % (1×) | 96 | 1 px |
| 125 % (1.25×) | 120 | 1.25 px → rounds to 1 or 2 |
| 150 % (1.5×) | 144 | 1.5 px → rounds to 2 |
| 200 % (2×) | 192 | 2 px |

### The `dp()` helper

```python
# fluent.py — single definition, re-exported from elevated_container
def dp(value: int | float) -> int:
    screen = QtWidgets.QApplication.primaryScreen()
    if screen is None:
        return round(value)
    scale = screen.logicalDotsPerInch() / 96.0
    return round(value * scale)
```

**Rule:** Every dimension value that enters a Qt API must pass through
`dp()`. No bare integer literals for sizes.

---

## 2. Application Startup

```python
# main.py — before QApplication(sys.argv)
QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
    QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)
```

| Policy | Behaviour | When to use |
|---|---|---|
| `PassThrough` | Exact fractional scales (1.25×, 1.5×) | General desktop apps — matches Word / Excel |
| `Round` | Snaps to nearest integer (1×, 2×, 3×) | Icon-heavy UIs needing crisp pixel-perfect edges |
| `RoundPreferFloor` | Conservative rounding | Rarely needed |

---

## 3. Token System — What Needs `dp()` and What Doesn't

The `Win11Tokens` dataclass is the single source of truth. Fields fall into
two categories:

### Needs `dp()` at the call site

These fields are stored in **dp** and must be converted at the point of use:

| Field group | Examples | How to use |
|---|---|---|
| `radius_*` | `radius_control=4`, `radius_overlay=8` | `dp(tok.radius_overlay)` before QSS or geometry |
| `spacing_*` | `spacing_s=8`, `spacing_l=16` | `dp(tok.spacing_l)` before `setContentsMargins` |
| `type_*_line_height` | `type_body_line_height=20` | `dp(tok.type_body_line_height)` |
| `type_*_size` | `type_body_size=14` | Passed to `make_font()` — dp() applied internally |
| `ElevationLevel.shadow_radius` | `CARD.shadow_radius=4` | Use `level.scaled_radius()` — dp() applied |
| `ElevationLevel.shadow_offset_y` | `CARD.shadow_offset_y=2` | Use `level.scaled_offset_y()` — dp() applied |

### Does NOT need `dp()`

| Field group | Examples | Reason |
|---|---|---|
| `QColor` fields | `layer_card`, `accent_default` | DPI-agnostic |
| `type_*_weight` | `type_body_weight` | Font weight enum |
| `motion_*_ms` | `motion_fast_ms=167` | Milliseconds, not pixels |
| `motion_*_curve` | `motion_fast_curve` | `QEasingCurve` value |

### Example — correct usage

```python
tok = fluent.tokens()

# Colors — use directly
frame.setStyleSheet(f"background-color: {tok.layer_card.name()};")

# Radii — dp() required
radius_px = fluent.dp(tok.radius_overlay)
frame.setStyleSheet(f"border-radius: {radius_px}px;")

# Spacing — dp() required
layout.setSpacing(fluent.dp(tok.spacing_s))
layout.setContentsMargins(
    fluent.dp(tok.spacing_l), fluent.dp(tok.spacing_xs),
    fluent.dp(tok.spacing_l), fluent.dp(tok.spacing_xs),
)

# Typography — make_font() applies dp() internally, don't pre-scale
font = fluent.make_font(tok.type_body_size, tok.type_body_weight)

# Elevation shadows — scaled_radius() / scaled_offset_y() apply dp() internally
effect.setBlurRadius(fluent.ElevationLevel.CARD.scaled_radius())
effect.setOffset(0.0, float(fluent.ElevationLevel.CARD.scaled_offset_y()))

# Motion — use directly
anim.setDuration(tok.motion_normal_ms)
anim.setEasingCurve(tok.motion_normal_curve)
```

---

## 4. Spacing Token Reference

WinUI3 uses a **4 dp base grid**. All spacing tokens are multiples of 4.

| Token | dp value | Use case |
|---|---|---|
| `spacing_xxs` | 2 dp | Icon-to-text gap within a single control |
| `spacing_xs` | 4 dp | Tight vertical padding (compact toolbar rows) |
| `spacing_s` | 8 dp | Control internal padding; inter-control gap |
| `spacing_m` | 12 dp | Gap between sibling control groups |
| `spacing_l` | 16 dp | Standard content horizontal inset; card padding |
| `spacing_xl` | 20 dp | Gap between card and page edge |
| `spacing_xxl` | 24 dp | Vertical spacing between sections |
| `spacing_xxxl` | 32 dp | Page-level margins |

Avoid values that don't land on this grid (e.g. 15, 10, 22). They look
slightly off next to native controls even when you can't immediately say why.

---

## 5. Elevation Reference

| Level | Enum | Use case | blur (dp) | offset_y (dp) |
|---|---|---|---|---|
| 0 | — | Flat surface, no shadow | — | — |
| 1 | `LAYER` | In-page surface layer | 1 | 1 |
| 2 | `CONTROL` | Resting buttons, inputs | 2 | 1 |
| **3** | **`CARD`** | **Content cards, input bars** | **4** | **2** |
| 4 | `FLYOUT` | Menus, flyouts, dropdowns | 8 | 4 |
| 5 | `DIALOG` | Modal dialogs | 16 | 8 |

Shadow colours come from the token system and switch automatically between
light and dark mode. Never hardcode `QColor(0, 0, 0, alpha)` for shadows —
use the RRGGBBAA strings from `ElevationLevel.shadow_color_light/dark`.

### Consuming elevation in a widget

```python
level = fluent.ElevationLevel.CARD
effect.setBlurRadius(level.scaled_radius())     # dp() applied internally
effect.setOffset(0.0, float(level.scaled_offset_y()))
shadow_hex = (
    level.shadow_color_light
    if fluent.current_mode() == fluent.ThemeMode.Light
    else level.shadow_color_dark
)
effect.setColor(fluent._hex_to_qcolor(shadow_hex))
```

---

## 6. Radius Reference

| Token | dp value | Used by |
|---|---|---|
| `radius_none` | 0 dp | Snapped/maximised windows; shared straight edges |
| `radius_control` | 4 dp | Buttons, inputs, checkboxes, InfoBar, progress bars |
| `radius_overlay` | 8 dp | Cards, flyouts, dialogs, menus, teaching tips |
| `radius_tooltip` | 4 dp | Tooltips (exception to overlay rule due to small size) |

**Pill shape:** `border_radius = height / 2`. Both values must derive from
the same constant. The radius token system does not cover pills — define
them locally with a named constant:

```python
_BAR_HEIGHT: int = 36
_BAR_RADIUS: int = _BAR_HEIGHT // 2   # 18 dp — must stay in sync
```

**QSS requires physical pixels.** Always scale before embedding:

```python
# Correct
radius_px = fluent.dp(tok.radius_overlay)
style = f"border-radius: {radius_px}px;"

# Wrong — dp value ends up in QSS unscaled
style = f"border-radius: {tok.radius_overlay}px;"
```

---

## 7. Control Heights

Prefer font-metric height for any control that holds text:

```python
def _natural_control_height() -> int:
    fm = QtGui.QFontMetrics(QtWidgets.QApplication.font())
    return fm.height() + fluent.dp(16)   # 8 dp top + 8 dp bottom
```

When a fixed height is required (e.g. pill shapes), use these reference values:

| Control type | Height (dp) | Notes |
|---|---|---|
| Compact toolbar / pill input | **36** | VS Code toolbar, Office search bar, WinUI SearchBox |
| Standard button | **32** | WinUI Button default |
| Comfortable list row | **40** | WinUI ListViewItem default |
| Dialog form field | **40** | WinUI TextBox in a form |

**Avoid 48 dp on desktop.** That is the Android / iOS touch target — it looks
oversized in a mouse-driven productivity app.

---

## 8. Typography Reference

WinUI3 type ramp — all sizes in dp, stored in `Win11Tokens.type_*_size`.
`make_font()` applies `dp()` internally; pass the raw token value.

| Token prefix | Size (dp) | Weight | Line height (dp) | Use |
|---|---|---|---|---|
| `type_caption` | 12 | Regular | 16 | Labels, metadata, timestamps |
| `type_body` | 14 | Regular | 20 | Default body text |
| `type_body_strong` | 14 | Semibold | 20 | Emphasis within body |
| `type_body_large` | 18 | Regular | 24 | Intro text, card headlines |
| `type_body_large_strong` | 18 | Semibold | 24 | Card headline emphasis |
| `type_subtitle` | 20 | Semibold | 28 | Section titles |
| `type_title` | 28 | Semibold | 36 | Page titles |
| `type_title_large` | 40 | Semibold | 52 | Hero titles |
| `type_display` | 68 | Semibold | 92 | Marketing / splash |

Rules from the WinUI3 spec:
- Only Regular (400) and Semibold (600) weights — no Bold, no Italic.
- Minimum legible: 12 dp Regular, 14 dp Semibold.
- All text is sentence case.

---

## 9. Icon Button Sizes

| Context | Size (dp) | Notes |
|---|---|---|
| Standard toolbar icon button | **28 × 28** | Office, VS Code — comfortable click target |
| Compact toolbar | 24 × 24 | Acceptable only in very tight rows |
| Standard button with icon | 32 × 32 | Matches standard button height |

Always use `dp()`:

```python
btn_size = fluent.dp(28)
button.setFixedSize(btn_size, btn_size)
```

---

## 10. Motion Reference

All durations are in milliseconds — no `dp()` needed.

| Token | ms | Curve | Use |
|---|---|---|---|
| `motion_fast` | 167 | bezier(0,0,0,1) | Entrance — controls appearing |
| `motion_normal` | 250 | bezier(0.55,0.55,0,1) | Moving point-to-point |
| `motion_exit` | 167 | bezier(0,0,0,1) | Exit — combine with fade-out |
| `motion_gentle_exit` | 167 | bezier(1,0,1,1) | Soft exit (position and scale) |
| `motion_fade` | 83 | linear | Bare opacity fade |

Only animate: `maximumHeight`, `minimumHeight`, `windowOpacity`, `pos`.
Never animate geometry (`width`, `height`, `geometry`) directly.

---

## 11. Quick-Reference Cheat Sheet

```
dp() required for ............ radius_*, spacing_*, type_*_size,
                                type_*_line_height, ElevationLevel px values
dp() NOT required for ........ QColor, QFont.Weight, motion_*_ms,
                                QEasingCurve, make_font() (applies internally)

Base grid unit ............... 4 dp (WinUI3), effective 8 dp for most gaps
Outer widget margin .......... spacing_s = 8 dp
Standard content H inset ..... spacing_l = 16 dp
Content V padding (compact)... spacing_xs = 4 dp
Inter-control spacing ........ spacing_s = 8 dp

Toolbar / pill input height .. 36 dp
Standard button height ....... 32 dp
List row height .............. 40 dp
Icon button size ............. 28 × 28 dp

Control border radius ........ radius_control = 4 dp
Card / overlay radius ........ radius_overlay = 8 dp
Pill radius .................. height / 2  (local constant, not a token)

Card shadow (CARD level) ..... blur 4 dp, offset_y 2 dp
Flyout shadow ................ blur 8 dp, offset_y 4 dp
Dialog shadow ................ blur 16 dp, offset_y 8 dp
```

---

## 12. What to Avoid

| Anti-pattern | Why | Fix |
|---|---|---|
| `tok.spacing_s` passed directly to `setSpacing()` | Token is dp, Qt expects physical px | `fluent.dp(tok.spacing_s)` |
| `tok.radius_overlay` embedded raw in QSS `Npx` | QSS px ≠ logical px | `fluent.dp(tok.radius_overlay)` |
| `QGraphicsDropShadowEffect(blurRadius=4)` raw | Shadow won't scale on HiDPI | `level.scaled_radius()` |
| `font.setPixelSize(tok.type_body_size)` directly | dp value used as physical px | `fluent.make_font(tok.type_body_size, ...)` |
| `height=48` for desktop bars | Mobile touch target | `36 dp` |
| `border_radius=12` for cards | Web / mobile convention | `radius_overlay = 8 dp` |
| Spacing `12 dp` inside toolbars | Off the 4 dp grid; web default | `spacing_s = 8 dp` |
| Icon buttons `24 × 24` | Mobile icon size | `28 × 28 dp` |
| Hardcoded `QColor(0,0,0,40)` for shadows | Ignores dark mode, doesn't scale | `ElevationLevel.*` shadow colours |
| Duplicating shadow values outside token system | Gets out of sync | Always read from `ElevationLevel` |
