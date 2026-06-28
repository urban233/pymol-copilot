"""Tests for widget state management."""

from __future__ import annotations

import unittest.mock
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

from fluentqt.core import state as state_module
from fluentqt.enums import roles


class MockStatefulWidget(state_module.StatefulWidget):
    """Mock stateful widget for testing."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the mock widget.

        Args:
            parent: Optional parent widget.
        """
        self.refresh_count = 0
        super().__init__(parent)

    @override
    def _refresh_stylesheet(self) -> None:
        """Increment stylesheet refresh counter."""
        self.refresh_count += 1


def test_initial_state(
    q_app: QtWidgets.QApplication,  # noqa: ARG001
) -> None:
    """Verify that initial state is Default.

    Args:
        q_app: Session-scoped QApplication instance.
    """
    # Arrange & Act
    tmp_widget = MockStatefulWidget()

    # Assert
    assert tmp_widget._state == roles.ControlState.Default
    assert tmp_widget.refresh_count == 1


def test_enter_leave_events(
    q_app: QtWidgets.QApplication,  # noqa: ARG001
) -> None:
    """Verify enter and leave events update state correctly.

    Args:
        q_app: Session-scoped QApplication instance.
    """
    # Arrange
    tmp_widget = MockStatefulWidget()

    # Act (enter while not pressed)
    tmp_enter_event = QtGui.QEnterEvent(
        QtCore.QPointF(0, 0), QtCore.QPointF(0, 0), QtCore.QPointF(0, 0)
    )
    tmp_widget.enterEvent(tmp_enter_event)

    # Assert
    assert tmp_widget._state == roles.ControlState.Hovered

    # Act (leave while not focused)
    tmp_leave_event = QtCore.QEvent(QtCore.QEvent.Type.Leave)
    tmp_widget.leaveEvent(tmp_leave_event)

    # Assert
    assert tmp_widget._state == roles.ControlState.Default


def test_mouse_press_release_events(
    q_app: QtWidgets.QApplication,  # noqa: ARG001
) -> None:
    """Verify mouse press and release events update state correctly.

    Args:
        q_app: Session-scoped QApplication instance.
    """
    # Arrange
    tmp_widget = MockStatefulWidget()

    # Act (press)
    tmp_press_event = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress,
        QtCore.QPointF(0, 0),
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
    )
    tmp_widget.mousePressEvent(tmp_press_event)

    # Assert
    assert tmp_widget._state == roles.ControlState.Pressed

    # Act (release under mouse)
    tmp_release_event = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonRelease,
        QtCore.QPointF(0, 0),
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
    )
    with unittest.mock.patch.object(
        tmp_widget, "underMouse", return_value=True
    ):
        tmp_widget.mouseReleaseEvent(tmp_release_event)

    # Assert
    assert tmp_widget._state == roles.ControlState.Hovered


def test_focus_events(
    q_app: QtWidgets.QApplication,  # noqa: ARG001
) -> None:
    """Verify focus events update state correctly.

    Args:
        q_app: Session-scoped QApplication instance.
    """
    # Arrange
    tmp_widget = MockStatefulWidget()

    # Act (focus in, not under mouse)
    tmp_focus_in = QtGui.QFocusEvent(
        QtCore.QEvent.Type.FocusIn, QtCore.Qt.FocusReason.TabFocusReason
    )
    with unittest.mock.patch.object(
        tmp_widget, "underMouse", return_value=False
    ):
        tmp_widget.focusInEvent(tmp_focus_in)

    # Assert
    assert tmp_widget._state == roles.ControlState.Focused

    # Act (focus out)
    tmp_focus_out = QtGui.QFocusEvent(
        QtCore.QEvent.Type.FocusOut, QtCore.Qt.FocusReason.TabFocusReason
    )
    with unittest.mock.patch.object(
        tmp_widget, "underMouse", return_value=False
    ):
        tmp_widget.focusOutEvent(tmp_focus_out)

    # Assert
    assert tmp_widget._state == roles.ControlState.Default


def test_enablement_changes(
    q_app: QtWidgets.QApplication,  # noqa: ARG001
) -> None:
    """Verify enablement changes update state to and from Disabled.

    Args:
        q_app: Session-scoped QApplication instance.
    """
    # Arrange
    tmp_widget = MockStatefulWidget()

    # Act (disable)
    tmp_widget.setEnabled(False)

    # Assert
    assert tmp_widget._state == roles.ControlState.Disabled

    # Act (enable)
    tmp_widget.setEnabled(True)

    # Assert
    assert tmp_widget._state == roles.ControlState.Default
