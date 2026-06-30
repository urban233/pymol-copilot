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
"""IntelliJ-style IDE tool-window layout block.

This module provides ToolWindowLayoutBlock, a QWidget that
composes nested QSplitter instances to deliver a four-zone workspace:

Left container: an upper project-overview panel stacked above a
QStackedWidget for arbitrary left-side tool panels.
Right zone: a QStackedWidget for right-side tool panels.
Bottom zone: a QStackedWidget for bottom tool panels.
Centre: the primary viewer widget, surrounded by an optional
horizontal ToolbarBlock.

All zones are independently collapsible and remember their last size so they
restore to the same position when re-opened.
"""

from __future__ import annotations

from typing import Callable
from typing import Optional
from typing import TYPE_CHECKING

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import styles
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults

if TYPE_CHECKING:
    from pymol_copilot.gui.qt.widgets import content_area
    from pymol_copilot.gui.qt.widgets import panel

__docformat__ = "google"


class ToolWindowLayoutBlock(QtWidgets.QWidget):
    """An IDE layout with collapsible left, right, and bottom panels.

    Mimics IDE tool windows using nested QSplitter and QStackedWidget
    instances. The central area hosts the primary viewer widget surrounded by
    optional tool panels on three sides.

    The layout hierarchy is:
        ToolWindowLayoutBlock (QVBoxLayout)
        └─ main_panel (QHBoxLayout)
           └─ bottom_splitter (Vertical QSplitter)
              ├─ left_splitter (Horizontal QSplitter)
              │   ├─ left_container (QWidget)
              │   │   ├─ left_upper_frame  ← project overview
              │   │   └─ left_frame        ← left_stack
              │   └─ right_splitter (Horizontal QSplitter)
              │       ├─ content_panel (center frame)
              │       └─ right_frame       ← right_stack
              └─ bottom_frame              ← bottom_stack

    All six QFrame / QStackedWidget members, the three splitters, and
    the viewer toolbar are exposed as public attributes.

    Attributes:
        _main_content_area: The primary content widget displayed in the central
            zone of the layout.
        _project_info_panel: The specific widget used for
            displaying project-related overview information in the upper-left zone.
        _left_stack: A stacked container for managing
            multiple tool panels on the left side of the workspace.
        _right_stack: A stacked container for managing
            multiple tool panels on the right side of the workspace.
        _bottom_stack: A stacked container for managing
            multiple tool panels in the bottom zone of the workspace.
        _left_upper_frame: A styled container frame that wraps
            the project overview panel for consistent visual presentation.
        _left_frame: A styled container frame that wraps the
            left stacked widget for tool panels.
        _center_frame: A styled container frame that wraps
            the primary viewer widget.
        _right_frame: A styled container frame that wraps the
            right stacked widget for tool panels.
        _bottom_frame: A styled container frame that wraps the
            bottom stacked widget for tool panels.
        _left_splitter: A horizontal splitter that defines
            the boundary between the left panel container and the rest of the workspace.
        _right_splitter: A horizontal splitter that defines
            the boundary between the central content area and the right panel zone.
        _bottom_splitter: A vertical splitter that separates
            the main upper workspace from the bottom tool panel zone.
        _left_container: A container widget that groups the
            upper project overview and the lower left tool panels.
        content_container: A container widget that hosts the
            central viewer frame and its associated layout.
        _last_left_size: Stores the last known width of the left panel to
            allow precise restoration when toggling visibility.
        _last_right_size: Stores the last known width of the right panel to
            allow precise restoration when toggling visibility.
        _last_bottom_size: Stores the last known height of the bottom panel
            to allow precise restoration when toggling visibility.
        _left_hidden: Tracks the current visibility state of the left
            panel container.
        _right_hidden: Tracks the current visibility state of the right
            panel zone.
        _bottom_hidden: Tracks the current visibility state of the bottom
            panel zone.
    """

    def __init__(
        self,
        main_content_area: "content_area.MainContentAreaBlock",
        project_info_panel: QtWidgets.QWidget,
        _left_toolbar_items: Optional[list[QtGui.QAction]] = None,
        _right_toolbar_bar_items: Optional[list[QtGui.QAction]] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the ToolWindowLayoutBlock.

        Args:
            main_content_area: The primary content block.
            project_info_panel: The project metadata panel.
            _left_toolbar_items: Items for the left quick access bar. Defaults to
                None.
            _right_toolbar_bar_items: Items for the right quick access bar.
                Defaults to None.
            parent: The parent widget. Defaults to None.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        # --- Main components ---
        self._main_content_area = main_content_area
        self._project_info_panel = project_info_panel

        # --- Stacked widgets for tool panels ---
        self._left_stack = QtWidgets.QStackedWidget()
        self._right_stack = QtWidgets.QStackedWidget()
        self._bottom_stack = QtWidgets.QStackedWidget()

        # --- Stylable QFrame containers ---
        self._left_upper_frame = QtWidgets.QFrame()
        self._left_frame = QtWidgets.QFrame()
        self._center_frame = QtWidgets.QFrame()
        self._right_frame = QtWidgets.QFrame()
        self._bottom_frame = QtWidgets.QFrame()

        # --- Splitters ---
        self._right_splitter = QtWidgets.QSplitter()
        self._left_splitter = QtWidgets.QSplitter()
        self._bottom_splitter = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Vertical
        )
        self._left_container: QtWidgets.QWidget

        # --- Panel size memory ---
        self._last_left_size = ui_defaults.UISize.LEFT_PANEL_WIDTH
        self._last_right_size = ui_defaults.UISize.RIGHT_PANEL_WIDTH
        self._last_bottom_size = ui_defaults.UISize.BOTTOM_PANEL_HEIGHT
        self._left_hidden = False
        self._right_hidden = False
        self._bottom_hidden = False
        # </editor-fold>
        self._init_ui()

    # <editor-fold desc="Public methods">

    # <editor-fold desc="Add panels">
    def add_left_panel(self, tool_panel: "panel.PanelBlock") -> None:
        """Add a panel to the left QStackedWidget.

        Integrates a new tool panel into the left sidebar stack and connects
        its open and close signals to manage workspace visibility.

        Args:
            tool_panel: The panel block instance to be added to the left stack.
        """
        self._left_stack.addWidget(tool_panel)
        tool_panel.panelClosed.connect(lambda: self.set_left_panel_hidden(True))
        tool_panel.panelOpened.connect(
            lambda: self._activate_and_show_panel(
                tool_panel, self._left_stack, self.set_left_panel_hidden
            )
        )

    def add_right_panel(self, tool_panel: "panel.PanelBlock") -> None:
        """Add a panel to the right QStackedWidget.

        Integrates a new tool panel into the right sidebar stack and connects
        its open and close signals to manage workspace visibility.

        Args:
            tool_panel: The panel block instance to be added to the right stack.
        """
        self._right_stack.addWidget(tool_panel)
        tool_panel.panelClosed.connect(
            lambda: self.set_right_panel_hidden(True)
        )
        tool_panel.panelOpened.connect(
            lambda: self._activate_and_show_panel(
                tool_panel, self._right_stack, self.set_right_panel_hidden
            )
        )

    def add_bottom_panel(self, tool_panel: "panel.PanelBlock") -> None:
        """Add a panel to the bottom QStackedWidget.

        Integrates a new tool panel into the bottom drawer stack and connects
        its open and close signals to manage workspace visibility.

        Args:
            tool_panel: The panel block instance to be added to the bottom
                stack.
        """
        self._bottom_stack.addWidget(tool_panel)
        tool_panel.panelClosed.connect(
            lambda: self.set_bottom_panel_hidden(True)
        )
        tool_panel.panelOpened.connect(
            lambda: self._activate_and_show_panel(
                tool_panel, self._bottom_stack, self.set_bottom_panel_hidden
            )
        )

    def _activate_and_show_panel(
        self,
        tool_panel: "panel.PanelBlock",
        stack: QtWidgets.QStackedWidget,
        visibility_setter: Callable[[bool], None],
    ) -> None:
        """Helper to make a panel active in its stack and ensure the zone is visible.

        Switches the current widget of the provided stack to the specified
        tool panel and updates the visibility of the containing zone.

        Args:
            tool_panel: The specific panel widget to activate.
            stack: The stack container where the panel is hosted.
            visibility_setter: A function or method used to update the
                visibility state of the zone.
        """
        stack.setCurrentWidget(tool_panel)
        visibility_setter(False)

    # </editor-fold>

    # TODO: Add methods for removing panels from the panel stacks

    # <editor-fold desc="Toggle panels">
    def toggle_left_panel(self) -> None:
        """Toggle the left panel between visible and hidden.

        Inverts the current visibility state of the left container.
        """
        self.set_left_panel_hidden(not self._left_hidden)

    def toggle_right_panel(self) -> None:
        """Toggle the right panel between visible and hidden.

        Inverts the current visibility state of the right zone.
        """
        self.set_right_panel_hidden(not self._right_hidden)

    def toggle_bottom_panel(self) -> None:
        """Toggle the bottom panel between visible and hidden.

        Inverts the current visibility state of the bottom zone.
        """
        self.set_bottom_panel_hidden(not self._bottom_hidden)

    # </editor-fold>

    # <editor-fold desc="Set panel visibility state">
    def set_left_panel_hidden(self, hidden: bool) -> None:
        """Show or hide the left panel container.

        Captures the current size of the left panel before hiding to ensure
        it can be restored to the same width when re-shown. The restoration
        is performed via a single-shot timer to ensure the layout has settled.

        Args:
            hidden: True to hide the left container, False to show it.
        """
        if hidden == self._left_hidden:
            return
        if hidden:
            tmp_sizes = self._left_splitter.sizes()
            if tmp_sizes[0] > 0:
                self._last_left_size = tmp_sizes[0]
            self._left_container.hide()
        else:
            self._left_container.show()
            tmp_total = sum(self._left_splitter.sizes())
            tmp_right = max(tmp_total - self._last_left_size, 100)
            QtCore.QTimer.singleShot(
                0,
                lambda: self._left_splitter.setSizes(
                    [self._last_left_size, tmp_right]
                ),
            )
        self._left_hidden = hidden

    def set_right_panel_hidden(self, hidden: bool) -> None:
        """Show or hide the right panel frame.

        Captures the current size of the right panel before hiding to ensure
        it can be restored to the same width when re-shown. The restoration
        is performed via a single-shot timer.

        Args:
            hidden: True to hide the right frame, False to show it.
        """
        if hidden == self._right_hidden:
            return
        if hidden:
            tmp_sizes = self._right_splitter.sizes()
            if tmp_sizes[1] > 0:
                self._last_right_size = tmp_sizes[1]
            self._right_frame.hide()
        else:
            self._right_frame.show()
            tmp_total = sum(self._right_splitter.sizes())
            tmp_left = max(tmp_total - self._last_right_size, 100)
            QtCore.QTimer.singleShot(
                0,
                lambda: self._right_splitter.setSizes(
                    [tmp_left, self._last_right_size]
                ),
            )
        self._right_hidden = hidden

    def set_bottom_panel_hidden(self, hidden: bool) -> None:
        """Show or hide the bottom panel frame.

        Captures the current height of the bottom panel before hiding to ensure
        it can be restored to the same height when re-shown. The restoration
        is performed via a single-shot timer.

        Args:
            hidden: True to hide the bottom frame, False to show it.
        """
        if hidden == self._bottom_hidden:
            return
        if hidden:
            tmp_sizes = self._bottom_splitter.sizes()
            if tmp_sizes[1] > 0:
                self._last_bottom_size = tmp_sizes[1]
            self._bottom_frame.hide()
        else:
            try:
                tmp_current = self._bottom_stack.currentWidget()
                if tmp_current is not None:
                    tmp_current.show()
            except Exception:
                pass
            self._bottom_frame.show()
            tmp_total = sum(self._bottom_splitter.sizes())
            tmp_top = max(tmp_total - self._last_bottom_size, 100)
            QtCore.QTimer.singleShot(
                0,
                lambda: self._bottom_splitter.setSizes(
                    [tmp_top, self._last_bottom_size]
                ),
            )
        self._bottom_hidden = hidden

    # </editor-fold>

    @property
    def is_left_panel_hidden(self) -> bool:
        """Return True when the left panel is currently hidden.

        Returns:
            The current hidden state of the left panel container.
        """
        return self._left_hidden

    @property
    def is_right_panel_hidden(self) -> bool:
        """Return True when the right panel is currently hidden.

        Returns:
            The current hidden state of the right panel frame.
        """
        return self._right_hidden

    @property
    def is_bottom_panel_hidden(self) -> bool:
        """Return True when the bottom panel is currently hidden.

        Returns:
            The current hidden state of the bottom panel frame.
        """
        return self._bottom_hidden

    def change_bg_color_for_center_frame(self, color: str) -> None:
        """Changes the background color of the center_frame widget.

        This method updates the center_frame's stylesheet to apply the
        specified color to its background and border.

        Args:
            color: The color string to be applied to the background and
                border of the center_frame widget.
        """
        self._center_frame.setStyleSheet(
            f"""
            QFrame {{
                border: 1px solid {color};
                background: {color};
                border-radius: 6px;
            }}
            """
        )

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_ui(self) -> None:
        """Assemble the full layout from frames, splitters, and content.

        Constructs the nested layout hierarchy, including the splitters that
        partition the workspace into its four primary zones. It also
        initializes the root layout of the widget.
        """
        self._setup_frame(self._left_upper_frame, self._project_info_panel)
        self._setup_stacked_frame(self._left_frame, self._left_stack)
        self._setup_stacked_frame(self._right_frame, self._right_stack)
        self._setup_stacked_frame(self._bottom_frame, self._bottom_stack)

        self.content_container = QtWidgets.QWidget()
        tmp_content_layout = QtWidgets.QVBoxLayout(self.content_container)
        tmp_content_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        tmp_content_layout.addWidget(self._center_frame)
        # Put the actual main content widget in the center frame
        tmp_center_frame_layout = QtWidgets.QVBoxLayout(self._center_frame)
        tmp_center_frame_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        tmp_center_frame_layout.addWidget(self._main_content_area)

        # Right splitter: center | right panel
        self._right_splitter.addWidget(self.content_container)
        self._right_splitter.addWidget(self._right_frame)
        self._right_splitter.setSizes([800, self._last_right_size])
        self._right_splitter.setChildrenCollapsible(False)

        # Left container: upper + left stacked panels
        self._left_container = QtWidgets.QWidget()
        tmp_left_panel_layout = QtWidgets.QVBoxLayout(self._left_container)
        tmp_left_panel_layout.addWidget(self._left_upper_frame)
        tmp_left_panel_layout.addWidget(self._left_frame)
        tmp_left_panel_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )

        # Left splitter: left container | right splitter
        self._left_splitter.addWidget(self._left_container)
        self._left_splitter.addWidget(self._right_splitter)
        self._left_splitter.setSizes([self._last_left_size, 800])
        self._left_splitter.setChildrenCollapsible(False)

        # Bottom splitter: top (left+right) | bottom panel
        self._bottom_splitter.addWidget(self._left_splitter)
        self._bottom_splitter.addWidget(self._bottom_frame)
        self._bottom_splitter.setSizes([600, self._last_bottom_size])
        self._bottom_splitter.setChildrenCollapsible(False)

        # Root
        tmp_main_panel = QtWidgets.QWidget()
        tmp_main_layout = QtWidgets.QHBoxLayout(tmp_main_panel)
        tmp_main_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_main_layout.addWidget(self._bottom_splitter)

        tmp_root_layout = QtWidgets.QVBoxLayout(self)
        tmp_root_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_root_layout.addWidget(tmp_main_panel)

        # Deferred size restore
        QtCore.QTimer.singleShot(
            0,
            lambda: self._left_splitter.setSizes([self._last_left_size, 800]),
        )
        self._apply_default_styles()

    @staticmethod
    def _setup_stacked_frame(
        frame: QtWidgets.QFrame,
        stacked_widget: QtWidgets.QStackedWidget,
    ) -> None:
        """Embed a stacked widget inside a frame with consistent margins.

        Applies a vertical layout to the frame and sets small margins to
        provide visual separation for the tool panels.

        Args:
            frame: The styled frame container.
            stacked_widget: The stack of tool
                panels to be embedded.
        """
        tmp_layout = QtWidgets.QVBoxLayout(frame)
        tmp_layout.setContentsMargins(*ui_defaults.SMALL_CONTENTS_MARGINS)
        tmp_layout.addWidget(stacked_widget)

    @staticmethod
    def _setup_frame(
        frame: QtWidgets.QFrame,
        widget: QtWidgets.QWidget,
    ) -> None:
        """Embed a widget directly inside a frame with consistent margins.

        Used primarily for the project overview panel to ensure it matches
        the visual style of other tool panels.

        Args:
            frame: The styled frame container.
            widget: The specific widget to be embedded.
        """
        tmp_layout = QtWidgets.QVBoxLayout(frame)
        tmp_layout.setContentsMargins(*ui_defaults.SMALL_CONTENTS_MARGINS)
        tmp_layout.addWidget(widget)

    def _apply_default_styles(self) -> None:
        """Apply the global visual styles to the layout components.

        Assigns stylesheet properties to the frames and splitters to ensure
        a cohesive appearance throughout the IDE interface.
        """
        self._left_upper_frame.setObjectName(theme.StyleId.PANEL_SURFACE)
        self._left_frame.setObjectName(theme.StyleId.PANEL_SURFACE)
        self._center_frame.setObjectName(theme.StyleId.PANEL_SURFACE)
        self._right_frame.setObjectName(theme.StyleId.PANEL_SURFACE)
        self._bottom_frame.setObjectName(theme.StyleId.PANEL_SURFACE)

        self._left_splitter.setObjectName(theme.StyleId.SPLITTER_HANDLE)

    # </editor-fold>
