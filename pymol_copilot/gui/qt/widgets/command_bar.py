from typing import TypeAlias

from pymol_copilot.gui.qt import QtCore, styles
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults

CommandBarButtonType: TypeAlias = QtCore.Qt.ToolButtonStyle


# _COMMAND_BAR_STYLESHEET = """
# QToolButton {
#     font-size: 12px;
#     background-color: white;
#     border: none;
#     border-radius: 0.375em;
# }
# QToolButton::hover {
#     font-size: 12px;
#     background: #f5f5f5;
#     border-radius: 0.375em;
# }
# """

_OUTER_FRAME_STYLE = """
QFrame {
    border: 0.075em solid white;
    background: white;
    border-radius: 0.6em;
    padding: 0.2em;
}
"""

# _COMMAND_BAR_STYLESHEET = """
# QToolButton {
#     font-size: 12px;
#     background-color: white;
#     border: none;
#     border-radius: 0.375em;
#     /* Adds extra padding on the right/bottom to clear space for the arrow */
#     padding-right: 10px;
#     padding-bottom: 4px;
# }
# QToolButton::hover {
#     font-size: 12px;
#     background: #f5f5f5;
#     border-radius: 0.375em;
# }
# /* Force anchors the arrow safely away from the text contents */
# QToolButton::menu-indicator {
#     subcontrol-origin: padding;
#     subcontrol-position: bottom right;
#     right: 2px;
#     bottom: 2px;
# }
# """

_COMMAND_BAR_STYLESHEET = """
QToolButton {
    font-size: 12px;
    background-color: white;
    border: none;
    border-radius: 0.375em;
    /* Extra right padding ensures text/icon won't bunch up against the split line */
    padding-right: 24px; 
    padding-top: 4px;
    padding-bottom: 4px;
}

QToolButton::hover {
    background: #f5f5f5;
}

/* Styles the right-hand arrow section and creates the split line */
QToolButton::menu-button {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    
    /* The vertical divider line */
    border-left: 1px solid #dcdcdc; 
    
    /* Matches the parent button's right-side rounding */
    border-top-right-radius: 0.375em;
    border-bottom-right-radius: 0.375em;
}

/* Adjusts the placement of the arrow icon inside the split section */
QToolButton::menu-arrow {
    subcontrol-origin: padding;
    subcontrol-position: center;
}
"""

class CommandBarButtonStyle:
    """Namespace class for Qt ToolButton styles."""
    TEXT_BESIDE = QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    TEXT_UNDER = QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
    TEXT_ONLY = QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly
    ICON_ONLY = QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly


class CommandBarButton(QtWidgets.QToolButton):

    def __init__(
            self,
            icon: QtGui.QIcon | None,
            text: str = "",
            style: CommandBarButtonType = CommandBarButtonStyle.ICON_ONLY,
            size: tuple[int, int] = ui_defaults.UISize.COMMAND_BAR_BUTTON_SIZE,
            parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        if icon is not None:
            self.setIcon(icon)
            self.setIconSize(QtCore.QSize(*size))
        if text != "":
            self.setText(text)
        self.setToolButtonStyle(style)
        # self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu = QtWidgets.QMenu(self)

        action_1 = menu.addAction("First action")
        action_2 = menu.addAction("Second action")
        menu.addSeparator()
        action_3 = menu.addAction("Third action")
        self.setMenu(menu)


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
