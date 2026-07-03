"""Module for the custom color grid widget."""

import logging
from typing import Callable

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.widgets import button
from pymol_copilot.gui.qt.widgets import flyout

logger = logging.getLogger(__name__)


def generate_color_stylesheet(hex_color: str) -> str:
    """Generates a color stylesheet for a QPushButton.

    Args:
        hex_color: The background color in hexadecimal format.

    Returns:
        The generated stylesheet string.

    Raises:
        ValueError: If hex_color is None or empty.
    """
    if hex_color is None or hex_color == "":
        raise ValueError("a_hex_color is either None or an empty string.")

    tmp_stylesheet = """QPushButton {
                background-color: %s;
                border: solid;
                border-width: 1px;
                border-radius: 4px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
            }
            QPushButton::hover {
                background-color: %s;
                border: solid;
                border-color: black;
                border-width: 2px;
                border-radius: 4px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
            }
        """ % (hex_color, hex_color)
    return tmp_stylesheet


class PyMOLColorGrid(QtWidgets.QWidget):
    """Class representing the color grid of PyMOL."""

    def __init__(self) -> None:
        """Initialize the PyMOL color grid widget and its buttons."""
        super().__init__()
        tmp_grid = QtWidgets.QGridLayout()
        self.setLayout(tmp_grid)

        # Colors - Reds
        self.c_red = QtWidgets.QPushButton()
        self.c_tv_red = QtWidgets.QPushButton()
        self.c_salmon = QtWidgets.QPushButton()
        self.c_raspberry = QtWidgets.QPushButton()

        self.c_red.setStyleSheet(generate_color_stylesheet("#ff0000"))
        self.c_tv_red.setStyleSheet(generate_color_stylesheet("#ff3333"))
        self.c_salmon.setStyleSheet(generate_color_stylesheet("#ff9999"))
        self.c_raspberry.setStyleSheet(generate_color_stylesheet("#b24c66"))

        tmp_grid.addWidget(self.c_red, 0, 0)
        tmp_grid.addWidget(self.c_tv_red, 1, 0)
        tmp_grid.addWidget(self.c_salmon, 2, 0)
        tmp_grid.addWidget(self.c_raspberry, 3, 0)

        # Colors - Greens
        self.c_green = QtWidgets.QPushButton()
        self.c_tv_green = QtWidgets.QPushButton()
        self.c_palegreen = QtWidgets.QPushButton()
        self.c_forest = QtWidgets.QPushButton()

        self.c_green.setStyleSheet(generate_color_stylesheet("#00ff00"))
        self.c_tv_green.setStyleSheet(generate_color_stylesheet("#33ff33"))
        self.c_palegreen.setStyleSheet(generate_color_stylesheet("#a5e5a5"))
        self.c_forest.setStyleSheet(generate_color_stylesheet("#339933"))

        tmp_grid.addWidget(self.c_green, 0, 1)
        tmp_grid.addWidget(self.c_tv_green, 1, 1)
        tmp_grid.addWidget(self.c_palegreen, 2, 1)
        tmp_grid.addWidget(self.c_forest, 3, 1)

        # Colors - Blues
        self.c_blue = QtWidgets.QPushButton()
        self.c_tv_blue = QtWidgets.QPushButton()
        self.c_lightblue = QtWidgets.QPushButton()
        self.c_skyblue = QtWidgets.QPushButton()

        self.c_blue.setStyleSheet(generate_color_stylesheet("#0000ff"))
        self.c_tv_blue.setStyleSheet(generate_color_stylesheet("#4c4cff"))
        self.c_lightblue.setStyleSheet(generate_color_stylesheet("#bfbfff"))
        self.c_skyblue.setStyleSheet(generate_color_stylesheet("#337fcc"))

        tmp_grid.addWidget(self.c_blue, 0, 2)
        tmp_grid.addWidget(self.c_tv_blue, 1, 2)
        tmp_grid.addWidget(self.c_lightblue, 2, 2)
        tmp_grid.addWidget(self.c_skyblue, 3, 2)

        # Colors - Yellows
        self.c_yellow = QtWidgets.QPushButton()
        self.c_tv_yellow = QtWidgets.QPushButton()
        self.c_paleyellow = QtWidgets.QPushButton()
        self.c_sand = QtWidgets.QPushButton()

        self.c_yellow.setStyleSheet(generate_color_stylesheet("#ffff00"))
        self.c_tv_yellow.setStyleSheet(generate_color_stylesheet("#ffff33"))
        self.c_paleyellow.setStyleSheet(generate_color_stylesheet("#ffff7f"))
        self.c_sand.setStyleSheet(generate_color_stylesheet("#b78c4c"))

        tmp_grid.addWidget(self.c_yellow, 0, 3)
        tmp_grid.addWidget(self.c_tv_yellow, 1, 3)
        tmp_grid.addWidget(self.c_paleyellow, 2, 3)
        tmp_grid.addWidget(self.c_sand, 3, 3)

        # Colors - Magentas
        self.c_magenta = QtWidgets.QPushButton()
        self.c_purple = QtWidgets.QPushButton()
        self.c_pink = QtWidgets.QPushButton()
        self.c_hotpink = QtWidgets.QPushButton()

        self.c_magenta.setStyleSheet(generate_color_stylesheet("#ff00ff"))
        self.c_purple.setStyleSheet(generate_color_stylesheet("#bf00bf"))
        self.c_pink.setStyleSheet(generate_color_stylesheet("#ffa5d8"))
        self.c_hotpink.setStyleSheet(generate_color_stylesheet("#ff007f"))

        tmp_grid.addWidget(self.c_magenta, 0, 4)
        tmp_grid.addWidget(self.c_purple, 1, 4)
        tmp_grid.addWidget(self.c_pink, 2, 4)
        tmp_grid.addWidget(self.c_hotpink, 3, 4)

        # Colors - Cyan
        self.c_cyan = QtWidgets.QPushButton()
        self.c_aquamarine = QtWidgets.QPushButton()
        self.c_palecyan = QtWidgets.QPushButton()
        self.c_teal = QtWidgets.QPushButton()

        self.c_cyan.setStyleSheet(generate_color_stylesheet("#00ffff"))
        self.c_aquamarine.setStyleSheet(generate_color_stylesheet("#7fffff"))
        self.c_palecyan.setStyleSheet(generate_color_stylesheet("#ccffff"))
        self.c_teal.setStyleSheet(generate_color_stylesheet("#00bfbf"))

        tmp_grid.addWidget(self.c_cyan, 0, 5)
        tmp_grid.addWidget(self.c_aquamarine, 1, 5)
        tmp_grid.addWidget(self.c_palecyan, 2, 5)
        tmp_grid.addWidget(self.c_teal, 3, 5)

        # Colors - Orange
        self.c_orange = QtWidgets.QPushButton()
        self.c_tv_orange = QtWidgets.QPushButton()
        self.c_lightorange = QtWidgets.QPushButton()
        self.c_olive = QtWidgets.QPushButton()

        self.c_orange.setStyleSheet(generate_color_stylesheet("#ff7f00"))
        self.c_tv_orange.setStyleSheet(generate_color_stylesheet("#ff8c26"))
        self.c_lightorange.setStyleSheet(generate_color_stylesheet("#ffcc7f"))
        self.c_olive.setStyleSheet(generate_color_stylesheet("#c4b200"))

        tmp_grid.addWidget(self.c_orange, 0, 6)
        tmp_grid.addWidget(self.c_tv_orange, 1, 6)
        tmp_grid.addWidget(self.c_lightorange, 2, 6)
        tmp_grid.addWidget(self.c_olive, 3, 6)

        # Colors - Grays
        self.c_white = QtWidgets.QPushButton()
        self.c_grey_70 = QtWidgets.QPushButton()
        self.c_grey_30 = QtWidgets.QPushButton()
        self.c_black = QtWidgets.QPushButton()

        self.c_white.setStyleSheet(generate_color_stylesheet("#ffffff"))
        self.c_grey_70.setStyleSheet(generate_color_stylesheet("#b2b2b2"))
        self.c_grey_30.setStyleSheet(generate_color_stylesheet("#4c4c4c"))
        self.c_black.setStyleSheet(generate_color_stylesheet("#000000"))

        tmp_grid.addWidget(self.c_white, 0, 7)
        tmp_grid.addWidget(self.c_grey_70, 1, 7)
        tmp_grid.addWidget(self.c_grey_30, 2, 7)
        tmp_grid.addWidget(self.c_black, 3, 7)

        self.set_all_tooltips()
        # Build the button lookup dict once; avoids dir() at runtime.
        self._color_buttons: dict[str, QtWidgets.QPushButton] = {
            tmp_widget.toolTip(): tmp_widget
            for tmp_attr_name in vars(self)
            if tmp_attr_name.startswith("c_")
            and isinstance(
                tmp_widget := getattr(self, tmp_attr_name),
                QtWidgets.QPushButton,
            )
        }

    # <editor-fold desc="Public methods">
    def set_all_tooltips(self) -> None:
        """Sets tooltips and objectNames for all color widgets."""
        self.c_red.setToolTip("red")
        self.c_red.setObjectName("color_red")
        self.c_tv_red.setToolTip("tv_red")
        self.c_tv_red.setObjectName("color_tv_red")
        self.c_salmon.setToolTip("salmon")
        self.c_salmon.setObjectName("color_salmon")
        self.c_raspberry.setToolTip("raspberry")
        self.c_raspberry.setObjectName("color_raspberry")

        self.c_green.setToolTip("green")
        self.c_green.setObjectName("color_green")
        self.c_tv_green.setToolTip("tv_green")
        self.c_tv_green.setObjectName("color_tv_green")
        self.c_palegreen.setToolTip("palegreen")
        self.c_palegreen.setObjectName("color_palegreen")
        self.c_forest.setToolTip("forest")
        self.c_forest.setObjectName("color_forest")

        self.c_blue.setToolTip("blue")
        self.c_blue.setObjectName("color_blue")
        self.c_tv_blue.setToolTip("tv_blue")
        self.c_tv_blue.setObjectName("color_tv_blue")
        self.c_lightblue.setToolTip("lightblue")
        self.c_lightblue.setObjectName("color_lightblue")
        self.c_skyblue.setToolTip("skyblue")
        self.c_skyblue.setObjectName("color_skyblue")

        self.c_yellow.setToolTip("yellow")
        self.c_yellow.setObjectName("color_yellow")
        self.c_tv_yellow.setToolTip("tv_yellow")
        self.c_tv_yellow.setObjectName("color_tv_yellow")
        self.c_paleyellow.setToolTip("paleyellow")
        self.c_paleyellow.setObjectName("color_paleyellow")
        self.c_sand.setToolTip("sand")
        self.c_sand.setObjectName("color_sand")

        self.c_magenta.setToolTip("magenta")
        self.c_magenta.setObjectName("color_magenta")
        self.c_purple.setToolTip("purple")
        self.c_purple.setObjectName("color_purple")
        self.c_pink.setToolTip("pink")
        self.c_pink.setObjectName("color_pink")
        self.c_hotpink.setToolTip("hotpink")
        self.c_hotpink.setObjectName("color_hotpink")

        self.c_cyan.setToolTip("cyan")
        self.c_cyan.setObjectName("color_cyan")
        self.c_aquamarine.setToolTip("aquamarine")
        self.c_aquamarine.setObjectName("color_aquamarine")
        self.c_palecyan.setToolTip("palecyan")
        self.c_palecyan.setObjectName("color_palecyan")
        self.c_teal.setToolTip("teal")
        self.c_teal.setObjectName("color_teal")

        self.c_orange.setToolTip("orange")
        self.c_orange.setObjectName("color_orange")
        self.c_tv_orange.setToolTip("tv_orange")
        self.c_tv_orange.setObjectName("color_tv_orange")
        self.c_lightorange.setToolTip("lightorange")
        self.c_lightorange.setObjectName("color_lightorange")
        self.c_olive.setToolTip("olive")
        self.c_olive.setObjectName("color_olive")

        self.c_white.setToolTip("white")
        self.c_white.setObjectName("color_white")
        self.c_grey_70.setToolTip("grey70")
        self.c_grey_70.setObjectName("color_grey70")
        self.c_grey_30.setToolTip("grey30")
        self.c_grey_30.setObjectName("color_grey30")
        self.c_black.setToolTip("black")
        self.c_black.setObjectName("color_black")

    def get_all_color_buttons(self) -> dict[str, QtWidgets.QPushButton]:
        """Return a dictionary of all color buttons, mapped by tooltip names.

        Returns:
            A copy of the pre-built mapping of tooltip string to QPushButton.
        """
        return dict(self._color_buttons)

    # </editor-fold>


class _RecentColorsGrid(QtWidgets.QWidget):
    """Widget for displaying recent colors."""

    def __init__(
        self,
        callback: Callable | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initializes the _RecentColorsGrid widget.

        Args:
            callback: Optional callback function triggered on color selection.
            parent: Optional parent widget.
        """
        super().__init__(parent=parent)
        self._recent_colors_layout = QtWidgets.QGridLayout()
        self._recent_colors_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._recent_colors_layout.setSpacing(ui_defaults.default_spacing())
        self.setLayout(self._recent_colors_layout)

        # <editor-fold desc="Instance attributes">
        # Track colors inside a list (8 slots initialized to #ffffff)
        self.recent_colors_list: list[str] = ["#ffffff"] * 8
        self._buttons: list[QtWidgets.QPushButton] = []
        # </editor-fold>

        self._init_widget(callback)

    # <editor-fold desc="Private methods">
    def _init_widget(self, callback: Callable | None) -> None:
        """Initializes the layout and buttons.

        Args:
            callback: Optional callback function triggered on color selection.
        """
        for tmp_i in range(8):
            tmp_btn = QtWidgets.QPushButton()
            tmp_btn.setStyleSheet(generate_color_stylesheet("#ffffff"))

            if callback:
                # Dynamically fetch the current hex value assigned to this
                # specific slot index on click
                tmp_btn.clicked.connect(
                    lambda _, tmp_idx=tmp_i: callback(
                        self.recent_colors_list[tmp_idx]
                    )
                )

            self._recent_colors_layout.addWidget(tmp_btn, 0, tmp_i)
            self._buttons.append(tmp_btn)

    # </editor-fold>

    # <editor-fold desc="Public methods">
    def add_recent_color(self, hex_color: str) -> None:
        """Inserts a new color at the front, shifting the older colors down.

        Args:
            hex_color: The new color in hexadecimal format.
        """
        # Insert at the beginning (Index 0) and drop the last item (Index 7)
        self.recent_colors_list.insert(0, hex_color)
        self.recent_colors_list.pop()

        # Update the visual UI stylesheets of all buttons to match
        # the updated order
        for tmp_btn, tmp_color in zip(
            self._buttons, self.recent_colors_list, strict=True
        ):
            tmp_btn.setStyleSheet(generate_color_stylesheet(tmp_color))

    # </editor-fold>


class ColorFlyout(flyout.FlyoutFrame):
    """Flyout panel displaying the PyMOL color grid."""

    color_selected: QtCore.pyqtSignal = QtCore.pyqtSignal(str)
    """Emitted with the hex color string when a recent color is selected."""

    def __init__(self) -> None:
        """Initialize the ColorFlyout widget."""
        super().__init__(shadow=False)
        # <editor-fold desc="Instance attributes">
        self._content = QtWidgets.QWidget()
        self._color_grid_label = QtWidgets.QLabel("PyMOL Colors")
        self._color_grid = PyMOLColorGrid()
        self._more_colors_button = button.BasicButton("More Colors")
        self._recent_colors_label = QtWidgets.QLabel("Recent Colors")

        # Passed active click handler slot to recent colors grid
        self._recent_colors_grid = _RecentColorsGrid(
            callback=self.__slot_recent_color_selected
        )
        # </editor-fold>
        tmp_layout = QtWidgets.QVBoxLayout(self._content)
        self._init_widget(tmp_layout)
        self._connect_signals()

    # <editor-fold desc="Private methods">
    def _init_widget(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Initializes the layout of the flyout.

        Args:
            layout: The main layout of the flyout content.
        """
        layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        layout.addWidget(self._color_grid_label)
        layout.addWidget(self._color_grid)
        layout.addWidget(self._recent_colors_label)
        layout.addWidget(self._recent_colors_grid)
        tmp_horizontal_layout = QtWidgets.QHBoxLayout()
        tmp_horizontal_layout.addWidget(self._more_colors_button)
        tmp_horizontal_layout.addStretch()
        layout.addLayout(tmp_horizontal_layout)
        self.set_content(self._content)

    def _connect_signals(self) -> None:
        """Connects signals to their respective slots."""
        self._more_colors_button.clicked.connect(self.__slot_open_color_picker)

    # </editor-fold>

    # <editor-fold desc="Private slots">
    def __slot_open_color_picker(self) -> None:
        """Opens the color picker dialog and handles the selected color."""
        tmp_color_picker_dialog = QtWidgets.QColorDialog(self)
        # Execute the dialog and check if the user confirmed/accepted a choice
        if (
            tmp_color_picker_dialog.exec()
            == QtWidgets.QDialog.DialogCode.Accepted
        ):
            tmp_color = tmp_color_picker_dialog.selectedColor()
            if tmp_color.isValid():
                # .name() returns the standard hexadecimal string format
                # (e.g., "#ff0000")
                self._recent_colors_grid.add_recent_color(tmp_color.name())

    def __slot_recent_color_selected(self, hex_color: str) -> None:
        """Triggered whenever a user clicks on a recent color slot.

        Args:
            hex_color: The selected color in hexadecimal format.
        """
        logger.debug("Recent color selected: %s", hex_color)
        self.color_selected.emit(hex_color)

    # </editor-fold>
