"""Tests for the input primitive."""

from __future__ import annotations

import unittest.mock

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.enums.roles as roles_module
import fluentqt.primitives.input as input_module


def test_token_input_default_properties(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify default properties of TokenInput.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange & Act
    tmp_input = input_module.TokenInput()

    # Assert
    assert tmp_input.text() == ""
    assert tmp_input.placeholderText() == ""
    assert tmp_input._state == roles_module.ControlState.Default


def test_token_input_getters_and_setters(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify properties can be dynamically updated via getters and setters.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_input = input_module.TokenInput()

    # Act
    tmp_input.setText("Hello World")
    tmp_input.setPlaceholderText("Enter text here")

    # Assert
    assert tmp_input.text() == "Hello World"
    assert tmp_input.placeholderText() == "Enter text here"


def test_token_input_state_transitions(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify state transitions on hover and focus events.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_input = input_module.TokenInput("Search")
    tmp_emitted_states = []

    def tmp_slot(state: roles_module.ControlState) -> None:
        tmp_emitted_states.append(state)

    tmp_input.state_changed.connect(tmp_slot)

    # Act 1 (Hover enter on internal QLineEdit)
    tmp_enter = QtGui.QEnterEvent(
        QtCore.QPointF(0, 0), QtCore.QPointF(0, 0), QtCore.QPointF(0, 0)
    )
    QtWidgets.QApplication.sendEvent(tmp_input._line_edit, tmp_enter)

    # Assert 1
    assert tmp_input._state == roles_module.ControlState.Hovered
    assert tmp_emitted_states == [roles_module.ControlState.Hovered]

    # Act 2 (Focus In on internal QLineEdit)
    tmp_focus_in = QtGui.QFocusEvent(QtCore.QEvent.Type.FocusIn)
    with unittest.mock.patch.object(
        tmp_input._line_edit, "hasFocus", return_value=True
    ):
        QtWidgets.QApplication.sendEvent(tmp_input._line_edit, tmp_focus_in)

    # Assert 2
    assert tmp_input._state == roles_module.ControlState.Focused
    assert tmp_emitted_states == [
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Focused,
    ]

    # Act 3 (Hover leave while focused)
    tmp_leave = QtCore.QEvent(QtCore.QEvent.Type.Leave)
    with unittest.mock.patch.object(
        tmp_input._line_edit, "hasFocus", return_value=True
    ):
        QtWidgets.QApplication.sendEvent(tmp_input._line_edit, tmp_leave)

    # Assert 3 (should remain Focused)
    assert tmp_input._state == roles_module.ControlState.Focused
    assert len(tmp_emitted_states) == 2

    # Act 4 (Focus Out on internal QLineEdit)
    tmp_focus_out = QtGui.QFocusEvent(QtCore.QEvent.Type.FocusOut)
    with (
        unittest.mock.patch.object(
            tmp_input._line_edit, "hasFocus", return_value=False
        ),
        unittest.mock.patch.object(tmp_input, "underMouse", return_value=False),
    ):
        QtWidgets.QApplication.sendEvent(tmp_input._line_edit, tmp_focus_out)

    # Assert 4
    assert tmp_input._state == roles_module.ControlState.Default
    assert tmp_emitted_states == [
        roles_module.ControlState.Hovered,
        roles_module.ControlState.Focused,
        roles_module.ControlState.Default,
    ]


def test_token_input_signals(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify that textChanged and returnPressed signals are forwarded.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_input = input_module.TokenInput()
    tmp_changed_payload = None
    tmp_return_called = False

    def tmp_on_changed(text: str) -> None:
        nonlocal tmp_changed_payload
        tmp_changed_payload = text

    def tmp_on_return() -> None:
        nonlocal tmp_return_called
        tmp_return_called = True

    tmp_input.textChanged.connect(tmp_on_changed)
    tmp_input.returnPressed.connect(tmp_on_return)

    # Act
    tmp_input._line_edit.textChanged.emit("New Text")
    tmp_input._line_edit.returnPressed.emit()

    # Assert
    assert tmp_changed_payload == "New Text"
    assert tmp_return_called is True


def test_token_input_disabled_state(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify that setting the enabled property propagates to the child.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_input = input_module.TokenInput()

    # Assert Initial State
    assert tmp_input.isEnabled() is True
    assert tmp_input._line_edit.isEnabled() is True
    assert tmp_input._state == roles_module.ControlState.Default

    # Act (Disable)
    tmp_input.setEnabled(False)

    # Assert Disabled State
    assert tmp_input.isEnabled() is False
    assert tmp_input._line_edit.isEnabled() is False
    assert tmp_input._state == roles_module.ControlState.Disabled

    # Act (Re-enable)
    tmp_input.setEnabled(True)

    # Assert Re-enabled State
    assert tmp_input.isEnabled() is True
    assert tmp_input._line_edit.isEnabled() is True
    assert tmp_input._state == roles_module.ControlState.Default


def test_token_input_dpi_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify geometry recalculates on screen scale changes.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app
    # Arrange
    tmp_input = input_module.TokenInput()
    tmp_apply_called = False

    def tmp_apply_tokens_spy() -> None:
        nonlocal tmp_apply_called
        tmp_apply_called = True

    tmp_input._apply_tokens = tmp_apply_tokens_spy

    # Act: emit scale_changed
    dp_module.notifier.scale_changed.emit(2.0)

    # Assert
    assert tmp_apply_called is True

    # Clean up / reset scale notifier to original state
    dp_module.notifier.scale_changed.emit(1.0)
