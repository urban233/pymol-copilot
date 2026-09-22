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
    """Own at most one private recovery point for one PyMOL session.

    Args:
        root: Home-directory root under which the private recovery directory
            is created. Defaults to the current user's resolved home path;
            injection keeps tests hermetic.
    """

    def __init__(self, root: Path | None = None) -> None:
        """Create a store rooted at the user's home directory or ``root``."""
        self._root = (Path.home() if root is None else root).resolve()
        self._retained: Path | None = None

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

        Any existing point owned by this store is discarded first. The saved
        file is not considered retained until it exists and its POSIX mode
        has been verified.

        Args:
            cmd: Live PyMOL command module.
            plan_id: Server-issued identifier naming this recovery point.

        Returns:
            The verified private ``.pse`` path.

        Raises:
            RecoveryPointError: If PyMOL cannot save the point or its file
                permissions cannot be established and verified.
        """
        self.discard()
        directory = self.directory
        path: Path | None = None
        try:
            directory.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
            os.chmod(directory, DIRECTORY_MODE)
            path = directory / f"plan-{plan_id}.pse"
            cmd.save(str(path))
            if not path.is_file():
                raise RecoveryPointError("PyMOL did not create recovery point")
            os.chmod(path, FILE_MODE)
            if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != FILE_MODE:
                raise RecoveryPointError("recovery point does not have mode 0600")
        except RecoveryPointError:
            self._remove_unretained(path)
            raise
        except (OSError, RuntimeError) as error:
            self._remove_unretained(path)
            raise RecoveryPointError("could not save recovery point") from error
        assert path is not None
        self._retained = path
        return path

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
        except (OSError, RuntimeError) as error:
            raise RecoveryPointError("could not restore recovery point") from error

    def discard(self) -> None:
        """Delete and forget this store's retained recovery point."""
        path = self._retained
        self._retained = None
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise RecoveryPointError("could not discard recovery point") from error

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
        self._retained = None
        return path

    def close(self) -> None:
        """Discard a retained point when its owning PyMOL session ends."""
        self.discard()

    @staticmethod
    def _remove_unretained(path: Path | None) -> None:
        """Best-effort cleanup for a point that never became retained."""
        if path is None:
            return
        with suppress(OSError):
            path.unlink(missing_ok=True)
