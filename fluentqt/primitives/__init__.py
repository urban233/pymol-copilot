"""Semantic design primitives."""

from __future__ import annotations

import fluentqt.primitives.button as button_module
import fluentqt.primitives.frame as frame_module
import fluentqt.primitives.label as label_module

TokenButton = button_module.TokenButton
TokenFrame = frame_module.TokenFrame
TokenLabel = label_module.TokenLabel

__all__ = [
    "TokenButton",
    "TokenFrame",
    "TokenLabel",
]
