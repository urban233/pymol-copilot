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
# Hannah Kullik
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================
#
"""Provide abstract repository base blocks for the Qt database layer.

Mirrors the SQLite repository exactly but types connection
parameters as QtSql.QSqlDatabase instead of sqlite3.Connection.

Notes:
    Public surface:
        RepositoryBlock — template base for single-table CRUD.
        BulkInsertRepositoryBlock — adds looped prepared-statement batch writes.
        NumpyRepositoryBlock — adds numpy-array in/out for numeric data.
"""

from __future__ import annotations

import abc
from abc import ABC
from collections.abc import Iterable
import contextlib
import logging
from typing import Any
from typing import ClassVar
from typing import Generator

import numpy as np

from pymol_copilot.gui.qt import QtSql
from pymol_copilot.gui.qt.database import query

__docformat__ = "google"

logger: logging.Logger = logging.getLogger(__name__)


class RepositoryBlock(abc.ABC):
    """Template base for a single-table data-access block (Qt backend).

    Subclasses set class-level SQL strings and override _row_to_dict.

    Notes:
        Class attributes to set:
            _TABLE        : str — table name (log messages only).
            _SELECT_ALL   : str — SELECT … WHERE parent_id = ?
            _SELECT_BY_ID : str — SELECT … WHERE id = ?
            _DELETE_BY_ID : str — DELETE FROM … WHERE id = ?

    Example:
        class WidgetRepositoryBlock(RepositoryBlock):
            _TABLE        = "Widget"
            _SELECT_ALL   = "SELECT id, name FROM Widget WHERE project_id = ?"
            _SELECT_BY_ID = "SELECT id, name FROM Widget WHERE id = ?"
            _DELETE_BY_ID = "DELETE FROM Widget WHERE id = ?"

            @classmethod
            def _row_to_dict(cls, row) -> dict:
                return {"id": row[0], "name": row[1]}

            @classmethod
            def insert(cls, database, name: str, project_id: int) -> int:
                tmp_query = query.run(database, "INSERT INTO Widget (name, project_id) "
                              "VALUES (?, ?)", name, project_id)
                return query.last_insert_id(tmp_query)
    """

    # <editor-fold desc="Class attributes">
    _TABLE: ClassVar[str] = ""
    _SELECT_ALL: ClassVar[str] = ""
    _SELECT_BY_ID: ClassVar[str] = ""
    _DELETE_BY_ID: ClassVar[str] = ""
    # </editor-fold>

    # <editor-fold desc="Public methods">
    @classmethod
    def get_all(
        cls,
        database: QtSql.QSqlDatabase,
        parent_id: int,
    ) -> list[dict[str, Any]]:
        """Return all rows for the given parent identifier using the select all query.

        Args:
            database: The active database connection.
            parent_id: The identifier of the parent record.

        Returns:
            A list of domain dictionaries representing the found rows.
        """
        # Convert each raw row tuple to a domain dictionary using list comprehension
        # for clean code and optimized CPython execution.
        return [
            cls._row_to_dict(tmp_row)
            for tmp_row in query.rows(database, cls._SELECT_ALL, parent_id)
        ]

    @classmethod
    def get_by_id(
        cls,
        database: QtSql.QSqlDatabase,
        row_id: int,
    ) -> dict[str, Any] | None:
        """Return the row for the given row identifier using the select by identifier query.

        Args:
            database: The active database connection.
            row_id: The identifier of the row to retrieve.

        Returns:
            The domain dictionary of the row if found, otherwise None.
        """
        # Fetch the records matching the requested identifier, converting
        # the single matching row tuple to a domain dictionary if found.
        tmp_result: list[tuple[Any, ...]] = query.rows(
            database, cls._SELECT_BY_ID, row_id
        )
        return cls._row_to_dict(tmp_result[0]) if tmp_result else None

    @classmethod
    def delete(
        cls,
        database: QtSql.QSqlDatabase,
        row_id: int,
    ) -> None:
        """Delete the row for the given row identifier using the delete by identifier query.

        Args:
            database: The active database connection.
            row_id: The identifier of the row to delete.
        """
        logger.debug("delete from %s id=%s", cls._TABLE, row_id)
        query.run(database, cls._DELETE_BY_ID, row_id)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    @classmethod
    @abc.abstractmethod
    def _row_to_dict(cls, row: tuple[Any, ...]) -> dict[str, Any]:
        """Convert a raw result tuple to a domain dictionary.

        Args:
            row: The database result row tuple to convert.

        Returns:
            The parsed domain dictionary representing the row.
        """

    # </editor-fold>


# ABC is listed explicitly even though RepositoryBlock already carries ABCMeta.
# This signals to readers and static-analysis tools that this class is an
# intentionally abstract middle layer, not a concrete class with a missing
# implementation. It also preserves the abstraction guarantee if RepositoryBlock
# is ever removed from the base list.
class BulkInsertRepositoryBlock(RepositoryBlock, ABC):
    """Extends RepositoryBlock with looped prepared-statement batch writes.

    Notes:
        Additional class attributes to set:
            _INSERT     : str — INSERT INTO … VALUES (…)
            _DELETE_ALL : str — DELETE FROM … WHERE parent_id = ?
    """

    # <editor-fold desc="Class attributes">
    _INSERT: ClassVar[str] = ""
    _DELETE_ALL: ClassVar[str] = ""
    # </editor-fold>

    # <editor-fold desc="Public methods">
    @classmethod
    def insert_many(
        cls,
        database: QtSql.QSqlDatabase,
        rows: Iterable[tuple[Any, ...]],
    ) -> None:
        """Insert rows using a prepared statement executed in a loop.

        Args:
            database: An open QSqlDatabase connection.
            rows: Parameter tuples matching the insert query placeholders.
        """
        # Wrapping the loop in a single transaction guarantees rows are
        # flushed to disk in one batch, avoiding costly per-statement fsyncs.
        with cls._optional_transaction(database):
            # Prepare the query once and execute it iteratively to reuse the
            # prepared statement, minimizing query compilation overhead in SQLite.
            tmp_query: QtSql.QSqlQuery = query.prepare(database, cls._INSERT)
            for tmp_row in rows:
                query.execute(tmp_query, *tmp_row)

    @classmethod
    def delete_all(
        cls,
        database: QtSql.QSqlDatabase,
        parent_id: int,
    ) -> None:
        """Delete all rows for the given parent identifier using the delete all query.

        Args:
            database: The active database connection.
            parent_id: The identifier of the parent record.
        """
        query.run(database, cls._DELETE_ALL, parent_id)

    @classmethod
    def replace_all(
        cls,
        database: QtSql.QSqlDatabase,
        parent_id: int,
        # Iterable instead of list matches the insert_many signature and lets
        # callers pass generators or tuples without a needless materialization
        # step. The atomic transaction guarantees correctness regardless of the
        # source type.
        rows: Iterable[tuple[Any, ...]],
    ) -> None:
        """Delete all rows for a parent identifier and then bulk-insert new rows.

        Args:
            database: The active database connection.
            parent_id: The identifier of the parent record.
            rows: Parameter tuples matching the insert query placeholders.
        """
        # Wrapping both delete and insert operations in the same transaction
        # boundary ensures atomic replacement. If the delete succeeds but
        # the subsequent insert_many fails, the transaction is rolled back,
        # preventing data loss and preserving pre-existing records.
        with cls._optional_transaction(database):
            cls.delete_all(database, parent_id)
            cls.insert_many(database, rows)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    @staticmethod
    @contextlib.contextmanager
    def _optional_transaction(
        database: QtSql.QSqlDatabase,
    ) -> Generator[None, None, None]:
        """Start a transaction if none is active, commit or rollback on exit.

        Because nested transactions are not supported by SQLite/QtSql, this
        context manager only starts and manages a transaction if one is not
        already active. If the caller already holds a transaction, this
        becomes a no-op wrapper.

        Args:
            database: The active database connection.

        Yields:
            None.
        """
        tmp_started = database.transaction()
        try:
            yield
        except Exception:
            if tmp_started:
                database.rollback()
            raise
        else:
            if tmp_started:
                database.commit()

    # </editor-fold>


# ABC is listed explicitly even though BulkInsertRepositoryBlock already
# carries ABCMeta. This signals to readers and static-analysis tools that
# this class is an intentionally abstract middle layer, not a concrete
# class with a missing implementation.
class NumpyRepositoryBlock(BulkInsertRepositoryBlock, ABC):
    """Extends BulkInsertRepositoryBlock for numpy-backed numeric data.

    Notes:
        Additional class attribute to set:
            _ARRAY_KEYS : tuple[str, ...] — column names matching the SELECT list.
    """

    # <editor-fold desc="Class attributes">
    _ARRAY_KEYS: ClassVar[tuple[str, ...]] = ()
    # </editor-fold>

    # <editor-fold desc="Public methods">
    @classmethod
    def get_as_arrays(
        cls,
        database: QtSql.QSqlDatabase,
        parent_id: int,
    ) -> dict[str, np.ndarray]:
        """Return all rows as a dictionary of numpy arrays keyed by array keys.

        Args:
            database: The active database connection.
            parent_id: The identifier of the parent record.

        Returns:
            A dictionary of NumPy arrays containing the query results.
        """
        # Query all numerical data from the parent container.
        tmp_data: list[tuple[Any, ...]] = query.rows(
            database, cls._SELECT_ALL, parent_id
        )
        if not tmp_data:
            # Create one independent empty array per key. A single shared
            # object would mean an in-place write (arr[:] = …) on one key
            # silently corrupts every other key in the returned dictionary.
            return {tmp_key: np.array([]) for tmp_key in cls._ARRAY_KEYS}

        # Transpose rows into column arrays and map them to their respective keys.
        tmp_transposed = zip(*tmp_data, strict=True)
        return {
            tmp_key: np.array(tmp_value)
            for tmp_key, tmp_value in zip(
                cls._ARRAY_KEYS, tmp_transposed, strict=True
            )
        }

    @classmethod
    def insert_arrays(
        cls,
        database: QtSql.QSqlDatabase,
        parent_id: int,
        arrays: dict[str, np.ndarray],
    ) -> None:
        """Bulk-insert from a dictionary of equal-length NumPy arrays.

        Args:
            database: The active database connection.
            parent_id: The identifier of the parent record.
            arrays: Dictionary of equal-length NumPy arrays to insert.
        """
        if not arrays:
            return
        # Determine the total elements from the first array in the dictionary.
        tmp_length: int = len(next(iter(arrays.values())))

        # Stream the row tuples dynamically using a generator expression,
        # avoiding large in-memory list allocations for bulk inserts.
        tmp_generate_rows = (
            cls._pack_array_row(arrays, parent_id, tmp_index)
            for tmp_index in range(tmp_length)
        )

        cls.insert_many(database, tmp_generate_rows)

    # </editor-fold>

    # <editor-fold desc="Private methods">
    @classmethod
    @abc.abstractmethod
    def _pack_array_row(
        cls,
        arrays: dict[str, np.ndarray],
        parent_id: int,
        index: int,
    ) -> tuple[Any, ...]:
        """Build one insert-parameter tuple for a row index.

        Args:
            arrays: Dictionary of equal-length NumPy arrays.
            parent_id: The identifier of the parent record.
            index: The index of the row to pack.

        Returns:
            The parameter tuple for insertion.
        """

    # </editor-fold>
