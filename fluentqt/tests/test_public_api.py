"""Tests for the public API exports of fluentqt."""

from __future__ import annotations

import fluentqt


def test_public_exports() -> None:
    """Verify that all required components are exported.

    This test asserts that the public module contains the core functions,
    stateful widgets, composite base, enums, primitives, and factories.
    """
    # Arrange & Act: Gather exported names
    tmp_exports = set(fluentqt.__all__)

    tmp_expected_exports = {
        # Core & Tokens
        "dp",
        "tokens",
        "make_font",
        "on_mode_changed",
        "register_accent",
        "TokenConsumer",
        # State
        "StatefulWidget",
        # Composite
        "CompositeWidget",
        # Enums
        "ButtonRole",
        "ControlState",
        "ElevationPreset",
        "FillRole",
        "IconSize",
        "TextRole",
        "TypeStyle",
        # Primitives
        "TokenButton",
        "TokenDivider",
        "TokenFrame",
        "TokenIcon",
        "TokenInput",
        "TokenLabel",
        # Factory
        "register_icon_provider",
        "get_icon_provider",
        "make_frame",
        "make_label",
        "make_button",
        "make_input",
        "make_icon",
        "make_divider",
        "make_dropdown",
    }

    # Assert
    for tmp_name in tmp_expected_exports:
        assert hasattr(fluentqt, tmp_name)
        assert tmp_name in tmp_exports

    # Assert that no internal details or stylesheet modules are in __all__
    assert "stylesheet" not in tmp_exports
    assert "build_frame_style" not in tmp_exports
    assert "build_label_style" not in tmp_exports
    assert "build_button_style" not in tmp_exports
    assert "build_input_style" not in tmp_exports
