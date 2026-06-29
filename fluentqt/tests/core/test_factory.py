"""Tests for the widget construction factory functions."""

from __future__ import annotations

from collections.abc import Generator

from PyQt6 import QtGui
from PyQt6 import QtWidgets
import pytest

from fluentqt.core import factory
import fluentqt.primitives.button as button_module
import fluentqt.primitives.divider as divider_module
import fluentqt.primitives.frame as frame_module
import fluentqt.primitives.icon as icon_module
import fluentqt.primitives.input as input_module
import fluentqt.primitives.label as label_module


@pytest.fixture(autouse=True)
def _reset_icon_provider() -> Generator[None, None, None]:
    """Reset the factory's global icon provider after each test.

    Yields:
        None
    """
    yield
    factory._state.provider = None


def test_register_icon_provider() -> None:
    """Verify that registering an icon provider stores it correctly."""
    tmp_provider_called = False

    def tmp_provider(tmp_name: str) -> QtGui.QIcon:
        nonlocal tmp_provider_called
        tmp_provider_called = True
        _ = tmp_name
        return QtGui.QIcon()

    # Act
    factory.register_icon_provider(tmp_provider)

    # Assert
    assert factory._state.provider is tmp_provider


def test_factory_creation() -> None:
    """Verify that factory functions construct and return correct widgets."""
    # Act
    tmp_frame = factory.make_frame()
    tmp_label = factory.make_label("test label")
    tmp_button = factory.make_button("test button")
    tmp_input = factory.make_input("test placeholder")
    tmp_icon = factory.make_icon("test_icon")
    tmp_divider = factory.make_divider()
    tmp_dropdown = factory.make_dropdown(["item1", "item2"])

    # Assert
    assert isinstance(tmp_frame, frame_module.TokenFrame)

    assert isinstance(tmp_label, label_module.TokenLabel)
    assert tmp_label.text() == "test label"

    assert isinstance(tmp_button, button_module.TokenButton)
    assert tmp_button.text() == "test button"

    assert isinstance(tmp_input, input_module.TokenInput)
    assert tmp_input.placeholderText() == "test placeholder"

    assert isinstance(tmp_icon, icon_module.TokenIcon)
    assert tmp_icon.icon() == "test_icon"

    assert isinstance(tmp_divider, divider_module.TokenDivider)

    assert isinstance(tmp_dropdown, QtWidgets.QComboBox)
    assert tmp_dropdown.count() == 2
    assert tmp_dropdown.itemText(0) == "item1"
    assert tmp_dropdown.itemText(1) == "item2"
