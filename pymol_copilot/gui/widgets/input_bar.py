"""Contains the InputBar class."""

from __future__ import annotations

import typing

from PyQt6 import QtWidgets

from pymol_copilot.gui import fluent
from pymol_copilot.gui.widgets import elevated_container
from pymol_copilot.gui.widgets import ui_styles

# ---------------------------------------------------------------------------
# InputBar sizing constants (all in dp — 96 DPI baseline)
# ---------------------------------------------------------------------------
# 36 dp matches the standard desktop single-line toolbar height used by
# VS Code (35 px), Office ribbon inputs (32-36 px), and WinUI SearchBox.
_BAR_HEIGHT: int = 36

# Pill shape: border_radius must equal exactly height / 2.
# Both values derive from the same constant so they can never get out of sync.
_BAR_RADIUS: int = _BAR_HEIGHT // 2  # 18 dp

# Icon buttons: 28 dp — comfortable click target on desktop.
# 24 dp is a mobile icon size; 28 dp matches Office / VS Code.
_ICON_BTN_SIZE: int = 28


class InputBar(elevated_container.ElevatedContainer):
    """A widget for entering text input.

    Sizing rationale
    ----------------
    * Height **36 dp** — standard desktop single-line toolbar height.
    * Border-radius **18 dp** (= height / 2) — true pill / capsule shape.
    * Icon buttons **28 x 28 dp** — desktop click-target minimum.
    * Vertical content margins read from ``tokens().spacing_xs`` (4 dp) —
      compact padding that keeps the row tight inside the 36 dp frame while
      preventing text clipping on larger system fonts.
    * Horizontal content margin reads from ``tokens().spacing_l`` (16 dp) —
      the standard Fluent content inset, inherited from ElevatedContainer.
    * Shadow sourced from ``ElevationLevel.CARD`` via the token system.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initializes the input bar.

        Args:
            parent: The parent widget for this input bar.
        """
        super().__init__(
            parent,
            height=_BAR_HEIGHT,
            border_radius=_BAR_RADIUS,
            # CARD elevation: 4 dp blur, 2 dp offset — appropriate for a
            # search bar resting on the content layer.
            elevation=fluent.ElevationLevel.CARD,
        )

    @typing.override
    def setup_ui(self) -> None:
        """Builds the input bar controls."""
        self.capsule_frame = self.container_frame
        tok = fluent.tokens()
        dp = elevated_container.dp

        # Override vertical margin to spacing_xs (4 dp) — the parent sets
        # spacing_xs by default; this call makes the intent explicit and
        # keeps the row compact inside the 36 dp frame.
        self.content_layout.setContentsMargins(
            dp(tok.spacing_l),
            dp(tok.spacing_xs),
            dp(tok.spacing_l),
            dp(tok.spacing_xs),
        )

        btn_size = dp(_ICON_BTN_SIZE)

        self.plus_button = QtWidgets.QPushButton("+")
        self.plus_button.setFixedSize(btn_size, btn_size)
        self.plus_button.setStyleSheet(ui_styles.UIStyles.FLAT_ICON_BUTTON)

        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("Ask Gemini")
        self.input_field.setStyleSheet(ui_styles.UIStyles.TRANSPARENT_INPUT)

        self.model_dropdown = QtWidgets.QComboBox()
        self.model_dropdown.addItems(["Flash Extended", "Pro", "Ultra"])
        self.model_dropdown.setStyleSheet(ui_styles.UIStyles.MODEL_DROPDOWN)

        self.mic_button = QtWidgets.QPushButton("Mic")
        self.mic_button.setFixedSize(btn_size, btn_size)
        self.mic_button.setStyleSheet(ui_styles.UIStyles.FLAT_ICON_BUTTON)

        self.content_layout.addWidget(self.plus_button)
        self.content_layout.addWidget(self.input_field, 1)
        self.content_layout.addWidget(self.model_dropdown)
        self.content_layout.addWidget(self.mic_button)
