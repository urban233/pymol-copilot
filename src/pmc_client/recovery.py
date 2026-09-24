# Copyright 2026 PyMOL Copilot contributors.
"""Private, plan-associated PyMOL recovery points.

This module owns the lifetime and file permissions of a recovery ``.pse``;
it does not decide whether a plan is safe to apply.  On POSIX, its directory
and files are enforced as 0700 and 0600 respectively.  Windows' ``chmod``
only maps to a read-only flag, so the corresponding privacy guarantee there
comes from the current user's profile ACL rather than a claimed POSIX mode.
"""

from __future__ import annotations

import os
import stat
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Protocol


RECOVERY_DIRECTORY = Path(".pymol-copilot") / "recovery"
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600


class RecoveryCmd(Protocol):
    """The narrow PyMOL command surface recovery needs."""

    def save(self, filename: str) -> None:
        """Save the complete current session to ``filename``."""

    def load(self, filename: str, *, partial: int) -> None:
        """Load a complete replacement session from ``filename``."""


class RecoveryPointError(RuntimeError):
    """Raised when a recovery point cannot be safely retained or restored."""


class RecoveryStore:
    """Own one active point, retaining its predecessor during a new apply.

    Args:
        root: Home-directory root under which the private recovery directory
            is created. Defaults to the current user's resolved home path;
            injection keeps tests hermetic.
    """

    def __init__(self, root: Path | None = None) -> None:
        """Create a store rooted at the user's home directory or ``root``."""
        self._root = (Path.home() if root is None else root).resolve()
        self._retained: Path | None = None
        self._previous: Path | None = None
        # A failed cleanup must not become an active rollback handle, but
        # its path must remain reachable for a later close() retry.
        self._obsolete: list[Path] = []

    @property
    def retained(self) -> Path | None:
        """Return the currently retained recovery point, if any."""
        return self._retained

    @property
    def directory(self) -> Path:
        """Return this store's private recovery directory."""
        return self._root / RECOVERY_DIRECTORY

    def save(self, cmd: RecoveryCmd, plan_id: str) -> Path:
        """Save a replacement-session recovery point before live mutation.

        A new point is staged and verified before it becomes active. The
        previous point remains available until the new apply succeeds.

        Args:
            cmd: Live PyMOL command module.
            plan_id: Server-issued identifier naming this recovery point.

        Returns:
            The verified private ``.pse`` path.

        Raises:
            RecoveryPointError: If PyMOL cannot save the point or its file
                permissions cannot be established and verified.
        """
        directory = self.directory
        path: Path | None = None
        staged: Path | None = None
        previous = self._retained
        if self._previous is not None:
            raise RecoveryPointError("prior apply has not been resolved")
        try:
            directory.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
            os.chmod(directory, DIRECTORY_MODE)
            path = directory / f"plan-{plan_id}.pse"
            if path == previous:
                raise RecoveryPointError("plan already has a recovery point")
            staged = directory / f".plan-{plan_id}-{uuid.uuid4().hex}.pse"
            cmd.save(str(staged))
            if not staged.is_file():
                raise RecoveryPointError("PyMOL did not create recovery point")
            os.chmod(staged, FILE_MODE)
            if (
                os.name != "nt"
                and stat.S_IMODE(staged.stat().st_mode) != FILE_MODE
            ):
                raise RecoveryPointError(
                    "recovery point does not have mode 0600"
                )
            os.replace(staged, path)
        except RecoveryPointError:
            self._remove_unretained(staged)
            raise
        except Exception as error:
            self._remove_unretained(staged)
            raise RecoveryPointError("could not save recovery point") from error
        assert path is not None
        self._retained = path
        self._previous = previous
        return path

    def commit(self) -> None:
        """Finish a successful apply and remove its older rollback point."""
        previous = self._previous
        self._previous = None
        if previous is None:
            return
        try:
            previous.unlink(missing_ok=True)
        except OSError as error:
            self._obsolete.append(previous)
            raise RecoveryPointError(
                "could not discard previous recovery point"
            ) from error

    def restore(self, cmd: RecoveryCmd, path: Path) -> None:
        """Replace the complete live session from one recovery point.

        Args:
            cmd: Live PyMOL command module.
            path: Recovery point to load.

        Raises:
            RecoveryPointError: If loading the complete session fails.
        """
        try:
            cmd.load(str(path), partial=0)
        except Exception as error:
            raise RecoveryPointError(
                "could not restore recovery point"
            ) from error

    def discard(self) -> None:
        """Discard the active point, restoring the older handle if present."""
        path = self._retained
        if path is None:
            return
        previous = self._previous
        if previous is not None:
            # A failed second apply restored the post-first-apply session.
            # Keep the first plan's rollback point even if unlinking the
            # temporary second point fails.
            self._retained = previous
            self._previous = None
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            if previous is not None:
                self._obsolete.append(path)
            raise RecoveryPointError(
                "could not discard recovery point"
            ) from error
        if previous is None:
            self._retained = None

    def consume(self) -> None:
        """Consume the retained point after a successful rollback."""
        self.discard()

    def preserve(self) -> Path:
        """Forget the retained handle while deliberately leaving its file.

        Returns:
            The preserved path for a manual-recovery message.

        Raises:
            RecoveryPointError: If no recovery point is available to preserve.
        """
        path = self._retained
        if path is None:
            raise RecoveryPointError("no recovery point to preserve")
        # A failed restore requires the new point for manual recovery; the
        # previous point can still be cleaned up when this session closes.
        self._retained = self._previous
        self._previous = None
        return path

    def close(self) -> None:
        """Discard active points and retry cleanup of obsolete files."""
        try:
            self.discard()
            self.discard()
        finally:
            for path in tuple(self._obsolete):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    # The earlier failed commit/discard already raised a
                    # warning. Keep this path for a later close() attempt.
                    continue
                self._obsolete.remove(path)

    @staticmethod
    def _remove_unretained(path: Path | None) -> None:
        """Best-effort cleanup for a point that never became retained."""
        if path is None:
            return
        with suppress(OSError):
            path.unlink(missing_ok=True)
