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
"""Provide menu widget blocks for dropdown and inline menu patterns.

This module provides two menu block classes. DropdownMenuBlock is a QMenu that
stays open when the user clicks checkable actions, enabling multi-selection
workflows. InlineMenuBlock is a QWidget that embeds a QMenu inline in a layout,
exposing convenience helpers to add labelled actions, descriptions, and
separators.
"""

from __future__ import annotations

from typing import Optional

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults

__docformat__ = "google"

# Shared stylesheet applied to both menu block types.
_MENU_STYLESHEET = """
QMenu {
    background-color: white;
    margin: 2px;
}
QMenu::item {
    padding-top: 5px;
    padding-bottom: 5px;
    padding-left: 7px;
    padding-right: 15px;
    font-size: 13px;
}
QMenu::item:selected {
    background: #D6E4FD;
    border-width: 2px;
    border-radius: 4px;
    border-color: white;
}
QMenu::icon {
    padding-left: 15px;
}
QMenu::separator {
    height: 1px;
    background: #E2E2E2;
    margin-left: 0px;
    margin-right: 0px;
}
QLabel {
    padding-top: 5px;
    padding-bottom: 5px;
    padding-right: 10px;
    margin-left: 10px;
    font: bold;
    font-size: 12px;
    color: #242424;
}
"""


class DropdownMenuBlock(QtWidgets.QMenu):
    """A QMenu that remains open after the user clicks a checkable action.

    The standard QMenu closes after every action click. This block
    overrides mouseReleaseEvent so that clicking a checkable action
    only toggles its state and keeps the menu visible, which is ideal for
    multi-selection workflows.

    For exclusive QActionGroup actions the behaviour is adjusted: the
    clicked action is checked (allowing Qt to uncheck the others) and the
    menu stays open. Non-checkable action clicks delegate to the base
    implementation, which closes the menu as usual.

    Example:
        menu = DropdownMenuBlock()
        menu.addAction("Option A").setCheckable(True)
        menu.addAction("Option B").setCheckable(True)
        tool_button.setMenu(menu)
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initialize the persistent dropdown menu.

        Args:
            parent: Optional parent widget. Defaults to None.
        """
        super().__init__(parent)

    # <editor-fold desc="Public methods">

    def mouseReleaseEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        """Toggle checkable actions without closing the menu.

        For exclusive action groups the clicked action is checked and the
        menu is kept open. For non-exclusive checkable actions the checked
        state is flipped and the menu remains open. Non-checkable actions
        are forwarded to the base class, which closes the menu normally.

        Args:
            event: The mouse-release event.
        """
        tmp_action = self.actionAt(event.pos())
        if tmp_action and tmp_action.isCheckable():
            tmp_group = tmp_action.actionGroup()
            if tmp_group is not None and tmp_group.isExclusive():
                if not tmp_action.isChecked():
                    tmp_action.setChecked(True)
                return
            else:
                tmp_action.setChecked(not tmp_action.isChecked())
                return
        super().mouseReleaseEvent(event)

    # </editor-fold>


class InlineMenuBlock(QtWidgets.QWidget):
    """A widget that embeds QMenu inline within a standard layout.

    Wraps a QMenu in a QVBoxLayout so it can be placed directly
    inside other layouts without needing a QMenuBar or QToolBar.
    Helper methods simplify adding actions, description labels, and
    separators.

    Attributes:
        menu: The underlying QMenu widget.

    Example:
        inline = InlineMenuBlock()
        inline.add_description("Import Sequence From")
        inline.add_action("Copy + Paste", icon=copy_icon)
        inline.add_action("This Device", icon=device_icon)
        inline.add_separator()
        layout.addWidget(inline)
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initialize the inline menu widget.

        Args:
            parent: Optional parent widget. Defaults to None.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self.menu = QtWidgets.QMenu(self)
        # </editor-fold>
        self._init_widget()
        self.setStyleSheet(_MENU_STYLESHEET)

    # <editor-fold desc="Public methods">
    def add_action(
        self,
        name: str,
        icon: Optional[QtGui.QIcon] = None,
    ) -> QtGui.QAction:
        """Add a named action to the menu with an optional icon.

        Args:
            name: The display text for the action.
            icon: An optional QIcon shown to the left of the action text.
                Defaults to None.

        Returns:
            The newly created and added QAction instance.
        """
        tmp_action = QtGui.QAction(name, self)
        if icon is not None:
            tmp_action.setIcon(icon)
        self.menu.addAction(tmp_action)
        return tmp_action

    def add_description(self, description: str) -> None:
        """Add a non-clickable description label at the current menu position.

        Uses a QWidgetAction wrapping a QLabel so the text is styled
        consistently with the menu stylesheet but cannot be triggered.

        Args:
            description: The descriptive text to insert.
        """
        tmp_label = QtWidgets.QLabel(description)
        tmp_widget_action = QtWidgets.QWidgetAction(self)
        tmp_widget_action.setDefaultWidget(tmp_label)
        self.menu.addAction(tmp_widget_action)

    def add_separator(self) -> None:
        """Insert a horizontal separator line at the current menu position."""
        self.menu.addSeparator()

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget layout and children."""
        tmp_layout = QtWidgets.QVBoxLayout(self)
        tmp_layout.addWidget(self.menu)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        self.setLayout(tmp_layout)

    # </editor-fold>
