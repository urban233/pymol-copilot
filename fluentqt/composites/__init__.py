"""Composite widgets subpackage."""

from __future__ import annotations

import fluentqt.composites.base as base_module
import fluentqt.composites.input_bar as input_bar_module

CompositeWidget = base_module.CompositeWidget
InputBar = input_bar_module.InputBar

__all__ = [
    "CompositeWidget",
    "InputBar",
]
