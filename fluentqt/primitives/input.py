"""A styled text input widget."""

from __future__ import annotations

import dataclasses
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.core.state as state_module
import fluentqt.core.stylesheet as stylesheet_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles_module


@dataclasses.dataclass(frozen=True)
class _InputGeometry:
    """Input geometry settings in physical pixels.

    Attributes:
        radius_px: Corner radius in physical pixels.
        height_px: Control height in physical pixels.
        padding_left_px: Left internal padding in physical pixels.
        padding_right_px: Right internal padding in physical pixels.
        padding_top_px: Top internal padding in physical pixels.
        padding_bottom_px: Bottom internal padding in physical pixels.
        font_size_px: Font size in physical pixels.
        font_size_dp: Font size in dp.
        font_weight: Font weight.
        font_family: Font family name.
    """

    radius_px: int
    height_px: int
    padding_left_px: int
    padding_right_px: int
    padding_top_px: int
    padding_bottom_px: int
    font_size_px: int
    font_size_dp: int
    font_weight: QtGui.QFont.Weight
    font_family: str


@dataclasses.dataclass(frozen=True)
class _InputStateColors:
    """Color settings for a single state of the input widget.

    Attributes:
        background: Background fill color.
        border: Border line color.
        text: Text color.
        placeholder: Placeholder text color.
        focus_border: Focus border color, or None if focus ring is disabled.
    """

    background: QtGui.QColor
    border: QtGui.QColor
    text: QtGui.QColor
    placeholder: QtGui.QColor
    focus_border: QtGui.QColor | None


@dataclasses.dataclass(frozen=True)
class _InputColors:
    """Input color settings mapping states to colors.

    Attributes:
        states: Mapping of ControlState to its corresponding colors.
    """

    states: dict[roles_module.ControlState, _InputStateColors]


class TokenInput(state_module.StatefulWidget):
    """WinUI3-faithful styled text input widget.

    This widget composes a QLineEdit internally to provide reliable text input,
    wrapped in a QFrame that serves as the visual border shell.
    """

    textChanged = QtCore.pyqtSignal(str)
    returnPressed = QtCore.pyqtSignal()

    def __init__(
        self,
        placeholder: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the TokenInput.

        Args:
            placeholder: The initial placeholder text.
            parent: Optional parent widget.
        """
        super().__init__(parent=parent)

        # Setup internal container and line edit
        tmp_layout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(0, 0, 0, 0)
        tmp_layout.setSpacing(0)

        self._container = QtWidgets.QFrame(self)
        tmp_layout.addWidget(self._container)

        self._container_layout = QtWidgets.QHBoxLayout(self._container)
        self._container_layout.setSpacing(0)

        self._line_edit = QtWidgets.QLineEdit(self._container)
        self._line_edit.setFrame(False)
        self._container_layout.addWidget(self._line_edit)

        # Forward signals
        self._line_edit.textChanged.connect(self.textChanged.emit)
        self._line_edit.returnPressed.connect(self.returnPressed.emit)

        # Redirect focus to internal QLineEdit
        self.setFocusProxy(self._line_edit)

        # Install event filter to track internal events on line edit
        self._line_edit.installEventFilter(self)

        self.setPlaceholderText(placeholder)

        # Initial token application since the super class constructor call
        # returned early due to the internal elements not being initialized yet.
        self._apply_tokens()

        # Connect DPI scaling changes
        dp_module.notifier.scale_changed.connect(self._handle_scale_changed)

    def text(self) -> str:
        """Get the current text in the input.

        Returns:
            The input text.
        """
        return self._line_edit.text()

    def setText(self, text: str) -> None:  # noqa: N802
        """Set the text in the input.

        Args:
            text: The text to set.
        """
        self._line_edit.setText(text)

    def setPlaceholderText(self, text: str) -> None:  # noqa: N802
        """Set the placeholder text.

        Args:
            text: The placeholder text to set.
        """
        self._line_edit.setPlaceholderText(text)

    def placeholderText(self) -> str:  # noqa: N802
        """Get the current placeholder text.

        Returns:
            The placeholder text.
        """
        return self._line_edit.placeholderText()

    def clear(self) -> None:
        """Clear the input text."""
        self._line_edit.clear()

    @override
    def sizeHint(self) -> QtCore.QSize:
        """Return the token-consistent size hint for the input.

        Returns:
            The recommended QSize of the widget.
        """
        tmp_width = dp_module.dp(200)
        return QtCore.QSize(tmp_width, self._geometry.height_px)

    @override
    def eventFilter(
        self,
        watched: QtCore.QObject,
        event: QtCore.QEvent,
    ) -> bool:
        """Filter events from the internal QLineEdit to synchronize state.

        Focus transitions are owned by the event filter because focus events
        from the proxy do not bubble up to the parent widget. We must return
        False from this handler to ensure QLineEdit continues to process its
        own focus and mouse events normally.

        Args:
            watched: The QObject being watched.
            event: The QEvent to filter.

        Returns:
            True if the event should be filtered, False otherwise.
        """
        if watched is self._line_edit:
            if event.type() == QtCore.QEvent.Type.FocusIn:
                self._set_state(roles_module.ControlState.Focused)
            elif event.type() == QtCore.QEvent.Type.FocusOut:
                if self.underMouse():
                    self._set_state(roles_module.ControlState.Hovered)
                else:
                    self._set_state(roles_module.ControlState.Default)
            elif event.type() == QtCore.QEvent.Type.Enter:
                if not self.isEnabled():
                    self._set_state(roles_module.ControlState.Disabled)
                elif not self._line_edit.hasFocus():
                    self._set_state(roles_module.ControlState.Hovered)
            elif event.type() == QtCore.QEvent.Type.Leave:
                if not self.isEnabled():
                    self._set_state(roles_module.ControlState.Disabled)
                elif self._line_edit.hasFocus():
                    self._set_state(roles_module.ControlState.Focused)
                else:
                    self._set_state(roles_module.ControlState.Default)
        return super().eventFilter(watched, event)

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        """Handle mouse enter events.

        Args:
            event: The QEnterEvent.
        """
        super().enterEvent(event)
        if not self.isEnabled():
            self._set_state(roles_module.ControlState.Disabled)
            return
        if self._line_edit.hasFocus():
            self._set_state(roles_module.ControlState.Focused)
        else:
            self._set_state(roles_module.ControlState.Hovered)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        """Handle mouse leave events.

        Args:
            event: The QEvent.
        """
        super().leaveEvent(event)
        if not self.isEnabled():
            self._set_state(roles_module.ControlState.Disabled)
            return
        if self._line_edit.hasFocus():
            self._set_state(roles_module.ControlState.Focused)
        else:
            self._set_state(roles_module.ControlState.Default)

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        """Handle focus in events as a no-op to prevent double transitions.

        Focus transitions are owned exclusively by the event filter installed
        on the internal QLineEdit.

        Args:
            event: The QFocusEvent.
        """
        _ = event

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        """Handle focus out events as a no-op to prevent double transitions.

        Focus transitions are owned exclusively by the event filter installed
        on the internal QLineEdit.

        Args:
            event: The QFocusEvent.
        """
        _ = event

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        """Handle state changes (e.g. enablement changes).

        Args:
            event: The QEvent.
        """
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            if not self.isEnabled():
                self._line_edit.setEnabled(False)
                self._set_state(roles_module.ControlState.Disabled)
            else:
                self._line_edit.setEnabled(True)
                if self._line_edit.hasFocus():
                    self._set_state(roles_module.ControlState.Focused)
                elif self.underMouse():
                    self._set_state(roles_module.ControlState.Hovered)
                else:
                    self._set_state(roles_module.ControlState.Default)

    def _compute_geometry(self) -> _InputGeometry:
        """Compute the DPI-scaled geometry values in physical pixels.

        Returns:
            A new _InputGeometry instance containing scaled dimensions.
        """
        tmp_tokens = tokens_module.tokens()
        tmp_radius_px = dp_module.dp(tmp_tokens.radius_control)
        tmp_height_px = dp_module.dp(32)
        tmp_padding_left_px = dp_module.dp(10)
        tmp_padding_right_px = dp_module.dp(10)
        tmp_padding_top_px = dp_module.dp(5)
        tmp_padding_bottom_px = dp_module.dp(5)

        tmp_size_dp = tmp_tokens.type_body_size
        tmp_weight = tmp_tokens.type_body_weight
        tmp_font = tokens_module.make_font(tmp_size_dp, tmp_weight)
        tmp_family = tmp_font.family()

        return _InputGeometry(
            radius_px=tmp_radius_px,
            height_px=tmp_height_px,
            padding_left_px=tmp_padding_left_px,
            padding_right_px=tmp_padding_right_px,
            padding_top_px=tmp_padding_top_px,
            padding_bottom_px=tmp_padding_bottom_px,
            font_size_px=dp_module.dp(tmp_size_dp),
            font_size_dp=tmp_size_dp,
            font_weight=tmp_weight,
            font_family=tmp_family,
        )

    def _compute_colors(self) -> _InputColors:
        """Resolve semantic roles to QColor instances based on current tokens.

        Returns:
            A new _InputColors instance containing resolved colors.
        """
        tmp_tok = tokens_module.tokens()
        tmp_states = {
            roles_module.ControlState.Default: _InputStateColors(
                background=tmp_tok.fill_control_default,
                border=tmp_tok.stroke_control,
                text=tmp_tok.text_primary,
                placeholder=tmp_tok.text_secondary,
                focus_border=tmp_tok.stroke_focus,
            ),
            roles_module.ControlState.Hovered: _InputStateColors(
                background=tmp_tok.fill_control_hover,
                border=tmp_tok.stroke_control,
                text=tmp_tok.text_primary,
                placeholder=tmp_tok.text_secondary,
                focus_border=tmp_tok.stroke_focus,
            ),
            roles_module.ControlState.Pressed: _InputStateColors(
                background=tmp_tok.fill_control_pressed,
                border=tmp_tok.stroke_control,
                text=tmp_tok.text_primary,
                placeholder=tmp_tok.text_secondary,
                focus_border=tmp_tok.stroke_focus,
            ),
            roles_module.ControlState.Focused: _InputStateColors(
                background=tmp_tok.fill_control_default,
                border=tmp_tok.stroke_focus,
                text=tmp_tok.text_primary,
                placeholder=tmp_tok.text_secondary,
                focus_border=tmp_tok.stroke_focus,
            ),
            roles_module.ControlState.Disabled: _InputStateColors(
                background=tmp_tok.fill_control_disabled,
                border=tmp_tok.stroke_control,
                text=tmp_tok.text_disabled,
                placeholder=tmp_tok.text_disabled,
                focus_border=None,
            ),
        }
        return _InputColors(states=tmp_states)

    @override
    def _apply_tokens(self) -> None:
        """Apply current design tokens to the widget."""
        if not hasattr(self, "_line_edit"):
            return

        self._colors = self._compute_colors()
        self._geometry = self._compute_geometry()

        tmp_font = tokens_module.make_font(
            self._geometry.font_size_dp,
            self._geometry.font_weight,
        )
        self.setFont(tmp_font)
        self._line_edit.setFont(tmp_font)

        self._container_layout.setContentsMargins(
            self._geometry.padding_left_px,
            self._geometry.padding_top_px,
            self._geometry.padding_right_px,
            self._geometry.padding_bottom_px,
        )

        self._refresh_stylesheet()

    @override
    def _refresh_stylesheet(self) -> None:
        """Rebuild and re-apply the stylesheet based on the control state."""
        tmp_state_colors = self._colors.states.get(
            self._state,
            self._colors.states[roles_module.ControlState.Default],
        )

        tmp_is_focused = self._state == roles_module.ControlState.Focused
        self._container.setProperty(
            "state",
            "focused" if tmp_is_focused else "default",
        )
        QtWidgets.QApplication.style().unpolish(self._container)
        QtWidgets.QApplication.style().polish(self._container)
        self._container.update()

        tmp_qss = stylesheet_module.build_input_style(
            bg=tmp_state_colors.background,
            border=tmp_state_colors.border,
            radius_px=self._geometry.radius_px,
            text=tmp_state_colors.text,
            placeholder=tmp_state_colors.placeholder,
            focus_border=tmp_state_colors.focus_border,
        )
        self._container.setStyleSheet(tmp_qss)

    def _handle_scale_changed(self, scale: float) -> None:
        """Handle screen scale changes by recomputing geometry.

        Args:
            scale: The new display scale factor.
        """
        _ = scale
        self._apply_tokens()
