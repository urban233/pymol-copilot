from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme


class Button(QtWidgets.QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._init_widget()
        self._set_styles()

    def _init_widget(self) -> None:
        raise NotImplementedError

    def _set_styles(self) -> None:
        raise NotImplementedError


class BasicButton(Button):

    def _init_widget(self) -> None:
        pass

    def _set_styles(self) -> None:
        self.setObjectName(theme.StyleId.BASIC_BUTTON)


class AccentButton(Button):

    def _init_widget(self) -> None:
        pass

    def _set_styles(self) -> None:
        self.setObjectName(theme.StyleId.ACCENT_BUTTON)
