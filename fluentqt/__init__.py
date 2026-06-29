"""fluentqt - WinUI3-faithful component library for PyQt6."""

from __future__ import annotations

import fluentqt.composites.base as base_module
import fluentqt.composites.input_bar as input_bar_module
import fluentqt.core.dp as dp_module
import fluentqt.core.factory as factory_module
import fluentqt.core.state as state_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles
import fluentqt.primitives.button as button_module
import fluentqt.primitives.divider as divider_module
import fluentqt.primitives.frame as frame_module
import fluentqt.primitives.icon as icon_module
import fluentqt.primitives.input as input_module
import fluentqt.primitives.label as label_module

# DP Core
dp = dp_module.dp

# Token Core
tokens = tokens_module.tokens
on_mode_changed = tokens_module.on_mode_changed
make_font = tokens_module.make_font
register_accent = tokens_module.register_accent
TokenConsumer = tokens_module.TokenConsumer

# State Core
StatefulWidget = state_module.StatefulWidget

# Composite Core
CompositeWidget = base_module.CompositeWidget
InputBar = input_bar_module.InputBar

# Enums
ButtonRole = roles.ButtonRole
ControlState = roles.ControlState
ElevationPreset = roles.ElevationPreset
FillRole = roles.FillRole
IconSize = roles.IconSize
TextRole = roles.TextRole
TypeStyle = roles.TypeStyle

# Primitives
TokenButton = button_module.TokenButton
TokenDivider = divider_module.TokenDivider
TokenFrame = frame_module.TokenFrame
TokenIcon = icon_module.TokenIcon
TokenInput = input_module.TokenInput
TokenLabel = label_module.TokenLabel

# Factory Functions
register_icon_provider = factory_module.register_icon_provider
get_icon_provider = factory_module.get_icon_provider
make_frame = factory_module.make_frame
make_label = factory_module.make_label
make_button = factory_module.make_button
make_input = factory_module.make_input
make_icon = factory_module.make_icon
make_divider = factory_module.make_divider
make_dropdown = factory_module.make_dropdown

__all__ = [
    "ButtonRole",
    "CompositeWidget",
    "ControlState",
    "ElevationPreset",
    "FillRole",
    "IconSize",
    "InputBar",
    "StatefulWidget",
    "TextRole",
    "TokenButton",
    "TokenConsumer",
    "TokenDivider",
    "TokenFrame",
    "TokenIcon",
    "TokenInput",
    "TokenLabel",
    "TypeStyle",
    "dp",
    "get_icon_provider",
    "make_button",
    "make_divider",
    "make_dropdown",
    "make_font",
    "make_frame",
    "make_icon",
    "make_input",
    "make_label",
    "on_mode_changed",
    "register_accent",
    "register_icon_provider",
    "tokens",
]
