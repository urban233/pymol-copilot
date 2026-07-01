"""Tests for command bar widgets."""

from __future__ import annotations

from PyQt6 import QtCore
from PyQt6 import QtWidgets
import pytest

from pymol_copilot.gui.qt.widgets import command_bar


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


@pytest.mark.parametrize(
    "style",
    [
        command_bar.CommandBarButtonStyle.ICON_ONLY,
        command_bar.CommandBarButtonStyle.TEXT_BESIDE,
        command_bar.CommandBarButtonStyle.TEXT_UNDER,
        command_bar.CommandBarButtonStyle.TEXT_ONLY,
    ],
)
def test_toggle_button_accepts_all_tool_button_styles(
    q_app: QtWidgets.QApplication,
    style: command_bar.CommandBarButtonType,
) -> None:
    """Tests that toggle buttons support every command bar display style.

    Args:
        q_app: The QApplication fixture.
        style: The tool button style under test.
    """
    # Arrange & Act
    assert q_app is not None
    tmp_button = command_bar.CommandBarToggleButton(None, "Bold", style)
    tmp_tool_button = tmp_button.findChild(QtWidgets.QToolButton)

    # Assert
    assert tmp_tool_button is not None
    assert tmp_tool_button.toolButtonStyle() == style
    assert tmp_tool_button.isCheckable()


def test_toggle_button_tracks_programmatic_state(
    q_app: QtWidgets.QApplication,
) -> None:
    """Tests that programmatic state changes use Qt's checked state.

    Args:
        q_app: The QApplication fixture.
    """
    # Arrange
    assert q_app is not None
    tmp_button = command_bar.CommandBarToggleButton(None, "Bold")

    # Act
    tmp_button.set_checked(True)

    # Assert
    assert tmp_button.is_checked()


def test_toggle_button_emits_toggled_signal(
    q_app: QtWidgets.QApplication,
) -> None:
    """Tests that toggling emits the wrapper signal.

    Args:
        q_app: The QApplication fixture.
    """
    # Arrange
    assert q_app is not None
    tmp_button = command_bar.CommandBarToggleButton(None, "Bold")
    tmp_states: list[bool] = []
    tmp_button.toggled.connect(tmp_states.append)

    # Act
    tmp_button.toggle()

    # Assert
    assert tmp_states == [True]
    assert tmp_button.is_checked()


def test_toggle_button_click_emits_clicked_signal(
    q_app: QtWidgets.QApplication,
) -> None:
    """Tests that the wrapper clicked signal hides the checked payload.

    Args:
        q_app: The QApplication fixture.
    """
    # Arrange
    assert q_app is not None
    tmp_button = command_bar.CommandBarToggleButton(None, "Bold")
    tmp_clicked: list[bool] = []
    tmp_button.clicked.connect(lambda: tmp_clicked.append(True))
    tmp_tool_button = tmp_button.findChild(QtWidgets.QToolButton)

    # Act
    assert tmp_tool_button is not None
    tmp_tool_button.click()
    QtWidgets.QApplication.processEvents(
        QtCore.QEventLoop.ProcessEventsFlag.AllEvents
    )

    # Assert
    assert tmp_clicked == [True]
    assert tmp_button.is_checked()
