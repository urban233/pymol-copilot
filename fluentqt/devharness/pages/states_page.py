"""Dev harness page for testing all control states."""

from __future__ import annotations

from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.enums.roles as roles_module
import fluentqt.primitives.button as button_module
import fluentqt.primitives.input as input_module


class StaticTokenButton(button_module.TokenButton):
    """TokenButton subclass that maintains a static control state."""

    def __init__(
        self,
        state: roles_module.ControlState,
        text: str = "",
        role: roles_module.ButtonRole = roles_module.ButtonRole.Standard,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the StaticTokenButton.

        Args:
            state: The static ControlState to show.
            text: The text of the button.
            role: The semantic button role.
            parent: Optional parent widget.
        """
        super().__init__(text=text, role=role, parent=parent)
        self._set_state(state)

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        pass

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        pass

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        pass

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        pass

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        pass

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        pass

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        pass


class StaticTokenInput(input_module.TokenInput):
    """TokenInput subclass that maintains a static control state."""

    def __init__(
        self,
        state: roles_module.ControlState,
        placeholder: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the StaticTokenInput.

        Args:
            state: The static ControlState to show.
            placeholder: The placeholder text.
            parent: Optional parent widget.
        """
        super().__init__(placeholder=placeholder, parent=parent)
        self._set_state(state)

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        return False

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        pass

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        pass

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        pass

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        pass

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        pass


class StatesPage(QtWidgets.QWidget):
    """Page displaying TokenButton and TokenInput in all ControlStates."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the StatesPage.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent=parent)

        tmp_layout = QtWidgets.QGridLayout(self)
        tmp_layout.setContentsMargins(20, 20, 20, 20)
        tmp_layout.setSpacing(15)

        # Header titles
        tmp_col_headers = [
            "State Name",
            "Standard Button",
            "Accent Button",
            "Token Input",
        ]
        for tmp_col_idx, tmp_header_text in enumerate(tmp_col_headers):
            tmp_header = QtWidgets.QLabel(tmp_header_text, self)
            tmp_header.setStyleSheet("font-weight: bold; font-size: 14px;")
            tmp_layout.addWidget(
                tmp_header, 0, tmp_col_idx, QtCore.Qt.AlignmentFlag.AlignCenter
            )

        tmp_states = [
            (roles_module.ControlState.Default, "Default"),
            (roles_module.ControlState.Hovered, "Hovered"),
            (roles_module.ControlState.Pressed, "Pressed"),
            (roles_module.ControlState.Focused, "Focused"),
            (roles_module.ControlState.Disabled, "Disabled"),
        ]

        for tmp_row_idx, (tmp_state, tmp_label_text) in enumerate(
            tmp_states, start=1
        ):
            # Row header (State Label)
            tmp_state_lbl = QtWidgets.QLabel(tmp_label_text, self)
            tmp_layout.addWidget(
                tmp_state_lbl,
                tmp_row_idx,
                0,
                QtCore.Qt.AlignmentFlag.AlignVCenter
                | QtCore.Qt.AlignmentFlag.AlignLeft,
            )

            # Standard button static instance
            tmp_std_btn = StaticTokenButton(
                tmp_state,
                text="Button",
                role=roles_module.ButtonRole.Standard,
                parent=self,
            )
            tmp_layout.addWidget(
                tmp_std_btn,
                tmp_row_idx,
                1,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )

            # Accent button static instance
            tmp_acc_btn = StaticTokenButton(
                tmp_state,
                text="Button",
                role=roles_module.ButtonRole.Accent,
                parent=self,
            )
            tmp_layout.addWidget(
                tmp_acc_btn,
                tmp_row_idx,
                2,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )

            # Token input static instance
            tmp_input = StaticTokenInput(
                tmp_state, placeholder="Placeholder...", parent=self
            )
            tmp_layout.addWidget(
                tmp_input,
                tmp_row_idx,
                3,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )

        # Spacer row at bottom
        tmp_spacer = QtWidgets.QSpacerItem(
            20,
            40,
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        tmp_layout.addItem(tmp_spacer, len(tmp_states) + 1, 0, 1, 4)
