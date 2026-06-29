"""Dev harness page for toggling light/dark themes."""

from __future__ import annotations

from PyQt6 import QtWidgets

import fluentqt
import fluentqt.core.factory as factory_module
import fluentqt.core.tokens as tokens_module
import fluentqt.enums.roles as roles_module


class ThemesPage(QtWidgets.QWidget):
    """Page for controlling and toggling global theme modes."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the ThemesPage.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent=parent)

        tmp_layout = QtWidgets.QVBoxLayout(self)
        tmp_layout.setContentsMargins(30, 30, 30, 30)
        tmp_layout.setSpacing(20)

        # Title Label
        tmp_title = factory_module.make_label(
            "Theme Mode Management",
            roles_module.TextRole.Primary,
            roles_module.TypeStyle.Subtitle,
            parent=self,
        )
        tmp_layout.addWidget(tmp_title)

        # Mode Indicator Label
        self._mode_label = factory_module.make_label(
            "",
            roles_module.TextRole.Secondary,
            roles_module.TypeStyle.BodyLarge,
            parent=self,
        )
        tmp_layout.addWidget(self._mode_label)

        # Toggle Button
        self._toggle_btn = factory_module.make_button(
            "Toggle Light/Dark Theme",
            roles_module.ButtonRole.Standard,
            parent=self,
        )
        self._toggle_btn.clicked.connect(self._handle_toggle)
        tmp_layout.addWidget(self._toggle_btn)

        # Spacer
        tmp_layout.addStretch()

        # Connect theme changed callback and initialize text
        tokens_module.on_mode_changed(self._update_theme_status)
        self._update_theme_status()

    def _update_theme_status(self) -> None:
        """Update active mode status text on the label."""
        tmp_mode = tokens_module.current_mode()
        self._mode_label.setText(f"Current Mode: {tmp_mode.value.upper()}")

    def _handle_toggle(self) -> None:
        """Toggle active theme mode between light and dark."""
        tmp_current = tokens_module.current_mode()
        tmp_next = (
            tokens_module.ThemeMode.Dark
            if tmp_current == tokens_module.ThemeMode.Light
            else tokens_module.ThemeMode.Light
        )
        fluentqt.set_mode(tmp_next)
