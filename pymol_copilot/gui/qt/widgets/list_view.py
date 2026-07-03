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
"""List view widgets for use with ListModel.

This module provides:

* ListView - a plain QListView pre-configured for use with ListModel.
* ListViewWithSearch - a composite widget that stacks a search field
  above a ListView and filters the model in real time as the user types,
  without requiring a proxy model.

Design rationale:
QListView requires very little boilerplate to work correctly with
QAbstractListModel, but callers commonly repeat the same setup steps
(selection mode, resize mode, no wrapping, word-wrap policy). ListView
bakes in sensible defaults so that the caller only needs to set a model
and connect to item_activated.

ListViewWithSearch additionally avoids the overhead of a
QSortFilterProxyModel by filtering the source model's items lazily:
the view is simply told to hide rows that do not match via a custom
_RowFilterDelegate that is only active while a search string is
present. When the search field is empty all rows are shown at their
natural height.

Typical usage:

    from pymol_copilot.gui.qt.model import list as list_model
    from pymol_copilot.gui.qt.widgets.list import ListView
    from pymol_copilot.gui.qt.widgets.list import ListViewWithSearch

    # Plain list view:
    model = list_model.ListModel(initial_data=["Alice", "Bob", "Carol"])
    view = ListView()
    view.set_model(model)
    view.item_activated.connect(lambda item: print("selected:", item))

    # List view with search:
    search_view = ListViewWithSearch()
    search_view.set_model(model)
"""

from __future__ import annotations

import logging
from typing import Optional

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.model import list_model


class CheckBoxDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate that draws a checkbox reflecting the item's selection state.

    This delegate overrides paint to dynamically set the check indicator state
    based on whether the row is selected in the parent item view.
    """

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        """Paint the item with a checkbox indicator reflecting selection state.

        Args:
            painter: The QPainter to draw with.
            option: The style options for the item.
            index: The model index of the item.
        """
        tmp_option = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(tmp_option, index)

        # Inject checkbox feature
        tmp_option.features |= (
            QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        )

        # Determine checked status from the parent view's selection model
        tmp_view = self.parent()
        if isinstance(tmp_view, QtWidgets.QAbstractItemView):
            tmp_selection_model = tmp_view.selectionModel()
            if (
                tmp_selection_model is not None
                and tmp_selection_model.isSelected(index)
            ):
                tmp_option.checkState = QtCore.Qt.CheckState.Checked
            else:
                tmp_option.checkState = QtCore.Qt.CheckState.Unchecked

        super().paint(painter, tmp_option, index)

    def editorEvent(
        self,
        event: QtCore.QEvent,
        model: QtCore.QAbstractItemModel,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        """Handle mouse clicks on the checkbox indicator.

        Toggles selection for the clicked row when the checkbox itself is
        clicked, without altering the selection of other rows.

        Args:
            event: The event to handle.
            model: The source model.
            option: The style option.
            index: The model index.

        Returns:
            True if the event was handled and should not be propagated;
            False otherwise.
        """
        if event.type() in (
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.MouseButtonRelease,
            QtCore.QEvent.Type.MouseButtonDblClick,
        ):
            if isinstance(event, QtGui.QMouseEvent):
                tmp_style = (
                    option.widget.style()
                    if option.widget
                    else QtWidgets.QApplication.style()
                )
                if tmp_style is None:
                    return False
                tmp_check_rect = tmp_style.subElementRect(
                    QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator,
                    option,
                    option.widget,
                )
                if tmp_check_rect.contains(event.position().toPoint()):
                    if (
                        event.type() == QtCore.QEvent.Type.MouseButtonPress
                        and event.button() == QtCore.Qt.MouseButton.LeftButton
                    ):
                        tmp_view = self.parent()
                        if isinstance(tmp_view, QtWidgets.QAbstractItemView):
                            tmp_selection_model = tmp_view.selectionModel()
                            if tmp_selection_model is not None:
                                tmp_selection_model.select(
                                    index,
                                    QtCore.QItemSelectionModel.SelectionFlag.Toggle,
                                )
                    return True
        return super().editorEvent(event, model, option, index)


logger = logging.getLogger(__name__)

__docformat__ = "google"


class ListView(QtWidgets.QListView):
    """A QListView pre-configured for use with ListModel.

    Provides sensible defaults (single selection, uniform row heights,
    no wrapping) and a convenience signal item_activated that
    carries the raw item object instead of a QModelIndex.

    The view is deliberately minimal so that subclasses or callers can
    customise it freely without fighting inherited styles.

    Attributes:
        item_activated: Signal emitted with the raw domain object when the
            user double-clicks or presses Enter on a row.

    Example:
        model = list_model.ListModel(initial_data=my_strings)
        view = ListView()
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
        self._checkbox_delegate: Optional[CheckBoxDelegate] = None
        self._init_widget()
        self._connect_signals()

    # <editor-fold desc="Public methods">
    def set_model(self, model: "list_model.ListModel") -> None:
        """Attach a ListModel to this view.

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

    def set_checkboxes_enabled(self, enabled: bool) -> None:
        """Enable or disable multi-select checkboxes.

        Args:
            enabled: True to show checkboxes and enable multi-selection;
                False to hide them and revert to single-selection.
        """
        if enabled:
            if self._checkbox_delegate is None:
                self._checkbox_delegate = CheckBoxDelegate(self)
            self.setItemDelegate(self._checkbox_delegate)
            self.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
            )
        else:
            self.setItemDelegate(None)
            self.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
            )

    def select_all(self) -> None:
        """Select all items in the list view, including hidden ones."""
        tmp_model = self.model()
        if tmp_model is None:
            return

        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is None:
            return

        tmp_top_left = tmp_model.index(0, 0)
        tmp_bottom_right = tmp_model.index(tmp_model.rowCount() - 1, 0)
        tmp_selection = QtCore.QItemSelection(tmp_top_left, tmp_bottom_right)
        tmp_selection_model.select(
            tmp_selection,
            QtCore.QItemSelectionModel.SelectionFlag.Select,
        )

    def select_all_visible(self) -> None:
        """Select all visible (non-hidden) items in the list view."""
        tmp_model = self.model()
        if tmp_model is None:
            return

        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is None:
            return

        # Select all non-hidden rows
        for tmp_row in range(tmp_model.rowCount()):
            if not self.isRowHidden(tmp_row):
                tmp_index = tmp_model.index(tmp_row, 0)
                tmp_selection_model.select(
                    tmp_index,
                    QtCore.QItemSelectionModel.SelectionFlag.Select,
                )

    def deselect_all(self) -> None:
        """Deselect all items in the list view."""
        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is not None:
            tmp_selection_model.clearSelection()

    def selected_items(self) -> list[object]:
        """Return the raw item objects for all currently selected/checked rows.

        Returns:
            A list of selected/checked item objects.
        """
        tmp_model = self.model()
        if tmp_model is None:
            return []

        tmp_indexes = self.selectedIndexes()
        # Ensure we return items in their visual list order
        tmp_indexes.sort(key=lambda idx: idx.row())

        return [
            tmp_model.data(idx, QtCore.Qt.ItemDataRole.UserRole)
            for idx in tmp_indexes
            if idx.isValid()
        ]

    def set_selected_items(self, items: list[object]) -> None:
        """Select/check the rows corresponding to the given items.

        Args:
            items: A list of item objects to select/check.
        """
        tmp_model = self.model()
        if tmp_model is None:
            return

        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is None:
            return

        tmp_selection_model.clearSelection()
        tmp_item_set = set(items)

        for tmp_row in range(tmp_model.rowCount()):
            tmp_index = tmp_model.index(tmp_row, 0)
            tmp_item = tmp_model.data(
                tmp_index, QtCore.Qt.ItemDataRole.UserRole
            )
            if tmp_item in tmp_item_set:
                tmp_selection_model.select(
                    tmp_index, QtCore.QItemSelectionModel.SelectionFlag.Select
                )

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


class ListViewWithSearch(QtWidgets.QWidget):
    """A composite widget combining a search field with a ListView.

    The search field filters rows in real time by hiding those whose display
    text does not contain the typed substring (case-insensitive). Filtering
    is implemented via setRowHidden on the inner view - no proxy model is
    needed - which keeps memory overhead minimal.

    Attributes:
        search_field: The QLineEdit used for filtering.
        list_view: The inner ListView.
        item_activated: Forwarded from list_view - emits the raw
            item object when the user activates a row.

    Example:
        widget = ListViewWithSearch()
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
        self._model: Optional["list_model.ListModel"] = None
        self.search_field = QtWidgets.QLineEdit()
        self.select_all_checkbox = QtWidgets.QCheckBox("Select All")
        self.list_view = ListView()
        # </editor-fold>
        self._init_widget()
        self._connect_signals()

    # <editor-fold desc="Public methods">
    def set_model(self, model: "list_model.ListModel") -> None:
        """Attach a ListModel to the inner list view.

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

        tmp_selection_model = self.list_view.selectionModel()
        if tmp_selection_model is not None:
            tmp_selection_model.selectionChanged.connect(
                self._update_select_all_checkbox
            )

    def clear_search(self) -> None:
        """Clear the search field and show all rows."""
        self.search_field.clear()

    def set_checkboxes_enabled(self, enabled: bool) -> None:
        """Enable or disable multi-select checkboxes on the inner list view.

        Args:
            enabled: True to show checkboxes and enable multi-selection;
                False to hide them and revert to single-selection.
        """
        self.list_view.set_checkboxes_enabled(enabled)
        self.select_all_checkbox.setVisible(enabled)
        if enabled:
            self._update_select_all_checkbox()

    def selected_items(self) -> list[object]:
        """Return the raw item objects for all currently selected/checked rows.

        Returns:
            A list of selected/checked item objects.
        """
        return self.list_view.selected_items()

    def set_selected_items(self, items: list[object]) -> None:
        """Select/check the rows corresponding to the given items.

        Args:
            items: A list of item objects to select/check.
        """
        self.list_view.set_selected_items(items)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget layout and child components."""
        self.search_field.setPlaceholderText("Search ...")
        self.search_field.setClearButtonEnabled(True)
        self.select_all_checkbox.setTristate(True)
        self.select_all_checkbox.setVisible(False)

        tmp_layout = QtWidgets.QVBoxLayout(self)
        tmp_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        tmp_layout.setSpacing(ui_defaults.DEFAULT_SPACING)
        tmp_layout.addWidget(self.search_field)
        tmp_layout.addWidget(self.select_all_checkbox)
        tmp_layout.addWidget(self.list_view)
        self.setLayout(tmp_layout)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self.list_view.item_activated.connect(self.item_activated)
        self.search_field.textChanged.connect(self._apply_filter)
        self.select_all_checkbox.stateChanged.connect(
            self._on_select_all_state_changed
        )

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

        self._update_select_all_checkbox()

    def _on_select_all_state_changed(self, state: int) -> None:
        """Handle changes to the Select All checkbox state.

        Args:
            state: The new Qt.CheckState value.
        """
        self.select_all_checkbox.blockSignals(True)
        try:
            if state == QtCore.Qt.CheckState.Checked.value:
                self.list_view.select_all_visible()
            elif state == QtCore.Qt.CheckState.Unchecked.value:
                self.list_view.deselect_all()
            elif state == QtCore.Qt.CheckState.PartiallyChecked.value:
                # Clicking a partially checked checkbox selects all visible
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.Checked
                )
                self.list_view.select_all_visible()
        finally:
            self.select_all_checkbox.blockSignals(False)

    def _update_select_all_checkbox(self) -> None:
        """Update the Select All checkbox state based on current selection."""
        if self._model is None or self.select_all_checkbox.isHidden():
            return

        tmp_total_visible = 0
        tmp_selected_visible = 0

        tmp_selection_model = self.list_view.selectionModel()
        if tmp_selection_model is None:
            return

        tmp_query = self.search_field.text().lower()
        for tmp_row in range(self._model.rowCount()):
            tmp_index = self._model.index(tmp_row, 0)
            tmp_text = (
                self._model.data(tmp_index, QtCore.Qt.ItemDataRole.DisplayRole)
                or ""
            )
            tmp_hidden = bool(tmp_query) and tmp_query not in tmp_text.lower()
            if not tmp_hidden:
                tmp_total_visible += 1
                if tmp_selection_model.isSelected(tmp_index):
                    tmp_selected_visible += 1

        self.select_all_checkbox.blockSignals(True)
        try:
            if tmp_total_visible == 0:
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.Unchecked
                )
            elif tmp_selected_visible == tmp_total_visible:
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.Checked
                )
            elif tmp_selected_visible == 0:
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.Unchecked
                )
            else:
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.PartiallyChecked
                )
        finally:
            self.select_all_checkbox.blockSignals(False)

    # </editor-fold>
