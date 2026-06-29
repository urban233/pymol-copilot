"""Semantic design primitives."""

from __future__ import annotations

import fluentqt.primitives.button as button_module
import fluentqt.primitives.frame as frame_module
import fluentqt.primitives.input as input_module
import fluentqt.primitives.label as label_module

TokenButton = button_module.TokenButton
TokenFrame = frame_module.TokenFrame
TokenInput = input_module.TokenInput
TokenLabel = label_module.TokenLabel

__all__ = [
    "TokenButton",
    "TokenFrame",
    "TokenInput",
    "TokenLabel",
]
