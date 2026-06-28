"""Core module of fluentqt containing sizing, tokens, state and stylesheet logic."""

from __future__ import annotations

import fluentqt.core.dp as dp

ScreenChangeNotifier = dp.ScreenChangeNotifier
notifier = dp.notifier

__all__ = [
    "ScreenChangeNotifier",
    "dp",
    "notifier",
]
