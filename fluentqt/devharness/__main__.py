"""Development harness entry point."""

from __future__ import annotations

import sys

from PyQt6 import QtGui
from PyQt6 import QtWidgets

import fluentqt.core.factory as factory_module
import fluentqt.devharness.pages.composites_page as composites_page
import fluentqt.devharness.pages.primitives_page as primitives_page
import fluentqt.devharness.pages.states_page as states_page
import fluentqt.devharness.pages.themes_page as themes_page
import fluentqt.enums.roles as roles_module
import fluentqt.primitives.frame as frame_module


def _mock_icon_provider(name: str) -> QtGui.QIcon:
    """Return a simple solid QIcon for testing.

    Args:
        name: Name of the icon.

    Returns:
        The generated QIcon.
    """
    _ = name
    tmp_pix = QtGui.QPixmap(24, 24)
    tmp_pix.fill(QtGui.QColor("#0067c0"))
    return QtGui.QIcon(tmp_pix)


class MainWindow(QtWidgets.QMainWindow):
    """Main window of the development harness."""

    def __init__(self) -> None:
        """Initialize the MainWindow."""
        super().__init__()

        self.setWindowTitle("fluentqt Developer Harness")
        self.resize(1000, 700)

        # Set central container frame using token styling
        tmp_central_frame = frame_module.TokenFrame(
            elevation=roles_module.ElevationPreset.Flat,
            fill_role=roles_module.FillRole.Transparent,
            parent=self,
        )
        self.setCentralWidget(tmp_central_frame)

        tmp_main_layout = QtWidgets.QHBoxLayout(tmp_central_frame)
        tmp_main_layout.setContentsMargins(10, 10, 10, 10)
        tmp_main_layout.setSpacing(10)

        # Sidebar navigation list
        self._sidebar = QtWidgets.QListWidget(tmp_central_frame)
        self._sidebar.setFixedWidth(180)
        self._sidebar.addItems(["Primitives", "States", "Composites", "Themes"])
        tmp_main_layout.addWidget(self._sidebar)

        # Right-side page stack
        self._stacked_widget = QtWidgets.QStackedWidget(tmp_central_frame)
        tmp_main_layout.addWidget(self._stacked_widget)

        # Add pages to stack
        self._primitives_page = primitives_page.PrimitivesPage(
            parent=self._stacked_widget
        )
        self._states_page = states_page.StatesPage(parent=self._stacked_widget)
        self._composites_page = composites_page.CompositesPage(
            parent=self._stacked_widget
        )
        self._themes_page = themes_page.ThemesPage(parent=self._stacked_widget)

        self._stacked_widget.addWidget(self._primitives_page)
        self._stacked_widget.addWidget(self._states_page)
        self._stacked_widget.addWidget(self._composites_page)
        self._stacked_widget.addWidget(self._themes_page)

        # Navigation connection
        self._sidebar.currentRowChanged.connect(
            self._stacked_widget.setCurrentIndex
        )
        self._sidebar.setCurrentRow(0)


def main() -> None:
    """Execute the development harness application."""
    # Register mock icon provider at startup
    factory_module.register_icon_provider(_mock_icon_provider)

    tmp_app = QtWidgets.QApplication.instance()
    if tmp_app is None:
        tmp_app = QtWidgets.QApplication(sys.argv)

    tmp_window = MainWindow()
    tmp_window.show()
    sys.exit(tmp_app.exec())


if __name__ == "__main__":
    main()
