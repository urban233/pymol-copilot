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
"""Generic database facade block for the Qt layer.

No application schema or domain methods live here.  Extend this class to
add application-specific persistence methods.

Notes:
    Public surface:
        DatabaseBlock: generic lifecycle and transaction helper.
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
from typing import Generator

from pymol_copilot.gui.qt import QtSql
from pymol_copilot.gui.qt.database import connection
from pymol_copilot.gui.qt.database import query
from pymol_copilot.gui.qt.database import queue

__docformat__ = "google"

logger: logging.Logger = logging.getLogger(__name__)


class DatabaseBlock:
    """Generic Qt-SQL database lifecycle block.

    Args:
        database_path: Absolute path to the SQLite file.
        project_id: Short stable identifier for log messages and pool
            labeling.

    Attributes:
        write_queue: Fire-and-forget async write queue.
    """

    def __init__(self, database_path: str, project_id: str) -> None:
        """Initialize the database block.

        Args:
            database_path: Absolute path to the SQLite file.
            project_id: Short stable identifier for log messages and pool
                labeling.

        Raises:
            ValueError: If database_path or project_id is empty, or if
                database_path is invalid.
        """
        if not database_path:
            raise ValueError("database_path cannot be empty")
        if not project_id:
            raise ValueError("project_id cannot be empty")
        try:
            # Support user home directory expansion (~ paths) and resolve absolute paths.
            # Catch OSError to handle platform-specific invalid path characters safely.
            tmp_database_path = str(
                pathlib.Path(database_path).expanduser().resolve()
            )
        except (TypeError, ValueError, OSError) as tmp_path_error:
            raise ValueError(
                f"Invalid db_path: {tmp_path_error}"
            ) from tmp_path_error

        # <editor-fold desc="Instance attributes">
        self._database_path = tmp_database_path
        self._project_id = project_id
        self._pool = connection.ConnectionPoolBlock(
            self._database_path, project_id
        )
        self.write_queue = queue.WriteQueueBlock(self)
        # </editor-fold>

        logger.info(
            "DatabaseBlock (Qt) ready: '%s' → '%s'",
            project_id,
            self._database_path,
        )

    # <editor-fold desc="Public methods">

    def initialise_schema(self, schema_sql: str) -> None:
        """Execute schema_sql DDL to create tables (idempotent).

        Args:
            schema_sql: DDL with CREATE TABLE IF NOT EXISTS statements
                separated by semicolons.

        Raises:
            query.QueryError: If any SQL statement cannot be prepared or
                executed, or if transaction fails to start.
        """
        # Execute schema DDL statements within an explicit transaction.
        # This guarantees atomicity (either all tables are created or none),
        # preventing partial schema initialization. It also optimizes write
        # performance by flushing schema updates to disk in a single sync.
        with self.transaction() as tmp_database:
            for tmp_stmt in schema_sql.strip().split(";"):
                tmp_stmt_stripped = tmp_stmt.strip()
                if tmp_stmt_stripped:
                    query.run(tmp_database, tmp_stmt_stripped)
        logger.info("Schema initialised for '%s'.", self._project_id)

    def close(self, drain_timeout: float = 10.0) -> None:
        """Drain async writes then release all connections.

        Args:
            drain_timeout: Max seconds to wait for the write queue.
        """
        try:
            if not self.write_queue.drain(timeout=drain_timeout):
                logger.warning(
                    "Write queue drain timed out after %.1fs — "
                    "pending writes may have been discarded for '%s'.",
                    drain_timeout,
                    self._project_id,
                )
        finally:
            # Guarantees connection cleanup even if draining writes fails or times out.
            self._pool.close_all()

    @contextlib.contextmanager
    def transaction(self) -> Generator[QtSql.QSqlDatabase, None, None]:
        """Yield the calling thread's connection inside a transaction.

        Commits on clean exit, rolls back on exception.

        Yields:
            The thread's connection inside an active transaction.

        Raises:
            query.QueryError: If the transaction cannot be started.
            Exception: If any exception occurs during the transaction blocks,
                triggering rollback.

        Example:
            with database_block.transaction() as transaction:
                query.run(transaction, "INSERT INTO ...")
        """
        with self._pool.connection() as tmp_connection:
            # SQLite does not natively support nested transactions, and Qt's
            # QSqlDatabase.transaction() will return False if a transaction
            # is already active on this connection. We fail fast here to
            # prevent invalid operations or unexpected rollbacks.
            if not tmp_connection.transaction():
                raise query.QueryError(
                    f"Failed to start database transaction: "
                    f"{tmp_connection.lastError().text()}"
                )
            try:
                yield tmp_connection
            except Exception:
                # If any exception escapes the context manager block, we
                # rollback the transaction to restore consistency, then
                # re-raise the exception to inform the caller.
                tmp_connection.rollback()
                raise
            else:
                tmp_connection.commit()

    # </editor-fold>

    # <editor-fold desc="Public methods (read-only connection)">

    @contextlib.contextmanager
    def connection(self) -> Generator[QtSql.QSqlDatabase, None, None]:
        """Yield the calling thread's raw connection without transaction wrapping.

        Use this for read-only queries. For writes, prefer transaction() which
        provides atomic commit/rollback semantics.

        Yields:
            The thread's raw QSqlDatabase connection.
        """
        # Delegate directly to the pool. No transaction is started here;
        # this is intentionally a lightweight passthrough for reads.
        with self._pool.connection() as tmp_database:
            yield tmp_database

    # </editor-fold>
