"""Provides an input bar widget for prompting the AI assistant."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import icons
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.widgets import button
from pymol_copilot.gui.qt.widgets import text_box


class InputBar(QtWidgets.QWidget):
    """Input bar widget containing a text box and send button."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the input bar.

        Args:
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
        tmp_shadow_effect.setBlurRadius(10)
        tmp_shadow_effect.setOffset(2, 2)
        tmp_shadow_effect.setColor(QtGui.QColor(0, 0, 0, 10))
        self._outer_frame.setGraphicsEffect(tmp_shadow_effect)
        self.setObjectName(theme.StyleId.INPUT_BAR)

    def _init_widget(self) -> None:
        """Initialize and lay out the child widgets."""
        self._layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        self._layout_outer_frame.setContentsMargins(
            *ui_defaults.default_contents_margins()
        )

        self._layout.addWidget(self._input)
        self._layout.addWidget(self._send_button)
        self._outer_frame.setLayout(self._layout)
        self._layout_outer_frame.addWidget(self._outer_frame)
        self.setLayout(self._layout_outer_frame)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
