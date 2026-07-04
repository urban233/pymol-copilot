from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt import theme
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
