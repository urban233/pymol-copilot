"""Tests for the composite base widget."""

from __future__ import annotations

from typing import Any
from typing import override
import unittest.mock

from PyQt6 import QtWidgets

from fluentqt.core import dp as dp_module
from fluentqt.enums import roles as roles_module
from fluentqt.composites import base as base_module


class _MockComposite(base_module.CompositeWidget):
    """Mock composite subclass for testing."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.build_called = False
        super().__init__(*args, **kwargs)

    @override
    def _build_content(self) -> None:
        self.build_called = True


def test_composite_widget_initialization(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify default properties and layout structure of CompositeWidget.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    tmp_composite = _MockComposite()

    assert tmp_composite.elevation() == roles_module.ElevationPreset.Flat
    assert tmp_composite.orientation() == "horizontal"
    assert tmp_composite.frame is not None
    assert tmp_composite.content_layout is not None
    assert isinstance(tmp_composite.content_layout, QtWidgets.QHBoxLayout)
    assert tmp_composite.build_called is True


def test_composite_widget_vertical_orientation(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify vertical layout class is QVBoxLayout when specified.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    tmp_composite = _MockComposite(orientation="vertical")

    assert tmp_composite.orientation() == "vertical"
    assert isinstance(tmp_composite.content_layout, QtWidgets.QVBoxLayout)


def test_composite_widget_elevation_change(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify elevation preset change propagates to inner frame.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    tmp_composite = _MockComposite(elevation=roles_module.ElevationPreset.Flat)
    assert tmp_composite.frame is not None
    assert tmp_composite.frame.elevation() == roles_module.ElevationPreset.Flat

    tmp_composite.set_elevation(roles_module.ElevationPreset.Card)
    assert tmp_composite.elevation() == roles_module.ElevationPreset.Card
    assert tmp_composite.frame is not None
    assert tmp_composite.frame.elevation() == roles_module.ElevationPreset.Card


def test_composite_widget_dpi_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify geometry recalculates on screen scale changes.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    tmp_composite = _MockComposite()

    # Act & Assert: Patch _apply_tokens as context manager to prevent leaks
    with unittest.mock.patch.object(
        tmp_composite, "_apply_tokens"
    ) as tmp_mock_apply:
        dp_module.notifier.scale_changed.emit(2.0)
        tmp_mock_apply.assert_called_once()


def test_composite_widget_fill_role_change(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify fill role property and setter propagate to inner frame.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    tmp_composite = _MockComposite(fill_role=roles_module.FillRole.Transparent)
    assert tmp_composite.fill_role() == roles_module.FillRole.Transparent
    assert tmp_composite.frame is not None
    assert tmp_composite.frame.fill_role() == roles_module.FillRole.Transparent

    tmp_composite.set_fill_role(roles_module.FillRole.CardBackground)
    assert tmp_composite.fill_role() == roles_module.FillRole.CardBackground
    assert (
        tmp_composite.frame.fill_role() == roles_module.FillRole.CardBackground
    )
