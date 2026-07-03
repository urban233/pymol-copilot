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
"""Provide logic for reading and writing Excel files using Pandas.

This module contains helper functions to read Excel files into TableModel and
NumpyTableModel instances, and to export model data back to Excel.
"""

from __future__ import annotations

from typing import Any
from typing import Callable
from typing import Optional

import numpy.typing as npt
import pandas as pd

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt.model import table_model


def read_excel_to_table_model(
    file_path: str,
    model: table_model.TableModel,
    row_factory: Optional[Callable[[dict[str, Any]], object]] = None,
    **pandas_kwargs: Any,
) -> None:
    """Read an Excel file and populate a TableModel.

    If the model's column headers are empty, they will be initialized using
    the columns of the read Excel file. If the model already has headers
    defined, the read data will be aligned to match the model's headers.

    Args:
        file_path: Path to the Excel file to read.
        model: The TableModel instance to populate.
        row_factory: Optional callable that takes a dictionary of row data
            and returns an item object for the model. If None, the row
            data dictionary itself is added.
        **pandas_kwargs: Additional keyword arguments passed to
            pandas.read_excel.

    Raises:
        ValueError: If pandas fails to read the file or if input arguments
            are invalid.
    """
    try:
        tmp_df = pd.read_excel(file_path, **pandas_kwargs)
    except Exception as tmp_err:
        raise ValueError(
            f"Failed to read Excel file '{file_path}': {tmp_err}"
        ) from tmp_err

    if not model.headers:
        model.set_column_headers([str(tmp_col) for tmp_col in tmp_df.columns])

    tmp_aligned_df = tmp_df.reindex(columns=model.headers)
    tmp_items = []
    for _, tmp_row in tmp_aligned_df.iterrows():
        tmp_row_dict = tmp_row.to_dict()
        if row_factory is not None:
            tmp_item = row_factory(tmp_row_dict)
        else:
            tmp_item = tmp_row_dict
        tmp_items.append(tmp_item)

    model.add_rows(tmp_items)


def read_excel_to_numpy_table_model(
    file_path: str,
    model: table_model.NumpyTableModel,
    **pandas_kwargs: Any,
) -> None:
    """Read an Excel file and populate a NumpyTableModel.

    The columns of the Excel file are aligned to match the model's headers.

    Args:
        file_path: Path to the Excel file to read.
        model: The NumpyTableModel instance to populate.
        **pandas_kwargs: Additional keyword arguments passed to
            pandas.read_excel.

    Raises:
        ValueError: If pandas fails to read the file or if input arguments
            are invalid.
    """
    try:
        tmp_df = pd.read_excel(file_path, **pandas_kwargs)
    except Exception as tmp_err:
        raise ValueError(
            f"Failed to read Excel file '{file_path}': {tmp_err}"
        ) from tmp_err

    # Reindex columns to match the model's headers
    tmp_aligned_df = tmp_df.reindex(columns=model.headers)
    tmp_data = tmp_aligned_df.to_numpy()
    model.add_rows(tmp_data)


def load_excel_as_table_model(
    file_path: str,
    row_factory: Optional[Callable[[dict[str, Any]], object]] = None,
    sort_key: Optional[Callable[[object], Any]] = None,
    parent: Optional[QtCore.QObject] = None,
    **pandas_kwargs: Any,
) -> table_model.TableModel:
    """Read an Excel file and return a new TableModel.

    Args:
        file_path: Path to the Excel file to read.
        row_factory: Optional callable that takes a dictionary of row data
            and returns an item object for the model. If None, the row
            data dictionary itself is added.
        sort_key: Optional callable used for sorting the model client-side.
        parent: Optional Qt parent object.
        **pandas_kwargs: Additional keyword arguments passed to
            pandas.read_excel.

    Returns:
        A new TableModel instance populated with the Excel data.

    Raises:
        ValueError: If pandas fails to read the file.
    """
    try:
        tmp_df = pd.read_excel(file_path, **pandas_kwargs)
    except Exception as tmp_err:
        raise ValueError(
            f"Failed to read Excel file '{file_path}': {tmp_err}"
        ) from tmp_err

    tmp_headers = [str(tmp_col) for tmp_col in tmp_df.columns]
    tmp_model = table_model.TableModel(
        column_headers=tmp_headers,
        sort_key=sort_key,
        parent=parent,
    )

    tmp_items = []
    for _, tmp_row in tmp_df.iterrows():
        tmp_row_dict = tmp_row.to_dict()
        if row_factory is not None:
            tmp_item = row_factory(tmp_row_dict)
        else:
            tmp_item = tmp_row_dict
        tmp_items.append(tmp_item)

    tmp_model.add_rows(tmp_items)
    return tmp_model


def load_excel_as_numpy_table_model(
    file_path: str,
    dtype: Optional[npt.DTypeLike] = None,
    sort_key: Optional[Callable[[object], Any]] = None,
    parent: Optional[QtCore.QObject] = None,
    **pandas_kwargs: Any,
) -> table_model.NumpyTableModel:
    """Read an Excel file and return a new NumpyTableModel.

    Args:
        file_path: Path to the Excel file to read.
        dtype: Optional numpy data type for the array. Defaults to np.float64.
        sort_key: Optional callable used for sorting.
        parent: Optional Qt parent object.
        **pandas_kwargs: Additional keyword arguments passed to
            pandas.read_excel.

    Returns:
        A new NumpyTableModel instance populated with the Excel data.

    Raises:
        ValueError: If pandas fails to read the file or if input arguments
            are invalid.
    """
    try:
        tmp_df = pd.read_excel(file_path, **pandas_kwargs)
    except Exception as tmp_err:
        raise ValueError(
            f"Failed to read Excel file '{file_path}': {tmp_err}"
        ) from tmp_err

    tmp_headers = [str(tmp_col) for tmp_col in tmp_df.columns]
    tmp_model = table_model.NumpyTableModel(
        column_headers=tmp_headers,
        dtype=dtype,
        sort_key=sort_key,
        parent=parent,
    )

    tmp_data = tmp_df.to_numpy()
    tmp_model.add_rows(tmp_data)
    return tmp_model


def write_table_model_to_excel(
    model: table_model.TableModel,
    file_path: str,
    role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    **pandas_kwargs: Any,
) -> None:
    """Write the contents of a TableModel to an Excel file.

    Extracts cell values using the specified Qt item data role.

    Args:
        model: The TableModel instance to write.
        file_path: Path to the Excel file to write.
        role: The Qt item data role to query for cell values. Defaults to
            QtCore.Qt.ItemDataRole.DisplayRole.
        **pandas_kwargs: Additional keyword arguments passed to
            pandas.DataFrame.to_excel.

    Raises:
        ValueError: If pandas fails to write the file.
    """
    tmp_rows = []
    tmp_row_count = model.rowCount()
    tmp_col_count = model.columnCount()

    for tmp_r in range(tmp_row_count):
        tmp_row_data = []
        for tmp_c in range(tmp_col_count):
            tmp_index = model.index(tmp_r, tmp_c)
            tmp_val = model.data(tmp_index, role)
            tmp_row_data.append(tmp_val)
        tmp_rows.append(tmp_row_data)

    tmp_df = pd.DataFrame(tmp_rows, columns=model.headers)
    try:
        tmp_df.to_excel(file_path, index=False, **pandas_kwargs)
    except Exception as tmp_err:
        raise ValueError(
            f"Failed to write Excel file '{file_path}': {tmp_err}"
        ) from tmp_err


def write_numpy_table_model_to_excel(
    model: table_model.NumpyTableModel,
    file_path: str,
    use_raw_data: bool = True,
    role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    **pandas_kwargs: Any,
) -> None:
    """Write the contents of a NumpyTableModel to an Excel file.

    By default, uses the underlying 2D NumPy array for maximum performance
    and type preservation. Set use_raw_data to False to query display values.

    Args:
        model: The NumpyTableModel instance to write.
        file_path: Path to the Excel file to write.
        use_raw_data: If True, writes the underlying raw numpy array directly.
            If False, queries the cell values using the specified role.
        role: The Qt item data role to query when use_raw_data is False.
            Defaults to QtCore.Qt.ItemDataRole.DisplayRole.
        **pandas_kwargs: Additional keyword arguments passed to
            pandas.DataFrame.to_excel.

    Raises:
        ValueError: If pandas fails to write the file.
    """
    if use_raw_data:
        tmp_df = pd.DataFrame(model.raw_data, columns=model.headers)
    else:
        tmp_rows = []
        tmp_row_count = model.rowCount()
        tmp_col_count = model.columnCount()

        for tmp_r in range(tmp_row_count):
            tmp_row_data = []
            for tmp_c in range(tmp_col_count):
                tmp_index = model.index(tmp_r, tmp_c)
                tmp_val = model.data(tmp_index, role)
                tmp_row_data.append(tmp_val)
            tmp_rows.append(tmp_row_data)
        tmp_df = pd.DataFrame(tmp_rows, columns=model.headers)

    try:
        tmp_df.to_excel(file_path, index=False, **pandas_kwargs)
    except Exception as tmp_err:
        raise ValueError(
            f"Failed to write Excel file '{file_path}': {tmp_err}"
        ) from tmp_err
