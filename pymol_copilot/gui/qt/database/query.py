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
"""Provide query execution blocks for the database layer.

This module is the lowest-level building block of the database layer. It
contains only pure, stateless helper functions and one exception type. No
connection management or domain logic lives here — callers obtain a connection
from the database connection module and pass the QSqlDatabase handle in.

Notes:
    Public surface:
        QueryError: Raised whenever a SQL statement cannot be prepared or
            executed.
        prepare: Prepare a SQL statement against an open connection.
        execute: Bind positional parameters and execute a prepared query,
            retrying on SQLITE_BUSY.
        run: Convenience wrapper that calls prepare then execute in one step.
        scalar: Execute and return the single value in column 0 of the first
            result row, or None.
        rows: Execute and return all result rows as a list of tuples.
        last_insert_id: Return the row identifier captured from the
            last executed INSERT query, without a SQL round-trip.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pymol_copilot.gui.qt import QtSql

__docformat__ = "google"

logger = logging.getLogger(__name__)


class QueryError(RuntimeError):
    """Raised when a SQL statement cannot be prepared or executed."""


def prepare(
    database_connection: QtSql.QSqlDatabase,
    sql_statement: str,
) -> QtSql.QSqlQuery:
    """Prepare a SQL statement against a database connection.

    Args:
        database_connection: An open QSqlDatabase connection.
        sql_statement: The SQL statement to prepare. Use ``?`` as the
            positional parameter placeholder. Qt's ``QSqlQuery.bindValue``
            uses ODBC-style positional markers, and SQLite itself accepts
            ``?`` natively. Values are bound separately from the SQL text,
            which prevents SQL injection by ensuring user-supplied data is
            never interpolated into the statement string.

    Returns:
        A QSqlQuery ready for parameter binding and execution.

    Raises:
        QueryError: If the database is not open or the statement cannot be
            prepared.

    Example:
        tmp_query = prepare(
        database_connection,
        "SELECT id FROM Project WHERE name = ?"
        )
        execute(tmp_query, "my_project")
    """
    if not database_connection.isOpen():
        raise QueryError("Database connection is not open.")
    tmp_query: QtSql.QSqlQuery = QtSql.QSqlQuery(database_connection)
    if not tmp_query.prepare(sql_statement):
        raise QueryError(
            f"Preparation of SQL statement failed: "
            f"{tmp_query.lastError().text()}\n"
            f"SQL: {sql_statement}"
        )
    return tmp_query


def execute(
    query: QtSql.QSqlQuery,
    *parameters: object,
    maximum_retries: int = 3,
) -> QtSql.QSqlQuery:
    """Bind positional parameters to a query and execute it.

    Retries automatically on SQLITE_BUSY (error code 5) using
    exponential back-off starting at 100 ms.

    Args:
        query: A prepared QSqlQuery.
        parameters: Positional values to bind in order. The * prefix
            collects any number of extra positional arguments after query
            into a tuple, making maximum_retries keyword-only. Index
            binds each value to the corresponding ? placeholder via
            QSqlQuery.bindValue.
        maximum_retries: Maximum number of retry attempts for SQLITE_BUSY
            before giving up.

    Returns:
        The executed query so callers can immediately iterate over results.

    Raises:
        QueryError: If execution fails after all retry attempts.

    Example:
        tmp_query = prepare(database_connection, "INSERT INTO Project (name) VALUES (?)", )
        execute(tmp_query, "alpha")
    """
    for tmp_index, tmp_value in enumerate(parameters):
        query.bindValue(tmp_index, tmp_value)

    tmp_last_error: str | None = None
    tmp_retry_delay: float = 0.1

    for tmp_attempt in range(maximum_retries + 1):
        if query.exec():
            return query

        tmp_last_error = query.lastError().text()
        tmp_native_code: str = query.lastError().nativeErrorCode()

        # Name the condition explicitly so the if/else reads as a positive
        # statement rather than a double-negative `else: break`.
        # Busy codes: 5 = SQLITE_BUSY (exclusive/shared lock held by another
        # connection), 261 = SQLITE_BUSY_RECOVERY (WAL checkpoint recovery),
        # 517 = SQLITE_BUSY_SNAPSHOT (read-to-write lock upgrade conflict).
        is_busy = tmp_native_code in ("5", "261", "517")
        if is_busy and tmp_attempt < maximum_retries:
            # Transient lock contention — yield to the other connection
            # via exponential back-off before retrying.
            logger.warning(
                "SQLITE_BUSY — retry %d/%d in %.2fs",
                tmp_attempt + 1,
                maximum_retries,
                tmp_retry_delay,
            )
            time.sleep(tmp_retry_delay)
            tmp_retry_delay *= 2
        else:
            # Either a non-retryable error or we have exhausted all
            # attempts. Break to fall through to the raise below.
            break

    raise QueryError(
        f"Execution failed after {maximum_retries + 1} attempt(s): "
        f"{tmp_last_error}"
    )


def run(
    database_connection: QtSql.QSqlDatabase,
    sql_statement: str,
    *parameters: object,
) -> QtSql.QSqlQuery:
    """Prepare and execute a SQL statement in one call.

    Convenience wrapper around prepare and execute.

    Args:
        database_connection: An open QSqlDatabase connection.
        sql_statement: The SQL statement to run.
        parameters: Positional bind parameters. The * prefix collects any
            number of extra positional arguments after sql_statement into a
            tuple. Index binds each value to the corresponding ? placeholder
            via QSqlQuery.bindValue.

    Returns:
        The executed QSqlQuery.

    Raises:
        QueryError: On prepare or execution failure.
    """
    return execute(
        prepare(database_connection, sql_statement),
        *parameters,
    )


def scalar(
    database_connection: QtSql.QSqlDatabase,
    sql_statement: str,
    *parameters: object,
) -> Any:
    """Execute a query and return the single value in column 0 of the first row.

    Args:
        database_connection: An open QSqlDatabase connection.
        sql_statement: A query expected to return at most one row.
        parameters: Positional bind parameters. The * prefix collects any
            number of extra positional arguments after sql_statement into a
            tuple. Index binds each value to the corresponding ? placeholder
            via QSqlQuery.bindValue.

    Returns:
        The value in column 0 of the first result row, or None if the
        result set is empty.

    Raises:
        QueryError: On prepare or execution failure.
    """
    tmp_query: QtSql.QSqlQuery = run(
        database_connection,
        sql_statement,
        *parameters,
    )
    if tmp_query.next():
        return tmp_query.value(0)
    return None


def rows(
    database_connection: QtSql.QSqlDatabase,
    sql_statement: str,
    *parameters: object,
) -> list[tuple[Any, ...]]:
    """Execute a query and return all result rows as a list of tuples.

    Args:
        database_connection: An open QSqlDatabase connection.
        sql_statement: The SELECT statement to run.
        parameters: Positional bind parameters. The * prefix collects any
            number of extra positional arguments after sql_statement into a
            tuple. Index binds each value to the corresponding ? placeholder
            via QSqlQuery.bindValue.

    Returns:
        A (possibly empty) list of tuples, one per result row.

    Raises:
        QueryError: On prepare or execution failure.
    """
    tmp_query: QtSql.QSqlQuery = run(
        database_connection,
        sql_statement,
        *parameters,
    )
    tmp_result: list[tuple[Any, ...]] = []
    tmp_field_count = tmp_query.record().count()
    tmp_range = range(tmp_field_count)

    while tmp_query.next():
        tmp_result.append(
            tuple(tmp_query.value(tmp_index) for tmp_index in tmp_range)
        )
    return tmp_result


def last_insert_id(last_query: QtSql.QSqlQuery) -> int:
    """Return the row identifier of the most recently inserted row.

    Reads the value Qt already captured from the INSERT execution — no
    extra SQL round-trip is issued. Always call this immediately after the
    INSERT query whose row ID you need; a later query on the same connection
    will overwrite the cached value.

    Args:
        last_query: The executed INSERT QSqlQuery returned by run() or
            execute().

    Returns:
        The last inserted row identifier. Returns 0 if the query did not
        insert a row (SQLite default).

    Example:
        tmp_query = run(database_connection, "INSERT INTO Project (name) VALUES (?)", "beta")
        new_id = last_insert_id(tmp_query)
    """
    # QSqlQuery.lastInsertId() returns the rowid that Qt captured during
    # exec() for the INSERT. Using it here avoids issuing a separate
    # SELECT last_insert_rowid() query — eliminating one full
    # prepare → bind → execute → fetch cycle per INSERT.
    return int(last_query.lastInsertId())
