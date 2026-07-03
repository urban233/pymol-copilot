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
"""Provide table view widgets for table models.

This module provides TableView (a QTableView pre-configured for use with
table_model.TableModel and SortFilterProxy) and TableViewWithToolbar (a composite widget
that places a configurable toolbar row above a TableView). The toolbar contains a search
field that filters rows in real time via a SortFilterProxy and an optional area for
custom action buttons.

Notes:
    Design rationale:
    QTableView starts with many UI affordances switched on (grid lines,
    stretch-last-column, alternating row colors) that callers then have to
    turn off one by one. TableView inverts this: it starts from
    a clean baseline and lets callers opt-in to extras.

TableViewWithToolbar follows the same pattern used by
ListViewWithSearchBlock: filtering happens via QSortFilterProxyModel rather than
row-hiding because table data usually has enough columns that a proxy's index
mapping is the correct abstraction.

Example:
    Typical usage:

    from pymol_copilot.gui.qt.model import table_model
    from pymol_copilot.gui.qt.widgets import table_view

    class JobTableModel(table_model.TableModel):
        def _cell_data(self, item, column):
            return [item.name, item.status, item.project][column]

    model = JobTableModel(column_headers=["Name", "Status", "Project"])
    model.add_rows(jobs)

    # Plain table:
    view = table_view.TableView()
    view.set_model(model)

    # Table with toolbar search + proxy:
    combo = table_view.TableViewWithToolbar(filter_column=1)
    combo.set_model(model)
"""

from __future__ import annotations

import logging
from typing import Optional

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.model import table_model

logger = logging.getLogger(__name__)

__docformat__ = "google"


class TableView(QtWidgets.QTableView):
    """A QTableView pre-configured for use with TableModel.

    Starts from a minimal-chrome baseline:
    Alternating row colors are disabled (easy to re-enable via stylesheet).
    Grid lines are hidden.
    Horizontal header stretches the last column to fill available space.
    Vertical header is hidden (row numbers are rarely useful).
    Single-row selection mode is active.
    No in-place editing is permitted.
    Rows resize to content and columns are resized interactively by the user.

    Subclasses or callers can override any of these after construction.

    Attributes:
        row_activated: Signal emitted with the raw domain object when the
            user double-clicks or presses Enter on a row.

    Example:
        model = MyTableModel(column_headers=["Name", "Value"])
        view = TableView()
        view.set_model(model)
        view.row_activated.connect(lambda item: print(item))
    """

    # <editor-fold desc="Class attributes">
    row_activated = QtCore.pyqtSignal(object)
    """Emitted with the raw row item when the user activates a row."""
    # </editor-fold>

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initialize the table view with sensible defaults.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._init_widget()

    # <editor-fold desc="Public methods">
    def set_model(
        self,
        model: table_model.TableModel | table_model.SortFilterProxy,
    ) -> None:
        """Attach a TableModel or SortFilterProxy.

        Passing a proxy is the recommended path when you need sorting or
        multi-criterion filtering; the raw model is fine for simple cases.

        Args:
            model: The model or proxy to display.
        """
        self.setModel(model)

    def current_item(self) -> Optional[object]:
        """Return the raw row item for the currently selected row.

        When a proxy model is active the item is resolved through the proxy.

        Returns:
            The domain object for the selected row, or None if no row is
            selected.
        """
        index: QtCore.QModelIndex = self.currentIndex()
        if not index.isValid():
            return None

        if (tmp_model := self.model()) is None:
            raise RuntimeError("tmp_model is None")

        return tmp_model.data(index, QtCore.Qt.ItemDataRole.UserRole)

    def resize_columns_to_content(self) -> None:
        """Resize all columns to fit their current content.

        Calls resizeColumnsToContents on the underlying QTableView
        and is provided as a convenience alias with a more Pythonic name.
        """
        self.resizeColumnsToContents()

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget layout and child components."""
        # --- Selection & edit policy ---
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )

        # --- Visual chrome ---
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setSortingEnabled(True)

        # --- Header configuration ---
        if (horizontal_header := self.horizontalHeader()) is None:
            raise RuntimeError("self.horizontalHeader is None")
        horizontal_header.setStretchLastSection(True)
        horizontal_header.setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Interactive
        )

        if (vertical_header := self.verticalHeader()) is None:
            raise RuntimeError("self.verticalHeader is None")
        vertical_header.setVisible(False)
        vertical_header.setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )

        self.activated.connect(self._on_activated)

    def _on_activated(self, index: QtCore.QModelIndex) -> None:
        """Translate a QModelIndex activation into a row_activated emission.

        Args:
            index: The activated model index.
        """
        if (tmp_model := self.model()) is None:
            raise RuntimeError("self.model() is None")
        if (
            tmp_item := tmp_model.data(index, QtCore.Qt.ItemDataRole.UserRole)
        ) is None:
            raise RuntimeError("tmp_item is None")

        self.row_activated.emit(tmp_item)

    # </editor-fold>


class TableViewWithToolbar(QtWidgets.QWidget):
    """A composite widget combining a toolbar with a TableView.

    The toolbar row contains a QLineEdit search field that filters displayed
    rows in real time using a SortFilterProxy, and a right-aligned
    QHBoxLayout slot (toolbar_actions_layout) where callers can insert custom
    QPushButton or QAction widgets.

    The search field filters by exact substring match (case-insensitive)
    against the display text of the column specified by filter_column.
    Set filter_column to -1 to disable the search field.

    Attributes:
        search_field: The QLineEdit for live filtering.
        table_view: The inner TableView.
        toolbar_actions_layout: Right-aligned QHBoxLayout for custom buttons.
        row_activated: Forwarded from table_view.

    Example:
        combo = TableViewWithToolbar(filter_column=2)
        combo.set_model(my_table_model)

        refresh_btn = QPushButton("Refresh")
        combo.toolbar_actions_layout.addWidget(refresh_btn)
    """

    # <editor-fold desc="Class attributes">
    row_activated = QtCore.pyqtSignal(object)
    """Emitted with the raw row item when the user activates a row."""
    # </editor-fold>

    def __init__(
        self,
        filter_column: int = 0,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Initialize the composite table widget.

        Args:
            filter_column: The zero-based column index whose display text is
                used for live filtering.  Pass -1 to hide the search
                field entirely.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._filter_column: int = filter_column
        self._proxy: table_model.SortFilterProxy | None = None
        self.search_field: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.toolbar_actions_layout: QtWidgets.QHBoxLayout = (
            QtWidgets.QHBoxLayout()
        )
        self.table_view: TableView = TableView()
        # </editor-fold>
        self._init_widget()
        self._connect_signals()

    # <editor-fold desc="Public methods">
    def set_model(self, model: table_model.TableModel) -> None:
        """Attach a TableModel and wire up the search proxy.

        A SortFilterProxy is created automatically and set as the view's
        model. The raw model is set as the proxy's source model.

        Args:
            model: The table model to display and filter.
        """
        self._proxy = table_model.SortFilterProxy()
        self._proxy.setSourceModel(model)

        if self._filter_column >= 0:
            self._proxy.set_filter_column(self._filter_column)

        self.table_view.set_model(self._proxy)

    def current_item(self) -> Optional[object]:
        """Return the raw row item for the currently selected row.

        Resolves the proxy mapping automatically.

        Returns:
            The domain object for the selected row, or None if no row is
            selected.
        """
        return self.table_view.current_item()

    def add_action_button(self, button: QtWidgets.QAbstractButton) -> None:
        """Add a button to the right side of the toolbar.

        Args:
            button: The button widget to add.
        """
        self.toolbar_actions_layout.addWidget(button)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget layout and child components."""
        self.search_field.setPlaceholderText("Search ...")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setVisible(self._filter_column >= 0)

        self.toolbar_actions_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self.toolbar_actions_layout.setSpacing(ui_defaults.DEFAULT_SPACING)

        toolbar_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        toolbar_layout.setSpacing(ui_defaults.DEFAULT_SPACING * 2)
        toolbar_layout.addWidget(self.search_field, stretch=1)
        toolbar_layout.addLayout(self.toolbar_actions_layout)

        root_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        root_layout.setSpacing(ui_defaults.DEFAULT_SPACING)
        root_layout.addLayout(toolbar_layout)
        root_layout.addWidget(self.table_view)
        self.setLayout(root_layout)

    def _connect_signals(self) -> None:
        """Connect internal widget signals."""
        self.table_view.row_activated.connect(self.row_activated)
        self.search_field.textChanged.connect(self._on_search_text_changed)

    def _on_search_text_changed(self, text: str) -> None:
        """Update the proxy filter when the search text changes.

        Uses a QSortFilterProxyModel text filter for substring matching.
        An empty string resets the filter (all rows visible).

        Args:
            text: The current text in the search field.
        """
        if self._proxy is None:
            return

        self._proxy.setFilterCaseSensitivity(
            QtCore.Qt.CaseSensitivity.CaseInsensitive
        )
        self._proxy.setFilterFixedString(text)
        self._proxy.setFilterKeyColumn(self._filter_column)

    # </editor-fold>
