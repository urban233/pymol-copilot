from typing import TypeAlias

from pymol_copilot.gui.qt import QtCore, styles
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults

CommandBarButtonType: TypeAlias = QtCore.Qt.ToolButtonStyle

_OUTER_FRAME_STYLE = """
QFrame {
    border: 0.075em solid white;
    background: white;
    border-radius: 0.6em;
    padding: 0.2em;
}
"""

_COMMAND_BAR_STYLESHEET = """
QToolButton {
    font-size: 12px;
    background-color: white;
    border: none;
    border-radius: 0.375em;
    padding: 4px 6px;
}
QToolButton:hover {
    background: #f5f5f5;
}
"""

_SPLIT_BUTTON_MAIN_STYLESHEET = """
QToolButton {
    font-size: 12px;
    background: white;
    border: none;
    border-top-left-radius: 0.375em;
    border-bottom-left-radius: 0.375em;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 0px;
    padding: 4px 6px;
}
QToolButton:hover {
    background: #f5f5f5;
}
"""

_SPLIT_BUTTON_ARROW_STYLESHEET = """
QToolButton {
    font-size: 12px;
    background: white;
    border: none;
    border-left: 1px solid transparent;
    border-top-right-radius: 0.375em;
    border-bottom-right-radius: 0.375em;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    min-width: 14px;
    max-width: 14px;
    padding: 4px 3px;
}
QToolButton:hover {
    background: #f5f5f5;
}
QToolButton::menu-indicator {
    image: none;
}
"""

class CommandBarButtonStyle:
    """Namespace class for Qt ToolButton styles."""
    TEXT_BESIDE = QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    TEXT_UNDER = QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
    TEXT_ONLY = QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly
    ICON_ONLY = QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly


class CommandBarButton(QtWidgets.QWidget):
    """Abstract base class for all command bar button variants.

    Defines the shared constructor contract, the ``clicked`` signal, and the
    three-phase template-method protocol (``_init_widget``, ``_set_styles``,
    ``_connect_signals``) that every concrete subclass must implement.

    Subclasses must not call the template methods themselves; the base
    ``__init__`` invokes them in order after storing the constructor arguments
    in protected attributes.
    """

    clicked: QtCore.pyqtSignal = QtCore.pyqtSignal()

    def __init__(
            self,
            icon: QtGui.QIcon | None,
            text: str = "",
            style: CommandBarButtonType = CommandBarButtonStyle.TEXT_BESIDE,
            size: tuple[int, int] = ui_defaults.UISize.COMMAND_BAR_BUTTON_SIZE,
            parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._icon: QtGui.QIcon | None = icon
        self._text: str = text
        self._style: CommandBarButtonType = style
        self._size: tuple[int, int] = size
        self._init_widget()
        self._set_styles()
        self._connect_signals()

    def _init_widget(self) -> None:
        raise NotImplementedError

    def _set_styles(self) -> None:
        raise NotImplementedError

    def _connect_signals(self) -> None:
        raise NotImplementedError


class CommandBarActionButton(CommandBarButton):
    """A plain single-click command bar button.

    Renders an icon, optional text, or both (controlled by *style*).  Emits
    ``clicked`` when the button is pressed.  Visual hover styling is provided
    by the ancestor :class:`CommandBar` stylesheet cascade — no individual
    stylesheet is required.
    """

    def __init__(
            self,
            icon: QtGui.QIcon | None,
            text: str = "",
            style: CommandBarButtonType = CommandBarButtonStyle.ICON_ONLY,
            size: tuple[int, int] = ui_defaults.UISize.COMMAND_BAR_BUTTON_SIZE,
            parent: QtWidgets.QWidget | None = None
    ) -> None:
        self._button: QtWidgets.QToolButton = QtWidgets.QToolButton()
        super().__init__(icon, text, style, size, parent)

    def _init_widget(self) -> None:
        if self._icon is not None:
            self._button.setIcon(self._icon)
            self._button.setIconSize(QtCore.QSize(*self._size))
        if self._text:
            self._button.setText(self._text)
        self._button.setToolButtonStyle(self._style)

        tmp_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_layout.addWidget(self._button)

    def _set_styles(self) -> None:
        pass  # Inherits _COMMAND_BAR_STYLESHEET from the CommandBar ancestor.

    def _connect_signals(self) -> None:
        self._button.clicked.connect(self.clicked)


class CommandBarSplitButton(CommandBarButton):
    """A command bar button with independent hover states for each section.

    The left section (icon + optional text) acts as a plain push button and
    emits ``clicked`` when activated.  The right section renders a down-arrow
    chevron; attach a :class:`QMenu` via :meth:`set_menu` to make it open a
    dropdown.

    Both sections highlight independently on hover: moving the cursor over one
    section does not affect the visual state of the other.
    """

    def __init__(
            self,
            icon: QtGui.QIcon | None,
            text: str = "",
            style: CommandBarButtonType = CommandBarButtonStyle.TEXT_BESIDE,
            size: tuple[int, int] = ui_defaults.UISize.COMMAND_BAR_BUTTON_SIZE,
            parent: QtWidgets.QWidget | None = None
    ) -> None:
        self._hovered: bool = False
        self._main_button: QtWidgets.QToolButton = QtWidgets.QToolButton()
        self._arrow_button: QtWidgets.QToolButton = QtWidgets.QToolButton()
        super().__init__(icon, text, style, size, parent)

    def _init_widget(self) -> None:
        if self._icon is not None:
            self._main_button.setIcon(self._icon)
            self._main_button.setIconSize(QtCore.QSize(*self._size))
        if self._text:
            self._main_button.setText(self._text)
        self._main_button.setToolButtonStyle(self._style)

        self._arrow_button.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        self._arrow_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        )

        self._main_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._arrow_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        # Reserve 1 px on every edge permanently so children never paint over
        # the hover border drawn in paintEvent. Using a fixed margin avoids any
        # layout shift when the hover state changes.
        self.setContentsMargins(1, 1, 1, 1)

        self._main_button.installEventFilter(self)
        self._arrow_button.installEventFilter(self)

        tmp_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_layout.addWidget(self._main_button)
        tmp_layout.addWidget(self._arrow_button)

    def _set_styles(self) -> None:
        self._main_button.setStyleSheet(_SPLIT_BUTTON_MAIN_STYLESHEET)
        self._arrow_button.setStyleSheet(_SPLIT_BUTTON_ARROW_STYLESHEET)

    def _connect_signals(self) -> None:
        self._main_button.clicked.connect(self.clicked)

    def eventFilter(
            self,
            obj: QtCore.QObject | None,
            event: QtCore.QEvent | None,
    ) -> bool:
        if event is not None and obj in (self._main_button, self._arrow_button):
            t = event.type()
            if t == QtCore.QEvent.Type.Enter:
                self._hovered = True
                self.update()
            elif t == QtCore.QEvent.Type.Leave:
                if not self.rect().contains(
                    self.mapFromGlobal(QtGui.QCursor.pos())
                ):
                    self._hovered = False
                    self.update()
        return super().eventFilter(obj, event)

    def paintEvent(self, event: QtGui.QPaintEvent | None) -> None:
        super().paintEvent(event)
        if not self._hovered:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor("#c7c7c7"))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        # Centre the 1 px pen inside the reserved 1 px margin ring.
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = styles.dp(5)  # ≈ 0.375em at 12 px font / 96 DPI
        painter.drawRoundedRect(r, radius, radius)

    def set_menu(self, menu: QtWidgets.QMenu) -> None:
        """Attach a dropdown menu to the arrow section.

        Args:
            menu: The :class:`QMenu` to open when the arrow button is clicked.
        """
        self._arrow_button.setMenu(menu)
        self._arrow_button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )


class CommandBar(QtWidgets.QWidget):

    def __init__(self, command_buttons: list[CommandBarButton], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._outer_frame: QtWidgets.QFrame = QtWidgets.QFrame()
        self._layout_outer_frame: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        self._layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout()
        self._init_widget(command_buttons)
        self._set_styles()

    def _set_styles(self):
        self._outer_frame.setStyleSheet(_OUTER_FRAME_STYLE)
        tmp_shadow_effect = QtWidgets.QGraphicsDropShadowEffect()
        tmp_shadow_effect.setBlurRadius(20)
        tmp_shadow_effect.setOffset(3, 3)
        tmp_shadow_effect.setColor(QtGui.QColor(0, 0, 0, 30))
        self._outer_frame.setGraphicsEffect(tmp_shadow_effect)
        self.setStyleSheet(_COMMAND_BAR_STYLESHEET)

    def _init_widget(self, command_buttons: list[CommandBarButton]) -> None:
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        for button in command_buttons:
            self._layout.addWidget(button)
        self._layout.addStretch(1)
        self._outer_frame.setLayout(self._layout)
        self._layout_outer_frame.addWidget(self._outer_frame)
        self.setLayout(self._layout_outer_frame)
