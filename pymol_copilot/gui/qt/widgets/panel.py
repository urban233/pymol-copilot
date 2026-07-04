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
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme

__docformat__ = "google"

from pymol_copilot.gui.qt.widgets import conversation_canvas, input_bar


class Panel(QtWidgets.QWidget):
    """A collapsible panel with a titled header and close button.

    The panel is composed of a horizontal header row (title label + stretch +
    close button) above a content_frame where callers add their content.

    Signals:
        panelClosed: Emitted when the close button is pressed.
        panelOpened: Emitted when show_panel is called.

    Attributes:
        _btn_close: The close QPushButton in the header row.
        _lbl_header: The QLabel displaying the panel title.
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
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the panel with a title.

        Args:
            title: Text displayed in the panel header.
            parent: Optional parent widget. Defaults to None.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._btn_close = QtWidgets.QPushButton()
        self._lbl_header = QtWidgets.QLabel(title)
        self._content_frame = QtWidgets.QFrame()
        self._layout_content_frame = QtWidgets.QVBoxLayout()
        # </editor-fold>
        self._content_frame.setLayout(self._layout_content_frame)
        self._init_widget()
        self._connect_signals()

    # <editor-fold desc="Public methods">
    def add_global_stretch(self) -> None:
        """Append a vertical stretch at the bottom of the global layout.

        Useful for panels whose content should remain anchored to the top.
        """
        if (tmp_layout := self.layout()) is None:
            raise RuntimeError("self.layout is None")

        # Check if the layout is a QVBoxLayout (because the layout() method
        # returns a QLayout instead of a QVBoxLayout which is a child of QLayout)
        if not isinstance(tmp_layout, QtWidgets.QVBoxLayout):
            raise TypeError(
                f"Expected QVBoxLayout, but widget has {type(tmp_layout).__name__}"
            )
        tmp_layout.addStretch()

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
        """Initializes the widget by setting up the correct layouts."""
        tmp_header_layout = QtWidgets.QHBoxLayout()
        tmp_header_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_header_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_header_layout.addWidget(self._lbl_header)
        tmp_header_layout.addStretch()
        tmp_header_layout.addWidget(self._btn_close)
        tmp_global_layout = QtWidgets.QVBoxLayout(self)
        tmp_global_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_global_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_global_layout.addLayout(tmp_header_layout)
        tmp_global_layout.addWidget(self._content_frame)
        self.setLayout(tmp_global_layout)

        self._set_styles()

    def _connect_signals(self) -> None:
        """Connects signals to slots."""
        self._btn_close.clicked.connect(self.panelClosed.emit)

    def _set_styles(self) -> None:
        """Sets the styles for specific UI components."""
        self._btn_close.setObjectName(theme.StyleId.PANEL_CLOSE_BUTTON)
        self._lbl_header.setObjectName(theme.StyleId.PANEL_HEADER_LABEL)
        self._content_frame.setObjectName(theme.StyleId.PANEL_SURFACE)

    # </editor-fold>


class PmlCopilotPanel(Panel):
    """A panel for the PML Copilot plugin."""

    def __init__(self) -> None:
        """Initializes the panel."""
        super().__init__("PyMOL-Copilot")
        self._container_widget = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self._layout.setSpacing(ui_defaults.EMPTY_SPACING)
        self._container_widget.setLayout(self._layout)

        self._cui_canvas = conversation_canvas.ConversationCanvas()
        self._input_bar = input_bar.InputBar()
        self._layout.addWidget(self._cui_canvas)
        self._layout.addWidget(self._input_bar)
        self.add_content(self._container_widget)

        self._demo_only()

    def _demo_only(self):
        tmp_user_card = conversation_canvas.UserRequestCard(
            "For the attached file, please make all heading 2s a font of 18, blue font, and not underline."
        )
        self._cui_canvas.add_card(tmp_user_card)
        tmp_working_card = conversation_canvas.AgentThinkingCard()
        self._cui_canvas.add_card(tmp_working_card)
        tool_card = conversation_canvas.ToolApprovalCard("write_cell", "Write value to Excel", {"row": "44", "col": "B", "value": "$24.50"})
        self._cui_canvas.add_card(tool_card)
        tool_card.approved.connect(print)
        tool_card.rejected.connect(lambda: print("rejected"))
        plan_card = conversation_canvas.PlanApprovalCard(
            "Reformat Document Headings",
            [
                "Scan document and collect all Heading 2 elements",
                "Set font size to 18 pt for each heading",
                "Apply blue colour (#0066cc) to each heading",
                "Remove underline formatting from each heading",
                "Save and close the document",
            ],
        )
        self._cui_canvas.add_card(plan_card)
        plan_card.approved.connect(lambda steps: print("Plan approved:", steps))
        plan_card.rejected.connect(lambda: print("Plan rejected"))
