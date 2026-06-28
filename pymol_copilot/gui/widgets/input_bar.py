"""Contains the InputBar class."""

from __future__ import annotations

import typing

from PyQt6 import QtWidgets

from pymol_copilot.gui.widgets import elevated_container
from pymol_copilot.gui.widgets import ui_styles

# ---------------------------------------------------------------------------
# InputBar sizing constants (all in density-independent pixels, 96 DPI base)
# ---------------------------------------------------------------------------
# 36 dp matches the standard desktop single-line toolbar height used by
# VS Code (35 px), Office ribbon inputs (32–36 px), and WinUI SearchBox.
# Mobile-first toolbars use 48 dp — avoid that on desktop.
_BAR_HEIGHT: int = 36

# Exact pill shape requires border_radius == height / 2.
# Because ElevatedContainer scales both values with dp() independently,
# we define them from the same constant so they stay in sync.
_BAR_RADIUS: int = _BAR_HEIGHT // 2  # 18 dp

# Icon buttons: 28 dp gives a comfortable click target on desktop
# (Fitts's Law minimum ≈ 24 dp; 28 dp matches Office / VS Code icon buttons).
# 24 dp is a mobile icon size and produces an undersized hit area on desktop.
_ICON_BTN_SIZE: int = 28


class InputBar(elevated_container.ElevatedContainer):
    """A widget for entering text input.

    Sizing rationale
    ----------------
    * Height **36 dp** — the standard desktop single-line control height
      (VS Code toolbar, Office search bar, WinUI SearchBox).  48 dp is
      the mobile convention and looks oversized on a productivity desktop app.
    * Border-radius **18 dp** (= height / 2) — produces a true pill / capsule
      shape without the radius exceeding the half-height, which would cause
      Qt to clip corners incorrectly.
    * Icon buttons **28 × 28 dp** — minimum comfortable click target on
      desktop; larger than the 24 dp mobile icon size.
    * Vertical content margins **4 dp** — small enough to keep the row
      compact inside the 36 dp frame while preventing text clipping on
      larger system fonts.
    * Horizontal content margins defer to the parent's 16 dp standard inset.
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
        )

    @typing.override
    def setup_ui(self) -> None:
        """Builds the input bar controls."""
        self.capsule_frame = self.container_frame

        # Override vertical margin only: reduce from parent's 8 dp to 4 dp so
        # the row stays compact inside the shorter 36 dp frame.  Horizontal
        # margin stays at the parent's 16 dp standard inset.
        # All values go through dp() so they scale correctly on HiDPI screens.
        dp = elevated_container.dp
        self.content_layout.setContentsMargins(dp(16), dp(4), dp(16), dp(4))

        # Icon buttons: 28 × 28 dp — desktop click-target minimum.
        # Do NOT use raw integers here; dp() is required for HiDPI correctness.
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
