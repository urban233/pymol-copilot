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
"""Provide an asynchronous write-queue block for the database layer.

This module serializes a fire-and-forget database written for one project using
a background thread pool. At most one worker drains the queue at any time,
giving the same serialization guarantee as a dedicated thread but using a
shared pool instead.

Notes:
    Public surface:
        WriteOperationBlock: A single unit of deferred database work.
        WriteQueueBlock: The queue; call WriteQueueBlock.submit
            from any thread and WriteQueueBlock.drain before closing.
"""

from __future__ import annotations

from collections.abc import Callable
import dataclasses
import logging
import queue
import threading
from typing import Any
from typing import TYPE_CHECKING

from pymol_copilot.gui.qt import thread

if TYPE_CHECKING:
    from pymol_copilot.gui.qt.database import database

__docformat__ = "google"

logger: logging.Logger = logging.getLogger(__name__)


@dataclasses.dataclass
class WriteOperationBlock:
    """A single unit of deferred database work.

    Args:
        callback: A callback function accepting the database block as its first
            argument.
        args: Positional arguments for the callback function.
        kwargs: Keyword arguments for the callback function.
    """

    callback: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = dataclasses.field(default_factory=dict)


class WriteQueueBlock:
    """Serialized write queue for one DatabaseBlock.

    At most one background worker drains this queue at any time. When the
    worker empties the queue it stops; the next submit call restarts it.

    Args:
        database_block: The database block to write into.
        max_queue_size: Maximum number of buffered operations.

    Example:
        import pymol_copilot.gui.qt.database.queue as queue_module

        def _insert_record(db, name):
            db.insert_something(name)

        write_queue = queue_module.WriteQueueBlock(database_block)
        operation = queue_module.WriteOperationBlock(_insert_record, ("test",))
        write_queue.submit(operation)
        write_queue.drain()
    """

    def __init__(
        self,
        database_block: database.DatabaseBlock,
        max_queue_size: int = 1000,
    ) -> None:
        """Initializes a WriteQueueBlock instance.

        This constructor method sets up an instance of WriteQueueBlock by initializing
        the database connection block, queue, and associated worker thread controls. It
        validates the provided parameters such as a non-null database handle and ensures
        a positive queue size. Internal attributes like locks and counters for tracking
        write operations are also initialized.

        Args:
            database_block: The database block used for write operations. Must not
                be None.
            max_queue_size: Maximum size of the queue used for buffering write
                operation blocks. Must be at least 1.

        Raises:
            ValueError: If `database_block` is None
            or `max_queue_size` is less than 1.
        """
        if database_block is None:
            raise ValueError("Database handle cannot be None.")
        if max_queue_size < 1:
            raise ValueError("Maximum queue size must be at least 1.")

        # <editor-fold desc="Instance attributes">
        # The database block that receives all dispatched write operations.
        self._database: database.DatabaseBlock = database_block
        # Bounded FIFO queue that buffers pending write operations.
        self._queue: queue.Queue[WriteOperationBlock] = queue.Queue(
            maxsize=max_queue_size
        )
        # Guards _worker_running to prevent duplicate worker starts.
        self._lock: threading.Lock = threading.Lock()
        # True while a background worker is actively draining the queue.
        self._worker_running: bool = False
        # Signaled when the queue is empty and no worker is running.
        self._drained: threading.Event = threading.Event()
        self._drained.set()
        # Cumulative count of operations that completed without error.
        self._successful_count: int = 0
        # Cumulative count of operations that raised an exception.
        self._failed_count: int = 0
        # </editor-fold>

        logger.info(
            "WriteQueueBlock initialized with max_queue_size=%d",
            max_queue_size,
        )

    # <editor-fold desc="Public methods">
    def submit(
        self,
        operation: WriteOperationBlock,
        timeout: float | None = 5.0,
    ) -> None:
        """Enqueue operation for asynchronous execution.

        This method is thread-safe. It blocks if the queue is full until timeout
        expires.

        Args:
            operation: The write operation to enqueue.
            timeout: Seconds to wait when the queue is full. None waits
                indefinitely. Defaults to 5.0.

        Raises:
            ValueError: If operation is None.
            queue.Full: If the queue is full and timeout expires.
        """
        if operation is None:
            raise ValueError("Operation cannot be None.")
        try:
            # Buffer the task in the bounded FIFO queue. If the queue is full,
            # block to apply backpressure to the producer thread, preventing
            # unbounded memory consumption.
            self._queue.put(operation, timeout=timeout)
        except queue.Full:
            # The item was never queued, so _drained must NOT be cleared.
            # Leaving it in its current state (signaled) is correct: there is
            # nothing new to drain, and drain() callers must not be blocked.
            logger.error(
                "WriteQueueBlock full (max=%d). Operation %s rejected.",
                self._queue.maxsize,
                operation.callback,
            )
            raise
        # Only clear _drained after the item is confirmed in the queue.
        # Clearing before put() would leave _drained unsignaled if put() raised,
        # causing all subsequent drain() calls to block until timeout.
        self._drained.clear()
        logger.debug("Queued operation: %s", operation.callback)
        # If no background worker is active, spawn one to drain the new item.
        self._ensure_worker_running()

    def drain(self, timeout: float = 10.0) -> bool:
        """Block until the queue is empty or timeout seconds elapse.

        Always call this before closing the database to guarantee all pending
        writes have been committed.

        Args:
            timeout: Maximum seconds to wait. Defaults to 10.0.

        Returns:
            True if drained successfully, False on timeout.
        """
        tmp_drained = self._drained.wait(timeout=timeout)
        if tmp_drained:
            logger.info(
                "WriteQueueBlock drained. ok=%d, fail=%d",
                self._successful_count,
                self._failed_count,
            )
        else:
            logger.warning(
                "WriteQueueBlock.drain() timed out after %.1fs (pending=%d)",
                timeout,
                self._queue.qsize(),
            )
        return tmp_drained

    def get_stats(self) -> dict[str, int]:
        """Return a snapshot of queue statistics.

        Returns:
            Dictionary containing successful, failed, pending, and max_size
            statistics.
        """
        return {
            "successful": self._successful_count,
            "failed": self._failed_count,
            "pending": self._queue.qsize(),
            "max_size": self._queue.maxsize,
        }

    # </editor-fold>

    # <editor-fold desc="Private methods">
    def _ensure_worker_running(self) -> None:
        """Ensure a background worker is running to drain the queue."""
        # Use a mutex lock to guarantee that at most one background worker is
        # started. This serializes all database writes sequentially on the
        # worker thread, preventing concurrent write conflicts or lock
        # contention on the SQLite file.
        with self._lock:
            if self._worker_running:
                return
            self._worker_running = True

        tmp_stats: dict[str, int] = {"successful": 0, "failed": 0}
        # Spawn the worker using the shared Qt thread pool instead of spinning
        # up a dedicated OS thread. This is resource-efficient.
        (
            _create_drain_job(self._database, self._queue, tmp_stats)
            .on_success(lambda _: self._on_worker_finished(tmp_stats))
            .on_error(self._on_worker_error)
            .start()
        )

    def _on_worker_finished(self, tmp_stats: dict[str, int]) -> None:
        """Process results when a background worker completes its execution.

        Args:
            tmp_stats: Dictionary containing successful and failed counts from
                the worker execution.
        """
        with self._lock:
            # Accumulate stats under the lock. In PyQt6, connecting a plain
            # Python callable with AutoConnection delivers the signal via a
            # direct call from the emitting (worker) thread rather than
            # queuing it. Incrementing these counters outside the lock would
            # create a data race with concurrent get_stats() callers.
            self._successful_count += tmp_stats["successful"]
            self._failed_count += tmp_stats["failed"]
            if self._queue.empty():
                # Queue is fully drained: mark the worker as stopped and
                # signal drain() waiters. Return without spawning a new worker.
                self._worker_running = False
                self._drained.set()
                return

        # Queue still has items. _worker_running remains True (no other thread
        # can start a second worker), and we spawn a fresh batch immediately
        # to drain what arrived since this worker started.
        tmp_new_stats: dict[str, int] = {"successful": 0, "failed": 0}
        (
            _create_drain_job(self._database, self._queue, tmp_new_stats)
            .on_success(lambda _: self._on_worker_finished(tmp_new_stats))
            .on_error(self._on_worker_error)
            .start()
        )

    def _on_worker_error(
        self,
        exception: Exception,
        traceback_string: str,
    ) -> None:
        """Handle errors raised by the background worker.

        Args:
            exception: The exception raised by the worker.
            traceback_string: The traceback of the exception.
        """
        logger.exception(
            "WriteQueueBlock worker raised an error: %s",
            traceback_string,
            exc_info=exception,
        )
        with self._lock:
            self._worker_running = False
            self._failed_count += 1
        if self._queue.empty():
            self._drained.set()
        else:
            logger.info(
                "Restarting worker after error (pending=%d)",
                self._queue.qsize(),
            )
            self._ensure_worker_running()

    # </editor-fold>


def _create_drain_job(
    database_block: database.DatabaseBlock,
    work_queue: queue.Queue[WriteOperationBlock],
    tmp_stats: dict[str, int],
) -> thread.BackgroundJob:
    """Create a background job that drains operations from the queue.

    Args:
        database_block: The database block to write into.
        work_queue: The queue of operations to drain.
        tmp_stats: Dictionary to collect execution statistics.

    Returns:
        A BackgroundJob ready for callback attachment and starting.
    """
    tmp_worker = thread.Worker(
        _drain_worker, database_block, work_queue, tmp_stats
    )
    return thread.BackgroundJob(tmp_worker)


def _drain_worker(
    database_block: database.DatabaseBlock,
    work_queue: queue.Queue[WriteOperationBlock],
    tmp_stats: dict[str, int],
    **_kwargs: Any,
) -> None:
    """Drain as many operations as possible from work_queue.

    Individual failures are logged and skipped, so one bad writing does not
    block later ones. Returns when the queue is empty.

    Args:
        database_block: The database block to write into.
        work_queue: The queue of operations to drain.
        tmp_stats: Dictionary to collect execution statistics.
        _kwargs: Additional keyword arguments passed by background runner.
    """
    # The worker runs on a background thread pool thread. It loops until the
    # queue is completely drained. To ensure robustness, each operation is
    # wrapped in its own try-except block so that a failure in one query (e.g.
    # a constraint violation or syntax error) does not abort the entire queue
    # processing or crash the worker.
    tmp_processed: int = 0
    while True:
        try:
            tmp_operation: WriteOperationBlock = work_queue.get_nowait()
        except queue.Empty:
            logger.debug(
                "Worker processed %d operations then queue was empty",
                tmp_processed,
            )
            return

        # noinspection PyBroadException
        try:
            # Execute the deferred write operation. The database_block is
            # always passed as the first argument, so the callback can open
            # transactions and run queries. The remaining positional and
            # keyword arguments were captured when the WriteOperationBlock
            # was created and are unpacked here.
            tmp_operation.callback(
                database_block,
                *tmp_operation.args,
                **tmp_operation.kwargs,
            )
            tmp_stats["successful"] += 1
            tmp_processed += 1
            logger.debug(
                "Operation executed: %s",
                tmp_operation.callback,
            )
        except Exception:
            tmp_stats["failed"] += 1
            logger.exception(
                "Write operation %s failed and was skipped.",
                tmp_operation.callback,
            )
