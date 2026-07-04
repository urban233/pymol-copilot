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

import contextlib
import logging
from typing import Any
from typing import Optional

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import ui_defaults
from pymol_copilot.gui.qt.model import table_model

logger = logging.getLogger(__name__)

__docformat__ = "google"


class CheckableProxyModel(QtCore.QAbstractProxyModel):
    """A proxy model that inserts a checkable checkbox column at column 0.

    All other columns are shifted by +1.
    """

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        """Initialize the proxy model.

        Args:
            parent: Optional parent object.
        """
        super().__init__(parent)

    def columnCount(  # noqa: N802
        self, parent: QtCore.QModelIndex | None = None
    ) -> int:
        """Return the number of columns, which is source column count + 1.

        Args:
            parent: The parent model index.

        Returns:
            The number of columns.
        """
        tmp_parent = parent if parent is not None else QtCore.QModelIndex()
        tmp_source = self.sourceModel()
        if tmp_source is None:
            return 0
        return tmp_source.columnCount(tmp_parent) + 1

    def rowCount(  # noqa: N802
        self, parent: QtCore.QModelIndex | None = None
    ) -> int:
        """Return the row count from the source model.

        Args:
            parent: The parent model index.

        Returns:
            The number of rows.
        """
        tmp_parent = parent if parent is not None else QtCore.QModelIndex()
        tmp_source = self.sourceModel()
        if tmp_source is None:
            return 0
        return tmp_source.rowCount(tmp_parent)

    def mapToSource(  # noqa: N802
        self, proxy_index: QtCore.QModelIndex
    ) -> QtCore.QModelIndex:
        """Map a proxy index to a source model index.

        Args:
            proxy_index: The proxy model index.

        Returns:
            The mapped source index, or an invalid index for column 0.
        """
        if not proxy_index.isValid():
            return QtCore.QModelIndex()
        if proxy_index.column() == 0:
            return QtCore.QModelIndex()
        tmp_source = self.sourceModel()
        if tmp_source is None:
            return QtCore.QModelIndex()
        return tmp_source.index(
            proxy_index.row(),
            proxy_index.column() - 1,
            proxy_index.parent(),
        )

    def mapFromSource(  # noqa: N802
        self, source_index: QtCore.QModelIndex
    ) -> QtCore.QModelIndex:
        """Map a source index to a proxy index.

        Args:
            source_index: The source model index.

        Returns:
            The mapped proxy index.
        """
        if not source_index.isValid():
            return QtCore.QModelIndex()
        return self.index(
            source_index.row(),
            source_index.column() + 1,
            source_index.parent(),
        )

    def index(
        self,
        row: int,
        column: int,
        parent: QtCore.QModelIndex | None = None,
    ) -> QtCore.QModelIndex:
        """Create a model index for the given row and column.

        Args:
            row: The row index.
            column: The column index.
            parent: The parent index.

        Returns:
            The created model index.
        """
        _ = parent
        return self.createIndex(row, column)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        """Return the parent of the child index (always invalid for flat table).

        Args:
            child: The child index.

        Returns:
            An invalid model index.
        """
        _ = child
        return QtCore.QModelIndex()

    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return data for the given index and role.

        Args:
            index: The model index.
            role: The data role.

        Returns:
            The data value.
        """
        if not index.isValid():
            return None

        if index.column() == 0:
            if role == QtCore.Qt.ItemDataRole.UserRole:
                tmp_source = self.sourceModel()
                if tmp_source is not None:
                    tmp_src_idx = tmp_source.index(index.row(), 0)
                    return tmp_source.data(
                        tmp_src_idx, QtCore.Qt.ItemDataRole.UserRole
                    )
            return None

        tmp_src_idx = self.mapToSource(index)
        tmp_source = self.sourceModel()
        if tmp_source is None:
            return None
        return tmp_source.data(tmp_src_idx, role)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return the header data for the given section.

        Args:
            section: The column/row index.
            orientation: The orientation (horizontal/vertical).
            role: The data role.

        Returns:
            The header value.
        """
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
        ):
            if section == 0:
                return "Select"
            tmp_source = self.sourceModel()
            if tmp_source is not None:
                return tmp_source.headerData(section - 1, orientation, role)
        return super().headerData(section, orientation, role)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        """Return item flags for the given index.

        Args:
            index: The index.

        Returns:
            The item flags.
        """
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags

        if index.column() == 0:
            return (
                QtCore.Qt.ItemFlag.ItemIsEnabled
                | QtCore.Qt.ItemFlag.ItemIsSelectable
            )

        tmp_src_idx = self.mapToSource(index)
        tmp_source = self.sourceModel()
        if tmp_source is None:
            return QtCore.Qt.ItemFlag.NoItemFlags
        return tmp_source.flags(tmp_src_idx)

    def setSourceModel(  # noqa: N802
        self, source_model: QtCore.QAbstractItemModel
    ) -> None:
        """Set the source model.

        Args:
            source_model: The source model.
        """
        tmp_old = self.sourceModel()
        if tmp_old is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.modelReset.disconnect(self.modelReset)
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.dataChanged.disconnect(self._on_source_data_changed)
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.rowsInserted.disconnect(self._on_source_rows_inserted)
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.rowsRemoved.disconnect(self._on_source_rows_removed)
        super().setSourceModel(source_model)
        source_model.modelReset.connect(self.modelReset)
        source_model.dataChanged.connect(self._on_source_data_changed)
        source_model.rowsInserted.connect(self._on_source_rows_inserted)
        source_model.rowsRemoved.connect(self._on_source_rows_removed)

    def _on_source_data_changed(
        self,
        top_left: QtCore.QModelIndex,
        bottom_right: QtCore.QModelIndex,
        roles: list[int] | None = None,
    ) -> None:
        """Forward data changes from the source model.

        Args:
            top_left: The top left index.
            bottom_right: The bottom right index.
            roles: The changed roles.
        """
        tmp_roles = roles if roles is not None else []
        self.dataChanged.emit(
            self.mapFromSource(top_left),
            self.mapFromSource(bottom_right),
            tmp_roles,
        )

    def _on_source_rows_inserted(
        self, parent: QtCore.QModelIndex, start: int, end: int
    ) -> None:
        """Forward row insertions from the source model.

        Args:
            parent: The parent index.
            start: The start row index.
            end: The end row index.
        """
        _ = parent
        self.beginInsertRows(QtCore.QModelIndex(), start, end)
        self.endInsertRows()

    def _on_source_rows_removed(
        self, parent: QtCore.QModelIndex, start: int, end: int
    ) -> None:
        """Forward row removals from the source model.

        Args:
            parent: The parent index.
            start: The start row index.
            end: The end row index.
        """
        _ = parent
        self.beginRemoveRows(QtCore.QModelIndex(), start, end)
        self.endRemoveRows()


class ExcelTableDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that paints Excel-style borders, backgrounds and checkboxes."""

    def __init__(
        self,
        parent: QtWidgets.QAbstractItemView,
        checkboxes_enabled: bool = False,
    ) -> None:
        """Initialize the delegate.

        Args:
            parent: The parent item view.
            checkboxes_enabled: Whether checkboxes are enabled on column 0.
        """
        super().__init__(parent)
        self._checkboxes_enabled = checkboxes_enabled

    def set_checkboxes_enabled(self, enabled: bool) -> None:
        """Set whether checkboxes are enabled.

        Args:
            enabled: True to enable checkboxes; False to disable.
        """
        self._checkboxes_enabled = enabled

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        """Paint the cell with Excel-style selection borders and shading.

        Args:
            painter: The QPainter to draw with.
            option: The style options.
            index: The model index.
        """
        tmp_option = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(tmp_option, index)

        tmp_view = self.parent()
        tmp_is_selected = False
        if isinstance(tmp_view, QtWidgets.QAbstractItemView):
            tmp_sel_model = tmp_view.selectionModel()
            if tmp_sel_model is not None:
                tmp_is_selected = tmp_sel_model.isSelected(index)

        # Determine if row is fully selected via isRowSelected — O(1) internal
        # Qt check, replacing the previous O(columns) isSelected loop.
        tmp_is_fully_sel = False
        if tmp_is_selected and isinstance(tmp_view, QtWidgets.QTableView):
            tmp_sel_model_2 = tmp_view.selectionModel()
            if tmp_sel_model_2 is not None:
                tmp_is_fully_sel = tmp_sel_model_2.isRowSelected(
                    index.row(), QtCore.QModelIndex()
                )

        # Checkboxes on column 0
        if self._checkboxes_enabled and index.column() == 0:
            tmp_feat = (
                QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
            )
            tmp_option.features |= tmp_feat
            if tmp_is_selected:
                tmp_option.checkState = QtCore.Qt.CheckState.Checked
            else:
                tmp_option.checkState = QtCore.Qt.CheckState.Unchecked

        # Set background shading if row is fully selected
        if tmp_is_fully_sel:
            tmp_option.backgroundBrush = QtGui.QBrush(QtGui.QColor("#f2f2f2"))

        # Clear standard selection and focus states to prevent default blue
        # highlight, focus frame, blue vertical lines, and text borders.
        tmp_option.state = (
            tmp_option.state & ~QtWidgets.QStyle.StateFlag.State_Selected
        )
        tmp_option.state = (
            tmp_option.state & ~QtWidgets.QStyle.StateFlag.State_HasFocus
        )

        super().paint(painter, tmp_option, index)

        # Draw borders on top
        if tmp_is_selected and isinstance(tmp_view, QtWidgets.QTableView):
            painter.save()
            tmp_pen = QtGui.QPen(QtGui.QColor("#107c41"), 2)
            painter.setPen(tmp_pen)
            tmp_rect = option.rect

            tmp_sel_model = tmp_view.selectionModel()
            tmp_model = tmp_view.model()
            if tmp_sel_model is not None and tmp_model is not None:
                tmp_row = index.row()
                tmp_col = index.column()
                tmp_row_count = tmp_model.rowCount()
                tmp_col_count = tmp_model.columnCount()

                # Top border: draw if top neighbor is not selected
                tmp_draw_top = True
                if tmp_row > 0:
                    tmp_top_idx = tmp_model.index(tmp_row - 1, tmp_col)
                    if tmp_sel_model.isSelected(tmp_top_idx):
                        tmp_draw_top = False

                # Bottom border: draw if bottom neighbor is not selected
                tmp_draw_bottom = True
                if tmp_row < tmp_row_count - 1:
                    tmp_bottom_idx = tmp_model.index(tmp_row + 1, tmp_col)
                    if tmp_sel_model.isSelected(tmp_bottom_idx):
                        tmp_draw_bottom = False

                # Left border: draw if left neighbor is not selected
                tmp_draw_left = True
                if tmp_col > 0:
                    tmp_left_idx = tmp_model.index(tmp_row, tmp_col - 1)
                    if tmp_sel_model.isSelected(tmp_left_idx):
                        tmp_draw_left = False

                # Right border: draw if right neighbor is not selected
                tmp_draw_right = True
                if tmp_col < tmp_col_count - 1:
                    tmp_right_idx = tmp_model.index(tmp_row, tmp_col + 1)
                    if tmp_sel_model.isSelected(tmp_right_idx):
                        tmp_draw_right = False

                # Draw top line
                if tmp_draw_top:
                    painter.drawLine(
                        tmp_rect.left(),
                        tmp_rect.top() + 1,
                        tmp_rect.right(),
                        tmp_rect.top() + 1,
                    )
                # Draw bottom line
                if tmp_draw_bottom:
                    painter.drawLine(
                        tmp_rect.left(),
                        tmp_rect.bottom() - 1,
                        tmp_rect.right(),
                        tmp_rect.bottom() - 1,
                    )
                # Draw left line
                if tmp_draw_left:
                    painter.drawLine(
                        tmp_rect.left() + 1,
                        tmp_rect.top(),
                        tmp_rect.left() + 1,
                        tmp_rect.bottom(),
                    )
                # Draw right line
                if tmp_draw_right:
                    painter.drawLine(
                        tmp_rect.right() - 1,
                        tmp_rect.top(),
                        tmp_rect.right() - 1,
                        tmp_rect.bottom(),
                    )

            painter.restore()


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
    selection_changed = QtCore.pyqtSignal()
    """Emitted when the selection changes."""
    # </editor-fold>

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initialize the table view with sensible defaults.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._excel_delegate = ExcelTableDelegate(self)
        self._init_widget()

    # <editor-fold desc="Public methods">
    def set_model(
        self,
        model: table_model.TableModel | table_model.SortFilterProxy,
    ) -> None:
        """Attach a TableModel or SortFilterProxy.

        Args:
            model: The model or proxy to display.
        """
        if self._excel_delegate._checkboxes_enabled:
            tmp_proxy = CheckableProxyModel(self)
            tmp_proxy.setSourceModel(model)
            self.setModel(tmp_proxy)
            self.setColumnWidth(0, 60)
            horizontal_header = self.horizontalHeader()
            if horizontal_header is not None:
                horizontal_header.setSectionResizeMode(
                    0, QtWidgets.QHeaderView.ResizeMode.Fixed
                )
        else:
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

    def set_checkboxes_enabled(self, enabled: bool) -> None:
        """Enable or disable multi-select checkboxes on column 0.

        Args:
            enabled: True to show checkboxes and enable multi-selection;
                False to hide them and revert to single-selection.
        """
        self._excel_delegate.set_checkboxes_enabled(enabled)
        if enabled:
            tmp_curr_model = self.model()
            if tmp_curr_model is not None and not isinstance(
                tmp_curr_model, CheckableProxyModel
            ):
                tmp_proxy = CheckableProxyModel(self)
                tmp_proxy.setSourceModel(tmp_curr_model)
                self.setModel(tmp_proxy)

            self.setItemDelegateForColumn(0, self._excel_delegate)
            self.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
            )
            self.setColumnWidth(0, 60)
            horizontal_header = self.horizontalHeader()
            if horizontal_header is not None:
                horizontal_header.setSectionResizeMode(
                    0, QtWidgets.QHeaderView.ResizeMode.Fixed
                )
        else:
            tmp_curr_model = self.model()
            if tmp_curr_model is not None and isinstance(
                tmp_curr_model, CheckableProxyModel
            ):
                tmp_src = tmp_curr_model.sourceModel()
                if tmp_src is not None:
                    self.setModel(tmp_src)

            self.setItemDelegateForColumn(0, None)
            self.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
            )

    def select_all(self) -> None:
        """Select all rows in the table view."""
        tmp_model = self.model()
        if tmp_model is None:
            return

        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is None:
            return

        tmp_top_left = tmp_model.index(0, 0)
        tmp_bottom_right = tmp_model.index(
            tmp_model.rowCount() - 1,
            tmp_model.columnCount() - 1,
        )
        tmp_selection = QtCore.QItemSelection(tmp_top_left, tmp_bottom_right)
        tmp_selection_model.select(
            tmp_selection,
            QtCore.QItemSelectionModel.SelectionFlag.Select
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )

    def select_all_visible(self) -> None:
        """Select all visible (non-hidden) rows in the table view."""
        tmp_model = self.model()
        if tmp_model is None:
            return

        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is None:
            return

        for tmp_row in range(tmp_model.rowCount()):
            if not self.isRowHidden(tmp_row):
                tmp_index = tmp_model.index(tmp_row, 0)
                tmp_selection_model.select(
                    tmp_index,
                    QtCore.QItemSelectionModel.SelectionFlag.Select
                    | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                )

    def deselect_all(self) -> None:
        """Deselect all rows in the table view."""
        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is not None:
            tmp_selection_model.clearSelection()

    def selected_items(self) -> list[object]:
        """Return the raw row objects for all currently selected/checked rows.

        Returns:
            A list of selected/checked row items.
        """
        tmp_model = self.model()
        if tmp_model is None:
            return []

        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is None:
            return []

        tmp_indexes = tmp_selection_model.selectedRows()
        tmp_indexes.sort(key=lambda idx: idx.row())

        return [
            tmp_model.data(idx, QtCore.Qt.ItemDataRole.UserRole)
            for idx in tmp_indexes
            if idx.isValid()
        ]

    def set_selected_items(self, items: list[object]) -> None:
        """Select/check the rows corresponding to the given items.

        Args:
            items: A list of row items to select/check.
        """
        tmp_model = self.model()
        if tmp_model is None:
            return

        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is None:
            return

        tmp_selection_model.clearSelection()
        try:
            tmp_item_set = set(items)
            tmp_is_hashable = True
        except TypeError:
            tmp_item_set = set()
            tmp_is_hashable = False

        for tmp_row in range(tmp_model.rowCount()):
            tmp_index = tmp_model.index(tmp_row, 0)
            tmp_item = tmp_model.data(
                tmp_index, QtCore.Qt.ItemDataRole.UserRole
            )
            tmp_match = (
                tmp_item in tmp_item_set
                if tmp_is_hashable
                else tmp_item in items
            )
            if tmp_match:
                tmp_selection_model.select(
                    tmp_index,
                    QtCore.QItemSelectionModel.SelectionFlag.Select
                    | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                )

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget layout and child components."""
        # --- Selection & edit policy ---
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems
        )
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.setItemDelegate(self._excel_delegate)

        # --- Visual chrome ---
        self.setShowGrid(True)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)

        # --- Header configuration ---
        if (horizontal_header := self.horizontalHeader()) is None:
            raise RuntimeError("self.horizontalHeader is None")
        horizontal_header.setStretchLastSection(True)
        horizontal_header.setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Interactive
        )
        horizontal_header.setHighlightSections(True)

        if (vertical_header := self.verticalHeader()) is None:
            raise RuntimeError("self.verticalHeader is None")
        vertical_header.setVisible(True)
        vertical_header.setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        vertical_header.setHighlightSections(True)

        self.activated.connect(self._on_activated)

    def _on_activated(self, index: QtCore.QModelIndex) -> None:
        """Translate a QModelIndex activation into a row_activated emission.

        Args:
            index: The activated model index.
        """
        if (tmp_model := self.model()) is None:
            logger.warning("_on_activated called with no model attached.")
            return
        tmp_item = tmp_model.data(index, QtCore.Qt.ItemDataRole.UserRole)
        if tmp_item is None:
            logger.warning(
                "_on_activated: no UserRole data at index (%d, %d).",
                index.row(),
                index.column(),
            )
            return

        self.row_activated.emit(tmp_item)

    def setModel(self, model: QtCore.QAbstractItemModel) -> None:  # noqa: N802
        """Override to reconnect selection model signals when model changes.

        Args:
            model: The new model.
        """
        # Disconnect the OLD selection model BEFORE super().setModel() replaces
        # it; otherwise the stale QItemSelectionModel keeps the slot alive and
        # selection_changed fires on an orphaned model.
        tmp_old_sel = self.selectionModel()
        if tmp_old_sel is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old_sel.selectionChanged.disconnect(
                    self._on_selection_changed
                )
        super().setModel(model)
        tmp_selection_model = self.selectionModel()
        if tmp_selection_model is not None:
            tmp_selection_model.selectionChanged.connect(
                self._on_selection_changed
            )

    def _on_selection_changed(self) -> None:
        """Forward selectionChanged signal from the selection model."""
        self.selection_changed.emit()

    def mousePressEvent(  # noqa: N802
        self, event: QtGui.QMouseEvent
    ) -> None:
        """Handle additive checkbox selection on left click in column 0.

        Args:
            event: The mouse event.
        """
        if self._excel_delegate._checkboxes_enabled:
            tmp_pos = event.position().toPoint()
            tmp_index = self.indexAt(tmp_pos)
            if tmp_index.isValid() and tmp_index.column() == 0:
                tmp_option = QtWidgets.QStyleOptionViewItem()
                tmp_option.rect = self.visualRect(tmp_index)
                tmp_option.widget = self
                tmp_feat = QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
                tmp_option.features |= tmp_feat
                tmp_style = self.style()
                if tmp_style is not None:
                    tmp_sub_elem = QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator
                    tmp_check_rect = tmp_style.subElementRect(
                        tmp_sub_elem,
                        tmp_option,
                        self,
                    )
                    if tmp_check_rect.contains(tmp_pos):
                        if event.button() == QtCore.Qt.MouseButton.LeftButton:
                            tmp_selection_model = self.selectionModel()
                            if tmp_selection_model is not None:
                                tmp_selection_model.select(
                                    tmp_index,
                                    QtCore.QItemSelectionModel.SelectionFlag.Toggle
                                    | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                                )
                        event.accept()
                        return
        super().mousePressEvent(event)

    def mouseReleaseEvent(  # noqa: N802
        self, event: QtGui.QMouseEvent
    ) -> None:
        """Handle ignoring release events on the checkbox area.

        Args:
            event: The mouse event.
        """
        if self._excel_delegate._checkboxes_enabled:
            tmp_pos = event.position().toPoint()
            tmp_index = self.indexAt(tmp_pos)
            if tmp_index.isValid() and tmp_index.column() == 0:
                tmp_option = QtWidgets.QStyleOptionViewItem()
                tmp_option.rect = self.visualRect(tmp_index)
                tmp_option.widget = self
                tmp_feat = QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
                tmp_option.features |= tmp_feat
                tmp_style = self.style()
                if tmp_style is not None:
                    tmp_sub_elem = QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator
                    tmp_check_rect = tmp_style.subElementRect(
                        tmp_sub_elem,
                        tmp_option,
                        self,
                    )
                    if tmp_check_rect.contains(tmp_pos):
                        event.accept()
                        return
        super().mouseReleaseEvent(event)

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
        self.select_all_checkbox = QtWidgets.QCheckBox("Select All")
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
        # Disconnect before reassigning to avoid stacking duplicate connections
        # on repeated set_model() calls.
        with contextlib.suppress(TypeError, RuntimeError):
            self.table_view.selection_changed.disconnect(
                self._update_select_all_checkbox
            )
        self._proxy = table_model.SortFilterProxy()
        self._proxy.setSourceModel(model)

        if self._filter_column >= 0:
            self._proxy.set_filter_column(self._filter_column)

        self.table_view.set_model(self._proxy)

        self.table_view.selection_changed.connect(
            self._update_select_all_checkbox
        )

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

    def set_checkboxes_enabled(self, enabled: bool) -> None:
        """Enable or disable multi-select checkboxes on the inner table view.

        Args:
            enabled: True to show checkboxes and enable multi-selection;
                False to hide them and revert to single-selection.
        """
        self.table_view.set_checkboxes_enabled(enabled)
        self.select_all_checkbox.setVisible(enabled)
        if enabled:
            self._update_select_all_checkbox()

    def selected_items(self) -> list[object]:
        """Return the raw row objects for all currently selected/checked rows.

        Returns:
            A list of selected/checked row items.
        """
        return self.table_view.selected_items()

    def set_selected_items(self, items: list[object]) -> None:
        """Select/check the rows corresponding to the given items.

        Args:
            items: A list of row items to select/check.
        """
        self.table_view.set_selected_items(items)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _init_widget(self) -> None:
        """Initialize the widget layout and child components."""
        self.search_field.setPlaceholderText("Search ...")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setVisible(self._filter_column >= 0)
        self.select_all_checkbox.setTristate(True)
        self.select_all_checkbox.setVisible(False)

        self.toolbar_actions_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self.toolbar_actions_layout.setSpacing(ui_defaults.default_spacing())

        toolbar_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        toolbar_layout.setSpacing(ui_defaults.default_spacing() * 2)
        toolbar_layout.addWidget(self.search_field, stretch=1)
        toolbar_layout.addLayout(self.toolbar_actions_layout)

        root_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        root_layout.setSpacing(ui_defaults.default_spacing())
        root_layout.addLayout(toolbar_layout)
        root_layout.addWidget(self.select_all_checkbox)
        root_layout.addWidget(self.table_view)
        self.setLayout(root_layout)

    def _connect_signals(self) -> None:
        """Connect internal widget signals."""
        self.table_view.row_activated.connect(self.row_activated)
        self.search_field.textChanged.connect(self._on_search_text_changed)
        self.select_all_checkbox.stateChanged.connect(
            self._on_select_all_state_changed
        )

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

        self._update_select_all_checkbox()

    def _on_select_all_state_changed(self, state: int) -> None:
        """Handle changes to the Select All checkbox state.

        Args:
            state: The new Qt.CheckState value.
        """
        self.select_all_checkbox.blockSignals(True)
        try:
            if state == QtCore.Qt.CheckState.Checked.value:
                self.table_view.select_all_visible()
            elif state == QtCore.Qt.CheckState.Unchecked.value:
                self.table_view.deselect_all()
            elif state == QtCore.Qt.CheckState.PartiallyChecked.value:
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.Checked
                )
                self.table_view.select_all_visible()
        finally:
            self.select_all_checkbox.blockSignals(False)

    def _update_select_all_checkbox(self) -> None:
        """Update the Select All checkbox state based on current selection."""
        if self._proxy is None or self.select_all_checkbox.isHidden():
            return

        tmp_selection_model = self.table_view.selectionModel()
        if tmp_selection_model is None:
            return

        tmp_model = self.table_view.model()
        if tmp_model is None:
            return

        tmp_total_visible = sum(
            1
            for tmp_row in range(tmp_model.rowCount())
            if not self.table_view.isRowHidden(tmp_row)
        )

        # Deduplicate by row to count selected ROWS, not selected cells.
        # selectedIndexes() is a single C++ call rather than an O(n) loop
        # of isSelected() invocations, avoiding the O(n²) behaviour that
        # occurred during select_all_visible (selection_changed fires per row).
        tmp_selected_rows: set[int] = {
            tmp_idx.row() for tmp_idx in tmp_selection_model.selectedIndexes()
        }
        tmp_selected_visible = len(tmp_selected_rows)

        self.select_all_checkbox.blockSignals(True)
        try:
            if tmp_total_visible == 0 or tmp_selected_visible == 0:
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.Unchecked
                )
            elif tmp_selected_visible >= tmp_total_visible:
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.Checked
                )
            else:
                self.select_all_checkbox.setCheckState(
                    QtCore.Qt.CheckState.PartiallyChecked
                )
        finally:
            self.select_all_checkbox.blockSignals(False)

    # </editor-fold>
