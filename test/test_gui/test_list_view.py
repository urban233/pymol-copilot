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
"""Unit tests for the ListView and ListViewWithSearch widgets."""

from __future__ import annotations

from PyQt6 import QtCore
from PyQt6 import QtWidgets
import pytest

from pymol_copilot.gui.qt.model import list_model
from pymol_copilot.gui.qt.widgets import list_view


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


def test_list_view_checkboxes_toggle(q_app: QtWidgets.QApplication) -> None:
    """Verify that checkboxes can be toggled on and off.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = ["Item A", "Item B", "Item C"]
    tmp_model = list_model.ListModel(initial_data=tmp_items)
    tmp_view = list_view.ListView()
    tmp_view.set_model(tmp_model)

    # Act - Enable checkboxes
    tmp_view.set_checkboxes_enabled(True)

    # Assert
    assert (
        tmp_view.selectionMode()
        == QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
    )
    assert tmp_view.itemDelegate() is not None

    # Act - Disable checkboxes
    tmp_view.set_checkboxes_enabled(False)

    # Assert
    assert (
        tmp_view.selectionMode()
        == QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
    )
    assert tmp_view.itemDelegate() is None


def test_list_view_selected_items(q_app: QtWidgets.QApplication) -> None:
    """Verify retrieving selected items when checkboxes are enabled.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = ["Item A", "Item B", "Item C"]
    tmp_model = list_model.ListModel(initial_data=tmp_items)
    tmp_view = list_view.ListView()
    tmp_view.set_model(tmp_model)
    tmp_view.set_checkboxes_enabled(True)

    # Act
    tmp_selection_model = tmp_view.selectionModel()
    assert tmp_selection_model is not None

    # Select row 0 and 2
    tmp_selection_model.select(
        tmp_model.index(0, 0),
        QtCore.QItemSelectionModel.SelectionFlag.Select,
    )
    tmp_selection_model.select(
        tmp_model.index(2, 0),
        QtCore.QItemSelectionModel.SelectionFlag.Select,
    )

    # Assert
    tmp_selected = tmp_view.selected_items()
    assert tmp_selected == ["Item A", "Item C"]


def test_list_view_set_selected_items(q_app: QtWidgets.QApplication) -> None:
    """Verify programmatic setting of selected items.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = ["Item A", "Item B", "Item C"]
    tmp_model = list_model.ListModel(initial_data=tmp_items)
    tmp_view = list_view.ListView()
    tmp_view.set_model(tmp_model)
    tmp_view.set_checkboxes_enabled(True)

    # Act
    tmp_to_select: list[object] = ["Item B", "Item C"]
    tmp_view.set_selected_items(tmp_to_select)

    # Assert
    tmp_selected = tmp_view.selected_items()
    assert tmp_selected == ["Item B", "Item C"]


def test_list_view_select_all_apis(q_app: QtWidgets.QApplication) -> None:
    """Verify the select_all, select_all_visible and deselect_all methods.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = ["Item A", "Item B", "Item C"]
    tmp_model = list_model.ListModel(initial_data=tmp_items)
    tmp_view = list_view.ListView()
    tmp_view.set_model(tmp_model)
    tmp_view.set_checkboxes_enabled(True)

    # Act - Select all
    tmp_view.select_all()

    # Assert
    assert tmp_view.selected_items() == ["Item A", "Item B", "Item C"]

    # Act - Deselect all
    tmp_view.deselect_all()

    # Assert
    assert tmp_view.selected_items() == []


def test_list_view_with_search_integration(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify checkbox and selection APIs on ListViewWithSearch.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = ["Apple", "Banana", "Apricot"]
    tmp_model = list_model.ListModel(initial_data=tmp_items)
    tmp_search_view = list_view.ListViewWithSearch()
    tmp_search_view.set_model(tmp_model)

    # Act & Assert
    tmp_search_view.set_checkboxes_enabled(True)
    assert (
        tmp_search_view.list_view.selectionMode()
        == QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
    )

    tmp_to_select: list[object] = ["Apple", "Apricot"]
    tmp_search_view.set_selected_items(tmp_to_select)
    assert tmp_search_view.selected_items() == ["Apple", "Apricot"]


def test_select_all_checkbox_with_filter(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify tristate Select All checkbox states and visibility filtering.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_items: list[object] = ["Apple", "Banana", "Apricot"]
    tmp_model = list_model.ListModel(initial_data=tmp_items)
    tmp_search_view = list_view.ListViewWithSearch()
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
    assert tmp_search_view.selected_items() == ["Apple", "Apricot"]

    # Clear filter -> Apple and Apricot are selected out of 3, so PartiallyChecked
    tmp_search_view.search_field.clear()
    assert (
        tmp_search_view.select_all_checkbox.checkState()
        == QtCore.Qt.CheckState.PartiallyChecked
    )

    # Select all via checking
    tmp_search_view.select_all_checkbox.setChecked(True)
    assert tmp_search_view.selected_items() == ["Apple", "Banana", "Apricot"]
    assert (
        tmp_search_view.select_all_checkbox.checkState()
        == QtCore.Qt.CheckState.Checked
    )
