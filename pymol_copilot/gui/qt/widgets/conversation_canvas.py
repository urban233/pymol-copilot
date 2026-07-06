# cBioMOL - open C++ and Python platform for BioMOLecular visualization and
# analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban
# (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
# Source code is available at <https://github.com/urban233/cBioMOL>
# -------------------------------------------------------------------
# It is unlawful to modify or remove this copyright notice.
# -------------------------------------------------------------------
# Please see the accompanying LICENSE file for further information.
# -------------------------------------------------------------------
# Primary author of this source file:
# Martin Urban
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================
#
"""Canvas and card widgets for displaying the conversation timeline."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import icons
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.widgets import button
from pymol_copilot.gui.qt.widgets import spinner


class BaseCard(QtWidgets.QWidget):
    """Abstract Base Card for the Component-Driven AI Agent Canvas.

    Implements the preferred structure: A base QWidget acting as the canvas
    item wrapper, containing an internal structural QFrame styled via the
    central design tokens.
    """

    def __init__(
        self, is_user: bool = False, parent: QtWidgets.QWidget | None = None
    ) -> None:
        """Initialize the BaseCard.

        Args:
            is_user: Whether the card belongs to the user or the agent.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._outer_frame = QtWidgets.QFrame()
        self.content_layout = QtWidgets.QVBoxLayout(self._outer_frame)
        self._init_widget(is_user)

    def _init_widget(self, is_user: bool) -> None:
        """Initialize card child components and layout.

        Args:
            is_user: Whether this is a user card.
        """
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self._layout.setSpacing(ui_defaults.EMPTY_SPACING)
        self.content_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self.content_layout.setSpacing(ui_defaults.EMPTY_SPACING)

        if is_user:
            self._outer_frame.setObjectName(theme.StyleId.CUI_USER_CARD_SURFACE)
        else:
            self._outer_frame.setObjectName(theme.StyleId.CUI_CARD_SURFACE)
        self._layout.addWidget(self._outer_frame)


class UserRequestCard(BaseCard):
    """Card component representing the user's initial input or instruction."""

    def __init__(
        self, text: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        """Initialize the UserRequestCard.

        Args:
            text: The user's input request text.
            parent: Optional parent widget.
        """
        super().__init__(is_user=True, parent=parent)
        self.text_label = QtWidgets.QLabel(text)
        self.text_label.setWordWrap(True)
        # Use standard text interaction flags so users can copy their prompts
        self.text_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        # Configure layout padding matching your office design criteria
        self.content_layout.addWidget(self.text_label)

    def set_text(self, text: str) -> None:
        """Dynamically updates the inner message text mapping.

        Args:
            text: The new message text.
        """
        self.text_label.setText(text)


class AgentThinkingCard(BaseCard):
    """Card that signals the AI agent is currently processing."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the AgentThinkingCard.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(is_user=False, parent=parent)
        self._spinner = spinner.SpinnerWidget(size=theme.dp(16))
        self._label = QtWidgets.QLabel("Working\u2026")

        tmp_row = QtWidgets.QHBoxLayout()
        tmp_row.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_row.setSpacing(theme.dp(8))
        tmp_row.addWidget(self._spinner)
        tmp_row.addWidget(self._label)
        tmp_row.addStretch()

        self.content_layout.addLayout(tmp_row)
        self._spinner.start()

    def stop(self) -> None:
        """Halts the spinner animation when processing is complete."""
        self._spinner.stop()


class AgentCancelledCard(BaseCard):
    """Card shown when the user cancels an in-progress generation."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the AgentCancelledCard.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(is_user=False, parent=parent)
        self._spinner = spinner.SpinnerWidget(
            size=theme.dp(16), color="#dc4352"
        )
        self._label = QtWidgets.QLabel("Cancelled")

        tmp_row = QtWidgets.QHBoxLayout()
        tmp_row.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_row.setSpacing(theme.dp(8))
        tmp_row.addWidget(self._spinner)
        tmp_row.addWidget(self._label)
        tmp_row.addStretch()

        self.content_layout.addLayout(tmp_row)
        self._spinner.start()

    def stop(self) -> None:
        """Halts the spinner animation."""
        self._spinner.stop()


class ToolApprovalCard(BaseCard):
    """Card that presents a proposed tool call for user review and approval.

    Displays the tool name, an intent description, and an editable parameter
    list. Emits ``approved`` with the (potentially user-edited) parameter
    values, or ``rejected`` when the user cancels.
    """

    approved: QtCore.pyqtSignal = QtCore.pyqtSignal(dict)
    rejected: QtCore.pyqtSignal = QtCore.pyqtSignal()

    def __init__(
        self,
        tool_name: str,
        description: str,
        parameters: dict[str, str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the ToolApprovalCard.

        Args:
            tool_name: The name of the tool to be executed.
            description: Description of the tool's purpose.
            parameters: Dictionary of tool parameters.
            parent: Optional parent widget.
        """
        super().__init__(is_user=False, parent=parent)
        self._parameters = parameters
        self._fields: dict[str, QtWidgets.QLineEdit] = {}

        # Card-level padding — spacing creates visual section breaks
        self.content_layout.setContentsMargins(
            *ui_defaults.default_contents_margins()
        )
        self.content_layout.setSpacing(theme.dp(8))

        # Header row: optional icon + bold title
        tmp_header_row = QtWidgets.QHBoxLayout()
        tmp_header_row.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_header_row.setSpacing(theme.dp(6))

        tmp_icon = icons.icon("pymol_copilot.gui.qt", "checklist")
        tmp_icon_size = theme.dp(16)
        tmp_icon_label = QtWidgets.QLabel()
        tmp_icon_label.setPixmap(
            tmp_icon.pixmap(QtCore.QSize(tmp_icon_size, tmp_icon_size))
        )
        tmp_icon_label.setFixedSize(tmp_icon_size, tmp_icon_size)
        tmp_header_row.addWidget(tmp_icon_label)
        tmp_header_row.addWidget(QtWidgets.QLabel(f"<b>{tool_name}</b>"))
        tmp_header_row.addStretch()

        tmp_desc_label = QtWidgets.QLabel(description)
        tmp_desc_label.setWordWrap(True)
        tmp_desc_label.setStyleSheet(
            f"color: {theme.ThemeColors.BORDER_ACTIVE.to_hex()}; "
            f"border: none; background: transparent;"
        )

        # Parameter rows — each in a white bordered sub-card
        tmp_params_container = QtWidgets.QWidget()
        tmp_params_layout = QtWidgets.QVBoxLayout(tmp_params_container)
        tmp_params_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        tmp_params_layout.setSpacing(theme.dp(4))

        for tmp_key, tmp_value in parameters.items():
            tmp_row_frame = QtWidgets.QFrame()
            tmp_row_frame.setStyleSheet(
                f"QFrame {{ "
                f"background-color: {theme.ThemeColors.SURFACE.to_hex()}; "
                f"border: 1px solid {theme.ThemeColors.BORDER_COLOR.to_hex()}; "
                f"border-radius: {theme.dp(4)}px; }}"
            )
            tmp_row_layout = QtWidgets.QHBoxLayout(tmp_row_frame)
            tmp_row_layout.setContentsMargins(
                theme.dp(8), theme.dp(6), theme.dp(8), theme.dp(6)
            )
            tmp_row_layout.setSpacing(theme.dp(8))

            tmp_key_label = QtWidgets.QLabel(tmp_key)
            tmp_key_label.setFixedWidth(theme.dp(80))
            tmp_key_label.setStyleSheet(
                f"color: {theme.ThemeColors.BORDER_ACTIVE.to_hex()}; "
                f"border: none; background: transparent;"
            )
            tmp_field = QtWidgets.QLineEdit(tmp_value)
            tmp_field.setObjectName(theme.StyleId.MINIMAL_TEXT_BOX)

            tmp_row_layout.addWidget(tmp_key_label)
            tmp_row_layout.addWidget(tmp_field, 1)
            tmp_params_layout.addWidget(tmp_row_frame)
            self._fields[tmp_key] = tmp_field

        # Footer
        self._footer = QtWidgets.QWidget()
        tmp_footer_layout = QtWidgets.QHBoxLayout(self._footer)
        tmp_footer_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._approve_btn = button.AccentButton("Approve")
        self._reject_btn = button.BasicButton("Reject")
        tmp_footer_layout.addWidget(self._approve_btn)
        tmp_footer_layout.addWidget(self._reject_btn)
        tmp_footer_layout.addStretch()

        # Status row shown after a decision is made
        self._status_widget = QtWidgets.QWidget()
        self._status_widget.hide()
        tmp_status_layout = QtWidgets.QHBoxLayout(self._status_widget)
        tmp_status_layout.setContentsMargins(0, 0, 0, 0)
        tmp_status_layout.setSpacing(theme.dp(6))
        self._status_icon_label = QtWidgets.QLabel()
        self._status_icon_label.setFixedSize(theme.dp(16), theme.dp(16))
        self._status_text_label = QtWidgets.QLabel()
        tmp_status_layout.addWidget(self._status_icon_label)
        tmp_status_layout.addWidget(self._status_text_label)
        tmp_status_layout.addStretch()

        # Assemble — spacing comes from content_layout's spacing setting
        self.content_layout.addLayout(tmp_header_row)
        self.content_layout.addWidget(tmp_desc_label)
        self.content_layout.addWidget(tmp_params_container)
        self.content_layout.addWidget(self._footer)
        self.content_layout.addWidget(self._status_widget)

        self._reject_btn.clicked.connect(self._on_reject)
        self._approve_btn.clicked.connect(self._on_approve)

    def _on_approve(self) -> None:
        """Handle plan/tool approval action."""
        tmp_data = {
            tmp_key: tmp_field.text()
            for tmp_key, tmp_field in self._fields.items()
        }
        self._finalize(
            icons.icon("pymol_copilot.gui.qt", "check_circle_green"), "Approved"
        )
        self.approved.emit(tmp_data)

    def _on_reject(self) -> None:
        """Handle tool rejection action."""
        self._finalize(
            icons.icon("pymol_copilot.gui.qt", "error_red"), "Rejected"
        )
        self.rejected.emit()

    def _finalize(self, outcome_icon: QtGui.QIcon, outcome_text: str) -> None:
        """Finalize card state after decision.

        Args:
            outcome_icon: Icon indicating approval/rejection.
            outcome_text: Label text indicating outcome.
        """
        self._footer.hide()
        self._status_icon_label.setPixmap(
            outcome_icon.pixmap(QtCore.QSize(theme.dp(16), theme.dp(16)))
        )
        self._status_text_label.setText(outcome_text)
        self._status_widget.show()
        self._outer_frame.setEnabled(False)


class PlanApprovalCard(BaseCard):
    """Card that presents a multi-step plan for review.

    Individual steps can be skipped before the overall plan is approved.
    Emits ``approved`` with the list of non-skipped step descriptions, or
    ``rejected`` when the user cancels the entire plan.
    """

    approved: QtCore.pyqtSignal = QtCore.pyqtSignal(list)
    rejected: QtCore.pyqtSignal = QtCore.pyqtSignal()

    def __init__(
        self,
        title: str,
        steps: list[str],
        icon: QtGui.QIcon | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the PlanApprovalCard.

        Args:
            title: Title of the plan.
            steps: List of step descriptions.
            icon: Optional custom icon.
            parent: Optional parent widget.
        """
        super().__init__(is_user=False, parent=parent)
        self._steps = steps
        self._skipped: set[int] = set()
        self._step_labels: list[QtWidgets.QLabel] = []
        self._step_buttons: list[button.BasicButton] = []

        self.content_layout.setContentsMargins(
            *ui_defaults.default_contents_margins()
        )
        self.content_layout.setSpacing(theme.dp(8))

        # Header row: optional icon + bold title
        tmp_header_row = QtWidgets.QHBoxLayout()
        tmp_header_row.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_header_row.setSpacing(theme.dp(6))

        tmp_icon = (
            icon
            if icon is not None
            else icons.icon("pymol_copilot.gui.qt", "checklist")
        )
        tmp_icon_size = theme.dp(16)
        tmp_icon_label = QtWidgets.QLabel()
        tmp_icon_label.setPixmap(
            tmp_icon.pixmap(QtCore.QSize(tmp_icon_size, tmp_icon_size))
        )
        tmp_icon_label.setFixedSize(tmp_icon_size, tmp_icon_size)
        tmp_header_row.addWidget(tmp_icon_label)
        tmp_title_label = QtWidgets.QLabel(f"<b>{title}</b>")
        tmp_title_label.setWordWrap(True)
        tmp_header_row.addWidget(tmp_title_label, 1)

        # Step rows — each in a white bordered sub-card with a numbered badge
        tmp_steps_widget = QtWidgets.QWidget()
        tmp_steps_layout = QtWidgets.QVBoxLayout(tmp_steps_widget)
        tmp_steps_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_steps_layout.setSpacing(theme.dp(4))

        tmp_chip_size = theme.dp(22)
        tmp_chip_radius = theme.dp(11)

        for tmp_i, tmp_step in enumerate(steps):
            tmp_row_layout = QtWidgets.QHBoxLayout()
            tmp_row_layout.setContentsMargins(
                theme.dp(8), theme.dp(8), theme.dp(8), theme.dp(8)
            )
            tmp_row_layout.setSpacing(theme.dp(8))

            # Accent-colored circle badge with step number
            tmp_num_chip = QtWidgets.QLabel(f"<b>{tmp_i + 1}</b>")
            tmp_num_chip.setFixedSize(tmp_chip_size, tmp_chip_size)
            tmp_num_chip.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            tmp_num_chip.setStyleSheet(
                f"background-color: {theme.ThemeColors.ACCENT.to_hex()}; "
                f"color: white; border-radius: {tmp_chip_radius}px; "
                f"border: none; font-size: {theme.dp(11)}px;"
            )

            tmp_step_label = QtWidgets.QLabel(tmp_step)
            tmp_step_label.setWordWrap(True)

            tmp_skip_btn = button.BasicButton("Skip")

            tmp_row_layout.addWidget(tmp_num_chip)
            tmp_row_layout.addWidget(tmp_step_label, 1)
            tmp_row_layout.addWidget(tmp_skip_btn)
            tmp_steps_layout.addLayout(tmp_row_layout)

            self._step_labels.append(tmp_step_label)
            self._step_buttons.append(tmp_skip_btn)
            tmp_skip_btn.clicked.connect(
                lambda _checked, idx=tmp_i: self._toggle_step(idx)
            )

        # Footer
        self._footer = QtWidgets.QWidget()
        tmp_footer_layout = QtWidgets.QHBoxLayout(self._footer)
        tmp_footer_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._approve_btn = button.AccentButton("Approve Plan")
        self._reject_btn = button.BasicButton("Reject All")
        tmp_footer_layout.addWidget(self._approve_btn)
        tmp_footer_layout.addWidget(self._reject_btn)
        tmp_footer_layout.addStretch()

        # Status row shown after a decision is made
        self._status_widget = QtWidgets.QWidget()
        self._status_widget.hide()
        tmp_status_layout = QtWidgets.QHBoxLayout(self._status_widget)
        tmp_status_layout.setContentsMargins(0, 0, 0, 0)
        tmp_status_layout.setSpacing(theme.dp(6))
        self._status_icon_label = QtWidgets.QLabel()
        self._status_icon_label.setFixedSize(theme.dp(16), theme.dp(16))
        self._status_text_label = QtWidgets.QLabel()
        tmp_status_layout.addWidget(self._status_icon_label)
        tmp_status_layout.addWidget(self._status_text_label)
        tmp_status_layout.addStretch()

        # Assemble
        self.content_layout.addLayout(tmp_header_row)
        self.content_layout.addWidget(tmp_steps_widget)
        self.content_layout.addWidget(self._footer)
        self.content_layout.addWidget(self._status_widget)

        self._reject_btn.clicked.connect(self._on_reject)
        self._approve_btn.clicked.connect(self._on_approve)

    def _toggle_step(self, index: int) -> None:
        """Toggle the skipped state of a single plan step.

        Args:
            index: The step index to toggle.
        """
        if index in self._skipped:
            self._skipped.discard(index)
            self._step_labels[index].setText(self._steps[index])
            self._step_buttons[index].setText("Skip")
        else:
            self._skipped.add(index)
            self._step_labels[index].setText(f"<s>{self._steps[index]}</s>")
            self._step_buttons[index].setText("Restore")

    def _on_approve(self) -> None:
        """Handle plan approval action."""
        tmp_accepted = [
            s for i, s in enumerate(self._steps) if i not in self._skipped
        ]
        self._finalize(
            icons.icon("pymol_copilot.gui.qt", "check_circle_green"),
            f"Approved ({len(tmp_accepted)}/{len(self._steps)} steps)",
        )
        self.approved.emit(tmp_accepted)

    def _on_reject(self) -> None:
        """Handle plan rejection action."""
        self._finalize(
            icons.icon("pymol_copilot.gui.qt", "error_red"), "Rejected"
        )
        self.rejected.emit()

    def _finalize(self, outcome_icon: QtGui.QIcon, outcome_text: str) -> None:
        """Finalize card state after decision.

        Args:
            outcome_icon: Icon indicating approval/rejection.
            outcome_text: Label text indicating outcome.
        """
        self._footer.hide()
        for tmp_btn in self._step_buttons:
            tmp_btn.hide()
        self._status_icon_label.setPixmap(
            outcome_icon.pixmap(QtCore.QSize(theme.dp(16), theme.dp(16)))
        )
        self._status_text_label.setText(outcome_text)
        self._status_widget.show()
        self._outer_frame.setEnabled(False)


class ConversationCanvas(QtWidgets.QScrollArea):
    """Canvas for displaying the component-driven conversation timeline."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the ConversationCanvas.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self.container)
        self.bottom_spacer = QtWidgets.QSpacerItem(
            0,
            0,
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._init_widget()

    def _init_widget(self) -> None:
        """Initialize the scroll container and layout settings."""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.setStyleSheet("QScrollArea { border: none; }")
        self.container.setObjectName("CanvasContainer")
        self.container.setStyleSheet(
            "#CanvasContainer { background: transparent;}"
        )

        self._layout.setContentsMargins(*ui_defaults.default_contents_margins())
        self._layout.setSpacing(theme.dp(8))
        self._layout.addItem(self.bottom_spacer)
        self.setWidget(self.container)

    def add_card(self, card: QtWidgets.QWidget) -> None:
        """Inserts a card into the stack timeline.

        Args:
            card: The QWidget card component to append.
        """
        tmp_insert_index = max(0, self._layout.count() - 1)
        self._layout.insertWidget(tmp_insert_index, card)


class CompletedCard(BaseCard):
    """Card shown after successful plan execution.

    Supports A/B toggle and rollback.
    """

    rollback_requested: QtCore.pyqtSignal = QtCore.pyqtSignal()
    ai_toggle_changed: QtCore.pyqtSignal = QtCore.pyqtSignal(bool)
    accepted: QtCore.pyqtSignal = QtCore.pyqtSignal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the CompletedCard.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(is_user=False, parent=parent)

        self.content_layout.setContentsMargins(
            *ui_defaults.default_contents_margins()
        )
        self.content_layout.setSpacing(theme.dp(8))

        # Header row: checklist icon + bold title
        tmp_header_row = QtWidgets.QHBoxLayout()
        tmp_header_row.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_header_row.setSpacing(theme.dp(6))

        tmp_icon = icons.icon("pymol_copilot.gui.qt", "check_circle_green")
        tmp_icon_size = theme.dp(16)
        tmp_icon_label = QtWidgets.QLabel()
        tmp_icon_label.setPixmap(
            tmp_icon.pixmap(QtCore.QSize(tmp_icon_size, tmp_icon_size))
        )
        tmp_icon_label.setFixedSize(tmp_icon_size, tmp_icon_size)
        tmp_header_row.addWidget(tmp_icon_label)

        self.title_label = QtWidgets.QLabel("<b>Execution Completed</b>")
        self.title_label.setWordWrap(True)
        tmp_header_row.addWidget(self.title_label, 1)

        # AI toggle button (single checkable button labeled "AI")
        self._ai_toggle_btn = button.ToggleButton("AI")
        self._ai_toggle_btn.setFixedWidth(theme.dp(60))
        tmp_header_row.addWidget(self._ai_toggle_btn)

        # Footer
        self._footer = QtWidgets.QWidget()
        tmp_footer_layout = QtWidgets.QHBoxLayout(self._footer)
        tmp_footer_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._accept_btn = button.AccentButton("Accept")
        self._rollback_btn = button.BasicButton("Rollback")
        tmp_footer_layout.addWidget(self._accept_btn)
        tmp_footer_layout.addWidget(self._rollback_btn)
        tmp_footer_layout.addStretch()

        # Status row shown after finalized or rolled back
        self._status_widget = QtWidgets.QWidget()
        self._status_widget.hide()
        tmp_status_layout = QtWidgets.QHBoxLayout(self._status_widget)
        tmp_status_layout.setContentsMargins(0, 0, 0, 0)
        tmp_status_layout.setSpacing(theme.dp(6))
        self._status_icon_label = QtWidgets.QLabel()
        self._status_icon_label.setFixedSize(theme.dp(16), theme.dp(16))
        self._status_text_label = QtWidgets.QLabel()
        tmp_status_layout.addWidget(self._status_icon_label)
        tmp_status_layout.addWidget(self._status_text_label)
        tmp_status_layout.addStretch()

        self.content_layout.addLayout(tmp_header_row)
        self.content_layout.addWidget(self._footer)
        self.content_layout.addWidget(self._status_widget)

        self._ai_toggle_btn.toggled.connect(self.ai_toggle_changed.emit)
        self._rollback_btn.clicked.connect(self.rollback_requested.emit)
        self._accept_btn.clicked.connect(self.accepted.emit)

    def show_rolled_back(self) -> None:
        """Freeze card state as Rolled Back."""
        self._finalize(
            icons.icon("pymol_copilot.gui.qt", "error_red"), "Rolled Back"
        )

    def show_accepted(self) -> None:
        """Freeze card state as Finalized."""
        self._finalize(
            icons.icon("pymol_copilot.gui.qt", "check_circle_green"),
            "Finalized",
        )

    def _finalize(self, outcome_icon: QtGui.QIcon, outcome_text: str) -> None:
        """Helper to lock the UI and show static status.

        Args:
            outcome_icon: The icon showing the outcome status.
            outcome_text: The label text describing the outcome.
        """
        self._footer.hide()
        self._ai_toggle_btn.setEnabled(False)
        self._status_icon_label.setPixmap(
            outcome_icon.pixmap(QtCore.QSize(theme.dp(16), theme.dp(16)))
        )
        self._status_text_label.setText(outcome_text)
        self._status_widget.show()
        self._outer_frame.setEnabled(False)
