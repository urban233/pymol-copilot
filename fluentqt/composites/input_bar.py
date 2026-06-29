"""A composite input bar widget designed with WinUI3 styling."""

from __future__ import annotations

from typing import override

from PyQt6 import QtWidgets

from fluentqt.composites import base as base_module
from fluentqt.core import dp as dp_module
from fluentqt.core import factory as factory_module
from fluentqt.enums import roles as roles_module
from fluentqt.primitives import button as button_module
from fluentqt.primitives import input as input_module


_BAR_HEIGHT_DP: int = 36
_BAR_RADIUS_DP: int = 18
_ICON_BTN_SIZE_DP: int = 28


class InputBar(base_module.CompositeWidget):
    """A WinUI3-faithful styled input bar widget.

    This composite widget groups a plus button, a line edit input, a model
    selection dropdown, and a microphone button into a single horizontal
    card container.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the InputBar.

        Args:
            parent: Optional parent widget.
        """
        self.plus_button: button_module.TokenButton | None = None
        self.input_field: input_module.TokenInput | None = None
        self.model_dropdown: QtWidgets.QComboBox | None = None
        self.mic_button: button_module.TokenButton | None = None

        super().__init__(
            elevation=roles_module.ElevationPreset.Card,
            orientation="horizontal",
            border_radius=_BAR_RADIUS_DP,
            parent=parent,
        )

    @override
    def _build_content(self) -> None:
        """Build and populate the layout with the input bar child controls."""
        self.plus_button = factory_module.make_button(
            "+", roles_module.ButtonRole.Subtle, parent=self
        )
        self.input_field = factory_module.make_input("Ask Gemini", parent=self)
        self.model_dropdown = factory_module.make_dropdown(
            ["Flash Extended", "Pro", "Ultra"], parent=self
        )
        self.mic_button = factory_module.make_button(
            "Mic", roles_module.ButtonRole.Subtle, parent=self
        )

        if self.content_layout is not None:
            self.content_layout.addWidget(self.plus_button)
            self.content_layout.addWidget(self.input_field, 1)
            self.content_layout.addWidget(self.model_dropdown)
            self.content_layout.addWidget(self.mic_button)

    @override
    def _apply_tokens(self) -> None:
        """Apply scale-dependent sizes to the frame and buttons.

        This ensures the height constraints are correctly enforced and updated on
        DPI scale adjustments.
        """
        super()._apply_tokens()

        if self.frame is not None:
            self.frame.setFixedHeight(dp_module.dp(_BAR_HEIGHT_DP))

        tmp_btn_size = dp_module.dp(_ICON_BTN_SIZE_DP)
        if self.plus_button is not None:
            self.plus_button.setFixedSize(tmp_btn_size, tmp_btn_size)
        if self.mic_button is not None:
            self.mic_button.setFixedSize(tmp_btn_size, tmp_btn_size)
