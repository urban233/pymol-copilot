"""Semantic style and layout enums.

This module defines semantic roles and styles to decouple widget styling
from raw token lookups.
"""

from __future__ import annotations

import enum

import fluentqt.core.tokens as tokens


class TextRole(enum.Enum):
    """Semantic text roles mapped to Win11Tokens fields.

    Attributes:
        Primary: Maps to ``Win11Tokens.text_primary``.
        Secondary: Maps to ``Win11Tokens.text_secondary``.
        Tertiary: Maps to ``Win11Tokens.text_tertiary``.
        Disabled: Maps to ``Win11Tokens.text_disabled``.
        OnAccent: Maps to ``Win11Tokens.text_on_accent``.
    """

    Primary = "text_primary"
    Secondary = "text_secondary"
    Tertiary = "text_tertiary"
    Disabled = "text_disabled"
    OnAccent = "text_on_accent"


class FillRole(enum.Enum):
    """Semantic fill roles mapped to Win11Tokens fields.

    Attributes:
        Control: Maps to ``Win11Tokens.fill_control_default``.
        Subtle: Maps to ``Win11Tokens.fill_subtle_hover``.
        Accent: Maps to ``Win11Tokens.accent_default``.
        Transparent: Maps to no token (fully transparent).
    """

    Control = "fill_control_default"
    Subtle = "fill_subtle_hover"
    Accent = "accent_default"
    Transparent = "transparent"


class TypeStyle(enum.Enum):
    """Semantic type style presets.

    Each member maps to a triple of ``type_*_size``, ``type_*_weight``,
    and ``type_*_line_height`` fields in ``Win11Tokens``.

    Attributes:
        Caption: Maps to ``type_caption_*`` tokens.
        Body: Maps to ``type_body_*`` tokens.
        BodyStrong: Maps to ``type_body_strong_*`` tokens.
        BodyLarge: Maps to ``type_body_large_*`` tokens.
        BodyLargeStrong: Maps to ``type_body_large_strong_*`` tokens.
        Subtitle: Maps to ``type_subtitle_*`` tokens.
        Title: Maps to ``type_title_*`` tokens.
        TitleLarge: Maps to ``type_title_large_*`` tokens.
        Display: Maps to ``type_display_*`` tokens.
    """

    Caption = "caption"
    Body = "body"
    BodyStrong = "body_strong"
    BodyLarge = "body_large"
    BodyLargeStrong = "body_large_strong"
    Subtitle = "subtitle"
    Title = "title"
    TitleLarge = "title_large"
    Display = "display"

    def size_token(self) -> str:
        """Return the size token field name.

        Returns:
            The name of the size field on Win11Tokens.
        """
        return f"type_{self.value}_size"

    def weight_token(self) -> str:
        """Return the weight token field name.

        Returns:
            The name of the weight field on Win11Tokens.
        """
        return f"type_{self.value}_weight"

    def line_height_token(self) -> str:
        """Return the line height token field name.

        Returns:
            The name of the line height field on Win11Tokens.
        """
        return f"type_{self.value}_line_height"


class IconSize(enum.Enum):
    """Semantic icon sizes.

    Attributes:
        Small: 16 dp.
        Medium: 20 dp.
        Large: 24 dp.
        XLarge: 32 dp.
    """

    Small = 16
    Medium = 20
    Large = 24
    XLarge = 32


class ButtonRole(enum.Enum):
    """Semantic button roles for styling and categorization.

    Attributes:
        Standard: Default standard button styling.
        Accent: High-priority accent button styling.
        Subtle: Low-priority subtle button styling.
        Danger: High-risk danger button styling.
    """

    Standard = "standard"
    Accent = "accent"
    Subtle = "subtle"
    Danger = "danger"


class ElevationPreset(enum.Enum):
    """Semantic elevation presets mapping surfaces to ElevationLevels.

    Attributes:
        Flat: No elevation shadow.
        Layer: Maps to ``ElevationLevel.LAYER``.
        Control: Maps to ``ElevationLevel.CONTROL``.
        Card: Maps to ``ElevationLevel.CARD``.
        Flyout: Maps to ``ElevationLevel.FLYOUT``.
        Dialog: Maps to ``ElevationLevel.DIALOG``.
    """

    Flat = "flat"
    Layer = "layer"
    Control = "control"
    Card = "card"
    Flyout = "flyout"
    Dialog = "dialog"

    @property
    def elevation_level(self) -> tokens.ElevationLevel | None:
        """Get the corresponding ElevationLevel.

        Returns:
            The mapped ElevationLevel, or None if Flat.
        """
        if self == ElevationPreset.Flat:
            return None
        return tokens.ElevationLevel[self.name.upper()]


class ControlState(enum.Enum):
    """Semantic control states for styling rules.

    Attributes:
        Default: Resting state.
        Hovered: Cursor is over control.
        Pressed: Control is active/pressed.
        Focused: Control has keyboard focus.
        Disabled: Control is disabled.
    """

    Default = "default"
    Hovered = "hovered"
    Pressed = "pressed"
    Focused = "focused"
    Disabled = "disabled"
