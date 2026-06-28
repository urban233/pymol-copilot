"""Tests for semantic layout and styling enums."""

from __future__ import annotations

import fluentqt.core.tokens as tokens
import fluentqt.enums.roles as roles


def test_text_role_mapping() -> None:
    """Verify TextRole enum values match expected token fields."""
    assert roles.TextRole.Primary.value == "text_primary"
    assert roles.TextRole.Secondary.value == "text_secondary"
    assert roles.TextRole.Tertiary.value == "text_tertiary"
    assert roles.TextRole.Disabled.value == "text_disabled"
    assert roles.TextRole.OnAccent.value == "text_on_accent"


def test_fill_role_mapping() -> None:
    """Verify FillRole enum values match expected token fields."""
    assert roles.FillRole.Control.value == "fill_control_default"
    assert roles.FillRole.Subtle.value == "fill_subtle_hover"
    assert roles.FillRole.Accent.value == "accent_default"
    assert roles.FillRole.Transparent.value == "transparent"


def test_type_style_tokens() -> None:
    """Verify TypeStyle size, weight, and line height token resolution."""
    tmp_style = roles.TypeStyle.Caption
    assert tmp_style.size_token() == "type_caption_size"
    assert tmp_style.weight_token() == "type_caption_weight"
    assert tmp_style.line_height_token() == "type_caption_line_height"


def test_icon_size_values() -> None:
    """Verify IconSize enum values match expected dp dimensions."""
    assert roles.IconSize.Small.value == 16
    assert roles.IconSize.Medium.value == 20
    assert roles.IconSize.Large.value == 24
    assert roles.IconSize.XLarge.value == 32


def test_button_role_values() -> None:
    """Verify ButtonRole enum values match expected strings."""
    assert roles.ButtonRole.Standard.value == "standard"
    assert roles.ButtonRole.Accent.value == "accent"
    assert roles.ButtonRole.Subtle.value == "subtle"
    assert roles.ButtonRole.Danger.value == "danger"


def test_elevation_preset_mapping() -> None:
    """Verify ElevationPreset maps to correct ElevationLevel member or None."""
    assert roles.ElevationPreset.Flat.elevation_level is None
    assert (
        roles.ElevationPreset.Layer.elevation_level
        == tokens.ElevationLevel.LAYER
    )
    assert (
        roles.ElevationPreset.Control.elevation_level
        == tokens.ElevationLevel.CONTROL
    )
    assert (
        roles.ElevationPreset.Card.elevation_level == tokens.ElevationLevel.CARD
    )
    assert (
        roles.ElevationPreset.Flyout.elevation_level
        == tokens.ElevationLevel.FLYOUT
    )
    assert (
        roles.ElevationPreset.Dialog.elevation_level
        == tokens.ElevationLevel.DIALOG
    )


def test_control_state_values() -> None:
    """Verify ControlState enum values match expected strings."""
    assert roles.ControlState.Default.value == "default"
    assert roles.ControlState.Hovered.value == "hovered"
    assert roles.ControlState.Pressed.value == "pressed"
    assert roles.ControlState.Focused.value == "focused"
    assert roles.ControlState.Disabled.value == "disabled"
