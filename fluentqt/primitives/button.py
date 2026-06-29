"""A styled button widget."""

from __future__ import annotations

import dataclasses
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.dp as dp_module
import fluentqt.core.stylesheet as stylesheet_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles_module


@dataclasses.dataclass(frozen=True)
class _ButtonGeometry:
    """Button visual dimensions in physical pixels.

    Attributes:
        radius_px: Corner radius in physical pixels.
        height_px: Height in physical pixels.
        padding_px: Horizontal padding in physical pixels.
        font_size_px: Font size in physical pixels.
        font_size_dp: Font size in dp.
        font_weight: Font weight (e.g. QFont.Weight).
        font_family: Font family name string.
    """

    radius_px: int
    height_px: int
    padding_px: int
    font_size_px: int
    font_size_dp: int
    font_weight: QtGui.QFont.Weight
    font_family: str


@dataclasses.dataclass(frozen=True)
class _ButtonColors:
    """Button color settings mapping states to colors.

    Attributes:
        states: Mapping of ControlState to (background, border, text) colors.
    """

    states: dict[
        roles_module.ControlState,
        tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor],
    ]


class TokenButton(tokens_module.TokenConsumer, QtWidgets.QPushButton):
    """WinUI3-faithful styled push button."""

    # Signal must be declared here on the concrete QObject subclass
    state_changed = QtCore.pyqtSignal(roles_module.ControlState)

    def __init__(
        self,
        text: str = "",
        role: roles_module.ButtonRole = roles_module.ButtonRole.Standard,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the TokenButton.

        Args:
            text: The text of the button.
            role: The semantic button role determining styling.
            parent: Optional parent widget.
        """
        self._role = role

        # Initialize state properties before super().__init__ because
        # TokenConsumer.__init__ calls _apply_tokens which immediately reads them
        self._state = roles_module.ControlState.Default
        self._is_pressed = False

        super().__init__(parent=parent)
        self.setText(text)

        if not self.isEnabled():
            self._state = roles_module.ControlState.Disabled

        # Connect to DPI scaling changes
        dp_module.notifier.scale_changed.connect(self._handle_scale_changed)

    def role(self) -> roles_module.ButtonRole:
        """Get the current button role.

        Returns:
            The active ButtonRole.
        """
        return self._role

    def set_role(self, role: roles_module.ButtonRole) -> None:
        """Set the button role and refresh the style.

        Args:
            role: The new ButtonRole.
        """
        if self._role == role:
            return
        self._role = role
        self._apply_tokens()

    def _set_state(self, state: roles_module.ControlState) -> None:
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
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        """Handle mouse enter event.

        Args:
            event: The QEnterEvent.
        """
        super().enterEvent(event)
        if not self.isEnabled():
            self._set_state(roles_module.ControlState.Disabled)
            return
        if self._is_pressed:
            self._set_state(roles_module.ControlState.Pressed)
        else:
            self._set_state(roles_module.ControlState.Hovered)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        """Handle mouse leave event.

        Args:
            event: The QEvent.
        """
        super().leaveEvent(event)
        if not self.isEnabled():
            self._set_state(roles_module.ControlState.Disabled)
            return
        if self.hasFocus():
            self._set_state(roles_module.ControlState.Focused)
        else:
            self._set_state(roles_module.ControlState.Default)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press event.

        Args:
            event: The QMouseEvent.
        """
        super().mousePressEvent(event)
        if not self.isEnabled():
            self._set_state(roles_module.ControlState.Disabled)
            return
        self._is_pressed = True
        self._set_state(roles_module.ControlState.Pressed)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release event.

        Args:
            event: The QMouseEvent.
        """
        super().mouseReleaseEvent(event)
        if not self.isEnabled():
            self._set_state(roles_module.ControlState.Disabled)
            return
        self._is_pressed = False
        if self.underMouse():
            self._set_state(roles_module.ControlState.Hovered)
        elif self.hasFocus():
            self._set_state(roles_module.ControlState.Focused)
        else:
            self._set_state(roles_module.ControlState.Default)

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        """Handle focus in event.

        Args:
            event: The QFocusEvent.
        """
        super().focusInEvent(event)
        if not self.isEnabled():
            self._set_state(roles_module.ControlState.Disabled)
            return
        if self.underMouse():
            self._set_state(roles_module.ControlState.Hovered)
        else:
            self._set_state(roles_module.ControlState.Focused)

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        """Handle focus out event.

        Args:
            event: The QFocusEvent.
        """
        super().focusOutEvent(event)
        if not self.isEnabled():
            self._set_state(roles_module.ControlState.Disabled)
            return
        if self.underMouse():
            self._set_state(roles_module.ControlState.Hovered)
        else:
            self._set_state(roles_module.ControlState.Default)

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        """Handle state change events, specifically enablement changes.

        Args:
            event: The QEvent.
        """
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            if not self.isEnabled():
                self._set_state(roles_module.ControlState.Disabled)
            else:
                if self._is_pressed:
                    self._set_state(roles_module.ControlState.Pressed)
                elif self.underMouse():
                    self._set_state(roles_module.ControlState.Hovered)
                elif self.hasFocus():
                    self._set_state(roles_module.ControlState.Focused)
                else:
                    self._set_state(roles_module.ControlState.Default)

    def _compute_geometry(self) -> _ButtonGeometry:
        """Compute the DPI-scaled geometry values in physical pixels.

        Returns:
            A new _ButtonGeometry instance containing scaled dimensions.
        """
        tmp_tokens = tokens_module.tokens()
        tmp_radius_px = dp_module.dp(tmp_tokens.radius_control)
        tmp_height_px = dp_module.dp(32)
        tmp_padding_px = dp_module.dp(12)

        tmp_size_dp = tmp_tokens.type_body_size
        tmp_weight = tmp_tokens.type_body_weight
        tmp_font = tokens_module.make_font(tmp_size_dp, tmp_weight)
        tmp_family = tmp_font.family()

        return _ButtonGeometry(
            radius_px=tmp_radius_px,
            height_px=tmp_height_px,
            padding_px=tmp_padding_px,
            font_size_px=dp_module.dp(tmp_size_dp),
            font_size_dp=tmp_size_dp,
            font_weight=tmp_weight,
            font_family=tmp_family,
        )

    def _compute_colors(self) -> _ButtonColors:
        """Resolve semantic roles to QColor instances based on current tokens.

        Returns:
            A new _ButtonColors instance containing resolved state colors.
        """
        tmp_tok = tokens_module.tokens()
        tmp_states = {}

        if self._role == roles_module.ButtonRole.Standard:
            tmp_states = {
                roles_module.ControlState.Default: (
                    tmp_tok.fill_control_default,
                    tmp_tok.stroke_control,
                    tmp_tok.text_primary,
                ),
                roles_module.ControlState.Hovered: (
                    tmp_tok.fill_control_hover,
                    tmp_tok.stroke_control,
                    tmp_tok.text_primary,
                ),
                roles_module.ControlState.Pressed: (
                    tmp_tok.fill_control_pressed,
                    tmp_tok.stroke_control,
                    tmp_tok.text_secondary,
                ),
                roles_module.ControlState.Focused: (
                    tmp_tok.fill_control_default,
                    tmp_tok.stroke_focus,
                    tmp_tok.text_primary,
                ),
                roles_module.ControlState.Disabled: (
                    tmp_tok.fill_control_disabled,
                    tmp_tok.stroke_control,
                    tmp_tok.text_disabled,
                ),
            }
        elif self._role == roles_module.ButtonRole.Accent:
            tmp_states = {
                roles_module.ControlState.Default: (
                    tmp_tok.accent_default,
                    tmp_tok.stroke_control,
                    tmp_tok.text_on_accent,
                ),
                roles_module.ControlState.Hovered: (
                    tmp_tok.accent_hover,
                    tmp_tok.stroke_control,
                    tmp_tok.text_on_accent,
                ),
                roles_module.ControlState.Pressed: (
                    tmp_tok.accent_pressed,
                    tmp_tok.stroke_control,
                    tmp_tok.text_on_accent,
                ),
                roles_module.ControlState.Focused: (
                    tmp_tok.accent_default,
                    tmp_tok.stroke_focus,
                    tmp_tok.text_on_accent,
                ),
                roles_module.ControlState.Disabled: (
                    tmp_tok.accent_disabled,
                    tmp_tok.stroke_control,
                    tmp_tok.text_disabled,
                ),
            }
        elif self._role == roles_module.ButtonRole.Subtle:
            tmp_transparent = QtGui.QColor(0, 0, 0, 0)
            tmp_states = {
                roles_module.ControlState.Default: (
                    tmp_transparent,
                    tmp_transparent,
                    tmp_tok.text_primary,
                ),
                roles_module.ControlState.Hovered: (
                    tmp_tok.fill_subtle_hover,
                    tmp_transparent,
                    tmp_tok.text_primary,
                ),
                roles_module.ControlState.Pressed: (
                    tmp_tok.fill_subtle_pressed,
                    tmp_transparent,
                    tmp_tok.text_secondary,
                ),
                roles_module.ControlState.Focused: (
                    tmp_transparent,
                    tmp_tok.stroke_focus,
                    tmp_tok.text_primary,
                ),
                roles_module.ControlState.Disabled: (
                    tmp_transparent,
                    tmp_transparent,
                    tmp_tok.text_disabled,
                ),
            }
        elif self._role == roles_module.ButtonRole.Danger:
            tmp_states = {
                roles_module.ControlState.Default: (
                    tmp_tok.status_error_background,
                    tmp_tok.status_error_border,
                    tmp_tok.status_error_text,
                ),
                roles_module.ControlState.Hovered: (
                    tmp_tok.status_error_background,
                    tmp_tok.status_error_border,
                    tmp_tok.status_error_text,
                ),
                roles_module.ControlState.Pressed: (
                    tmp_tok.status_error_background,
                    tmp_tok.status_error_border,
                    tmp_tok.status_error_text,
                ),
                roles_module.ControlState.Focused: (
                    tmp_tok.status_error_background,
                    tmp_tok.stroke_focus,
                    tmp_tok.status_error_text,
                ),
                roles_module.ControlState.Disabled: (
                    tmp_tok.status_error_background,
                    tmp_tok.status_error_border,
                    tmp_tok.text_disabled,
                ),
            }

        return _ButtonColors(states=tmp_states)

    @override
    def _apply_tokens(self) -> None:
        """Apply current design tokens to the widget."""
        self._colors = self._compute_colors()
        self._geometry = self._compute_geometry()

        tmp_font = tokens_module.make_font(
            self._geometry.font_size_dp,
            self._geometry.font_weight,
        )
        self.setFont(tmp_font)

        self._refresh_stylesheet()

    def _refresh_stylesheet(self) -> None:
        """Rebuild and re-apply the stylesheet based on the control state."""
        tmp_qss = stylesheet_module.build_button_style(
            self._colors.states,
            self._geometry.radius_px,
        )
        self.setStyleSheet(tmp_qss)

    def _handle_scale_changed(self, scale: float) -> None:
        """Handle screen scale changes by recomputing geometry.

        Args:
            scale: The new display scale factor.
        """
        _ = scale
        self._apply_tokens()

    @override
    def sizeHint(self) -> QtCore.QSize:
        """Return a token-consistent size hint for the button.

        Returns:
            The recommended size of the widget.
        """
        tmp_fm = self.fontMetrics()
        tmp_text_width = tmp_fm.horizontalAdvance(self.text())
        tmp_width = tmp_text_width + 2 * self._geometry.padding_px
        return QtCore.QSize(tmp_width, self._geometry.height_px)
