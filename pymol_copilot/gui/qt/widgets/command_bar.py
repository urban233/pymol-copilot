"""Command bar widgets including action, split, and dropdown button variants."""

from __future__ import annotations

import contextlib

from typing import TYPE_CHECKING, TypeAlias, override

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults


if TYPE_CHECKING:
    from pymol_copilot.gui.qt.widgets.flyout import FlyoutFrame

CommandBarButtonType: TypeAlias = QtCore.Qt.ToolButtonStyle


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
        size: tuple[int, int] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the command bar button.

        Args:
            icon: Icon displayed on the button, or None.
            text: Label text.
            style: The arrangement style of the button.
            size: The button size token.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._icon: QtGui.QIcon | None = icon
        self._text: str = text
        self._style: CommandBarButtonType = style
        self._size: tuple[int, int] = (
            size
            if size is not None
            else ui_defaults.UISize.command_bar_button_size()
        )
        self._init_widget()
        self._set_styles()
        self._connect_signals()

    def _init_widget(self) -> None:
        """Initialize the widget's child components and layout.

        Raises:
            NotImplementedError: Always; subclasses must override.
        """
        raise NotImplementedError

    def _set_styles(self) -> None:
        """Apply visual styles and object names to child components.

        Raises:
            NotImplementedError: Always; subclasses must override.
        """
        raise NotImplementedError

    def _connect_signals(self) -> None:
        """Wire signal-slot connections between child components.

        Raises:
            NotImplementedError: Always; subclasses must override.
        """
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
        size: tuple[int, int] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the action button.

        Args:
            icon: Icon displayed on the button, or None.
            text: Label text.
            style: The button visual style.
            size: Size in physical pixels, or None to use the DPI-scaled default.
            parent: Optional parent widget.
        """
        self._button: QtWidgets.QToolButton = QtWidgets.QToolButton()
        super().__init__(icon, text, style, size, parent)

    @override
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

    @override
    def _set_styles(self) -> None:
        """Use the inherited command bar QToolButton stylesheet cascade."""

    @override
    def _connect_signals(self) -> None:
        self._button.clicked.connect(self.clicked)


class CommandBarToggleButton(CommandBarButton):
    """A checkable command bar button backed by one ``QToolButton``.

    The button uses Qt's native checkable state, so mouse, keyboard, and
    programmatic changes all share one source of truth.  Visual feedback is
    supplied by QSS through the ``:checked`` pseudo-state.
    """

    toggled: QtCore.pyqtSignal = QtCore.pyqtSignal(bool)

    def __init__(
        self,
        icon: QtGui.QIcon | None,
        text: str = "",
        style: CommandBarButtonType = CommandBarButtonStyle.ICON_ONLY,
        size: tuple[int, int] | None = None,
        checked: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the toggle button.

        Args:
            icon: Icon displayed on the button, or None.
            text: Label text.
            style: The icon and text arrangement style.
            size: Size in physical pixels, or None to use the DPI-scaled default.
            checked: Whether the button starts in the checked state.
            parent: Optional parent widget.
        """
        self._button: QtWidgets.QToolButton = QtWidgets.QToolButton()
        self._checked: bool = checked
        super().__init__(icon, text, style, size, parent)

    @override
    def _init_widget(self) -> None:
        """Set up the internal checkable QToolButton and layout."""
        if self._icon is not None:
            self._button.setIcon(self._icon)
            self._button.setIconSize(QtCore.QSize(*self._size))
        if self._text:
            self._button.setText(self._text)
        self._button.setToolButtonStyle(self._style)
        self._button.setCheckable(True)
        self._button.setChecked(self._checked)
        self._button.setAutoRaise(False)
        self._button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        tmp_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_layout.addWidget(self._button)

    @override
    def _set_styles(self) -> None:
        """Apply the command-bar toggle object name."""
        self._button.setObjectName(theme.StyleId.TOGGLE_BUTTON)

    @override
    def _connect_signals(self) -> None:
        """Connect native button state to public wrapper signals."""
        self._button.clicked.connect(self._emit_clicked)
        self._button.toggled.connect(self._emit_toggled)

    def is_checked(self) -> bool:
        """Return whether the toggle is currently checked.

        Returns:
            True when the button is checked, otherwise False.
        """
        return self._button.isChecked()

    def set_checked(self, checked: bool) -> None:
        """Set the checked state.

        Args:
            checked: The new checked state.
        """
        self._button.setChecked(checked)

    def toggle(self) -> None:
        """Invert the checked state and emit Qt's native toggled signal."""
        self._button.toggle()

    def _emit_clicked(self, checked: bool = False) -> None:
        """Emit the wrapper click signal.

        Args:
            checked: Native checked payload from ``QToolButton.clicked``.
        """
        del checked
        self.clicked.emit()

    def _emit_toggled(self, checked: bool) -> None:
        """Emit the wrapper toggled signal and refresh QSS state.

        Args:
            checked: The current checked state.
        """
        self.toggled.emit(checked)
        theme.refresh_widget_style(self._button)


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
        size: tuple[int, int] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the split button with independent hover halves.

        Args:
            icon: Icon displayed on the left half, or None.
            text: Label text.
            style: Button layout style.
            size: Size in physical pixels.
            parent: Optional parent widget.
        """
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

    @override
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

    @override
    def _set_styles(self) -> None:
        self._main_button.setObjectName(theme.StyleId.SPLIT_BUTTON_MAIN)
        self._arrow_button.setObjectName(theme.StyleId.SPLIT_BUTTON_ARROW)

    @override
    def _connect_signals(self) -> None:
        self._main_button.clicked.connect(self.clicked)

    def _is_main_checked(self) -> bool:
        """Return whether the main button should paint as checked.

        Returns:
            False for plain split buttons.
        """
        return False

    def _update_hover_from_parent_x(self, x: float) -> None:
        """Set hover flags based on x-coordinate in parent (self) space."""
        divider_x = float(self._arrow_button.geometry().left())
        new_main = x < divider_x
        new_arrow = x >= divider_x
        if new_main != self._main_hovered or new_arrow != self._arrow_hovered:
            self._main_hovered = new_main
            self._arrow_hovered = new_arrow
            self.update()

    @override
    def mouseMoveEvent(self, a0: QtGui.QMouseEvent | None) -> None:
        """Handle mouse moves that land in the gap between child buttons.

        Args:
            a0: The mouse event.
        """
        if a0 is not None:
            self._update_hover_from_parent_x(a0.position().x())
        super().mouseMoveEvent(a0)

    @override
    def leaveEvent(self, a0: QtCore.QEvent | None) -> None:
        """Reset all interactive state when the cursor exits the widget.

        Args:
            a0: The leave event.
        """
        if not self._menu_open:
            self._main_hovered = False
            self._arrow_hovered = False
            self._main_pressed = False
            self._arrow_pressed = False
            self.update()
        super().leaveEvent(a0)

    @override
    def eventFilter(
        self,
        a0: QtCore.QObject | None,
        a1: QtCore.QEvent | None,
    ) -> bool:
        """Filter events on child buttons to update visual hover and press states.

        Args:
            a0: The object monitored.
            a1: The event captured.

        Returns:
            True if the event should be consumed, False otherwise.
        """
        if (
            isinstance(a0, QtWidgets.QWidget)
            and isinstance(a1, QtGui.QMouseEvent)
            and a0 in (self._main_button, self._arrow_button)
        ):
            tmp_type = a1.type()
            if tmp_type == QtCore.QEvent.Type.MouseMove:
                tmp_parent_pos = a0.mapToParent(a1.position().toPoint())
                self._update_hover_from_parent_x(float(tmp_parent_pos.x()))
            elif tmp_type == QtCore.QEvent.Type.MouseButtonPress:
                if a0 is self._main_button:
                    self._main_pressed = True
                else:
                    self._arrow_pressed = True
                self.update()
            elif tmp_type == QtCore.QEvent.Type.MouseButtonRelease:
                if a0 is self._main_button:
                    self._main_pressed = False
                else:
                    self._arrow_pressed = False
                # Deferred sync: Qt's mouse grab may have suppressed leaveEvent
                # during the hold, leaving pressed flags stuck if the cursor moved away.
                QtCore.QTimer.singleShot(0, self._sync_pressed_state)
        return super().eventFilter(a0, a1)

    def _sync_pressed_state(self) -> None:
        """Clear pressed flags if the cursor left the widget during a mouse-grab."""
        if not (
            self._main_button.underMouse()
            or self._arrow_button.underMouse()
            or self.underMouse()
        ) and (self._main_pressed or self._arrow_pressed):
            self._main_pressed = False
            self._arrow_pressed = False
            self.update()
        self._main_button.setDown(False)
        self._arrow_button.setDown(False)

    def _on_menu_show(self) -> None:
        """Set menu-open flag and update split button painting."""
        self._menu_open = True
        self.update()

    def _on_menu_hide(self) -> None:
        """Reset menu-open flag, clear pressed/hover states, and update painting."""
        self._menu_open = False
        self._arrow_pressed = False
        self._arrow_hovered = False
        self._arrow_button.setDown(False)
        self._main_button.setDown(False)
        QtCore.QTimer.singleShot(0, self._sync_pressed_state)
        self.update()

    @override
    def paintEvent(self, a0: QtGui.QPaintEvent | None) -> None:
        """Paint the background highlights, borders, and dividers.

        Args:
            a0: The paint event.
        """
        super().paintEvent(a0)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        radius = theme.ThemeMetrics.CORNER_RADIUS.px
        full = QtCore.QRectF(self.rect())
        divider_x = float(self._arrow_button.geometry().left())

        # 1. Surface base — establishes the rounded shape for the whole widget.
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(theme.ThemeColors.SURFACE.to_qcolor()))
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
        main_checked = self._is_main_checked()

        if self._arrow_pressed or self._menu_open or main_checked:
            _fill_section(
                main_clip, theme.ThemeColors.PRESSED_SHARED.to_qcolor()
            )
            _fill_section(
                arrow_clip, theme.ThemeColors.PRESSED_SHARED.to_qcolor()
            )
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
            or main_checked
        )

        # 3. Divider — only when hovering, not while arrow is pressed or menu is open.
        # if (self._main_hovered or self._arrow_hovered) and not (
        #     self._arrow_pressed or self._menu_open
        # ):
        if (self._main_hovered or self._arrow_hovered) and not (
            self._arrow_pressed
            or self._menu_open
            or self._main_pressed
            or main_checked
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
                if (self._arrow_pressed or self._menu_open or main_checked)
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
        """Attach a flyout panel to the arrow section.

        Works as an alternative to :meth:`set_menu`: clicking the arrow opens
        the flyout below the button and drives the same ``_menu_open`` paint
        state so the button renders correctly while the flyout is visible.

        Args:
            flyout: The flyout panel to open when the arrow is clicked.
        """
        if self._flyout is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._flyout.about_to_show.disconnect(self._on_menu_show)
            with contextlib.suppress(TypeError, RuntimeError):
                self._flyout.about_to_hide.disconnect(self._on_menu_hide)
            with contextlib.suppress(TypeError, RuntimeError):
                self._arrow_button.clicked.disconnect(self._show_flyout)
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
        if self._menu is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._menu.aboutToShow.disconnect(self._on_menu_show)
            with contextlib.suppress(TypeError, RuntimeError):
                self._menu.aboutToHide.disconnect(self._on_menu_hide)
            with contextlib.suppress(TypeError, RuntimeError):
                self._arrow_button.clicked.disconnect(self._show_menu)
        self._menu = menu
        menu.aboutToShow.connect(self._on_menu_show)
        menu.aboutToHide.connect(self._on_menu_hide)
        self._arrow_button.clicked.connect(self._show_menu)


class CommandToggleSplitButton(CommandBarSplitButton):
    """A split button whose main section behaves as a toggle button.

    The main section uses one native checkable ``QToolButton`` while the arrow
    section inherits the menu and flyout behaviour from
    :class:`CommandBarSplitButton`.
    """

    toggled: QtCore.pyqtSignal = QtCore.pyqtSignal(bool)

    def __init__(
        self,
        icon: QtGui.QIcon | None,
        text: str = "",
        style: CommandBarButtonType = CommandBarButtonStyle.TEXT_ONLY,
        size: tuple[int, int] | None = None,
        checked: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the toggle split button.

        Args:
            icon: Icon displayed on the main section, or None.
            text: Label text.
            style: Main button layout style.
            size: Size in physical pixels.
            checked: Whether the main section starts checked.
            parent: Optional parent widget.
        """
        self._checked: bool = checked
        super().__init__(icon, text, style, size, parent)

    @override
    def _init_widget(self) -> None:
        """Set up the inherited split UI and make the main button checkable."""
        super()._init_widget()
        self._main_button.setCheckable(True)
        self._main_button.setChecked(self._checked)

    @override
    def _connect_signals(self) -> None:
        """Connect native toggle state to public wrapper signals."""
        self._main_button.clicked.connect(self._emit_clicked)
        self._main_button.toggled.connect(self._emit_toggled)

    @override
    def _is_main_checked(self) -> bool:
        """Return whether the main button is checked.

        Returns:
            True when the main section is checked, otherwise False.
        """
        return self._main_button.isChecked()

    def is_checked(self) -> bool:
        """Return whether the main section is currently checked.

        Returns:
            True when the main section is checked, otherwise False.
        """
        return self._main_button.isChecked()

    def set_checked(self, checked: bool) -> None:
        """Set the main section checked state.

        Args:
            checked: The new checked state.
        """
        self._main_button.setChecked(checked)
        self.update()

    def toggle(self) -> None:
        """Invert the main section checked state."""
        self._main_button.toggle()

    def _emit_clicked(self, checked: bool = False) -> None:
        """Emit the wrapper clicked signal.

        Args:
            checked: Native checked payload from ``QToolButton.clicked``.
        """
        del checked
        self.clicked.emit()

    def _emit_toggled(self, checked: bool) -> None:
        """Emit the wrapper toggled signal and refresh custom painting.

        Args:
            checked: The current checked state.
        """
        self.toggled.emit(checked)
        self.update()


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
        size: tuple[int, int] | None = None,
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

    @override
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

    @override
    def _set_styles(self) -> None:
        """Apply the style-adaptive object name."""
        tmp_text_under = (
            self._style == QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        )
        if tmp_text_under:
            self._button.setObjectName(theme.StyleId.DROPDOWN_BUTTON_UNDER)
        else:
            self._button.setObjectName(theme.StyleId.DROPDOWN_BUTTON_BESIDE)

    @override
    def _connect_signals(self) -> None:
        """Leave clicks to the popup/flyout handlers."""

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
        self._button.installEventFilter(self)
        flyout.about_to_show.connect(self._on_flyout_show)
        flyout.about_to_hide.connect(self._on_flyout_hide)

    @override
    def eventFilter(
        self,
        a0: QtCore.QObject | None,
        a1: QtCore.QEvent | None,
    ) -> bool:
        """Filter events to intercept mouse presses on the button when flyout is set.

        Args:
            a0: The object receiving the event.
            a1: The event being sent.

        Returns:
            True to consume the event, False to let it propagate.
        """
        if (
            a0 is self._button
            and a1 is not None
            and a1.type() == QtCore.QEvent.Type.MouseButtonPress
            and self._flyout is not None
        ):
            assert isinstance(a1, QtGui.QMouseEvent)
            if a1.button() == QtCore.Qt.MouseButton.LeftButton:
                self._show_flyout()
                return True
        return super().eventFilter(a0, a1)

    def _show_flyout(self) -> None:
        """Open the attached flyout anchored below the button."""
        from pymol_copilot.gui.qt.widgets.flyout import FlyoutPlacement

        if self._flyout is not None:
            self._flyout.show_for(self._button, FlyoutPlacement.BELOW)

    def _on_flyout_show(self) -> None:
        """Slot triggered when the flyout is about to show."""
        self._button.setProperty("flyoutOpen", True)
        theme.refresh_widget_style(self._button)

    def _on_flyout_hide(self) -> None:
        """Slot triggered when the flyout is about to hide."""
        self._button.setProperty("flyoutOpen", False)
        theme.refresh_widget_style(self._button)


class CommandBar(QtWidgets.QWidget):
    """A horizontal container bar for action and split buttons."""

    def __init__(
        self,
        command_buttons: list[CommandBarButton],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the command bar with a list of buttons.

        Args:
            command_buttons: Buttons to display in the bar.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._outer_frame: QtWidgets.QFrame = QtWidgets.QFrame(self)
        self._layout_outer_frame: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(
            self
        )
        self._layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout(
            self._outer_frame
        )
        self._init_widget(command_buttons)
        self._set_styles()

    def append_command_button(self, command_button: CommandBarButton) -> None:
        """Append a button to the command bar."""
        self._layout.addWidget(command_button)

    def _set_styles(self) -> None:
        """Apply the global theme object names and shadow effects."""
        self._outer_frame.setObjectName(theme.StyleId.COMMAND_BAR_OUTER)
        tmp_shadow_effect = QtWidgets.QGraphicsDropShadowEffect()
        tmp_shadow_effect.setBlurRadius(10)
        tmp_shadow_effect.setOffset(2, 2)
        tmp_shadow_effect.setColor(QtGui.QColor(0, 0, 0, 10))
        self._outer_frame.setGraphicsEffect(tmp_shadow_effect)
        self.setObjectName(theme.StyleId.COMMAND_BAR)

    def _init_widget(self, command_buttons: list[CommandBarButton]) -> None:
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self._layout_outer_frame.setContentsMargins(
            *ui_defaults.default_contents_margins()
        )

        for button in command_buttons:
            self._layout.addWidget(button)
        self._layout.addStretch(1)
        self._outer_frame.setLayout(self._layout)
        self._layout_outer_frame.addWidget(self._outer_frame)
        self.setLayout(self._layout_outer_frame)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )


class TabbedCommandBar(QtWidgets.QWidget):
    """A command bar with named tabs; each tab shows its own set of buttons."""

    def __init__(
        self,
        tabs: list[tuple[str, list[CommandBarButton]]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the tabbed command bar.

        Args:
            tabs: Ordered list of (tab_name, buttons) pairs. The first entry
                is selected on construction.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._outer_frame: QtWidgets.QFrame = QtWidgets.QFrame(self)
        self._layout_outer_frame: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(self)
        self._tab_buttons: list[QtWidgets.QPushButton] = []
        self._tab_group: QtWidgets.QButtonGroup = QtWidgets.QButtonGroup(self)
        self._stack: QtWidgets.QStackedWidget = QtWidgets.QStackedWidget(
            self._outer_frame
        )
        self._divider: QtWidgets.QFrame = QtWidgets.QFrame(self._outer_frame)
        self._init_widget(tabs)
        self._set_styles()

    def _init_widget(self, tabs: list[tuple[str, list[CommandBarButton]]]) -> None:
        self._layout_outer_frame.setContentsMargins(
            *ui_defaults.default_contents_margins()
        )

        outer_content_layout = QtWidgets.QVBoxLayout()
        outer_content_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        outer_content_layout.setSpacing(0)
        self._outer_frame.setLayout(outer_content_layout)

        # Tab bar row
        tab_bar_widget = QtWidgets.QWidget(self._outer_frame)
        tab_bar_layout = QtWidgets.QHBoxLayout(tab_bar_widget)
        tab_bar_layout.setContentsMargins(
            theme.dp(4), theme.dp(2), theme.dp(4), 0
        )
        tab_bar_layout.setSpacing(ui_defaults.EMPTY_SPACING)

        # Bold font metrics for pre-allocating minimum button width.
        # The :checked QSS state applies font-weight:bold, which widens the
        # text.  Computing the min-width now (before the stylesheet is
        # applied) prevents clipping when a tab becomes active.
        _bold_font = QtGui.QFont()
        _bold_font.setPixelSize(theme.ThemeMetrics.FONT_SIZE_BASE.px)
        _bold_font.setBold(True)
        _fm = QtGui.QFontMetrics(_bold_font)
        # QSS padding: 10 px each side; dp(4) safety buffer
        _tab_h_padding = theme.dp(10) * 2 + theme.dp(4)

        self._tab_group.setExclusive(True)
        for i, (name, _) in enumerate(tabs):
            btn = QtWidgets.QPushButton(name, tab_bar_widget)
            btn.setCheckable(True)
            btn.setMinimumWidth(_fm.horizontalAdvance(name) + _tab_h_padding)
            self._tab_group.addButton(btn, i)
            self._tab_buttons.append(btn)
            tab_bar_layout.addWidget(btn)
        tab_bar_layout.addStretch(1)
        self._tab_group.idClicked.connect(self._switch_tab)

        # Divider between tab bar and content
        self._divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self._divider.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self._divider.setFixedHeight(theme.dp(1))

        # Content stack — one page per tab
        for _, buttons in tabs:
            page = QtWidgets.QWidget()
            page_layout = QtWidgets.QHBoxLayout(page)
            page_layout.setContentsMargins(*ui_defaults.default_contents_margins())
            page_layout.setSpacing(ui_defaults.default_spacing())
            for btn in buttons:
                page_layout.addWidget(btn)
            page_layout.addStretch(1)
            self._stack.addWidget(page)

        outer_content_layout.addWidget(tab_bar_widget)
        outer_content_layout.addWidget(self._divider)
        outer_content_layout.addWidget(self._stack)

        self._layout_outer_frame.addWidget(self._outer_frame)
        self.setLayout(self._layout_outer_frame)

        if self._tab_buttons:
            self._switch_tab(0)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )

    def _switch_tab(self, index: int) -> None:
        """Switch the visible content page and mark the corresponding tab button.

        Args:
            index: Zero-based index of the tab to activate.
        """
        self._stack.setCurrentIndex(index)
        btn = self._tab_group.button(index)
        if btn is not None:
            btn.setChecked(True)

    def append_command_button(
        self, tab_index: int, command_button: CommandBarButton
    ) -> None:
        """Append a button to the end of a tab's button row.

        The button is added after the trailing stretch, mirroring the
        behaviour of :meth:`CommandBar.append_command_button`.

        Args:
            tab_index: Zero-based index of the target tab.
            command_button: The button to append.
        """
        page = self._stack.widget(tab_index)
        if page is not None:
            layout = page.layout()
            if isinstance(layout, QtWidgets.QHBoxLayout):
                layout.addWidget(command_button)

    def _set_styles(self) -> None:
        """Apply global theme object names and shadow effects."""
        self._outer_frame.setObjectName(theme.StyleId.TABBED_COMMAND_BAR_OUTER)
        self._divider.setObjectName(theme.StyleId.TABBED_COMMAND_BAR_DIVIDER)
        for btn in self._tab_buttons:
            btn.setObjectName(theme.StyleId.TABBED_COMMAND_BAR_TAB)
        tmp_shadow = QtWidgets.QGraphicsDropShadowEffect()
        tmp_shadow.setBlurRadius(10)
        tmp_shadow.setOffset(2, 2)
        tmp_shadow.setColor(QtGui.QColor(0, 0, 0, 10))
        self._outer_frame.setGraphicsEffect(tmp_shadow)
        self.setObjectName(theme.StyleId.TABBED_COMMAND_BAR)
