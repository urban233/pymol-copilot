"""Tests for the widget construction factory functions."""

from __future__ import annotations

from collections.abc import Generator

from PyQt6 import QtGui
import pytest

from fluentqt.core import factory


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


def test_factory_placeholders() -> None:
    """Verify all factory functions return None as a placeholder at this stage."""
    # Act
    tmp_frame = factory.make_frame()
    tmp_label = factory.make_label()
    tmp_button = factory.make_button("test")
    tmp_input = factory.make_input()
    tmp_icon = factory.make_icon("test")
    tmp_divider = factory.make_divider()
    tmp_dropdown = factory.make_dropdown(["test"])

    # Assert
    assert tmp_frame is None
    assert tmp_label is None
    assert tmp_button is None
    assert tmp_input is None
    assert tmp_icon is None
    assert tmp_divider is None
    assert tmp_dropdown is None
