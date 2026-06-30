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
"""Provide a cold-handle block for the database layer.

ColdHandleBlock is a narrow, write-only interface handed to
background jobs that need to persist results into a project that is not
currently open in the UI. The job receives only what it needs — the ability
to submit write operations — without a reference to the full
DatabaseBlock, the UI controller, or application state.

Notes:
    Public surface:
        ColdHandleBlock: Lightweight write-only proxy for a cold project.
"""

from __future__ import annotations

import logging
import threading
import types
from collections.abc import Callable
from typing import TYPE_CHECKING

from pymol_copilot.gui.qt.database import queue

if TYPE_CHECKING:
    from pymol_copilot.gui.qt.database import database

__docformat__ = "google"

logger: logging.Logger = logging.getLogger(__name__)


class ColdHandleBlock:
    """Represent a write-only proxy to a cold project database block.

    The background job receives only the ability to submit writes — no UI
    controller, no AppState, no full database reference. The handle is
    cheap to pass around as a thin wrapper.

    Calling close drains the writing queue and releases all connections.
    An optional on_closed callback notifies the controller so it can remove
    the entry from its internal cold-database registry without the job
    needing to know about the controller.

    Example:
        from pymol_copilot.gui.qt.database import queue

        def _insert_pair(db, pair):
            db.insert_protein_pair_full(pair)

        def _analysis_worker(progress_callback, is_cancelled, handle, pair):
            # ... analysis work ...
            operation = queue.WriteOperationBlock(_insert_pair, (pair,))
            handle.submit(operation)
            handle.close()
    """

    __slots__ = (
        # Flag indicating whether the handle has been closed.
        "_closed",
        # The underlying database block for write operations.
        "_database_block",
        # Lock guarding closed state and submit for thread safety.
        "_lock",
        # Optional callback invoked with project_id after close.
        "_on_closed",
        # Stable identifier for the project this handle represents.
        "_project_id",
    )

    def __init__(
        self,
        project_id: str,
        database_block: database.DatabaseBlock,
        on_closed: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize the ColdHandleBlock.

        Args:
            project_id: The stable identifier for this project. Must be a
                non-empty string.
            database_block: The underlying database block.
            on_closed: Optional callback invoked after close drains and
                releases the database. Receives project_id as its only
                argument. If None, no callback is invoked.

        Raises:
            ValueError: If project_id is empty.
        """
        if not project_id:
            raise ValueError("project_id cannot be empty.")

        # <editor-fold desc="Instance attributes">
        # Stable identifier for the project this handle was created for.
        self._project_id: str = project_id
        # The underlying database block that receives all submitted write operations.
        self._database_block: database.DatabaseBlock = database_block
        # Optional callback invoked with project_id after the handle is closed.
        self._on_closed: Callable[[str], None] | None = on_closed
        # True once close() has been called; prevents duplicate close operations.
        self._closed: bool = False
        # Guards _closed and submit to ensure thread-safe state transitions.
        self._lock: threading.Lock = threading.Lock()
        # </editor-fold>

    # <editor-fold desc="Public methods">

    def __enter__(self) -> ColdHandleBlock:
        """Enter the context manager.

        Returns:
            The ColdHandleBlock instance itself.
        """
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        exception_traceback: types.TracebackType | None,
    ) -> None:
        """Exit the context, ensuring the handle is closed.

        Args:
            exception_type: The exception type, or None if the context exited
                without an exception.
            exception_value: The exception instance, or None if the context
                exited without an exception.
            exception_traceback: The exception traceback, or None if the context
                exited without an exception.
        """
        self.close()

    @property
    def project_id(self) -> str:
        """Get the stable project identifier this handle was created for.

        Returns:
            The stable project identifier string.
        """
        return self._project_id

    @property
    def closed(self) -> bool:
        """Check if the handle has been closed. Thread-safe.

        Returns:
            True if the handle is closed, False otherwise.
        """
        with self._lock:
            return self._closed

    def submit(self, operation: queue.WriteOperationBlock) -> None:
        """Enqueue a fire-and-forget writing operation. Thread-safe.

        Args:
            operation: The write operation block to enqueue.

        Raises:
            RuntimeError: If the handle has already been closed.
        """
        # Acquire the lock only to read _closed. Release it immediately so
        # that write_queue.submit() — which may block up to its timeout when
        # the queue is full — is never executed while holding this lock.
        # Holding the lock across a blocking call creates a deadlock cycle:
        #   Thread A (submit): holds _lock, blocked waiting for queue space.
        #   Thread B (close):  waits on _lock to drain the queue that would
        #                      free the space Thread A is waiting for.
        with self._lock:
            if self._closed:
                raise RuntimeError(
                    f"ColdHandleBlock for project '{self._project_id}' "
                    f"has already been closed."
                )
        # Lock released. The brief race window here is intentional and
        # acceptable: at worst one extra write is submitted to a closing
        # database, and the write queue's own drain will execute it.
        self._database_block.write_queue.submit(operation)

    def close(self, drain_timeout: float = 10.0) -> None:
        """Drain pending writes and close the database.

        Safe to call multiple times — later calls are silent no-operations.
        Also invokes the optional on_closed callback with project_id.

        Args:
            drain_timeout: Maximum seconds to wait for the writing queue to
                empty before closing. Must be non-negative. Defaults to 10.0.

        Raises:
            ValueError: If drain_timeout is negative.
        """
        if drain_timeout < 0.0:
            raise ValueError("drain_timeout must be non-negative.")

        with self._lock:
            if self._closed:
                return
            self._closed = True

        self._database_block.close(drain_timeout=drain_timeout)
        if self._on_closed is not None:
            self._on_closed(self._project_id)
        logger.info(
            "ColdHandleBlock session for project '%s' closed successfully.",
            self._project_id,
        )

    # </editor-fold>
