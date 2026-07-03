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
"""Unit tests for the excel reading and writing functions."""

from __future__ import annotations

import pathlib
from typing import Any

import numpy as np
import pandas as pd

from pymol_copilot.gui.qt import excel
from pymol_copilot.gui.qt.model import table_model


class DummyTableModelForExcel(table_model.TableModel):
    """Dummy table model for testing Excel reading/writing."""

    def _cell_data(self, item: object, column: int) -> Any:
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
        return None


def test_read_excel_to_table_model(tmp_path: pathlib.Path) -> None:
    """Verify reading an Excel file into an existing TableModel.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Arrange
    tmp_excel_file = tmp_path / "test_table_model.xlsx"
    tmp_df = pd.DataFrame(
        [
            {"Name": "Alice", "Age": 30},
            {"Name": "Bob", "Age": 25},
        ]
    )
    tmp_df.to_excel(tmp_excel_file, index=False)

    tmp_model = DummyTableModelForExcel(column_headers=["Name", "Age"])

    # Act
    excel.read_excel_to_table_model(str(tmp_excel_file), tmp_model)

    # Assert
    assert tmp_model.rowCount() == 2
    assert tmp_model.columnCount() == 2
    assert tmp_model.row_item(0) == {"Name": "Alice", "Age": 30}
    assert tmp_model.row_item(1) == {"Name": "Bob", "Age": 25}


def test_read_excel_to_numpy_table_model(tmp_path: pathlib.Path) -> None:
    """Verify reading an Excel file into a NumpyTableModel.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Arrange
    tmp_excel_file = tmp_path / "test_numpy_table_model.xlsx"
    tmp_df = pd.DataFrame(
        [
            {"Val1": 1.5, "Val2": 2.5},
            {"Val1": 3.5, "Val2": 4.5},
        ]
    )
    tmp_df.to_excel(tmp_excel_file, index=False)

    tmp_model = table_model.NumpyTableModel(
        column_headers=["Val1", "Val2"], dtype=np.float64
    )

    # Act
    excel.read_excel_to_numpy_table_model(str(tmp_excel_file), tmp_model)

    # Assert
    assert tmp_model.rowCount() == 2
    assert tmp_model.columnCount() == 2
    np.testing.assert_array_almost_equal(
        tmp_model.row_item(0), np.array([1.5, 2.5])
    )
    np.testing.assert_array_almost_equal(
        tmp_model.row_item(1), np.array([3.5, 4.5])
    )


def test_load_excel_as_table_model(tmp_path: pathlib.Path) -> None:
    """Verify load_excel_as_table_model factory.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Arrange
    tmp_excel_file = tmp_path / "test_load_list.xlsx"
    tmp_df = pd.DataFrame(
        [
            {"A": 10, "B": 20},
            {"A": 30, "B": 40},
        ]
    )
    tmp_df.to_excel(tmp_excel_file, index=False)

    # Act
    tmp_model = excel.load_excel_as_table_model(str(tmp_excel_file))

    # Assert
    assert tmp_model.rowCount() == 2
    assert tmp_model.columnCount() == 2
    assert tmp_model.row_item(0) == {"A": 10, "B": 20}


def test_load_excel_as_numpy_table_model(tmp_path: pathlib.Path) -> None:
    """Verify load_excel_as_numpy_table_model factory.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Arrange
    tmp_excel_file = tmp_path / "test_load_numpy.xlsx"
    tmp_df = pd.DataFrame(
        [
            {"A": 10.0, "B": 20.0},
            {"A": 30.0, "B": 40.0},
        ]
    )
    tmp_df.to_excel(tmp_excel_file, index=False)

    # Act
    tmp_model = excel.load_excel_as_numpy_table_model(
        str(tmp_excel_file), dtype=np.float64
    )

    # Assert
    assert tmp_model.rowCount() == 2
    assert tmp_model.columnCount() == 2
    np.testing.assert_array_almost_equal(
        tmp_model.row_item(0), np.array([10.0, 20.0])
    )


def test_write_table_model_to_excel(tmp_path: pathlib.Path) -> None:
    """Verify writing a TableModel to an Excel file.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Arrange
    tmp_excel_file = tmp_path / "test_write_list.xlsx"
    tmp_model = DummyTableModelForExcel(column_headers=["Col1", "Col2"])
    tmp_model.add_rows(
        [
            {"Col1": "Val1", "Col2": "Val2"},
            {"Col1": "Val3", "Col2": "Val4"},
        ]
    )

    # Act
    excel.write_table_model_to_excel(tmp_model, str(tmp_excel_file))

    # Assert
    assert tmp_excel_file.exists()
    tmp_df = pd.read_excel(tmp_excel_file)
    assert list(tmp_df.columns) == ["Col1", "Col2"]
    assert tmp_df.iloc[0].to_dict() == {"Col1": "Val1", "Col2": "Val2"}
    assert tmp_df.iloc[1].to_dict() == {"Col1": "Val3", "Col2": "Val4"}


def test_write_numpy_table_model_to_excel(tmp_path: pathlib.Path) -> None:
    """Verify writing a NumpyTableModel to an Excel file.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Arrange
    tmp_excel_file = tmp_path / "test_write_numpy.xlsx"
    tmp_model = table_model.NumpyTableModel(
        column_headers=["ColA", "ColB"], dtype=np.float64
    )
    tmp_model.add_rows(np.array([[1.0, 2.0], [3.0, 4.0]]))

    # Act
    excel.write_numpy_table_model_to_excel(tmp_model, str(tmp_excel_file))

    # Assert
    assert tmp_excel_file.exists()
    tmp_df = pd.read_excel(tmp_excel_file)
    assert list(tmp_df.columns) == ["ColA", "ColB"]
    assert tmp_df.iloc[0].to_dict() == {"ColA": 1.0, "ColB": 2.0}
    assert tmp_df.iloc[1].to_dict() == {"ColA": 3.0, "ColB": 4.0}


def test_write_numpy_table_model_to_excel_display_role(
    tmp_path: pathlib.Path,
) -> None:
    """Verify writing a NumpyTableModel querying display values.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Arrange
    tmp_excel_file = tmp_path / "test_write_numpy_display.xlsx"
    tmp_model = table_model.NumpyTableModel(
        column_headers=["ColA", "ColB"], dtype=np.float64
    )
    tmp_model.add_rows(np.array([[1.1, 2.2], [3.3, 4.4]]))

    # Act
    excel.write_numpy_table_model_to_excel(
        tmp_model, str(tmp_excel_file), use_raw_data=False
    )

    # Assert
    assert tmp_excel_file.exists()
    tmp_df = pd.read_excel(tmp_excel_file)
    assert list(tmp_df.columns) == ["ColA", "ColB"]
    assert tmp_df.iloc[0].to_dict() == {"ColA": 1.1, "ColB": 2.2}
