"""Tests for the button primitive."""

from __future__ import annotations

import unittest.mock

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.enums.roles as roles_module
import fluentqt.primitives.button as button_module


def test_token_button_default_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify default properties of TokenButton.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_button = button_module.TokenButton()

    # Assert
    assert tmp_button.text() == ""
    assert tmp_button.role() == roles_module.ButtonRole.Standard
    assert tmp_button._state == roles_module.ControlState.Default


def test_token_button_setters(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify properties can be dynamically updated via setters.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_button = button_module.TokenButton()
    tmp_apply_count = 0

    def tmp_spy() -> None:
        nonlocal tmp_apply_count
        tmp_apply_count += 1

    tmp_button._apply_tokens = tmp_spy

    # Act
    tmp_button.setText("New Text")
    tmp_button.set_role(roles_module.ButtonRole.Accent)

    # Assert
    assert tmp_button.text() == "New Text"
    assert tmp_button.role() == roles_module.ButtonRole.Accent
    assert tmp_apply_count == 1

    # Act (no-op guard test)
    tmp_button.set_role(roles_module.ButtonRole.Accent)

    # Assert (count should remain 1)
    assert tmp_apply_count == 1


def test_token_button_state_transitions(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify state transitions and signal emissions on events.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_button = button_module.TokenButton("Test")
    tmp_emitted_states = []

    def tmp_slot(state: roles_module.ControlState) -> None:
        tmp_emitted_states.append(state)

    tmp_button.state_changed.connect(tmp_slot)

    # Act 1 (enter event)
    tmp_enter = QtGui.QEnterEvent(
        QtCore.QPointF(0, 0), QtCore.QPointF(0, 0), QtCore.QPointF(0, 0)
    )
    tmp_button.enterEvent(tmp_enter)

    # Assert 1
    assert tmp_button._state == roles_module.ControlState.Hovered
    assert tmp_emitted_states == [roles_module.ControlState.Hovered]

    # Act 2 (mouse press event)
    tmp_press = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress,
        QtCore.QPointF(0, 0),
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
    )
    tmp_button.mousePressEvent(tmp_press)

    # Assert 2
    assert tmp_button._state == roles_module.ControlState.Pressed
    assert tmp_emitted_states == [
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Pressed,
    ]

    # Act 3 (mouse release event under mouse)
    tmp_release = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonRelease,
        QtCore.QPointF(0, 0),
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
    )
    with unittest.mock.patch.object(
        tmp_button, "underMouse", return_value=True
    ):
        tmp_button.mouseReleaseEvent(tmp_release)

    # Assert 3
    assert tmp_button._state == roles_module.ControlState.Hovered
    assert tmp_emitted_states == [
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Pressed,
        roles_module.ControlState.Hovered,
    ]

    # Act 4 (leave event)
    tmp_leave = QtCore.QEvent(QtCore.QEvent.Type.Leave)
    tmp_button.leaveEvent(tmp_leave)

    # Assert 4
    assert tmp_button._state == roles_module.ControlState.Default
    assert tmp_emitted_states == [
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Pressed,
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Default,
    ]

    # Act 5 (disable button)
    tmp_button.setEnabled(False)

    # Assert 5
    assert tmp_button._state == roles_module.ControlState.Disabled
    assert tmp_emitted_states == [
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Pressed,
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Default,
        roles_module.ControlState.Disabled,
    ]

    # Act 6 (enable button)
    tmp_button.setEnabled(True)

    # Assert 6
    assert tmp_button._state == roles_module.ControlState.Default
    assert tmp_emitted_states == [
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Pressed,
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Default,
        roles_module.ControlState.Disabled,
        roles_module.ControlState.Default,
    ]


def test_token_button_dpi_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify geometry recalculates on screen scale changes.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_button = button_module.TokenButton()
    tmp_apply_called = False

    def tmp_apply_tokens_spy() -> None:
        nonlocal tmp_apply_called
        tmp_apply_called = True

    tmp_button._apply_tokens = tmp_apply_tokens_spy

    # Act: emit scale_changed
    dp_module.notifier.scale_changed.emit(2.0)

    # Assert
    assert tmp_apply_called is True

    # Clean up / reset scale notifier to original state
    dp_module.notifier.scale_changed.emit(1.0)


def test_token_button_size_hint(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify that sizeHint returns correctly computed QSize.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_button = button_module.TokenButton("Click")

    # Act
    tmp_size = tmp_button.sizeHint()

    # Assert
    tmp_fm = tmp_button.fontMetrics()
    tmp_expected_width = tmp_fm.horizontalAdvance("Click") + 2 * dp_module.dp(
        12
    )
    assert tmp_size.height() == dp_module.dp(32)
    assert tmp_size.width() == tmp_expected_width
