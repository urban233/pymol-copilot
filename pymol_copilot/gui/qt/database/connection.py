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
"""Provide a connection pool block for the database layer.

This module provides ConnectionPoolBlock, which maintains exactly one
QSqlDatabase connection per calling thread. This is the correct model for
Qt's SQL driver: connections must not be shared across threads, but within
a single thread a single connection is reused for the lifetime of the pool.

Notes:
    Public surface:
        ConnectionPoolBlock: Thread-safe per-thread SQLite connection pool.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Generator

from pymol_copilot.gui.qt import QtSql

__docformat__ = "google"

logger = logging.getLogger(__name__)


class ConnectionPoolBlock:
    """Thread-safe SQLite connection pool issuing one connection per thread.

    Each DatabaseBlock owns exactly one ConnectionPoolBlock.
    The pool creates a new QSqlDatabase connection the first time a thread
    calls connection, then reuses that connection for every subsequent call
    from the same thread. Connections are held open until close_all is
    called (typically when the owning database is closed).

    Args:
        database_path: Absolute path to the SQLite file. The file does not need
            to exist yet - it will be created on first connect.
        pool_id: A short, stable identifier for the owning project (e.g., the
            project name or a UUID). Used as the QSqlDatabase connection-name
            prefix so that multiple open projects never clash in Qt's global
            connection registry.
        driver: Qt SQL driver name passed to QSqlDatabase.addDatabase.
            Defaults to "QSQLITE".

    Example:
        pool = ConnectionPoolBlock("/data/projects/alpha.db", "alpha")

        with pool.connection() as database_connection:
            query = QtSql.QSqlQuery(database_connection)
            query.prepare("SELECT id FROM Project WHERE name = ?")
            query.bindValue(0, "alpha")
            query.exec()
    """

    def __init__(
        self,
        database_path: str,
        pool_id: str,
        driver: str = "QSQLITE",
    ) -> None:
        """Initialize the ConnectionPoolBlock.

        Args:
            database_path: Absolute path to the SQLite file.
            pool_id: Stable identifier prefix for Qt database connection names.
            driver: Qt SQL driver name passed to QSqlDatabase.addDatabase.
                Defaults to "QSQLITE".
        """
        # <editor-fold desc="Instance attributes">
        self._database_path = database_path
        self._pool_id = pool_id
        self._driver = driver
        self._lock = threading.Lock()
        self._local = threading.local()
        self._closed = False
        self._all_connections: list[QtSql.QSqlDatabase] = []
        # </editor-fold>

    # <editor-fold desc="Public methods">
    @contextlib.contextmanager
    def connection(
        self,
        max_retries: int = 3,
        retry_delay: float = 0.1,
    ) -> Generator[QtSql.QSqlDatabase, None, None]:
        """Context manager yielding an open, thread-local QSqlDatabase.

        Retries on transient errors (SQLITE_BUSY, connection failures)
        using exponential back-off. The connection is kept alive after the
        context exits - it is reused by subsequent calls from the same thread.
        Call close_all to release all connections.

        Args:
            max_retries: Maximum number of open-retry attempts.
            retry_delay: Initial delay between retries in seconds (doubled on
                each subsequent retry).

        Yields:
            An open QSqlDatabase connection bound to the calling thread.

        Raises:
            ConnectionError: If the connection cannot be opened after all
                retries.

        Example:
            with pool.connection() as database_connection:
                run(database_connection, "INSERT INTO Project (name) VALUES (?)", "beta")
        """
        tmp_database = self._get_or_create()
        tmp_current_delay = retry_delay

        for tmp_attempt in range(max_retries + 1):
            if tmp_database.isOpen():
                break
            if tmp_database.open():
                logger.debug(
                    "[%s] Connection opened for thread %d",
                    self._pool_id,
                    threading.get_ident(),
                )
                break

            tmp_last_error = tmp_database.lastError().text()
            if tmp_attempt < max_retries:
                logger.warning(
                    "[%s] Connection attempt %d/%d failed: %s — "
                    "retrying in %.1fs…",
                    self._pool_id,
                    tmp_attempt + 1,
                    max_retries + 1,
                    tmp_last_error,
                    tmp_current_delay,
                )
                time.sleep(tmp_current_delay)
                # Double the current delay for exponential back-off.
                tmp_current_delay *= 2
            else:
                raise ConnectionError(
                    f"[{self._pool_id}] Cannot open database after "
                    f"{max_retries + 1} attempt(s): {tmp_last_error}"
                )

        # Connection is kept alive for reuse; closing is deferred to
        # close_all().
        yield tmp_database

    def close_all(self) -> None:
        """Close all thread connections and remove them from Qt's registry.

        Always call this before discarding a ConnectionPoolBlock to
        avoid leaking Qt connection names.
        """
        with self._lock:
            self._closed = True
            tmp_names_to_remove = []
            for tmp_database in self._all_connections:
                tmp_connection_name = tmp_database.connectionName()
                tmp_database.close()
                tmp_names_to_remove.append(tmp_connection_name)

            # Qt's QSqlDatabase maintains a global connection registry. If
            # any QSqlDatabase Python object wrapper remains in scope for a
            # connection, calling QtSql.QSqlDatabase.removeDatabase() will
            # print a warning that the database connection is still in use.
            # We must clear all Python references in both the pool's list
            # and the thread-local storage to drop the reference counts
            # to zero before removing it from the global registry.
            self._all_connections.clear()

            if hasattr(self._local, "connection"):
                delattr(self._local, "connection")

            for tmp_connection_name in tmp_names_to_remove:
                QtSql.QSqlDatabase.removeDatabase(tmp_connection_name)
                logger.debug(
                    "[%s] Closed connection %s",
                    self._pool_id,
                    tmp_connection_name,
                )

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _get_or_create(self) -> QtSql.QSqlDatabase:
        """Return the thread connection, creating it if needed.

        Returns:
            The thread-local QtSql database connection instance.
        """
        # Check early so that threads which already have a cached
        # thread-local connection still observe a closed pool.
        # Reading _closed without the lock is safe: the flag is a
        # monotonic bool (False -> True, once) set under the lock in
        # close_all(), and Python's GIL guarantees atomic attribute reads.
        if self._closed:
            raise ConnectionError(
                f"[{self._pool_id}] Connection pool is closed."
            )
        # We use threading.local to provide lock-free lookup for subsequent
        # connection requests on the same thread, preventing thread contention.
        if not hasattr(self._local, "connection"):
            # A lock is required to guard the actual creation because
            # QSqlDatabase.addDatabase registers the connection globally.
            # Threading races during registration could result in duplicate
            # connection names or corrupted internal registries.
            with self._lock:
                if self._closed:
                    raise ConnectionError(
                        f"[{self._pool_id}] Connection pool is closed."
                    )
                tmp_thread_id = threading.get_ident()
                tmp_connection_name = f"{self._pool_id}_t{tmp_thread_id}"
                # Stubs resolve the QSqlDatabase overload first; passing a
                # driver name str is valid Qt API.
                tmp_database = QtSql.QSqlDatabase.addDatabase(
                    self._driver, tmp_connection_name
                )
                tmp_database.setDatabaseName(self._database_path)
                self._local.connection = tmp_database
                self._all_connections.append(tmp_database)
                logger.debug(
                    "[%s] Created connection %s",
                    self._pool_id,
                    tmp_connection_name,
                )
        return self._local.connection

    # </editor-fold>
