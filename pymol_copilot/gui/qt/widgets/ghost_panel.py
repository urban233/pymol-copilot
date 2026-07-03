from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt.widgets import command_bar


class GhostPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 1. Root layout for HoverOverlay itself
        self._root_layout = QtWidgets.QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)

        # 2. Visual content container
        self._content_frame = QtWidgets.QFrame()
        self._main_layout = QtWidgets.QVBoxLayout(self._content_frame)
        # Padding inside the panel
        self._main_layout.setContentsMargins(10, 10, 10, 10)

        # Add the visual frame to the root layout
        self._root_layout.addWidget(self._content_frame)

        self._setup_opacity_animation()
        self._set_style()

    def set_content(self, content: QtWidgets.QWidget):
        self._main_layout.addWidget(content)
        # Force the overlay to shrink-wrap strictly to what its content demands
        self.adjustSize()

    def _set_style(self):
        self._content_frame.setObjectName(theme.StyleId.PANEL_SURFACE)

    def _setup_opacity_animation(self):
        # 2. Create an opacity effect and apply it to this widget
        self.opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # Set default idle opacity (Semi-transparent)
        self.opacity_effect.setOpacity(0.2)

        # 3. Set up the fade animation
        self.animation = QtCore.QPropertyAnimation(
            self.opacity_effect, b"opacity"
        )
        # 250ms (Standard Material Design speed)
        self.animation.setDuration(350)
        self.animation.setEasingCurve(QtCore.QEasingCurve.Type.InOutQuad)

    def enterEvent(self, event):
        """Triggered when mouse enters the widget"""
        self.animation.stop()
        self.animation.setEndValue(0.90)  # Fade to near-solid
        self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Triggered when mouse leaves the widget"""
        self.animation.stop()
        self.animation.setEndValue(0.2)  # Fade back to semi-transparent
        self.animation.start()
        super().leaveEvent(event)


class GhostBar(GhostPanel):
    def __init__(self, command_buttons: list[command_bar.CommandBarButton], parent=None):
        super().__init__(parent)
        self._command_bar = command_bar.CommandBar(command_buttons, parent=self)
        self.set_content(self._command_bar)
        # self._content_frame.setObjectName(theme.StyleId.GHOST_BAR)
