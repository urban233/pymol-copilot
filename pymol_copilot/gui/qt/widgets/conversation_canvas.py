from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt.widgets import button
from pymol_copilot.gui.qt.widgets import input_bar


class BaseCard(QtWidgets.QWidget):
    """Abstract Base Card for the Component-Driven AI Agent Canvas.

    Implements the preferred structure: A base QWidget acting as the canvas
    item wrapper, containing an internal structural QFrame styled via the
    central design tokens.
    """

    def __init__(self, is_user: bool = False, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._outer_frame = QtWidgets.QFrame()
        self.content_layout = QtWidgets.QVBoxLayout(self._outer_frame)
        self._init_widget(is_user)

    def _init_widget(self, is_user) -> None:
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self._layout.setSpacing(ui_defaults.EMPTY_SPACING)
        self.content_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self.content_layout.setSpacing(ui_defaults.EMPTY_SPACING)

        if is_user:
            self._outer_frame.setObjectName(theme.StyleId.CUI_USER_CARD_SURFACE)
        else:
            self._outer_frame.setObjectName(theme.StyleId.CUI_CARD_SURFACE)
        self._layout.addWidget(self._outer_frame)

    # def transitionToHistoric(self) -> None:
    #     """Executes the State Flattening lifecycle routine.
    #
    #     Freezes user interactions, signals a state shift to the style engine,
    #     and leverages the schema's refresh utility to update the visual canvas.
    #     """
    #     if self._outer_frame.property("state") == "historic":
    #         return
    #
    #     # Step 1: Disable input mechanics inside the card layout container
    #     self._outer_frame.setEnabled(False)
    #
    #     # Step 2: Mutate the state property to target historic styling rules
    #     self._outer_frame.setProperty("state", "historic")
    #
    #     # Step 3: Use design system's style evaluation helper to force a repaint
    #     # theme.refresh_widget_style(self.outer_frame)


class UserRequestCard(BaseCard):
    """Card component representing the user's initial input or instruction."""

    def __init__(self, text: str, parent: QtWidgets.QWidget | None = None) -> None:
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
        """Dynamically updates the inner message text mapping."""
        self.text_label.setText(text)


class SpinnerWidget(QtWidgets.QWidget):
    """Lightweight rotating-arc spinner drawn entirely with QPainter."""

    def __init__(self, size: int = 16, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._size = size
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(size, size)

    def _tick(self) -> None:
        self._angle = (self._angle + 4) % 360
        self.update()

    def start(self) -> None:
        self._timer.start(16)

    def stop(self) -> None:
        self._timer.stop()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(theme.ThemeColors.ACCENT.to_hex()))
        pen.setWidthF(2.0)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        margin = pen.widthF() + 0.5
        rect = QtCore.QRectF(
            margin, margin,
            self._size - 2 * margin, self._size - 2 * margin,
        )
        # Qt arc angles are in 1/16°; arc starts from top (90°) and sweeps 270°
        painter.drawArc(rect, (90 - self._angle) * 16, 270 * 16)
        painter.end()


class AgentThinkingCard(BaseCard):
    """Card that signals the AI agent is currently processing."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(is_user=False, parent=parent)
        self._spinner = SpinnerWidget(size=theme.dp(16))
        self._label = QtWidgets.QLabel("Working\u2026")

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.dp(8))
        row.addWidget(self._spinner)
        row.addWidget(self._label)
        row.addStretch()

        self.content_layout.addLayout(row)
        self._spinner.start()

    def stop(self) -> None:
        """Halts the spinner animation when processing is complete."""
        self._spinner.stop()


class ToolApprovalCard(BaseCard):
    """Card that presents a proposed tool call for user review and approval.

    Displays the tool name, an intent description, and an editable parameter
    list. Emits ``approved`` with the (potentially user-edited) parameter
    values, or ``rejected`` when the user cancels.
    """

    approved = QtCore.pyqtSignal(dict)
    rejected = QtCore.pyqtSignal()

    def __init__(
        self,
        tool_name: str,
        description: str,
        parameters: dict[str, str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(is_user=False, parent=parent)
        self._parameters = parameters
        self._fields: dict[str, QtWidgets.QLineEdit] = {}

        # Card-level padding — spacing creates visual section breaks
        padding = theme.dp(12)
        self.content_layout.setContentsMargins(padding, padding, padding, padding)
        self.content_layout.setSpacing(theme.dp(8))

        # Header
        header_label = QtWidgets.QLabel(f"<b>\u2699 {tool_name}</b>")
        desc_label = QtWidgets.QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"color: {theme.ThemeColors.BORDER_ACTIVE.to_hex()}; "
            f"border: none; background: transparent;"
        )

        # Parameter rows — each in a white bordered sub-card
        params_container = QtWidgets.QWidget()
        params_layout = QtWidgets.QVBoxLayout(params_container)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(theme.dp(4))

        for key, value in parameters.items():
            row_frame = QtWidgets.QFrame()
            row_frame.setStyleSheet(
                f"QFrame {{ "
                f"background-color: {theme.ThemeColors.SURFACE.to_hex()}; "
                f"border: 1px solid {theme.ThemeColors.BORDER_COLOR.to_hex()}; "
                f"border-radius: {theme.dp(4)}px; }}"
            )
            row_layout = QtWidgets.QHBoxLayout(row_frame)
            row_layout.setContentsMargins(
                theme.dp(8), theme.dp(6), theme.dp(8), theme.dp(6)
            )
            row_layout.setSpacing(theme.dp(8))

            key_label = QtWidgets.QLabel(key)
            key_label.setFixedWidth(theme.dp(80))
            key_label.setStyleSheet(
                f"color: {theme.ThemeColors.BORDER_ACTIVE.to_hex()}; "
                f"border: none; background: transparent;"
            )
            field = QtWidgets.QLineEdit(value)
            field.setObjectName(theme.StyleId.MINIMAL_TEXT_BOX)

            row_layout.addWidget(key_label)
            row_layout.addWidget(field, 1)
            params_layout.addWidget(row_frame)
            self._fields[key] = field

        # Footer
        self._footer = QtWidgets.QWidget()
        footer_layout = QtWidgets.QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self._approve_btn = button.AccentButton("Approve")
        self._reject_btn = button.BasicButton("Reject")
        footer_layout.addWidget(self._approve_btn)
        footer_layout.addWidget(self._reject_btn)
        footer_layout.addStretch()

        # Status label shown after a decision is made
        self._status_label = QtWidgets.QLabel("")
        self._status_label.hide()

        # Assemble — spacing between sections comes from content_layout.setSpacing
        self.content_layout.addWidget(header_label)
        self.content_layout.addWidget(desc_label)
        self.content_layout.addWidget(params_container)
        self.content_layout.addWidget(self._footer)
        self.content_layout.addWidget(self._status_label)

        self._reject_btn.clicked.connect(self._on_reject)
        self._approve_btn.clicked.connect(self._on_approve)

    def _on_approve(self) -> None:
        data = {key: field.text() for key, field in self._fields.items()}
        self._finalize("\u2713 Approved")
        self.approved.emit(data)

    def _on_reject(self) -> None:
        self._finalize("\u2717 Rejected")
        self.rejected.emit()

    def _finalize(self, outcome: str) -> None:
        self._footer.hide()
        self._status_label.setText(outcome)
        self._status_label.show()
        self._outer_frame.setEnabled(False)


class PlanApprovalCard(BaseCard):
    """Card that presents a multi-step plan for review.

    Individual steps can be skipped before the overall plan is approved.
    Emits ``approved`` with the list of non-skipped step descriptions, or
    ``rejected`` when the user cancels the entire plan.
    """

    approved = QtCore.pyqtSignal(list)
    rejected = QtCore.pyqtSignal()

    def __init__(
        self,
        title: str,
        steps: list[str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(is_user=False, parent=parent)
        self._steps = steps
        self._skipped: set[int] = set()
        self._step_labels: list[QtWidgets.QLabel] = []
        self._step_buttons: list[button.BasicButton] = []

        # Card-level padding
        padding = theme.dp(12)
        self.content_layout.setContentsMargins(padding, padding, padding, padding)
        self.content_layout.setSpacing(theme.dp(8))

        # Header
        header_label = QtWidgets.QLabel(f"<b>\U0001f4cb {title}</b>")
        header_label.setWordWrap(True)

        # Step rows — each in a white bordered sub-card with a numbered badge
        steps_widget = QtWidgets.QWidget()
        steps_layout = QtWidgets.QVBoxLayout(steps_widget)
        steps_layout.setContentsMargins(0, 0, 0, 0)
        steps_layout.setSpacing(theme.dp(4))

        chip_size = theme.dp(22)
        chip_radius = theme.dp(11)

        for i, step in enumerate(steps):
            step_frame = QtWidgets.QFrame()
            step_frame.setStyleSheet(
                f"QFrame {{ "
                f"background-color: {theme.ThemeColors.SURFACE.to_hex()}; "
                f"border: 1px solid {theme.ThemeColors.BORDER_COLOR.to_hex()}; "
                f"border-radius: {theme.dp(4)}px; }}"
            )
            row_layout = QtWidgets.QHBoxLayout(step_frame)
            row_layout.setContentsMargins(
                theme.dp(8), theme.dp(8), theme.dp(8), theme.dp(8)
            )
            row_layout.setSpacing(theme.dp(8))

            # Accent-colored circle badge with step number
            num_chip = QtWidgets.QLabel(f"<b>{i + 1}</b>")
            num_chip.setFixedSize(chip_size, chip_size)
            num_chip.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            num_chip.setStyleSheet(
                f"background-color: {theme.ThemeColors.ACCENT.to_hex()}; "
                f"color: white; border-radius: {chip_radius}px; "
                f"border: none; font-size: {theme.dp(11)}px;"
            )

            step_label = QtWidgets.QLabel(step)
            step_label.setWordWrap(True)

            skip_btn = button.BasicButton("Skip")

            row_layout.addWidget(num_chip)
            row_layout.addWidget(step_label, 1)
            row_layout.addWidget(skip_btn)
            steps_layout.addWidget(step_frame)

            self._step_labels.append(step_label)
            self._step_buttons.append(skip_btn)
            skip_btn.clicked.connect(
                lambda _checked, idx=i: self._toggle_step(idx)
            )

        # Footer
        self._footer = QtWidgets.QWidget()
        footer_layout = QtWidgets.QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self._approve_btn = button.AccentButton("Approve Plan")
        self._reject_btn = button.BasicButton("Reject All")
        footer_layout.addWidget(self._approve_btn)
        footer_layout.addWidget(self._reject_btn)
        footer_layout.addStretch()

        # Status label shown after a decision is made
        self._status_label = QtWidgets.QLabel("")
        self._status_label.hide()

        # Assemble
        self.content_layout.addWidget(header_label)
        self.content_layout.addWidget(steps_widget)
        self.content_layout.addWidget(self._footer)
        self.content_layout.addWidget(self._status_label)

        self._reject_btn.clicked.connect(self._on_reject)
        self._approve_btn.clicked.connect(self._on_approve)

    def _toggle_step(self, index: int) -> None:
        """Toggle the skipped state of a single plan step."""
        if index in self._skipped:
            self._skipped.discard(index)
            self._step_labels[index].setText(self._steps[index])
            self._step_buttons[index].setText("Skip")
        else:
            self._skipped.add(index)
            self._step_labels[index].setText(f"<s>{self._steps[index]}</s>")
            self._step_buttons[index].setText("Restore")

    def _on_approve(self) -> None:
        accepted = [s for i, s in enumerate(self._steps) if i not in self._skipped]
        self._finalize(f"\u2713 Approved ({len(accepted)}/{len(self._steps)} steps)")
        self.approved.emit(accepted)

    def _on_reject(self) -> None:
        self._finalize("\u2717 Rejected")
        self.rejected.emit()

    def _finalize(self, outcome: str) -> None:
        self._footer.hide()
        for btn in self._step_buttons:
            btn.hide()
        self._status_label.setText(outcome)
        self._status_label.show()
        self._outer_frame.setEnabled(False)


class ConversationCanvas(QtWidgets.QScrollArea):
    """Canvas for displaying the component-driven conversation timeline."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self.container)
        self.bottom_spacer = QtWidgets.QSpacerItem(
            0, 0,
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding
        )
        self._init_widget()

    def _init_widget(self) -> None:
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container.setObjectName("CanvasContainer")
        self.container.setStyleSheet("#CanvasContainer { background: transparent;}")

        self._layout.setContentsMargins(*ui_defaults.default_contents_margins())
        self._layout.setSpacing(ui_defaults.default_spacing())
        self._layout.addItem(self.bottom_spacer)
        self.setWidget(self.container)

    def add_card(self, card: QtWidgets.QWidget) -> None:
        """Inserts a card into the stack timeline above the bottom spacer safety zone."""
        insert_index = max(0, self._layout.count() - 1)
        self._layout.insertWidget(insert_index, card)
