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
    background: transparent;
    border: none;
    padding: 4px 6px;
}
QToolButton:hover, QToolButton:pressed, QToolButton:focus {
    background: transparent;
    outline: none;
}
"""

_SPLIT_BUTTON_ARROW_STYLESHEET = """
QToolButton {
    font-size: 12px;
    background: transparent;
    border: none;
    min-width: 14px;
    max-width: 14px;
    padding: 4px 3px;
}
QToolButton:hover, QToolButton:pressed, QToolButton:focus {
    background: transparent;
    outline: none;
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
            style: CommandBarButtonType = CommandBarButtonStyle.TEXT_ONLY,
            size: tuple[int, int] = ui_defaults.UISize.COMMAND_BAR_BUTTON_SIZE,
            parent: QtWidgets.QWidget | None = None
    ) -> None:
        self._main_hovered: bool = False
        self._arrow_hovered: bool = False
        self._main_pressed: bool = False
        self._arrow_pressed: bool = False
        self._menu_open: bool = False
        self._menu: QtWidgets.QMenu | None = None
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

        self._main_button.setAutoFillBackground(False)
        self._arrow_button.setAutoFillBackground(False)

        self._main_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._arrow_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.setMouseTracking(True)
        self._main_button.setMouseTracking(True)
        self._arrow_button.setMouseTracking(True)

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

    def _update_hover_from_parent_x(self, x: float) -> None:
        """Set hover flags based on x-coordinate in parent (self) space."""
        divider_x = float(self._arrow_button.geometry().left())
        new_main = x < divider_x
        new_arrow = x >= divider_x
        if new_main != self._main_hovered or new_arrow != self._arrow_hovered:
            self._main_hovered = new_main
            self._arrow_hovered = new_arrow
            self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent | None) -> None:
        """Handle mouse moves that land in the gap between child buttons."""
        if event is not None:
            self._update_hover_from_parent_x(event.position().x())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QtCore.QEvent | None) -> None:
        """Reset all interactive state when the cursor exits the widget."""
        if not self._menu_open:
            self._main_hovered = False
            self._arrow_hovered = False
            self._main_pressed = False
            self._arrow_pressed = False
            self.update()
        super().leaveEvent(event)

    def eventFilter(
            self,
            obj: QtCore.QObject | None,
            event: QtCore.QEvent | None,
    ) -> bool:
        if event is not None and obj in (self._main_button, self._arrow_button):
            t = event.type()
            if t == QtCore.QEvent.Type.MouseMove:
                parent_pos = obj.mapToParent(event.position().toPoint())
                self._update_hover_from_parent_x(float(parent_pos.x()))
            elif t == QtCore.QEvent.Type.MouseButtonPress:
                if obj is self._main_button:
                    self._main_pressed = True
                else:
                    self._arrow_pressed = True
                self.update()
            elif t == QtCore.QEvent.Type.MouseButtonRelease:
                if obj is self._main_button:
                    self._main_pressed = False
                else:
                    self._arrow_pressed = False
                # Deferred sync: Qt's mouse grab may have suppressed leaveEvent
                # during the hold, leaving pressed flags stuck if the cursor moved away.
                QtCore.QTimer.singleShot(0, self._sync_pressed_state)
        return super().eventFilter(obj, event)

    def _sync_pressed_state(self) -> None:
        """Clear pressed flags if the cursor left the widget during a mouse-grab."""
        if not (self._main_button.underMouse() or
                self._arrow_button.underMouse() or
                self.underMouse()):
            if self._main_pressed or self._arrow_pressed:
                self._main_pressed = False
                self._arrow_pressed = False
                self.update()

    def _on_menu_show(self) -> None:
        self._menu_open = True
        self.update()

    def _on_menu_hide(self) -> None:
        self._menu_open = False
        self._arrow_pressed = False
        self._arrow_hovered = False
        QtCore.QTimer.singleShot(0, self._sync_pressed_state)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent | None) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        radius = styles.dp(5)
        full = QtCore.QRectF(self.rect())
        divider_x = float(self._arrow_button.geometry().left())

        # 1. White base — establishes the rounded shape for the whole widget.
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("white")))
        painter.drawRoundedRect(full, radius, radius)

        # 2. Section highlights — clip to each half, then draw the same full
        #    rounded rect so corners are geometrically identical to the border.
        def _fill_section(clip: QtCore.QRectF, color: str) -> None:
            painter.setClipRect(clip)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(color)))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(full, radius, radius)
            painter.setClipping(False)

        main_clip = QtCore.QRectF(0, 0, divider_x, full.height())
        arrow_clip = QtCore.QRectF(divider_x, 0, full.width() - divider_x, full.height())

        if self._arrow_pressed or self._menu_open:
            _fill_section(main_clip, "#ebebeb")
            _fill_section(arrow_clip, "#ebebeb")
        else:
            if self._main_pressed:
                _fill_section(main_clip, "#e0e0e0")
            elif self._main_hovered:
                _fill_section(main_clip, "#f5f5f5")

            if self._arrow_hovered:
                _fill_section(arrow_clip, "#f5f5f5")

        any_active = (
            self._main_hovered or self._arrow_hovered
            or self._main_pressed or self._arrow_pressed
            or self._menu_open
        )

        # 3. Divider — only when hovering, not while arrow is pressed or menu is open.
        if (self._main_hovered or self._arrow_hovered) and not (self._arrow_pressed or self._menu_open):
            pen = QtGui.QPen(QtGui.QColor("#dcdcdc"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(
                QtCore.QPointF(divider_x - 0.5, 0.0),
                QtCore.QPointF(divider_x - 0.5, full.height()),
            )

        # 4. Outer border — same radius as base so pixels align exactly.
        if any_active:
            color = "#616161" if (self._arrow_pressed or self._menu_open) else "#c7c7c7"
            pen = QtGui.QPen(QtGui.QColor(color))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(full.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

    def _show_menu(self) -> None:
        """Open the menu aligned to the widget's bottom-left corner."""
        if self._menu is not None:
            pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
            self._menu.popup(pos)

    def set_menu(self, menu: QtWidgets.QMenu) -> None:
        """Attach a dropdown menu to the arrow section.

        Args:
            menu: The :class:`QMenu` to open when the arrow button is clicked.
        """
        self._menu = menu
        menu.aboutToShow.connect(self._on_menu_show)
        menu.aboutToHide.connect(self._on_menu_hide)
        self._arrow_button.clicked.connect(self._show_menu)


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
