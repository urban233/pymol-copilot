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
"""Unit tests for the TableView and TableViewWithToolbar widgets."""

from __future__ import annotations

from PyQt6 import QtCore
from PyQt6 import QtWidgets
import pytest

from pymol_copilot.gui.qt.model import table_model
from pymol_copilot.gui.qt.widgets import table_view


@pytest.fixture
def q_app() -> QtWidgets.QApplication:
    """Fixture for providing a QApplication instance.

    Returns:
        The QApplication instance.
    """
    tmp_app = QtWidgets.QApplication.instance()
    if isinstance(tmp_app, QtWidgets.QApplication):
        return tmp_app
    return QtWidgets.QApplication([])


class DummyTableModel(table_model.TableModel):
    """Dummy table model for testing TableView."""

    def _cell_data(self, item: object, column: int) -> object:
        """Return the cell data for the given item and column.

        Args:
            item: The row item object.
            column: The column index.

        Returns:
            The data at the column.
        """
        if isinstance(item, dict):
            tmp_keys = list(item.keys())
            if column < len(tmp_keys):
                return item[tmp_keys[column]]
        return ""


def test_table_view_checkboxes_toggle(q_app: QtWidgets.QApplication) -> None:
    """Verify that checkboxes can be toggled on and off.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = [
        {"Name": "Item A", "Val": 1},
        {"Name": "Item B", "Val": 2},
    ]
    tmp_model = DummyTableModel(column_headers=["Name", "Val"])
    tmp_model.add_rows(tmp_items)
    tmp_view = table_view.TableView()
    tmp_view.set_model(tmp_model)

    # Act - Enable checkboxes
    tmp_view.set_checkboxes_enabled(True)

    # Assert
    assert (
        tmp_view.selectionMode()
        == QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
    )
    assert tmp_view.itemDelegateForColumn(0) is not None

    # Act - Disable checkboxes
    tmp_view.set_checkboxes_enabled(False)

    # Assert
    assert (
        tmp_view.selectionMode()
        == QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
    )
    assert tmp_view.itemDelegateForColumn(0) is None


def test_table_view_selected_items(q_app: QtWidgets.QApplication) -> None:
    """Verify retrieving selected items when checkboxes are enabled.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = [
        {"Name": "Item A", "Val": 1},
        {"Name": "Item B", "Val": 2},
        {"Name": "Item C", "Val": 3},
    ]
    tmp_model = DummyTableModel(column_headers=["Name", "Val"])
    tmp_model.add_rows(tmp_items)
    tmp_view = table_view.TableView()
    tmp_view.set_model(tmp_model)
    tmp_view.set_checkboxes_enabled(True)

    # Act
    tmp_selection_model = tmp_view.selectionModel()
    assert tmp_selection_model is not None

    # Select row 0 and 2
    tmp_view_model = tmp_view.model()
    assert tmp_view_model is not None
    tmp_selection_model.select(
        tmp_view_model.index(0, 0),
        QtCore.QItemSelectionModel.SelectionFlag.Select
        | QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )
    tmp_selection_model.select(
        tmp_view_model.index(2, 0),
        QtCore.QItemSelectionModel.SelectionFlag.Select
        | QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )

    # Assert
    tmp_selected = tmp_view.selected_items()
    assert tmp_selected == [tmp_items[0], tmp_items[2]]


def test_table_view_set_selected_items(q_app: QtWidgets.QApplication) -> None:
    """Verify programmatic setting of selected items.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = [
        {"Name": "Item A", "Val": 1},
        {"Name": "Item B", "Val": 2},
        {"Name": "Item C", "Val": 3},
    ]
    tmp_model = DummyTableModel(column_headers=["Name", "Val"])
    tmp_model.add_rows(tmp_items)
    tmp_view = table_view.TableView()
    tmp_view.set_model(tmp_model)
    tmp_view.set_checkboxes_enabled(True)

    # Act
    tmp_to_select: list[object] = [tmp_items[1], tmp_items[2]]
    tmp_view.set_selected_items(tmp_to_select)

    # Assert
    tmp_selected = tmp_view.selected_items()
    assert tmp_selected == [tmp_items[1], tmp_items[2]]


def test_table_view_select_all_apis(q_app: QtWidgets.QApplication) -> None:
    """Verify the select_all, select_all_visible and deselect_all methods.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = [
        {"Name": "Item A", "Val": 1},
        {"Name": "Item B", "Val": 2},
    ]
    tmp_model = DummyTableModel(column_headers=["Name", "Val"])
    tmp_model.add_rows(tmp_items)
    tmp_view = table_view.TableView()
    tmp_view.set_model(tmp_model)
    tmp_view.set_checkboxes_enabled(True)

    # Act - Select all
    tmp_view.select_all()

    # Assert
    assert tmp_view.selected_items() == tmp_items

    # Act - Deselect all
    tmp_view.deselect_all()

    # Assert
    assert tmp_view.selected_items() == []


def test_table_view_with_toolbar_integration(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify checkbox and selection APIs on TableViewWithToolbar.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = [
        {"Name": "Apple", "Val": 1},
        {"Name": "Banana", "Val": 2},
    ]
    tmp_model = DummyTableModel(column_headers=["Name", "Val"])
    tmp_model.add_rows(tmp_items)
    tmp_search_view = table_view.TableViewWithToolbar()
    tmp_search_view.set_model(tmp_model)

    # Act & Assert
    tmp_search_view.set_checkboxes_enabled(True)
    assert (
        tmp_search_view.table_view.selectionMode()
        == QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
    )

    tmp_to_select: list[object] = [tmp_items[0]]
    tmp_search_view.set_selected_items(tmp_to_select)
    assert tmp_search_view.selected_items() == [tmp_items[0]]


def test_table_view_select_all_checkbox_with_filter(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify tristate Select All checkbox states and visibility filtering.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = [
        {"Name": "Apple", "Val": 1},
        {"Name": "Banana", "Val": 2},
        {"Name": "Apricot", "Val": 3},
    ]
    tmp_model = DummyTableModel(column_headers=["Name", "Val"])
    tmp_model.add_rows(tmp_items)
    tmp_search_view = table_view.TableViewWithToolbar(filter_column=0)
    tmp_search_view.set_model(tmp_model)
    tmp_search_view.set_checkboxes_enabled(True)

    # Initially, nothing is selected -> Unchecked
    assert (
        tmp_search_view.select_all_checkbox.checkState()
        == QtCore.Qt.CheckState.Unchecked
    )

    # Filter by search string "ap"
    tmp_search_view.search_field.setText("ap")  # Apple and Apricot

    # Check "Select All" -> should select Apple and Apricot
    tmp_search_view.select_all_checkbox.setChecked(True)
    assert tmp_search_view.selected_items() == [tmp_items[0], tmp_items[2]]

    # Clear filter -> Apple and Apricot selected out of 3, so PartiallyChecked
    tmp_search_view.search_field.clear()
    assert (
        tmp_search_view.select_all_checkbox.checkState()
        == QtCore.Qt.CheckState.PartiallyChecked
    )

    # Select all via checking
    tmp_search_view.select_all_checkbox.setChecked(True)
    assert tmp_search_view.selected_items() == tmp_items
    assert (
        tmp_search_view.select_all_checkbox.checkState()
        == QtCore.Qt.CheckState.Checked
    )


def test_table_view_excel_selection(q_app: QtWidgets.QApplication) -> None:
    """Verify Excel-style selection delegate paint parameters.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = [
        {"Name": "Item A", "Val": 1},
        {"Name": "Item B", "Val": 2},
    ]
    tmp_model = DummyTableModel(column_headers=["Name", "Val"])
    tmp_model.add_rows(tmp_items)
    tmp_view = table_view.TableView()
    tmp_view.set_model(tmp_model)
    tmp_view.set_checkboxes_enabled(True)

    # Act & Assert
    assert (
        tmp_view.selectionBehavior()
        == QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems
    )

    tmp_selection_model = tmp_view.selectionModel()
    assert tmp_selection_model is not None
    tmp_view_model = tmp_view.model()
    assert tmp_view_model is not None

    tmp_idx_single = tmp_view_model.index(0, 2)
    tmp_selection_model.select(
        tmp_idx_single,
        QtCore.QItemSelectionModel.SelectionFlag.Select,
    )

    tmp_delegate = tmp_view.itemDelegate()
    assert isinstance(tmp_delegate, table_view.ExcelTableDelegate)

    assert tmp_selection_model.isSelected(tmp_idx_single)
    assert not tmp_selection_model.isSelected(tmp_view_model.index(0, 1))

    for tmp_col in range(tmp_view_model.columnCount()):
        tmp_selection_model.select(
            tmp_view_model.index(1, tmp_col),
            QtCore.QItemSelectionModel.SelectionFlag.Select,
        )

    for tmp_col in range(tmp_view_model.columnCount()):
        assert tmp_selection_model.isSelected(tmp_view_model.index(1, tmp_col))
