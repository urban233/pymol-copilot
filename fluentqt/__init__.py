"""fluentqt - WinUI3-faithful component library for PyQt6."""

from __future__ import annotations

import fluentqt.core.dp as dp_module

ScreenChangeNotifier = dp_module.ScreenChangeNotifier
dp = dp_module.dp
notifier = dp_module.notifier

__all__ = [
    "ScreenChangeNotifier",
    "dp",
    "notifier",
]
