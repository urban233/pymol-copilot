"""Tests for input bar widgets."""

from __future__ import annotations

import typing

from PyQt6 import QtWidgets
import pytest

from pymol_copilot.gui.widgets import elevated_container
from pymol_copilot.gui.widgets import input_bar


class SampleContainer(elevated_container.ElevatedContainer):
    """Concrete test container for validating the template method."""

    @typing.override
    def setup_ui(self) -> None:
        """Adds a single child widget to the inherited content layout."""
        self.label = QtWidgets.QLabel("Sample")
        self.content_layout.addWidget(self.label)


@pytest.fixture
def q_app() -> QtWidgets.QApplication:
    """Fixture for providing a QApplication instance.

    Returns:
        The QApplication instance.
    """
    tmp_app = QtWidgets.QApplication.instance()
    if isinstance(tmp_app, QtWidgets.QApplication):
        return tmp_app
    return QtWidgets.QApplication([])


def test_elevated_container_builds_shared_structure(
    q_app: QtWidgets.QApplication,
) -> None:
    """Tests that ElevatedContainer creates the shared card structure.

    Args:
        q_app: The QApplication fixture.
    """
    # Arrange & Act
    assert q_app is not None
    tmp_container = SampleContainer(height=40, border_radius=10)

    # Assert
    assert tmp_container.outer_layout.count() == 1
    assert tmp_container.container_frame.height() == 40
    assert (
        tmp_container.container_frame.graphicsEffect() is tmp_container.shadow
    )
    assert tmp_container.content_layout.count() == 1


def test_input_bar_uses_elevated_container_inner_layout(
    q_app: QtWidgets.QApplication,
) -> None:
    """Tests that InputBar only injects controls into the base layout.

    Args:
        q_app: The QApplication fixture.
    """
    # Arrange & Act
    assert q_app is not None
    tmp_input_bar = input_bar.InputBar()

    # Assert
    assert isinstance(
        tmp_input_bar,
        elevated_container.ElevatedContainer,
    )
    assert tmp_input_bar.capsule_frame is tmp_input_bar.container_frame
    assert tmp_input_bar.content_layout.count() == 4
    assert tmp_input_bar.input_field.placeholderText() == "Ask Gemini"
    assert tmp_input_bar.model_dropdown.count() == 3


def test_elevated_container_rejects_unknown_orientation(
    q_app: QtWidgets.QApplication,
) -> None:
    """Tests that unsupported layout orientation values are rejected.

    Args:
        q_app: The QApplication fixture.
    """
    # Arrange
    assert q_app is not None
    tmp_orientation = typing.cast(
        typing.Literal["horizontal", "vertical"],
        "diagonal",
    )

    # Act & Assert
    with pytest.raises(ValueError):
        SampleContainer(orientation=tmp_orientation)
