"""fluentqt - WinUI3-faithful component library for PyQt6."""

from __future__ import annotations

import fluentqt.core.dp as dp_module
import fluentqt.core.factory as factory_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles
import fluentqt.primitives.divider as divider_module
import fluentqt.primitives.frame as frame_module
import fluentqt.primitives.icon as icon_module
import fluentqt.primitives.input as input_module
import fluentqt.primitives.label as label_module

ScreenChangeNotifier = dp_module.ScreenChangeNotifier
dp = dp_module.dp
notifier = dp_module.notifier

tokens = tokens_module.tokens
current_mode = tokens_module.current_mode
on_mode_changed = tokens_module.on_mode_changed
make_font = tokens_module.make_font
register_accent = tokens_module.register_accent
TokenConsumer = tokens_module.TokenConsumer

get_icon_provider = factory_module.get_icon_provider
make_divider = factory_module.make_divider
make_frame = factory_module.make_frame
make_icon = factory_module.make_icon
register_icon_provider = factory_module.register_icon_provider

ButtonRole = roles.ButtonRole
ControlState = roles.ControlState
ElevationPreset = roles.ElevationPreset
FillRole = roles.FillRole
IconSize = roles.IconSize
TextRole = roles.TextRole
TypeStyle = roles.TypeStyle

TokenDivider = divider_module.TokenDivider
TokenFrame = frame_module.TokenFrame
TokenIcon = icon_module.TokenIcon
TokenInput = input_module.TokenInput
TokenLabel = label_module.TokenLabel

__all__ = [
    "ButtonRole",
    "ControlState",
    "ElevationPreset",
    "FillRole",
    "IconSize",
    "ScreenChangeNotifier",
    "TextRole",
    "TokenConsumer",
    "TokenDivider",
    "TokenFrame",
    "TokenIcon",
    "TokenInput",
    "TokenLabel",
    "TypeStyle",
    "current_mode",
    "dp",
    "get_icon_provider",
    "make_divider",
    "make_font",
    "make_frame",
    "make_icon",
    "notifier",
    "on_mode_changed",
    "register_accent",
    "register_icon_provider",
    "tokens",
]
