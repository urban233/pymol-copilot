"""Interactive state management for widgets."""

from __future__ import annotations

from typing import Any
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

from fluentqt.core import tokens
from fluentqt.enums import roles


class StatefulWidget(tokens.TokenConsumer, QtWidgets.QWidget):
    """Base class for interactive widgets with state tracking.

    This class manages interactive state transitions (Default, Hovered,
    Pressed, Focused, Disabled) and triggers stylesheet refreshes on state
    changes.
    """

    state_changed = QtCore.pyqtSignal(roles.ControlState)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the StatefulWidget.

        Args:
            parent: Optional parent widget.
            *args: Positional arguments forwarded to parent classes.
            **kwargs: Keyword arguments forwarded to parent classes.
        """
        self._state = roles.ControlState.Default
        self._is_pressed = False
        super().__init__(parent, *args, **kwargs)
        if not self.isEnabled():
            self._state = roles.ControlState.Disabled

    def _set_state(self, state: roles.ControlState) -> None:
        """Update the control state and refresh the stylesheet.

        Args:
            state: The new ControlState.
        """
        if self._state == state:
            return
        self._state = state
        self._refresh_stylesheet()
        self.state_changed.emit(state)

    @override
    def _apply_tokens(self) -> None:
        """Apply current design tokens to the widget.

        This base implementation ensures the state matches the enablement
        before refreshing the stylesheet.
        """
        if not self.isEnabled():
            self._state = roles.ControlState.Disabled
        self._refresh_stylesheet()

    def _refresh_stylesheet(self) -> None:
        """Rebuild and re-apply the stylesheet based on the control state.

        Subclasses must implement this method to update their visual style.

        Raises:
            NotImplementedError: If not overridden by a subclass.
        """
        raise NotImplementedError(
            "Subclasses must implement _refresh_stylesheet"
        )

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        """Handle mouse enter event.

        Args:
            event: The QEnterEvent.
        """
        super().enterEvent(event)
        if not self.isEnabled():
            self._set_state(roles.ControlState.Disabled)
            return
        if self._is_pressed:
            self._set_state(roles.ControlState.Pressed)
        else:
            self._set_state(roles.ControlState.Hovered)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        """Handle mouse leave event.

        Args:
            event: The QEvent.
        """
        super().leaveEvent(event)
        if not self.isEnabled():
            self._set_state(roles.ControlState.Disabled)
            return
        if self.hasFocus():
            self._set_state(roles.ControlState.Focused)
        else:
            self._set_state(roles.ControlState.Default)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press event.

        Args:
            event: The QMouseEvent.
        """
        super().mousePressEvent(event)
        if not self.isEnabled():
            self._set_state(roles.ControlState.Disabled)
            return
        self._is_pressed = True
        self._set_state(roles.ControlState.Pressed)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release event.

        Args:
            event: The QMouseEvent.
        """
        super().mouseReleaseEvent(event)
        if not self.isEnabled():
            self._set_state(roles.ControlState.Disabled)
            return
        self._is_pressed = False
        if self.underMouse():
            self._set_state(roles.ControlState.Hovered)
        elif self.hasFocus():
            self._set_state(roles.ControlState.Focused)
        else:
            self._set_state(roles.ControlState.Default)

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        """Handle focus in event.

        Args:
            event: The QFocusEvent.
        """
        super().focusInEvent(event)
        if not self.isEnabled():
            self._set_state(roles.ControlState.Disabled)
            return
        if self.underMouse():
            self._set_state(roles.ControlState.Hovered)
        else:
            self._set_state(roles.ControlState.Focused)

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        """Handle focus out event.

        Args:
            event: The QFocusEvent.
        """
        super().focusOutEvent(event)
        if not self.isEnabled():
            self._set_state(roles.ControlState.Disabled)
            return
        if self.underMouse():
            self._set_state(roles.ControlState.Hovered)
        else:
            self._set_state(roles.ControlState.Default)

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        """Handle state change events, specifically enablement changes.

        Args:
            event: The QEvent.
        """
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            if not self.isEnabled():
                self._set_state(roles.ControlState.Disabled)
            else:
                if self._is_pressed:
                    self._set_state(roles.ControlState.Pressed)
                elif self.underMouse():
                    self._set_state(roles.ControlState.Hovered)
                elif self.hasFocus():
                    self._set_state(roles.ControlState.Focused)
                else:
                    self._set_state(roles.ControlState.Default)
