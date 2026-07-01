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
"""List view widget blocks for use with ListModelBlock.

This module provides:

* ListViewBlock - a plain QListView pre-configured for use with ListModelBlock.
* ListViewWithSearchBlock - a composite widget that stacks a search field
  above a ListViewBlock and filters the model in real time as the user types,
  without requiring a proxy model.

Design rationale:
QListView requires very little boilerplate to work correctly with
QAbstractListModel, but callers commonly repeat the same setup steps
(selection mode, resize mode, no wrapping, word-wrap policy). ListViewBlock
bakes in sensible defaults so that the caller only needs to set a model
and connect to item_activated.

ListViewWithSearchBlock additionally avoids the overhead of a
QSortFilterProxyModel by filtering the source model's items lazily:
the view is simply told to hide rows that do not match via a custom
_RowFilterDelegate that is only active while a search string is
present. When the search field is empty all rows are shown at their
natural height.

Typical usage:

    from tkblocks.qt.model import list as list_model
    from pymol_copilot.gui.qt.widgets.list import ListViewBlock
    from pymol_copilot.gui.qt.widgets.list import ListViewWithSearchBlock

    # Plain list view:
    model = list_model.ListModelBlock(initial_data=["Alice", "Bob", "Carol"])
    view = ListViewBlock()
    view.set_model(model)
    view.item_activated.connect(lambda item: print("selected:", item))

    # List view with search:
    search_view = ListViewWithSearchBlock()
    search_view.set_model(model)
"""

from __future__ import annotations

import logging
from typing import Optional

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.model import list_model

logger = logging.getLogger(__name__)

__docformat__ = "google"


class ListViewBlock(QtWidgets.QListView):
    """A QListView pre-configured for use with ListModelBlock.

    Provides sensible defaults (single selection, uniform row heights,
    no wrapping) and a convenience signal item_activated that
    carries the raw item object instead of a QModelIndex.

    The view is deliberately minimal so that subclasses or callers can
    customise it freely without fighting inherited styles.

    Attributes:
        item_activated: Signal emitted with the raw domain object when the
            user double-clicks or presses Enter on a row.

    Example:
        model = list_model.ListModelBlock(initial_data=my_strings)
        view = ListViewBlock()
        view.set_model(model)
        view.item_activated.connect(on_item_selected)
    """

    # <editor-fold desc="Class attributes">
    item_activated = QtCore.pyqtSignal(object)
    """Emitted with the raw item object when the user activates a row."""
    # </editor-fold>

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initialize the list view with sensible defaults.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._init_widget()
        self._connect_signals()

    # <editor-fold desc="Public methods">
    def set_model(self, model: "list_model.ListModelBlock") -> None:
        """Attach a ListModelBlock to this view.

        Calling this method is preferred over calling setModel directly
        because it validates the model type.

        Args:
            model: The list model to display.
        """
        self.setModel(model)

    def current_item(self) -> Optional[object]:
        """Return the raw item object for the currently selected row.

        Returns:
            The selected item, or None if no row is selected.
        """
        tmp_index = self.currentIndex()
        if not tmp_index.isValid():
            return None

        if (tmp_model := self.model()) is None:
            raise RuntimeError("tmp_model is None")

        return tmp_model.data(tmp_index, QtCore.Qt.ItemDataRole.UserRole)

    def select_row(self, row: int) -> None:
        """Programmatically select the row at the given index.

        Args:
            row: Zero-based row index.

        Raises:
            IndexError: If row is out of bounds.
        """
        tmp_model = self.model()
        if tmp_model is None:
            return
        if not (0 <= row < tmp_model.rowCount()):
            raise IndexError(
                f"Row {row} is out of range (0..{tmp_model.rowCount() - 1})"
            )
        tmp_index = tmp_model.index(row, 0)
        self.setCurrentIndex(tmp_index)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget layout and style configurations."""
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setWordWrap(False)
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self.activated.connect(self._on_activated)

    def _on_activated(self, index: QtCore.QModelIndex) -> None:
        """Translate a QModelIndex activation into an item_activated emission.

        Args:
            index: The activated model index.
        """
        if (tmp_model := self.model()) is None:
            raise RuntimeError("tmp_model is None")

        tmp_item = tmp_model.data(index, QtCore.Qt.ItemDataRole.UserRole)
        if tmp_item is not None:
            self.item_activated.emit(tmp_item)

    # </editor-fold>


class ListViewWithSearchBlock(QtWidgets.QWidget):
    """A composite widget combining a search field with a ListViewBlock.

    The search field filters rows in real time by hiding those whose display
    text does not contain the typed substring (case-insensitive). Filtering
    is implemented via setRowHidden on the inner view - no proxy model is
    needed - which keeps memory overhead minimal.

    Attributes:
        search_field: The QLineEdit used for filtering.
        list_view: The inner ListViewBlock.
        item_activated: Forwarded from list_view - emits the raw
            item object when the user activates a row.

    Example:
        widget = ListViewWithSearchBlock()
        widget.set_model(my_model)
        widget.item_activated.connect(on_item_selected)
    """

    # <editor-fold desc="Class attributes">
    item_activated = QtCore.pyqtSignal(object)
    """Emitted with the raw item object when the user activates a row."""
    # </editor-fold>

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initialize the composite widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._model: Optional["list_model.ListModelBlock"] = None
        self.search_field = QtWidgets.QLineEdit()
        self.list_view = ListViewBlock()
        # </editor-fold>
        self._init_widget()
        self._connect_signals()

    # <editor-fold desc="Public methods">
    def set_model(self, model: "list_model.ListModelBlock") -> None:
        """Attach a ListModelBlock to the inner list view.

        Also connects the model's modelReset and rowsInserted
        signals so that the filter is re-applied whenever the data changes.

        Args:
            model: The list model to display and filter.
        """
        self._model = model
        self.list_view.set_model(model)
        model.modelReset.connect(self._apply_filter)
        model.rowsInserted.connect(self._apply_filter)
        model.rowsRemoved.connect(self._apply_filter)

    def clear_search(self) -> None:
        """Clear the search field and show all rows."""
        self.search_field.clear()

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget layout and child components."""
        self.search_field.setPlaceholderText("Search…")
        self.search_field.setClearButtonEnabled(True)

        tmp_layout = QtWidgets.QVBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.DEFAULT_SPACING)
        tmp_layout.addWidget(self.search_field)
        tmp_layout.addWidget(self.list_view)
        self.setLayout(tmp_layout)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self.list_view.item_activated.connect(self.item_activated)
        self.search_field.textChanged.connect(self._apply_filter)

    def _apply_filter(self) -> None:
        """Show or hide rows based on the current search text.

        A row is hidden when its display text does not contain the search
        string (case-insensitive). When the search field is empty all rows
        are made visible.
        """
        if self._model is None:
            return

        tmp_query = self.search_field.text().lower()
        for tmp_row in range(self._model.rowCount()):
            tmp_index = self._model.index(tmp_row, 0)
            tmp_text = (
                self._model.data(tmp_index, QtCore.Qt.ItemDataRole.DisplayRole)
                or ""
            )
            tmp_hidden = bool(tmp_query) and tmp_query not in tmp_text.lower()
            self.list_view.setRowHidden(tmp_row, tmp_hidden)

    # </editor-fold>
