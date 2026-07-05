# cBioMOL - open C++ and Python platform for BioMOLecular visualization and analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
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
"""Panel widget providing collapsible side and bottom tool panels.

This module contains the Panel class, which represents a collapsible panel
with a titled header and a close button. It can be used anywhere, for example,
as a side or bottom panel.

The block emits panelClosed and panelOpened signals and exposes a
content_frame where child widgets should be added. It connects its close
button to the panelClosed signal directly.
"""

from __future__ import annotations

from typing import Optional

from pymol_copilot.gui.qt import QtCore, ui_defaults, icons
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme

__docformat__ = "google"

from pymol_copilot.gui.qt.widgets import (
    command_bar,
    conversation_canvas,
    input_bar,
    button,
)


class PanelHeader(QtWidgets.QWidget):
    """A header widget for a panel with a title label and close button.

    Signals:
        panelClosed: Emitted when the user clicks the close button.

    Attributes:
        _lbl_header: The QLabel displaying the panel title.
        _btn_close: The close QPushButton.
    """

    panelClosed = QtCore.pyqtSignal()
    """Emitted when the user clicks the close button."""

    def __init__(
        self,
        title: str,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the panel header.

        Args:
            title: Text displayed in the header label.
            parent: Optional parent widget. Defaults to None.
        """
        super().__init__(parent)
        self._lbl_header = QtWidgets.QLabel(title)
        self._btn_close = button.IconButton(
            icons.icon("pymol_copilot.gui.qt", "close")
        )
        self._init_widget()
        self._connect_signals()

    def _init_widget(self) -> None:
        """Set up layout and styles."""
        tmp_layout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.default_contents_margins())
        tmp_layout.setSpacing(ui_defaults.default_spacing())
        tmp_layout.addWidget(self._lbl_header)
        tmp_layout.addStretch()
        tmp_layout.addWidget(self._btn_close)
        self._set_styles()

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._btn_close.clicked.connect(self.panelClosed.emit)

    def _set_styles(self) -> None:
        """Apply object names for QSS styling."""
        self._btn_close.setObjectName(theme.StyleId.PANEL_CLOSE_BUTTON)
        self._lbl_header.setObjectName(theme.StyleId.PANEL_HEADER_LABEL)


class PmlCopilotPanelHeader(PanelHeader):
    """Panel header for PmlCopilotPanel with an additional History navigation button.

    Extends PanelHeader by inserting a CommandBarActionButton between the title
    label and the stretch. Emits ``historyRequested`` when the History button is
    clicked; callers can toggle the button text via ``set_history_button_icon``.

    Signals:
        historyRequested: Emitted when the user clicks the History button.
    """

    historyRequested = QtCore.pyqtSignal()
    """Emitted when the user clicks the History button."""

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the header.

        Args:
            parent: Optional parent widget. Defaults to None.
        """
        # Must be created before super().__init__() calls _init_widget().
        self._btn_history = button.IconButton(
            icon=icons.icon("pymol_copilot.gui.qt", "history")
        )
        super().__init__("PyMOL-Copilot", parent)

    def _init_widget(self) -> None:
        """Set up layout with History button inserted before the stretch."""
        tmp_layout = QtWidgets.QHBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.default_contents_margins())
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)

        tmp_icon = icons.icon("pymol_copilot.gui.qt", "ai")
        icon_size = theme.dp(24)
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(
            tmp_icon.pixmap(QtCore.QSize(icon_size, icon_size))
        )
        icon_label.setFixedSize(icon_size, icon_size)
        icon_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignVCenter
            | QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        tmp_layout.addWidget(icon_label)

        tmp_layout.addWidget(self._lbl_header)
        tmp_layout.addStretch()
        tmp_layout.addWidget(self._btn_history)
        tmp_layout.addWidget(self._btn_close)
        self._set_styles()

    def _connect_signals(self) -> None:
        """Connect close and history button signals."""
        super()._connect_signals()
        self._btn_history.clicked.connect(self.historyRequested.emit)

    def set_history_button_icon(self, icon: QtGui.QIcon) -> None:
        """Update the History button icon.

        Args:
            icon: The new icon to display.
        """
        self._btn_history.setIcon(icon)


class Panel(QtWidgets.QWidget):
    """A collapsible panel with a titled header and close button.

    The panel mirrors the CommandBar inner/outer-frame pattern: a transparent
    outer QVBoxLayout sits on ``self``, and a styled ``_outer_frame`` QFrame
    inside it holds the actual content.  The frame receives the PANEL_SURFACE
    QSS object name and a subtle drop shadow.

    Signals:
        panelClosed: Emitted when the close button is pressed.
        panelOpened: Emitted when show_panel is called.

    Attributes:
        _outer_frame: The styled QFrame containing header + content.
        _layout_outer_frame: The QVBoxLayout on self (outer wrapper).
        _layout: The QVBoxLayout inside _outer_frame.
        _header: The PanelHeader widget at the top.
        _content_frame: A QFrame into which callers should add content.
        _layout_content_frame: The QVBoxLayout inside content_frame.
    """

    # <editor-fold desc="Class attributes">
    panelClosed = QtCore.pyqtSignal()
    """Emitted when the user clicks the close button."""

    panelOpened = QtCore.pyqtSignal()
    """Emitted when show_panel is called."""
    # </editor-fold>

    def __init__(
        self,
        title: str,
        header: Optional[PanelHeader] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the panel with a title.

        Args:
            title: Text displayed in the panel header. Ignored when a custom
                *header* is supplied.
            header: Optional custom PanelHeader to use instead of the default.
                When None a default PanelHeader(title) is created.
            parent: Optional parent widget. Defaults to None.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._outer_frame: QtWidgets.QFrame = QtWidgets.QFrame(self)
        self._layout_outer_frame: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(
            self
        )
        self._layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(
            self._outer_frame
        )
        self._header: PanelHeader = (
            header if header is not None else PanelHeader(title)
        )
        self._content_frame = QtWidgets.QFrame()
        self._layout_content_frame = QtWidgets.QVBoxLayout()
        # </editor-fold>
        self._content_frame.setLayout(self._layout_content_frame)
        self._init_widget()
        self._connect_signals()

    # <editor-fold desc="Public methods">
    def add_global_stretch(self) -> None:
        """Append a vertical stretch at the bottom of the inner layout.

        Useful for panels whose content should remain anchored to the top.
        """
        self._layout.addStretch()

    def show_panel(self) -> None:
        """Emit panelOpened to signal that the panel should be shown.

        The actual visibility is typically managed by listening to this
        signal, or by connecting it directly to self.show().
        """
        self.panelOpened.emit()

    def add_content(self, widget: QtWidgets.QWidget) -> None:
        """Add a widget to the content frame."""
        self._content_frame.layout().addWidget(widget)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget by setting up the inner/outer frame layout."""
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self._layout.setSpacing(ui_defaults.EMPTY_SPACING)
        self._layout.addWidget(self._header)
        self._layout.addWidget(self._content_frame)
        self._outer_frame.setLayout(self._layout)

        self._layout_outer_frame.setContentsMargins(
            *ui_defaults.default_contents_margins()
        )
        self._layout_outer_frame.setSpacing(ui_defaults.EMPTY_SPACING)
        self._layout_outer_frame.addWidget(self._outer_frame)
        self.setLayout(self._layout_outer_frame)

        self._set_styles()

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._header.panelClosed.connect(self.panelClosed.emit)

    def _set_styles(self) -> None:
        """Apply object names and shadow effect to the outer frame."""
        self._outer_frame.setObjectName(theme.StyleId.PANEL_SURFACE)
        tmp_shadow_effect = QtWidgets.QGraphicsDropShadowEffect()
        tmp_shadow_effect.setBlurRadius(10)
        tmp_shadow_effect.setOffset(2, 2)
        tmp_shadow_effect.setColor(QtGui.QColor(0, 0, 0, 10))
        self._outer_frame.setGraphicsEffect(tmp_shadow_effect)

    # </editor-fold>


class PmlCopilotPanel(Panel):
    """A two-page panel for the PML Copilot plugin.

    Page 0 (chat): ConversationCanvas + InputBar.
    Page 1 (history): QTableWidget listing past conversations.

    The History button in the header toggles between pages and updates its
    own label to reflect the current navigation direction.
    """

    def __init__(self) -> None:
        """Initializes the panel."""
        self._panel_header = PmlCopilotPanelHeader()
        super().__init__("PyMOL-Copilot", header=self._panel_header)

        self._stacked_widget = QtWidgets.QStackedWidget()

        # Page 0 — chat
        self._chat_widget = QtWidgets.QWidget()
        self._chat_layout = QtWidgets.QVBoxLayout()
        self._chat_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._chat_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        self._chat_widget.setLayout(self._chat_layout)
        self._cui_canvas = conversation_canvas.ConversationCanvas()
        self._input_bar = input_bar.InputBar()
        self._chat_layout.addWidget(self._cui_canvas)
        self._chat_layout.addWidget(self._input_bar)

        # Page 1 — history
        self._history_table = QtWidgets.QTableWidget(0, 2)
        self._history_table.setHorizontalHeaderLabels(["Date", "Conversation"])
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._history_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )

        self._stacked_widget.addWidget(self._chat_widget)  # index 0
        self._stacked_widget.addWidget(self._history_table)  # index 1

        self.add_content(self._stacked_widget)

        self._panel_header.historyRequested.connect(self._toggle_history_page)

    def submit_text(self, text: str) -> None:
        """Forward *text* into the panel as if the user typed and submitted it.

        Args:
            text: The message text to submit.
        """
        self._input_bar.set_processing(True)
        self._input_bar.submitted.emit(text)

    def _toggle_history_page(self) -> None:
        """Toggle between the chat page and the history page."""
        if self._stacked_widget.currentIndex() == 0:
            self._stacked_widget.setCurrentIndex(1)
            self._panel_header.set_history_button_icon(
                icons.icon("pymol_copilot.gui.qt", "arrow_back")
            )
        else:
            self._stacked_widget.setCurrentIndex(0)
            self._panel_header.set_history_button_icon(
                icons.icon("pymol_copilot.gui.qt", "history")
            )


class SidePanelStack(QtWidgets.QWidget):
    """A collapsible side panel container backed by a QStackedWidget.

    The entire stack can be shown or hidden; the caller is responsible for
    triggering show/hide (e.g. via a toolbar button). Panels inside own their
    own visual appearance — no extra frame or border is added here.

    Signals:
        panelToggled: Emitted when visibility or the active panel changes.
            Carries (index, is_expanded) where index is -1 when hidden.

    Attributes:
        _stacked_widget: The QStackedWidget switching between panel contents.
        _panel_count: Number of panels registered so far.
        _active_index: Index of the currently visible panel, or -1 if hidden.
    """

    panelToggled = QtCore.pyqtSignal(int, bool)
    """Emitted when the panel is toggled. Args: (panel_index, is_expanded)."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initialize the SidePanelStack.

        Args:
            parent: Optional parent widget. Defaults to None.
        """
        super().__init__(parent)
        self._panel_count: int = 0
        self._active_index: int = -1

        self._stacked_widget = QtWidgets.QStackedWidget()

        tmp_layout = QtWidgets.QVBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_layout.addWidget(self._stacked_widget)
        self.setLayout(tmp_layout)

        self.setMinimumWidth(theme.dp(240))

    def add_panel(
        self,
        title: str,
        icon: QtGui.QIcon,
        widget: QtWidgets.QWidget,
    ) -> int:
        """Register a panel and return its index.

        The stack starts hidden; call :meth:`set_active` to show a panel.

        Args:
            title: Descriptive name (reserved for future use).
            icon: Panel icon (reserved for future use).
            widget: The widget shown as the panel content.

        Returns:
            The zero-based index of the newly added panel.
        """
        index = self._panel_count
        self._stacked_widget.addWidget(widget)
        self._panel_count += 1
        return index

    def set_active(self, index: int) -> None:
        """Show the panel at *index*, making the stack visible if hidden.

        Args:
            index: Zero-based panel index to activate.
        """
        if not (0 <= index < self._panel_count):
            return
        self._stacked_widget.setCurrentIndex(index)
        self._active_index = index
        self.show()
        self.panelToggled.emit(index, True)

    def collapse(self) -> None:
        """Hide the entire stack."""
        self._active_index = -1
        self.hide()
        self.panelToggled.emit(-1, False)
