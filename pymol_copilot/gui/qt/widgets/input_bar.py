from pymol_copilot.gui.qt import QtGui, icons
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.widgets import text_box, button


class InputBar(QtWidgets.QWidget):
    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the inout bar.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._outer_frame: QtWidgets.QFrame = QtWidgets.QFrame()
        self._layout_outer_frame: QtWidgets.QVBoxLayout = (
            QtWidgets.QVBoxLayout()
        )
        self._layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout()
        self._input = text_box.ExpandingTextBox()
        self._send_button = button.CircleIconButton(
            icons.icon("pymol_copilot.gui.qt", "arrow_upward")
        )
        self._init_widget()
        self._set_styles()

    def _set_styles(self) -> None:
        """Apply the global theme object names and shadow effects."""
        self._outer_frame.setObjectName(theme.StyleId.INPUT_BAR)
        tmp_shadow_effect = QtWidgets.QGraphicsDropShadowEffect()
        tmp_shadow_effect.setBlurRadius(20)
        tmp_shadow_effect.setOffset(3, 3)
        tmp_shadow_effect.setColor(QtGui.QColor(0, 0, 0, 30))
        self._outer_frame.setGraphicsEffect(tmp_shadow_effect)
        self.setObjectName(theme.StyleId.INPUT_BAR)

    def _init_widget(self) -> None:
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self._layout.addWidget(self._input)
        self._layout.addWidget(self._send_button)
        self._outer_frame.setLayout(self._layout)
        self._layout_outer_frame.addWidget(self._outer_frame)
        self.setLayout(self._layout_outer_frame)
