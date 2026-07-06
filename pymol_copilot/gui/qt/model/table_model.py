# cBioMOL - open C++ and Python platform for BioMOLecular visualization and
# analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban
# (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
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
"""Provide table model blocks for QTableView-backed data.

This module provides three classes:

TableModel is a column-aware table model
that stores row objects in a plain Python list and delegates all
cell-data extraction to a single subclass hook, so no cell-level objects
are ever allocated.

NumpyTableModel is a column-aware table model
that stores all rows in a contiguous 2D numpy.ndarray. Data types are
strictly enforced.

SortFilterProxy is a thin QSortFilterProxyModel subclass
that filters rows by matching a configurable column's display text against
an accepted-values set. It replaces the legacy ActiveJobsProxyModel
and CompletedJobsProxyModel pair with a single, reusable class.
"""

from __future__ import annotations

import abc
import contextlib
import logging
import operator
from typing import Any
from typing import Callable
from typing import Generic
from typing import TypeVar
from typing import Union
from typing import override

import numpy as np
import numpy.typing as npt

from pymol_copilot.gui.qt import QtCore

logger = logging.getLogger(__name__)

__docformat__ = "google"

RowType = TypeVar("RowType")


class TableModel(QtCore.QAbstractTableModel, Generic[RowType]):
    """A column-aware table model for QTableView.

    Stores all rows in a plain Python list.  Each element represents one
    logical row; column data is extracted on demand by _cell_data.
    This means zero extra Python/C++ objects are allocated per cell, and
    large datasets remain efficient.

    Column headers are supplied at construction time via column_headers and
    can be replaced later with set_column_headers.

    A client-side sort key function can be injected via sort_key so that
    sort works without requiring a proxy model for simple cases.

    Attributes:
        _items: Internal row storage.
        _headers: Column header strings.
        _sort_key: Optional callable used by sort.

    Example:
        class JobTable(TableModel):
            def _cell_data(self, item: object, column: int) -> object:
                job = item  # type: Job
                values = [
                    job.type_label,
                    job.name,
                    job.project,
                    job.status,
                ]
                return values[column]

        model = JobTable(column_headers=["Job", "Name", "Project", "Status"])
        model.add_row(my_job)
        table_view.setModel(model)
    """

    def __init__(
        self,
        column_headers: list[str] | None = None,
        sort_key: Callable[[RowType], Any] | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        """Initialize the table model.

        Args:
            column_headers: Column header strings in left-to-right order.
                Defaults to an empty list (no headers).
            sort_key: Optional callable (item) -> sort_key_value used by
                sort to order rows client-side.  When None,
                calling sort is a no-op.
            parent: Optional Qt parent object. If None, the model has no
                parent.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._items: list[RowType] = []
        if column_headers:
            self._headers: list[str] = column_headers
        else:
            self._headers: list[str] = []
        # Any is used here to allow any comparable type returned by the
        # sort key.
        self._sort_key: Callable[[RowType], Any] | None = sort_key
        # </editor-fold>

    # <editor-fold desc="Public methods">

    @override
    def rowCount(
        self,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),  # noqa: B008
    ) -> int:
        """Return the number of rows in the model.

        Args:
            parent: Must be invalid for a flat table model; a valid parent
                always returns 0.

        Returns:
            The total number of rows, or 0 when parent is valid.
        """
        if parent.isValid():
            return 0
        return len(self._items)

    @override
    def columnCount(
        self,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),  # noqa: B008
    ) -> int:
        """Return the number of columns defined by the header list.

        Args:
            parent: Must be invalid for a flat table model; a valid parent
                always returns 0.

        Returns:
            The number of columns, or 0 when parent is valid.
        """
        if parent.isValid():
            return 0
        return len(self._headers)

    @override
    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return the data stored for index under the given role.

        Supported roles:
        Qt.DisplayRole delegates to _cell_data.
        Qt.UserRole returns the full row item object.

        All other roles return None.

        Args:
            index: The model index to query.
            role: The data role requested by the view.

        Returns:
            A value for the requested role, or None if the role is not
            supported or the index is invalid.
        """
        # Any is required to match QAbstractTableModel.data interface signature.
        if not index.isValid():
            return None
        tmp_row: int = index.row()
        tmp_column: int = index.column()
        if not (0 <= tmp_row < len(self._items)):
            return None
        if not (0 <= tmp_column < len(self._headers)):
            return None

        tmp_item: object = self._items[tmp_row]

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._cell_data(tmp_item, tmp_column)
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return tmp_item

        return None

    @override
    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return header data for the given section.

        Only horizontal (column) headers are supported; vertical (row)
        headers return None.

        Args:
            section: Zero-based column index.
            orientation: Qt.Horizontal for column headers, Qt.Vertical
                for row numbers (not supported).
            role: Only Qt.DisplayRole is handled.

        Returns:
            The header string for section, or None.
        """
        # Any is required to match QAbstractTableModel.headerData interface
        # signature.
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._headers)
        ):
            return self._headers[section]
        return None

    @override
    def sort(
        self,
        column: int,
        order: QtCore.Qt.SortOrder = QtCore.Qt.SortOrder.AscendingOrder,
    ) -> None:
        """Sort all rows using the injected sort_key function.

        The sort is stable.  If no sort_key was supplied at construction
        time this method is a no-op.

        Args:
            column: The column index that the view wants to sort by.  Passed
                to _sort_key if the function accepts it, otherwise
                the column is ignored and the key function determines order.
            order: Qt.AscendingOrder or Qt.DescendingOrder.
        """
        if self._sort_key is None or not self._items:
            return

        self.layoutAboutToBeChanged.emit()
        self._items.sort(
            key=self._sort_key,
            reverse=(order == QtCore.Qt.SortOrder.DescendingOrder),
        )
        self.layoutChanged.emit()

    def set_column_headers(self, headers: list[str]) -> None:
        """Replace the current column headers.

        Triggers a headerDataChanged emission for horizontal headers and
        an update of the column count.

        Args:
            headers: New column header strings.  Must not be None.

        Raises:
            ValueError: If headers is None.
        """
        if headers is None:
            raise ValueError("Invalid parameter: headers must not be None.")

        self.beginResetModel()
        self._headers = list(headers)
        self.endResetModel()

    def add_row(self, item: RowType) -> int:
        """Append a single item to the end of the model.

        Args:
            item: The row object.

        Returns:
            The row index of the newly inserted item.

        Raises:
            ValueError: If item is None.
        """
        if item is None:
            raise ValueError("Invalid parameter: item must not be None.")

        tmp_row: int = len(self._items)
        self.beginInsertRows(QtCore.QModelIndex(), tmp_row, tmp_row)
        self._items.append(item)
        self.endInsertRows()
        logger.debug(
            "TableModel: row successfully appended at index %d.", tmp_row
        )
        return tmp_row

    def add_rows(self, items: list[RowType]) -> None:
        """Append multiple rows in a single batched operation.

        Wraps the insertion in one beginInsertRows/endInsertRows pair
        so views only repaint once.

        Args:
            items: The row objects to append.  An empty list is silently
                ignored.

        Raises:
            ValueError: If items is None.
        """
        if items is None:
            raise ValueError("Invalid parameter: items must not be None.")
        if not items:
            return

        tmp_first_row: int = len(self._items)
        tmp_last_row: int = tmp_first_row + len(items) - 1
        self.beginInsertRows(QtCore.QModelIndex(), tmp_first_row, tmp_last_row)
        self._items.extend(items)
        self.endInsertRows()
        logger.debug(
            "TableModel: %d rows successfully appended (rows %d-%d).",
            len(items),
            tmp_first_row,
            tmp_last_row,
        )

    def remove_row(self, row: int) -> None:
        """Remove the row at the given index.

        Args:
            row: Zero-based row index.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < len(self._items)):
            raise IndexError(
                f"Row index {row} is out of range (0..{len(self._items) - 1})."
            )

        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._items[row]
        self.endRemoveRows()
        logger.debug("TableModel: row %d successfully removed.", row)

    def clear(self) -> None:
        """Remove all rows from the model.

        Emits a single beginResetModel/endResetModel pair.
        """
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()
        logger.debug("TableModel: all rows successfully cleared.")

    def row_item(self, row: int) -> RowType:
        """Return the raw item stored at row.

        Args:
            row: Zero-based row index.

        Returns:
            The item stored at the given row.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < len(self._items)):
            raise IndexError(
                f"Row index {row} is out of range (0..{len(self._items) - 1})."
            )
        return self._items[row]

    def all_items(self) -> list[RowType]:
        """Return a shallow copy of all stored row items.

        Returns:
            A new list containing every item in row order.
        """
        return list(self._items)

    def is_empty(self) -> bool:
        """Return whether the model contains no rows.

        Returns:
            True if the model has zero rows.
        """
        return not self._items

    def notify_row_changed(self, row: int) -> None:
        """Notify attached views that all columns in row have changed.

        Call this after mutating a row item in-place so that views request a
        repaint for the affected row.

        Args:
            row: Zero-based row index of the modified row.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < len(self._items)):
            raise IndexError(
                f"Row index {row} is out of range (0..{len(self._items) - 1})."
            )
        tmp_first_index: QtCore.QModelIndex = self.index(row, 0)
        tmp_last_index: QtCore.QModelIndex = self.index(
            row, len(self._headers) - 1
        )
        self.dataChanged.emit(
            tmp_first_index,
            tmp_last_index,
            [QtCore.Qt.ItemDataRole.DisplayRole],
        )

    @property
    def headers(self) -> list[str]:
        """Return a copy of the column header list.

        Returns:
            A new list of column header strings.
        """
        return list(self._headers)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _cell_data(self, item: object, column: int) -> Any:
        """Return the display value for a single cell.

        Subclasses must override this method to map item fields to
        column indices.  The default implementation returns str(item)
        for column 0 and None for all other columns.

        Args:
            item: The raw row item stored in the model.
            column: Zero-based column index.

        Returns:
            A display-friendly value (typically str, int, or
            float), or None for empty cells.
        """
        # Any is required because the cell display value can be of any type.
        if column == 0:
            return str(item)
        return None

    # </editor-fold>


class NumpyTableModel(QtCore.QAbstractTableModel):
    """A column-aware, performance-aware table model backed by a NumPy array.

    Stores all rows in a contiguous 2D numpy.ndarray. Columns/headers must
    be provided at initialization time and are immutable. Data types are
    strictly enforced and will raise a ValueError if appended/inserted data
    cannot be safely and cleanly aligned with the model's target datatype.

    Attributes:
        _headers: Column header strings.
        _sort_key: Optional callable used by sort.
        _data: Backing 2D numpy array.
    """

    def __init__(
        self,
        column_headers: list[str] | None = None,
        dtype: npt.DTypeLike | None = None,
        sort_key: Callable[[object], Any] | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        """Initialize the NumPy table model.

        Args:
            column_headers: Column header strings in left-to-right order.
                Defaults to an empty list (no headers).
            dtype: Optional numpy data type for the array. Defaults to
                np.float64.
            sort_key: Optional callable (item) -> sort_key_value used by
                sort to order rows.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._headers: list[str] = (
            list(column_headers) if column_headers else []
        )
        # Any is used here to allow any comparable type returned by the
        # sort key.
        self._sort_key: Callable[[object], Any] | None = sort_key
        actual_dtype: npt.DTypeLike = dtype if dtype is not None else np.float64
        self._data: np.ndarray = np.empty(
            (0, len(self._headers)), dtype=actual_dtype
        )
        # </editor-fold>

    @override
    def rowCount(
        self,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),  # noqa
    ) -> int:
        """Return the number of rows in the model.

        Args:
            parent: Must be invalid for a flat table model; a valid parent
                always returns 0.

        Returns:
            The total number of rows, or 0 when parent is valid.
        """
        if parent.isValid():
            return 0
        return self._data.shape[0]

    @override
    def columnCount(
        self,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),  # noqa
    ) -> int:
        """Return the number of columns defined by the header list.

        Args:
            parent: Must be invalid for a flat table model; a valid parent
                always returns 0.

        Returns:
            The number of columns, or 0 when parent is valid.
        """
        if parent.isValid():
            return 0
        return len(self._headers)

    @override
    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return the data stored for index under the given role.

        Args:
            index: The model index to query.
            role: The data role requested by the view.

        Returns:
            A value for the requested role, or None if the role is not
            supported or the index is invalid.
        """
        # Any is required to match QAbstractTableModel.data interface signature.
        if not index.isValid():
            return None
        tmp_row: int = index.row()
        tmp_column: int = index.column()
        if not (0 <= tmp_row < self._data.shape[0]):
            return None
        if not (0 <= tmp_column < len(self._headers)):
            return None

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._cell_data(self._data[tmp_row], tmp_column)
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return self._data[tmp_row]

        return None

    @override
    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return header data for the given section.

        Args:
            section: Zero-based column index.
            orientation: Qt.Horizontal for column headers.
            role: Only Qt.DisplayRole is handled.

        Returns:
            The header string, or None.
        """
        # Any is required to match QAbstractTableModel.headerData interface
        # signature.
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._headers)
        ):
            return self._headers[section]
        return None

    @override
    def sort(
        self,
        column: int,
        order: QtCore.Qt.SortOrder = QtCore.Qt.SortOrder.AscendingOrder,
    ) -> None:
        """Sort all rows in the NumPy array.

        Args:
            column: The column index to sort by.
            order: Qt.AscendingOrder or Qt.DescendingOrder.
        """
        if self._data.shape[0] == 0:
            return

        self.layoutAboutToBeChanged.emit()
        tmp_reverse: bool = order == QtCore.Qt.SortOrder.DescendingOrder

        if self._sort_key is not None:
            tmp_keys: list[Any] = [
                self._sort_key(self._data[tmp_i])
                for tmp_i in range(self._data.shape[0])
            ]
            tmp_sorted_indices: list[int] = sorted(
                range(len(tmp_keys)),
                key=lambda tmp_i: tmp_keys[tmp_i],
                reverse=tmp_reverse,
            )
            self._data = self._data[tmp_sorted_indices]
        else:
            tmp_argsort_indices: np.ndarray = np.argsort(self._data[:, column])
            if tmp_reverse:
                tmp_argsort_indices = tmp_argsort_indices[::-1]
            self._data = self._data[tmp_argsort_indices]

        self.layoutChanged.emit()

    def set_column_headers(self, headers: list[str]) -> None:
        """Replace column headers. Raises RuntimeError as headers are immutable.

        Args:
            headers: New column header strings.

        Raises:
            RuntimeError: Always raised because headers are immutable after
                init.
        """
        _ = headers
        raise RuntimeError(
            "Headers and columns are immutable for NumpyTableModel."
        )

    def add_row(self, item: Any) -> int:
        """Append a single row to the model.

        Args:
            item: The row array or sequence.

        Returns:
            The row index of the newly inserted row.

        Raises:
            ValueError: If the item length or data type is invalid.
        """
        if item is None:
            raise ValueError("Invalid parameter: item must not be None.")

        try:
            tmp_row_data: np.ndarray = np.asarray(item, dtype=self._data.dtype)
        except (ValueError, TypeError) as tmp_exception:
            raise ValueError(
                f"Data type mismatch: {tmp_exception}"
            ) from tmp_exception

        if tmp_row_data.dtype != self._data.dtype:
            raise ValueError(
                f"Data type mismatch: expected {self._data.dtype}, "
                f"got {tmp_row_data.dtype}."
            )

        tmp_row_data = tmp_row_data.reshape(1, -1)
        if tmp_row_data.shape[1] != len(self._headers):
            raise ValueError(
                "Invalid parameter format: row length "
                f"{tmp_row_data.shape[1]} does not match column count "
                f"{len(self._headers)}."
            )

        tmp_row: int = self._data.shape[0]
        self.beginInsertRows(QtCore.QModelIndex(), tmp_row, tmp_row)
        # Directly extend _data so the model is consistent for the entire
        # duration of the beginInsertRows / endInsertRows pair.  Deferring
        # this into a pending buffer and flushing inside data() was unsafe:
        # the view's C++ delegate could call data() mid-paint and trigger a
        # np.vstack that moved the array in memory.
        self._data = np.vstack([self._data, tmp_row_data])
        self.endInsertRows()
        return tmp_row

    def add_rows(self, items: Any) -> None:
        """Append multiple rows in a single batched operation.

        Args:
            items: The row objects to append.

        Raises:
            ValueError: If items is None or shape or data type is invalid.
        """
        if items is None:
            raise ValueError("Invalid parameter: items must not be None.")

        try:
            tmp_rows_data: np.ndarray = np.asarray(
                items, dtype=self._data.dtype
            )
        except (ValueError, TypeError) as tmp_exception:
            raise ValueError(
                f"Data type mismatch: {tmp_exception}"
            ) from tmp_exception

        if tmp_rows_data.dtype != self._data.dtype:
            raise ValueError(
                f"Data type mismatch: expected {self._data.dtype}, "
                f"got {tmp_rows_data.dtype}."
            )

        if tmp_rows_data.ndim == 1:
            tmp_rows_data = tmp_rows_data.reshape(1, -1)

        if tmp_rows_data.shape[1] != len(self._headers):
            raise ValueError(
                "Invalid parameter format: input column count "
                f"{tmp_rows_data.shape[1]} does not match model columns "
                f"{len(self._headers)}."
            )

        if tmp_rows_data.shape[0] == 0:
            return

        tmp_first_row: int = self._data.shape[0]
        tmp_last_row: int = tmp_first_row + tmp_rows_data.shape[0] - 1
        self.beginInsertRows(QtCore.QModelIndex(), tmp_first_row, tmp_last_row)
        self._data = np.vstack([self._data, tmp_rows_data])
        self.endInsertRows()

    def remove_row(self, row: int) -> None:
        """Remove the row at the given index.

        Args:
            row: Zero-based row index.

        Raises:
            IndexError: If row is out of range.
        """
        if not (0 <= row < self._data.shape[0]):
            raise IndexError(
                f"Row index {row} is out of range "
                f"(0..{self._data.shape[0] - 1})."
            )

        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        self._data = np.delete(self._data, row, axis=0)
        self.endRemoveRows()

    def clear(self) -> None:
        """Remove all rows from the model."""
        if self._data.shape[0] == 0:
            return
        self.beginResetModel()
        self._data = np.empty((0, len(self._headers)), dtype=self._data.dtype)
        self.endResetModel()

    def row_item(self, row: int) -> np.ndarray:
        """Return the row data stored at row.

        Args:
            row: Zero-based row index.

        Returns:
            The numpy array for the row.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < self._data.shape[0]):
            raise IndexError(
                f"Row index {row} is out of range "
                f"(0..{self._data.shape[0] - 1})."
            )
        return self._data[row]

    def all_items(self) -> np.ndarray:
        """Return a view of all stored row items.

        Returns:
            A view of the internal numpy array.
        """
        return self._data.view()

    def is_empty(self) -> bool:
        """Return whether the model contains no rows.

        Returns:
            True if the model has zero rows.
        """
        return self._data.shape[0] == 0

    def notify_row_changed(self, row: int) -> None:
        """Notify attached views that all columns in row have changed.

        Args:
            row: Zero-based row index.

        Raises:
            IndexError: If row is out of range.
        """
        if not (0 <= row < self._data.shape[0]):
            raise IndexError(
                f"Row index {row} is out of range "
                f"(0..{self._data.shape[0] - 1})."
            )
        first_index: QtCore.QModelIndex = self.index(row, 0)
        last_index: QtCore.QModelIndex = self.index(row, len(self._headers) - 1)
        self.dataChanged.emit(
            first_index, last_index, [QtCore.Qt.ItemDataRole.DisplayRole]
        )

    @property
    def headers(self) -> list[str]:
        """Return a copy of the column header list.

        Returns:
            A new list of column header strings.
        """
        return list(self._headers)

    @property
    def raw_data(self) -> np.ndarray:
        """Return a read-only view of the backing numpy array.

        Returns:
            A read-only view of the internal 2D array.
        """
        return self._data.view()

    def _cell_data(self, item: np.ndarray, column: int) -> Any:
        """Return the display value for a single cell.

        Args:
            item: The row array stored in the model.
            column: Zero-based column index.

        Returns:
            The display value.
        """
        # Any is required because the cell display value can be of any type.
        return item[column]


def create_list_table_model(
    column_headers: list[str] | None = None,
    initial_data: list[object] | None = None,
    sort_key: Callable[[object], Any] | None = None,
    parent: QtCore.QObject | None = None,
) -> TableModel:
    """Create a table model backed by a Python list.

    Args:
        column_headers: Column header strings.
        initial_data: Optional initial rows of data to populate.
        sort_key: Optional callable used for sorting.
        parent: Optional Qt parent object.

    Returns:
        An instance of TableModel.
    """
    tmp_model: TableModel = TableModel(
        column_headers=column_headers,
        sort_key=sort_key,
        parent=parent,
    )
    if initial_data is not None and len(initial_data) > 0:
        tmp_model.add_rows(initial_data)
    return tmp_model


def create_numpy_table_model(
    column_headers: list[str] | None = None,
    initial_data: np.ndarray | None = None,
    dtype: npt.DTypeLike | None = None,
    sort_key: Callable[[object], Any] | None = None,
    parent: QtCore.QObject | None = None,
) -> NumpyTableModel:
    """Create a table model backed by a NumPy array.

    Args:
        column_headers: Column header strings.
        initial_data: Optional initial rows of data to populate.
        dtype: Optional numpy data type for NumpyTableModel.
        sort_key: Optional callable used for sorting.
        parent: Optional Qt parent object.

    Returns:
        An instance of NumpyTableModel.
    """
    tmp_model: NumpyTableModel = NumpyTableModel(
        column_headers=column_headers,
        dtype=dtype,
        sort_key=sort_key,
        parent=parent,
    )
    if initial_data is not None and len(initial_data) > 0:
        tmp_model.add_rows(initial_data)
    return tmp_model


Comparable = Union[int, float, str]


class TableFilter(Generic[RowType], abc.ABC):
    """Abstract base class for all generic table filters."""

    @abc.abstractmethod
    def accepts(self, item: RowType) -> bool:
        """Evaluate if the raw domain item is accepted by this filter.

        Args:
            item: The raw row item/domain object.

        Returns:
            True if the item is accepted, False otherwise.

        Raises:
            NotImplementedError: Always raised in the base class.
        """
        raise NotImplementedError("Subclasses must implement accepts.")


class PropertyEqualsFilter(Generic[RowType], TableFilter[RowType]):
    """Filters rows where an attribute equals a target value."""

    def __init__(self, property_name: str, target_value: object) -> None:
        """Initialize the filter.

        Args:
            property_name: The attribute name on the row object.
            target_value: The value to compare against.
        """
        self._getter: Callable[[RowType], object] = operator.attrgetter(
            property_name
        )
        self._target_value: object = target_value

    @override
    def accepts(self, item: RowType) -> bool:
        """Check if the item's property matches target_value.

        Args:
            item: The row item object.

        Returns:
            True if property matches target_value, False otherwise.
        """
        try:
            tmp_val = self._getter(item)
            return bool(tmp_val == self._target_value)
        except AttributeError:
            return False


class PropertyTextFilter(Generic[RowType], TableFilter[RowType]):
    """Filters rows where an attribute matches a substring."""

    def __init__(
        self,
        property_name: str,
        search_text: str,
        case_sensitive: bool = False,
    ) -> None:
        """Initialize the filter.

        Args:
            property_name: The attribute name on the row object.
            search_text: The substring to look for.
            case_sensitive: Whether the comparison is case sensitive.
        """
        self._getter: Callable[[RowType], object] = operator.attrgetter(
            property_name
        )
        self._search_text: str = search_text
        self._case_sensitive: bool = case_sensitive

    @override
    def accepts(self, item: RowType) -> bool:
        """Check if the item's property contains the search string.

        Args:
            item: The row item object.

        Returns:
            True if property contains search_text, False otherwise.
        """
        try:
            tmp_val = self._getter(item)
            if not isinstance(tmp_val, str):
                tmp_val = str(tmp_val)
            if self._case_sensitive:
                return self._search_text in tmp_val
            return self._search_text.lower() in tmp_val.lower()
        except AttributeError:
            return False


class PropertyRangeFilter(Generic[RowType], TableFilter[RowType]):
    """Filters rows where an attribute is within a range."""

    def __init__(
        self,
        property_name: str,
        min_val: Comparable,
        max_val: Comparable,
    ) -> None:
        """Initialize the filter.

        Args:
            property_name: The attribute name on the row object.
            min_val: Minimum acceptable value (inclusive).
            max_val: Maximum acceptable value (inclusive).
        """
        self._getter: Callable[[RowType], Any] = operator.attrgetter(
            property_name
        )
        self._min_val: Any = min_val
        self._max_val: Any = max_val

    @override
    def accepts(self, item: RowType) -> bool:
        """Check if the item's property lies within the range.

        Args:
            item: The row item object.

        Returns:
            True if within range, False otherwise.
        """
        try:
            tmp_val = self._getter(item)
            if tmp_val is None:
                return False
            return bool(self._min_val <= tmp_val <= self._max_val)
        except (AttributeError, TypeError):
            return False


class PropertySetFilter(Generic[RowType], TableFilter[RowType]):
    """Filters rows where an attribute is inside a set of allowed values."""

    def __init__(self, property_name: str, values: set[object]) -> None:
        """Initialize the filter.

        Args:
            property_name: The attribute name on the row object.
            values: Set of allowed values.
        """
        self._getter: Callable[[RowType], object] = operator.attrgetter(
            property_name
        )
        self._values: frozenset[object] = frozenset(values)

    @override
    def accepts(self, item: RowType) -> bool:
        """Check if the item's property is inside the set.

        Args:
            item: The row item object.

        Returns:
            True if property is in values, False otherwise.
        """
        try:
            tmp_val = self._getter(item)
            return tmp_val in self._values
        except AttributeError:
            return False


class SortFilterProxy(QtCore.QSortFilterProxyModel, Generic[RowType]):
    """A configurable filter proxy for TableModel.

    Filters rows by matching the display text of a configurable column
    against a fixed set of accepted string values, or by applying registered
    TableFilter objects on the raw row items.

    Attributes:
        _filters: Registry of TableFilter objects.
        _cached_mask: Cached boolean mask of accepted rows.
        _filter_column: The source column whose display text is compared.
        _accepted_values: The set of string values that pass through the
            filter.
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        """Initialize the proxy with no filter applied (all rows visible).

        Args:
            parent: Optional Qt parent object. If None, the proxy has no
                parent.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._filters: dict[str, TableFilter[RowType]] = {}
        self._cached_mask: np.ndarray | None = None
        self._filter_column: int = 0
        self._accepted_values: frozenset[str] = frozenset()
        # </editor-fold>

    # <editor-fold desc="Public methods">
    def set_filter(
        self, filter_id: str, filter_obj: TableFilter[RowType]
    ) -> None:
        """Register or update a named filter object.

        Args:
            filter_id: A unique identifier for the filter.
            filter_obj: An instance of a TableFilter subclass.
        """
        self._filters[filter_id] = filter_obj
        self._invalidate_cache()
        self.invalidateFilter()

    def remove_filter(self, filter_id: str) -> None:
        """Remove an active filter by its ID.

        Args:
            filter_id: The ID of the filter to remove.
        """
        if filter_id in self._filters:
            del self._filters[filter_id]
            self._invalidate_cache()
            self.invalidateFilter()

    def clear_filters(self) -> None:
        """Remove all custom registered filters."""
        if self._filters:
            self._filters.clear()
            self._invalidate_cache()
            self.invalidateFilter()

    def set_filter_column(self, column: int) -> None:
        """Set the source column whose display text is used for filtering.

        Args:
            column: Zero-based column index in the source model.

        Raises:
            ValueError: If column is negative.
        """
        if column < 0:
            raise ValueError(
                "Invalid parameter: column index must be non-negative, "
                f"got {column}."
            )
        self._filter_column = column
        self.invalidateFilter()

    def set_accepted_values(self, values: set[str]) -> None:
        """Set the string values that are allowed through the filter.

        Only rows whose display text in the filter column exactly matches one
        of the strings in values are shown.  Passing an empty set hides all
        rows.

        Args:
            values: The set of accepted display strings.

        Raises:
            ValueError: If values is None.
        """
        if values is None:
            raise ValueError("Invalid parameter: values must not be None.")
        self._accepted_values = frozenset(values)
        self.invalidateFilter()

    @override
    def setSourceModel(self, source_model: QtCore.QAbstractItemModel) -> None:
        """Attach a source model and connect invalidation slots.

        Args:
            source_model: The source table model.
        """
        tmp_old = self.sourceModel()
        if tmp_old is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.modelReset.disconnect(self._invalidate_cache)
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.rowsInserted.disconnect(self._invalidate_cache)
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.rowsRemoved.disconnect(self._invalidate_cache)
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.dataChanged.disconnect(self._invalidate_cache)
            with contextlib.suppress(TypeError, RuntimeError):
                tmp_old.layoutChanged.disconnect(self._invalidate_cache)

        super().setSourceModel(source_model)

        if source_model is not None:
            source_model.modelReset.connect(self._invalidate_cache)
            source_model.rowsInserted.connect(self._invalidate_cache)
            source_model.rowsRemoved.connect(self._invalidate_cache)
            source_model.dataChanged.connect(self._invalidate_cache)
            source_model.layoutChanged.connect(self._invalidate_cache)

        self._invalidate_cache()

    @override
    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QtCore.QModelIndex,
    ) -> bool:
        """Decide whether a source row should be visible in the proxy.

        Retrieves the display text of the filter column for source_row and
        checks whether it is contained in _accepted_values, then checks all
        registered filters.

        Args:
            source_row: Row index in the source model.
            source_parent: Parent index (always invalid for flat models).

        Returns:
            True if the row is accepted by all active filters, False otherwise.
        """
        if not super().filterAcceptsRow(source_row, source_parent):
            return False

        tmp_source_model = self.sourceModel()
        if tmp_source_model is None:
            return False

        if self._accepted_values:
            tmp_col_idx = tmp_source_model.index(
                source_row, self._filter_column, source_parent
            )
            tmp_value = tmp_source_model.data(
                tmp_col_idx, QtCore.Qt.ItemDataRole.DisplayRole
            )
            if tmp_value not in self._accepted_values:
                return False

        if self._cached_mask is None:
            self._rebuild_filter_mask()

        if self._cached_mask is not None and source_row < len(
            self._cached_mask
        ):
            return bool(self._cached_mask[source_row])

        return True

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _invalidate_cache(self, *args: Any, **kwargs: Any) -> None:
        """Clear the cached filter mask. Slot for source model signals.

        Args:
            *args: Positional signal args (ignored).
            **kwargs: Keyword signal args (ignored).
        """
        _ = args
        _ = kwargs
        self._cached_mask = None

    def _rebuild_filter_mask(self) -> None:
        """Evaluate all custom filters and build the boolean mask."""
        tmp_source = self.sourceModel()
        if tmp_source is None:
            self._cached_mask = None
            return

        tmp_row_count = tmp_source.rowCount()
        if tmp_row_count == 0:
            self._cached_mask = np.ones(0, dtype=np.bool_)
            return

        tmp_mask = np.ones(tmp_row_count, dtype=np.bool_)

        if self._filters:
            tmp_items = getattr(tmp_source, "_items", None)
            if tmp_items is not None:
                for tmp_filter in self._filters.values():
                    tmp_mask &= np.fromiter(
                        (tmp_filter.accepts(item) for item in tmp_items),
                        dtype=np.bool_,
                        count=tmp_row_count,
                    )

        self._cached_mask = tmp_mask

    # </editor-fold>
