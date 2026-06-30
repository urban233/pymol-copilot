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
"""Toolbar widget blocks for icon-based toolbars."""

from __future__ import annotations

from typing import Dict
from typing import Optional

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults

__docformat__ = "google"

# Shared stylesheet applied to toolbar buttons.
_TOOLBAR_STYLESHEET = """
QToolButton {
    font-size: 7.9pt;
    background-color: white;
    padding: 0.15em;
    border: none;
    border-radius: 0.375em;
}
QToolButton::hover {
    background: #f5f5f5;
    color: black;
    border-radius: 0.375em;
}
"""


class ToolbarBlock(QtWidgets.QWidget):
    """A compact icon-only toolbar for rapidly accessing common actions.

    Renders each QtGui.QAction as a fixed-size QToolButton.
    The layout is split into a start group and an end group separated by
    a central stretch, so items can be anchored to either end of the bar.

    Orientation is controlled by the horizontal parameter. If False (the
    default), it is a vertical bar and items stack top-to-bottom. If True,
    it is a horizontal bar and items flow left-to-right.

    Attributes:
        _toolbar_actions: List of QtGui.QAction passed
            at construction time.
        _is_horizontal: Boolean flag indicating if the toolbar is horizontal.
        _button_size: (width, height) in pixels for each button.
        _layout: The main QBoxLayout for the widget.
        _start_layout: The layout for actions at the beginning/top.
        _end_layout: The layout for actions at the end/bottom.
        _item_to_button: Mapping from each action to its QToolButton.
    """

    def __init__(
        self,
        toolbar_actions: list[QtGui.QAction],
        horizontal: bool = False,
        button_size: tuple[int, int] = (
            ui_defaults.UISize.TOOLBAR_BUTTON_SIZE,
            ui_defaults.UISize.TOOLBAR_BUTTON_SIZE,
        ),
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the toolbar and populate it with action buttons.

        Args:
            toolbar_actions: Ordered list of QtGui.QAction objects added to the
                start group.
            horizontal: When True the bar uses a QHBoxLayout; when False
                it uses a QVBoxLayout. Defaults to False.
            button_size: The width and height in pixels for each button and its
                icon. Defaults to (TOOLBAR_BUTTON_SIZE, TOOLBAR_BUTTON_SIZE).
            parent: Optional parent widget. Defaults to None.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._toolbar_actions: list[QtGui.QAction] = toolbar_actions
        self._is_horizontal = horizontal
        self._button_size = button_size

        if horizontal:
            self._layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout()
            self._start_layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout()
            self._end_layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout()
        else:
            self._layout = QtWidgets.QVBoxLayout()
            self._start_layout = QtWidgets.QVBoxLayout()
            self._end_layout = QtWidgets.QVBoxLayout()

        self._item_to_button: Dict[QtGui.QAction, QtWidgets.QToolButton] = {}
        # </editor-fold>
        self._init_widget()
        self.setStyleSheet(_TOOLBAR_STYLESHEET)

    # <editor-fold desc="Public methods">
    def get_tool_button_for_action(
        self, action: QtGui.QAction
    ) -> Optional[QtWidgets.QToolButton]:
        """Return the QToolButton associated with action.

        Args:
            action: The QtGui.QAction whose button is needed.

        Returns:
            The corresponding QToolButton, or None if not found.
        """
        return self._item_to_button.get(action)

    def add_action(
        self, action: QtGui.QAction, position: str = "start"
    ) -> None:
        """Create a button for action and add it to the bar.

        Args:
            action: The action for which to create a button.
            position: Which group to add the button to. Accepted values are
                "top", "start", "left" (start group) and "bottom", "end",
                "right" (end group). Defaults to "start".
        """
        tmp_pos = (position or "start").strip().lower()
        tmp_target = (
            self._end_layout
            if tmp_pos in {"bottom", "end", "right"}
            else self._start_layout
        )
        tmp_button = self._create_tool_button(action)
        tmp_target.addWidget(tmp_button)
        self._item_to_button[action] = tmp_button

    def add_top_action(self, action: QtGui.QAction) -> None:
        """Add action to the start or top group.

        Args:
            action: The action to add.
        """
        self.add_action(action, position="start")

    def add_bottom_action(self, action: QtGui.QAction) -> None:
        """Add action to the end or bottom group.

        Args:
            action: The action to add.
        """
        self.add_action(action, position="end")

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Set up the layout and add initial buttons.

        Initializes margins for all layouts, adds the stretch between start and
        end groups, and sets the widget size policy.
        """
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self._start_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._end_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)

        self._layout.addLayout(self._start_layout)
        self._layout.addStretch(1)
        self._layout.addLayout(self._end_layout)
        self.setLayout(self._layout)

        self._add_actions()

        if self._is_horizontal:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        else:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )

    def _add_actions(self) -> None:
        """Create buttons for all constructor-provided actions.

        Iterates through actions and populates the start layout.
        """
        for tmp_action in self._toolbar_actions:
            tmp_button = self._create_tool_button(tmp_action)
            self._start_layout.addWidget(tmp_button)
            self._item_to_button[tmp_action] = tmp_button

    def _create_tool_button(
        self, action: QtGui.QAction
    ) -> QtWidgets.QToolButton:
        """Build and return a configured QToolButton for action.

        Args:
            action: The action for which the button is created.

        Returns:
            A configured QToolButton with the action set, icon-only style,
            and fixed dimensions.
        """
        tmp_button = QtWidgets.QToolButton()
        tmp_button.setDefaultAction(action)
        tmp_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        tmp_button.setIconSize(
            QtCore.QSize(self._button_size[0], self._button_size[1])
        )
        tmp_button.setFixedSize(self._button_size[0], self._button_size[1])
        return tmp_button

    # </editor-fold>
