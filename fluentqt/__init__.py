"""fluentqt - WinUI3-faithful component library for PyQt6."""

from __future__ import annotations

import fluentqt.core.dp as dp_module
import fluentqt.core.factory as factory_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles
import fluentqt.primitives.frame as frame_module

ScreenChangeNotifier = dp_module.ScreenChangeNotifier
dp = dp_module.dp
notifier = dp_module.notifier

tokens = tokens_module.tokens
current_mode = tokens_module.current_mode
on_mode_changed = tokens_module.on_mode_changed
make_font = tokens_module.make_font
register_accent = tokens_module.register_accent
TokenConsumer = tokens_module.TokenConsumer

make_frame = factory_module.make_frame

ButtonRole = roles.ButtonRole
ControlState = roles.ControlState
ElevationPreset = roles.ElevationPreset
FillRole = roles.FillRole
IconSize = roles.IconSize
TextRole = roles.TextRole
TypeStyle = roles.TypeStyle

TokenFrame = frame_module.TokenFrame

__all__ = [
    "ButtonRole",
    "ControlState",
    "ElevationPreset",
    "FillRole",
    "IconSize",
    "ScreenChangeNotifier",
    "TextRole",
    "TokenConsumer",
    "TokenFrame",
    "TypeStyle",
    "current_mode",
    "dp",
    "make_font",
    "make_frame",
    "notifier",
    "on_mode_changed",
    "register_accent",
    "tokens",
]
