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
"""Provide list model blocks for QListView-backed data.

This module provides the ListModel base class - a
high-performance, low-memory-footprint flat list model for use with
QListView and QComboBox.

Notes:
    Design rationale:
    The legacy SequenceModel and PSASequenceModel subclass
    QStandardItemModel, which allocates one QStandardItem C++ object per
    row. For large datasets this causes significant heap fragmentation.
    ListModel stores all items in a plain Python list and only
    talks to Qt's C++ layer when the view requests a repaint - a pure
    data-oriented approach that keeps item count from affecting memory
    in any meaningful way.

Notes:
    Typical usage:

    # Flat string list, display each item as-is:
    class NameListModel(ListModel):
        def _display_text(self, item: object) -> str:
            return item.full_name  # type: ignore[union-attr]

    model = NameListModel(initial_data=my_names)
    list_view.setModel(model)
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from typing import Optional
import logging

import numpy as np
import numpy.typing as npt

from pymol_copilot.gui.qt import QtCore

logger = logging.getLogger(__name__)

__docformat__ = "google"


class ListModel(QtCore.QAbstractListModel):
    """A flat list model for QListView and QComboBox.

    Stores every item in a plain Python list - no QStandardItem
    objects are ever allocated - and implements the minimal
    QAbstractListModel contract so that any Qt list/combo view can
    consume it directly.

    Subclasses override _display_text (and optionally
    _icon_for_item and _tooltip_for_item) to customise how
    each row is presented without touching any of the model plumbing.

    Attributes:
        _items: Internal storage for all row objects.

    Example:
        model = ListModel(initial_data=["Alice", "Bob", "Carol"])
        list_view.setModel(model)

        model.add_item("Dave")
        model.remove_item(0)  # removes "Alice"
    """

    def __init__(
        self,
        initial_data: Optional[list[object]] = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        """Initialize the list model with optional seed data.

        Args:
            initial_data: An optional list of objects to pre-populate the
                model. The list is copied so that external mutations do not
                affect the model's state.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        # <editor-fold desc="Instance attributes">
        self._items: list[object] = list(initial_data) if initial_data else []
        # </editor-fold>

    # <editor-fold desc="Public methods">

    def rowCount(  # noqa: N802
        self,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),  # noqa: B008
    ) -> int:
        """Return the number of rows in the model.

        A valid parent always yields zero because this is a flat (non-tree)
        model.

        Args:
            parent: The parent index. A valid parent means we are inside a
                sub-tree, which this model does not support.

        Returns:
            The total number of items in the model, or 0 when parent
            is valid.
        """
        if parent.isValid():
            return 0
        return len(self._items)

    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return the data stored for index under the given role.

        Supported roles:

        * Qt.DisplayRole - calls _display_text.
        * Qt.UserRole - returns the raw item object (useful for
          delegate access without sub-classing the model).

        Args:
            index: The model index to query. Must be valid.
            role: The data role requested by the view.

        Returns:
            A string for DisplayRole, the raw item object for
            UserRole, or None for any other role.

        Notes:
            Any is used here as Qt data() can return diverse types
            (str, QIcon, QColor, or objects)
        """
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        tmp_item = self._items[index.row()]

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._display_text(tmp_item)
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return tmp_item
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return self._tooltip_for_item(tmp_item)

        return None

    def add_item(self, item: object) -> int:
        """Append a single item to the end of the model.

        Args:
            item: The object to append.

        Returns:
            The row index of the newly inserted item.

        Raises:
            ValueError: If item is None.
        """
        if item is None:
            raise ValueError("item must not be None")

        tmp_row = len(self._items)
        self.beginInsertRows(QtCore.QModelIndex(), tmp_row, tmp_row)
        self._items.append(item)
        self.endInsertRows()
        logger.debug("ListModel: item appended at row %d.", tmp_row)
        return tmp_row

    def add_items(self, items: list[object]) -> None:
        """Append multiple items in a single batched operation.

        Wraps the entire insertion in one beginInsertRows/
        endInsertRows pair so that connected views only receive a single
        layout-changed notification instead of one per row.

        Args:
            items: The list of objects to append. Empty lists are silently
                ignored.

        Raises:
            ValueError: If items is None.
        """
        if items is None:
            raise ValueError("items must not be None")
        if not items:
            return

        tmp_first_row = len(self._items)
        tmp_last_row = tmp_first_row + len(items) - 1
        self.beginInsertRows(QtCore.QModelIndex(), tmp_first_row, tmp_last_row)
        self._items.extend(items)
        self.endInsertRows()
        logger.debug(
            "ListModel: %d items appended (rows %d-%d).",
            len(items),
            tmp_first_row,
            tmp_last_row,
        )

    def remove_item(self, row: int) -> None:
        """Remove the item at the given row index.

        Args:
            row: Zero-based row index of the item to remove.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < len(self._items)):
            raise IndexError(
                f"Row {row} is out of range (0..{len(self._items) - 1})"
            )

        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._items[row]
        self.endRemoveRows()
        logger.debug("ListModel: item at row %d removed.", row)

    def remove_items(self, row: int, count: int) -> None:
        """Remove a block of items from the model in a single batch.

        Args:
            row: The starting zero-based row index to remove.
            count: The number of items to remove.

        Raises:
            ValueError: If count is negative.
            IndexError: If the range [row, row + count) is out of bounds.
        """
        if count < 0:
            raise ValueError("count must not be negative")
        if count == 0:
            return

        last_row = row + count - 1
        if not (0 <= row < len(self._items)) or not (
            0 <= last_row < len(self._items)
        ):
            raise IndexError(
                f"Range [{row}, {last_row}] is out of bounds "
                f"(0..{len(self._items) - 1})"
            )

        self.beginRemoveRows(QtCore.QModelIndex(), row, last_row)
        del self._items[row : row + count]
        self.endRemoveRows()
        logger.debug(
            "ListModel: %d items removed starting at row %d.",
            count,
            row,
        )

    def clear(self) -> None:
        """Remove all items from the model.

        Emits a single beginResetModel/endResetModel pair so that
        connected views reset efficiently.
        """
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()
        logger.debug("ListModel: all items cleared.")

    def item(self, row: int) -> object:
        """Return the raw item stored at row.

        Args:
            row: Zero-based row index.

        Returns:
            The object stored at the given row.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < len(self._items)):
            raise IndexError(
                f"Row {row} is out of range (0..{len(self._items) - 1})"
            )
        return self._items[row]

    def items(self) -> list[object]:
        """Return a shallow copy of all stored items.

        Returns:
            A new list containing every item in row order.
        """
        return list(self._items)

    def iter_items(self) -> Generator[object, None, None]:
        """Yield stored items lazily without memory allocation.

        Returns:
            A generator yielding each stored item in row order.
        """
        yield from self._items

    def is_empty(self) -> bool:
        """Return whether the model contains no items.

        Returns:
            True if the model has zero rows.
        """
        return not self._items

    def notify_item_changed(self, row: int) -> None:
        """Notify attached views that the item at row has changed.

        Call this after mutating the underlying item object in-place so that
        views request a repaint for the affected row.

        Args:
            row: Zero-based row index of the modified item.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < len(self._items)):
            raise IndexError(
                f"Row {row} is out of range (0..{len(self._items) - 1})"
            )
        tmp_index = self.index(row)
        self.dataChanged.emit(
            tmp_index,
            tmp_index,
            [QtCore.Qt.ItemDataRole.DisplayRole],
        )

    # </editor-fold>

    # <editor-fold desc="Private methods">

    def _display_text(self, item: object) -> str:
        """Return the string shown in the view for item.

        The default implementation calls str(item). Override in a
        subclass to provide domain-specific display names.

        Args:
            item: The raw item object stored in the model.

        Returns:
            A non-empty string to display in the view.
        """
        return str(item)

    def _tooltip_for_item(self, item: object) -> Optional[str]:  # noqa: ARG002
        """Return an optional tooltip string for item.

        The default implementation returns None (no tooltip). Override
        in a subclass to provide context-sensitive tooltips.

        Args:
            item: The raw item object stored in the model.

        Returns:
            A tooltip string, or None to suppress the tooltip.
        """
        return None

    # </editor-fold>


class NumpyListModel(QtCore.QAbstractListModel):
    """A flat list model backed by a 1D NumPy array.

    Stores all row elements in a contiguous 1D NumPy array. Ideal for
    large datasets of homogeneous data types, such as coordinates, indexes,
    or numeric values, where standard Python lists would incur high memory
    overhead and heap fragmentation.

    Attributes:
        _data: The backing 1D NumPy array.
    """

    def __init__(
        self,
        initial_data: Optional[npt.ArrayLike] = None,
        dtype: Optional[npt.DTypeLike] = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        """Initialize the NumPy list model with optional seed data.

        Args:
            initial_data: Optional NumPy array or array-like seed data to
                populate the model.
            dtype: Optional NumPy data type for the backing array. Defaults
                to np.float64.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        tmp_actual_dtype = dtype if dtype is not None else np.float64
        if initial_data is not None:
            self._data: np.ndarray = np.asarray(
                initial_data, dtype=tmp_actual_dtype
            )
        else:
            self._data = np.empty((0,), dtype=tmp_actual_dtype)

    def rowCount(  # noqa: N802
        self,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),  # noqa: B008
    ) -> int:
        """Return the number of rows in the model.

        Args:
            parent: The parent index. A valid parent means we are inside a
                sub-tree, which this model does not support.

        Returns:
            The total number of items in the model, or 0 when parent
            is valid.
        """
        if parent.isValid():
            return 0
        return self._data.shape[0]

    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return the data stored for index under the given role.

        Args:
            index: The model index to query. Must be valid.
            role: The data role requested by the view.

        Returns:
            A value for the requested role, or None.
        """
        if not index.isValid() or not (0 <= index.row() < self._data.shape[0]):
            return None

        tmp_val = self._data[index.row()]

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._display_text(tmp_val)
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return tmp_val
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return self._tooltip_for_item(tmp_val)

        return None

    def add_item(self, item: Any) -> int:
        """Append a single item to the end of the model.

        Args:
            item: The value to append.

        Returns:
            The row index of the newly inserted item.

        Raises:
            ValueError: If item is None or cannot be coerced to the backing
                array's data type.
        """
        if item is None:
            raise ValueError("item must not be None")

        try:
            tmp_coerced = np.asarray([item], dtype=self._data.dtype)
        except (ValueError, TypeError) as tmp_exc:
            raise ValueError(f"Data type mismatch: {tmp_exc}") from tmp_exc

        tmp_row = self._data.shape[0]
        self.beginInsertRows(QtCore.QModelIndex(), tmp_row, tmp_row)
        self._data = np.concatenate([self._data, tmp_coerced])
        self.endInsertRows()
        logger.debug("NumpyListModel: item appended at row %d.", tmp_row)
        return tmp_row

    def add_items(self, items: npt.ArrayLike) -> None:
        """Append multiple items in a single batched operation.

        Args:
            items: The array-like sequence of objects to append.

        Raises:
            ValueError: If items is None or cannot be coerced.
        """
        if items is None:
            raise ValueError("items must not be None")

        try:
            tmp_coerced = np.asarray(items, dtype=self._data.dtype)
        except (ValueError, TypeError) as tmp_exc:
            raise ValueError(f"Data type mismatch: {tmp_exc}") from tmp_exc

        if tmp_coerced.size == 0:
            return

        tmp_first_row = self._data.shape[0]
        tmp_last_row = tmp_first_row + tmp_coerced.size - 1
        self.beginInsertRows(QtCore.QModelIndex(), tmp_first_row, tmp_last_row)
        self._data = np.concatenate([self._data, tmp_coerced.reshape(-1)])
        self.endInsertRows()
        logger.debug(
            "NumpyListModel: %d items appended (rows %d-%d).",
            tmp_coerced.size,
            tmp_first_row,
            tmp_last_row,
        )

    def remove_item(self, row: int) -> None:
        """Remove the item at the given row index.

        Args:
            row: Zero-based row index of the item to remove.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < self._data.shape[0]):
            raise IndexError(
                f"Row {row} is out of range (0..{self._data.shape[0] - 1})"
            )

        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        self._data = np.delete(self._data, row)
        self.endRemoveRows()
        logger.debug("NumpyListModel: item at row %d removed.", row)

    def remove_items(self, row: int, count: int) -> None:
        """Remove a block of items from the model in a single batch.

        Args:
            row: The starting zero-based row index to remove.
            count: The number of items to remove.

        Raises:
            ValueError: If count is negative.
            IndexError: If the range [row, row + count) is out of bounds.
        """
        if count < 0:
            raise ValueError("count must not be negative")
        if count == 0:
            return

        tmp_last_row = row + count - 1
        if not (0 <= row < self._data.shape[0]) or not (
            0 <= tmp_last_row < self._data.shape[0]
        ):
            raise IndexError(
                f"Range [{row}, {tmp_last_row}] is out of bounds "
                f"(0..{self._data.shape[0] - 1})"
            )

        self.beginRemoveRows(QtCore.QModelIndex(), row, tmp_last_row)
        self._data = np.delete(self._data, np.arange(row, row + count))
        self.endRemoveRows()
        logger.debug(
            "NumpyListModel: %d items removed starting at row %d.",
            count,
            row,
        )

    def clear(self) -> None:
        """Remove all items from the model."""
        if self._data.shape[0] == 0:
            return
        self.beginResetModel()
        self._data = np.empty((0,), dtype=self._data.dtype)
        self.endResetModel()
        logger.debug("NumpyListModel: all items cleared.")

    def item(self, row: int) -> Any:
        """Return the raw item value stored at row.

        Args:
            row: Zero-based row index.

        Returns:
            The value stored at the given row.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < self._data.shape[0]):
            raise IndexError(
                f"Row {row} is out of range (0..{self._data.shape[0] - 1})"
            )
        return self._data[row]

    def items(self) -> np.ndarray:
        """Return a copy of the backing NumPy array.

        Returns:
            A copy of the backing 1D NumPy array.
        """
        return np.copy(self._data)

    def iter_items(self) -> Generator[Any, None, None]:
        """Yield stored items lazily without memory allocation.

        Returns:
            A generator yielding each stored item in row order.
        """
        yield from self._data

    def is_empty(self) -> bool:
        """Return whether the model contains no items.

        Returns:
            True if the model has zero rows.
        """
        return self._data.shape[0] == 0

    def notify_item_changed(self, row: int) -> None:
        """Notify attached views that the item at row has changed.

        Args:
            row: Zero-based row index of the modified item.

        Raises:
            IndexError: If row is out of bounds.
        """
        if not (0 <= row < self._data.shape[0]):
            raise IndexError(
                f"Row {row} is out of range (0..{self._data.shape[0] - 1})"
            )
        tmp_index = self.index(row)
        self.dataChanged.emit(
            tmp_index,
            tmp_index,
            [QtCore.Qt.ItemDataRole.DisplayRole],
        )

    def _display_text(self, item: Any) -> str:
        """Return the string shown in the view for item.

        Args:
            item: The raw item value stored in the model.

        Returns:
            A non-empty string to display in the view.
        """
        return str(item)

    def _tooltip_for_item(self, item: Any) -> Optional[str]:
        """Return an optional tooltip string for item.

        Args:
            item: The raw item value stored in the model.

        Returns:
            A tooltip string, or None to suppress the tooltip.
        """
        _ = item
        return None
