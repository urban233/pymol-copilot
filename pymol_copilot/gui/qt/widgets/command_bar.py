from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from pymol_copilot.gui.qt import QtCore, styles
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults

if TYPE_CHECKING:
    from pymol_copilot.gui.qt.widgets.flyout import FlyoutFrame, FlyoutPlacement

CommandBarButtonType: TypeAlias = QtCore.Qt.ToolButtonStyle

_OUTER_FRAME_TEMPLATE = """
QFrame {
    border: ${border_width} solid ${surface};
    background: ${surface};
    border-radius: ${corner_radius};
    padding: ${padding_frame};
}
"""

_COMMAND_BAR_TEMPLATE = """
QToolButton {
    font-size: ${font_size_base};
    background-color: ${surface};
    border: none;
    border-radius: ${corner_radius_button};
    padding: ${padding_small} ${padding_button_h};
}
QToolButton:hover {
    background: ${hover};
}
"""

_SPLIT_BUTTON_MAIN_TEMPLATE = """
QToolButton {
    font-size: ${font_size_base};
    background: transparent;
    border: none;
    padding: ${padding_small} ${padding_button_h};
}
QToolButton:hover, QToolButton:pressed, QToolButton:focus {
    background: transparent;
    outline: none;
}
"""

_SPLIT_BUTTON_ARROW_TEMPLATE = """
QToolButton {
    font-size: ${font_size_base};
    background: transparent;
    border: none;
    min-width: ${arrow_button_width};
    max-width: ${arrow_button_width};
    padding: ${padding_small} ${padding_xsmall};
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
        parent: QtWidgets.QWidget | None = None,
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
        parent: QtWidgets.QWidget | None = None,
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
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        self._main_hovered: bool = False
        self._arrow_hovered: bool = False
        self._main_pressed: bool = False
        self._arrow_pressed: bool = False
        self._menu_open: bool = False
        self._menu: QtWidgets.QMenu | None = None
        self._flyout: FlyoutFrame | None = None
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
        self._main_button.setStyleSheet(
            theme.compile_stylesheet(_SPLIT_BUTTON_MAIN_TEMPLATE)
        )
        self._arrow_button.setStyleSheet(
            theme.compile_stylesheet(_SPLIT_BUTTON_ARROW_TEMPLATE)
        )

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
        if not (
            self._main_button.underMouse()
            or self._arrow_button.underMouse()
            or self.underMouse()
        ):
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

        radius = theme.ThemeMetrics.CORNER_RADIUS_BUTTON.px
        full = QtCore.QRectF(self.rect())
        divider_x = float(self._arrow_button.geometry().left())

        # 1. Surface base — establishes the rounded shape for the whole widget.
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(
            QtGui.QBrush(theme.ThemeColors.SURFACE.to_qcolor())
        )
        painter.drawRoundedRect(full, radius, radius)

        # 2. Section highlights — clip to each half, then draw the same full
        #    rounded rect so corners are geometrically identical to the border.
        def _fill_section(clip: QtCore.QRectF, color: QtGui.QColor) -> None:
            painter.setClipRect(clip)
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(full, radius, radius)
            painter.setClipping(False)

        main_clip = QtCore.QRectF(0, 0, divider_x, full.height())
        arrow_clip = QtCore.QRectF(
            divider_x, 0, full.width() - divider_x, full.height()
        )

        if self._arrow_pressed or self._menu_open:
            _fill_section(main_clip, theme.ThemeColors.PRESSED_SHARED.to_qcolor())
            _fill_section(arrow_clip, theme.ThemeColors.PRESSED_SHARED.to_qcolor())
        else:
            if self._main_pressed:
                _fill_section(main_clip, theme.ThemeColors.PRESSED.to_qcolor())
            elif self._main_hovered:
                _fill_section(main_clip, theme.ThemeColors.HOVER.to_qcolor())

            if self._arrow_hovered:
                _fill_section(arrow_clip, theme.ThemeColors.HOVER.to_qcolor())

        any_active = (
            self._main_hovered
            or self._arrow_hovered
            or self._main_pressed
            or self._arrow_pressed
            or self._menu_open
        )

        # 3. Divider — only when hovering, not while arrow is pressed or menu is open.
        if (self._main_hovered or self._arrow_hovered) and not (
            self._arrow_pressed or self._menu_open
        ):
            pen = QtGui.QPen(theme.ThemeColors.DIVIDER.to_qcolor())
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(
                QtCore.QPointF(divider_x - 0.5, 0.0),
                QtCore.QPointF(divider_x - 0.5, full.height()),
            )

        # 4. Outer border — same radius as base so pixels align exactly.
        if any_active:
            border_color = (
                theme.ThemeColors.BORDER_ACTIVE.to_qcolor()
                if (self._arrow_pressed or self._menu_open)
                else theme.ThemeColors.BORDER_HOVER.to_qcolor()
            )
            pen = QtGui.QPen(border_color)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                full.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius
            )

    def _show_menu(self) -> None:
        """Open the menu aligned to the widget's bottom-left corner."""
        if self._menu is not None:
            pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
            self._menu.popup(pos)

    def set_flyout(self, flyout: FlyoutFrame) -> None:
        """Attach a :class:`~pymol_copilot.gui.qt.widgets.flyout.FlyoutFrame`
        to the arrow section.

        Works as an alternative to :meth:`set_menu`: clicking the arrow opens
        the flyout below the button and drives the same ``_menu_open`` paint
        state so the button renders correctly while the flyout is visible.

        Args:
            flyout: The flyout panel to open when the arrow is clicked.
        """
        from pymol_copilot.gui.qt.widgets.flyout import FlyoutPlacement

        self._flyout = flyout
        flyout.about_to_show.connect(self._on_menu_show)
        flyout.about_to_hide.connect(self._on_menu_hide)
        self._arrow_button.clicked.connect(self._show_flyout)

    def _show_flyout(self) -> None:
        """Open the flyout anchored below the button."""
        from pymol_copilot.gui.qt.widgets.flyout import FlyoutPlacement

        if self._flyout is not None:
            self._flyout.show_for(self, FlyoutPlacement.BELOW)

    def set_menu(self, menu: QtWidgets.QMenu) -> None:
        """Attach a dropdown menu to the arrow section.

        Args:
            menu: The :class:`QMenu` to open when the arrow button is clicked.
        """
        self._menu = menu
        menu.aboutToShow.connect(self._on_menu_show)
        menu.aboutToHide.connect(self._on_menu_hide)
        self._arrow_button.clicked.connect(self._show_menu)


class CommandBarDropdownButton(CommandBarButton):
    """A unified dropdown button — single click area, menu or flyout on click.

    Unlike :class:`CommandBarSplitButton`, there is no separate arrow
    section: the entire button is the clickable area.  A down-arrow
    indicator is rendered via QSS in the padding reserved beside (or
    below) the icon/text content.  The indicator position adapts
    automatically to the configured :class:`CommandBarButtonStyle`:

    * ``ICON_ONLY``, ``TEXT_BESIDE``, ``TEXT_ONLY`` — arrow to the right.
    * ``TEXT_UNDER`` — arrow below the text.

    .. warning::
        The inherited ``clicked`` signal is **never emitted**.
        ``QToolButton.ToolButtonPopupMode.InstantPopup`` consumes the
        click internally to open the attached menu.  React to user
        interaction via ``QMenu.triggered`` or the flyout's
        ``about_to_show`` / ``about_to_hide`` signals instead.

    .. note::
        Calling both :meth:`set_menu` and :meth:`set_flyout` on the same
        instance is not supported.  The second call overwrites the menu
        attached via ``setMenu()``.
    """

    def __init__(
        self,
        icon: QtGui.QIcon | None,
        text: str = "",
        style: CommandBarButtonType = CommandBarButtonStyle.TEXT_BESIDE,
        size: tuple[int, int] = ui_defaults.UISize.COMMAND_BAR_BUTTON_SIZE,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialise the dropdown button.

        Args:
            icon: Icon displayed on the button, or ``None`` for text-only.
            text: Label text; may be empty for icon-only mode.
            style: Controls icon/text arrangement and arrow placement.
            size: Icon size in physical pixels as ``(width, height)``.
            parent: Optional parent widget.
        """
        self._button: QtWidgets.QToolButton = QtWidgets.QToolButton()
        self._menu: QtWidgets.QMenu | None = None
        self._flyout: FlyoutFrame | None = None
        super().__init__(icon, text, style, size, parent)

    def _init_widget(self) -> None:
        """Set up the internal QToolButton and wrap it in a layout."""
        if self._icon is not None:
            self._button.setIcon(self._icon)
            self._button.setIconSize(QtCore.QSize(*self._size))
        if self._text:
            self._button.setText(self._text)
        self._button.setToolButtonStyle(self._style)
        self._button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self._button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        tmp_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_layout.addWidget(self._button)

    def _set_styles(self) -> None:
        """Apply the style-adaptive QSS stylesheet."""
        self._button.setStyleSheet(self._build_stylesheet())

    def _build_stylesheet(self) -> str:
        """Build the QSS stylesheet adapted to the current button style.

        Reserves extra padding (right or bottom) so the
        ``::menu-indicator`` subcontrol never overlaps the icon or text,
        then positions the indicator inside that gap.

        Returns:
            A complete QSS string ready for
            :meth:`~PyQt6.QtWidgets.QWidget.setStyleSheet`.
        """
        tmp_text_under = (
            self._style == QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        )
        if tmp_text_under:
            tmp_extra_padding = "padding-bottom: 14px;"
            tmp_indicator_pos = "bottom center"
            tmp_indicator_offset = "bottom: 2px;"
        else:
            tmp_extra_padding = "padding-right: 14px;"
            tmp_indicator_pos = "right center"
            tmp_indicator_offset = "right: 2px;"
        font_sz = theme.ThemeMetrics.FONT_SIZE_BASE.to_qss()
        surface = theme.ThemeColors.SURFACE.to_hex()
        radius = theme.ThemeMetrics.CORNER_RADIUS_BUTTON.to_qss()
        pad_v = theme.ThemeMetrics.PADDING_SMALL.to_qss()
        pad_h = theme.ThemeMetrics.PADDING_BUTTON_H.to_qss()
        hover = theme.ThemeColors.HOVER.to_hex()
        return (
            f"QToolButton {{"
            f" font-size: {font_sz};"
            f" background-color: {surface};"
            f" border: none;"
            f" border-radius: {radius};"
            f" padding: {pad_v} {pad_h}; {tmp_extra_padding}"
            f"}}"
            f"QToolButton:hover {{ background: {hover}; }}"
            f"QToolButton::menu-indicator {{"
            f" subcontrol-origin: padding;"
            f" subcontrol-position: {tmp_indicator_pos};"
            f" width: 8px;"
            f" height: 8px;"
            f" {tmp_indicator_offset}"
            f"}}"
        )

    def _connect_signals(self) -> None:
        pass  # InstantPopup handles menu/flyout; clicked is not emitted.

    def set_menu(self, menu: QtWidgets.QMenu) -> None:
        """Attach a dropdown menu; clicking the button opens it instantly.

        Args:
            menu: The :class:`QMenu` to open when the button is clicked.
        """
        self._menu = menu
        self._button.setMenu(menu)

    def set_flyout(self, flyout: FlyoutFrame) -> None:
        """Attach a flyout panel; clicking the button opens it.

        Switches the button to ``DelayedPopup`` mode so that a short
        click emits the ``clicked`` signal (which opens the flyout) while
        an empty :class:`QMenu` is still attached to trigger the
        ``::menu-indicator`` QSS subcontrol rendering.

        Args:
            flyout: The
                :class:`~pymol_copilot.gui.qt.widgets.flyout.FlyoutFrame`
                to show below the button on click.
        """
        self._flyout = flyout
        self._button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.DelayedPopup
        )
        # Empty menu attached only so ::menu-indicator is rendered via QSS.
        self._button.setMenu(QtWidgets.QMenu(self._button))
        self._button.clicked.connect(self._show_flyout)

    def _show_flyout(self) -> None:
        """Open the attached flyout anchored below the button."""
        from pymol_copilot.gui.qt.widgets.flyout import FlyoutPlacement

        if self._flyout is not None:
            self._flyout.show_for(self._button, FlyoutPlacement.BELOW)


class CommandBar(QtWidgets.QWidget):
    def __init__(
        self,
        command_buttons: list[CommandBarButton],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._outer_frame: QtWidgets.QFrame = QtWidgets.QFrame()
        self._layout_outer_frame: QtWidgets.QVBoxLayout = (
            QtWidgets.QVBoxLayout()
        )
        self._layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout()
        self._init_widget(command_buttons)
        self._set_styles()

    def _set_styles(self):
        self._outer_frame.setStyleSheet(
            theme.compile_stylesheet(_OUTER_FRAME_TEMPLATE)
        )
        tmp_shadow_effect = QtWidgets.QGraphicsDropShadowEffect()
        tmp_shadow_effect.setBlurRadius(20)
        tmp_shadow_effect.setOffset(3, 3)
        tmp_shadow_effect.setColor(QtGui.QColor(0, 0, 0, 30))
        self._outer_frame.setGraphicsEffect(tmp_shadow_effect)
        self.setStyleSheet(theme.compile_stylesheet(_COMMAND_BAR_TEMPLATE))

    def _init_widget(self, command_buttons: list[CommandBarButton]) -> None:
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        for button in command_buttons:
            self._layout.addWidget(button)
        self._layout.addStretch(1)
        self._outer_frame.setLayout(self._layout)
        self._layout_outer_frame.addWidget(self._outer_frame)
        self.setLayout(self._layout_outer_frame)
