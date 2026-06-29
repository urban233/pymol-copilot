"""Dev harness page for primitive widgets."""

from __future__ import annotations

from PyQt6 import QtWidgets

import fluentqt.core.factory as factory_module
import fluentqt.enums.roles as roles_module


class PrimitivesPage(QtWidgets.QWidget):
    """Page displaying all primitives in their default state on panels."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the PrimitivesPage.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent=parent)

        tmp_layout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(10, 10, 10, 10)
        tmp_layout.setSpacing(20)

        # Light background panel
        tmp_light_frame = QtWidgets.QFrame(self)
        tmp_light_frame.setStyleSheet(
            "QFrame { "
            "background-color: #f3f3f3; "
            "border: 1px solid #e5e5e5; "
            "border-radius: 8px; "
            "}"
        )
        tmp_light_layout = QtWidgets.QVBoxLayout(tmp_light_frame)
        tmp_light_layout.setContentsMargins(15, 15, 15, 15)
        tmp_light_layout.setSpacing(15)

        tmp_light_title = QtWidgets.QLabel("Light Panel Style", tmp_light_frame)
        tmp_light_title.setStyleSheet(
            "font-weight: bold; font-size: 16px; color: #000000; border: none;"
        )
        tmp_light_layout.addWidget(tmp_light_title)
        self._populate_primitives(tmp_light_frame, tmp_light_layout)

        tmp_layout.addWidget(tmp_light_frame)

        # Dark background panel
        tmp_dark_frame = QtWidgets.QFrame(self)
        tmp_dark_frame.setStyleSheet(
            "QFrame { "
            "background-color: #202020; "
            "border: 1px solid #3d3d3d; "
            "border-radius: 8px; "
            "}"
        )
        tmp_dark_layout = QtWidgets.QVBoxLayout(tmp_dark_frame)
        tmp_dark_layout.setContentsMargins(15, 15, 15, 15)
        tmp_dark_layout.setSpacing(15)

        tmp_dark_title = QtWidgets.QLabel("Dark Panel Style", tmp_dark_frame)
        tmp_dark_title.setStyleSheet(
            "font-weight: bold; font-size: 16px; color: #ffffff; border: none;"
        )
        tmp_dark_layout.addWidget(tmp_dark_title)
        self._populate_primitives(tmp_dark_frame, tmp_dark_layout)

        tmp_layout.addWidget(tmp_dark_frame)

    def _populate_primitives(
        self,
        panel: QtWidgets.QFrame,
        layout: QtWidgets.QVBoxLayout,
    ) -> None:
        """Populate a panel layout with labeled primitives.

        Args:
            panel: The parent panel.
            layout: The layout to add widgets to.
        """
        # TokenLabel
        tmp_lbl_section = QtWidgets.QLabel("TokenLabel:", panel)
        tmp_lbl_section.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(tmp_lbl_section)

        tmp_label_primary = factory_module.make_label(
            "Primary text", roles_module.TextRole.Primary, parent=panel
        )
        layout.addWidget(tmp_label_primary)

        tmp_label_secondary = factory_module.make_label(
            "Secondary text", roles_module.TextRole.Secondary, parent=panel
        )
        layout.addWidget(tmp_label_secondary)

        # TokenButton
        tmp_btn_section = QtWidgets.QLabel("TokenButton:", panel)
        tmp_btn_section.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(tmp_btn_section)

        tmp_btn_std = factory_module.make_button(
            "Standard Button", roles_module.ButtonRole.Standard, parent=panel
        )
        layout.addWidget(tmp_btn_std)

        tmp_btn_accent = factory_module.make_button(
            "Accent Button", roles_module.ButtonRole.Accent, parent=panel
        )
        layout.addWidget(tmp_btn_accent)

        # TokenInput
        tmp_input_section = QtWidgets.QLabel("TokenInput:", panel)
        tmp_input_section.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(tmp_input_section)

        tmp_input = factory_module.make_input(
            "Enter text here...", parent=panel
        )
        layout.addWidget(tmp_input)

        # TokenIcon
        tmp_icon_section = QtWidgets.QLabel("TokenIcon:", panel)
        tmp_icon_section.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(tmp_icon_section)

        tmp_icon = factory_module.make_icon(
            "home_icon", roles_module.IconSize.Medium, parent=panel
        )
        layout.addWidget(tmp_icon)

        # TokenDivider
        tmp_div_section = QtWidgets.QLabel("TokenDivider:", panel)
        tmp_div_section.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(tmp_div_section)

        tmp_divider = factory_module.make_divider(parent=panel)
        layout.addWidget(tmp_divider)

        # TokenFrame
        tmp_frame_section = QtWidgets.QLabel("TokenFrame (Card):", panel)
        tmp_frame_section.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(tmp_frame_section)

        tmp_nested_frame = factory_module.make_frame(
            roles_module.ElevationPreset.Card,
            roles_module.FillRole.Control,
            parent=panel,
        )
        tmp_nested_frame.setMinimumHeight(40)
        layout.addWidget(tmp_nested_frame)

        # Spacer at the bottom
        layout.addStretch()
