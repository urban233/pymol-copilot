# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic lifecycle and permissions tests for private recovery points."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pmc_client.recovery import DIRECTORY_MODE
from pmc_client.recovery import FILE_MODE
from pmc_client.recovery import RecoveryPointError
from pmc_client.recovery import RecoveryStore


class _FakeCmd:
    """Record session save/load calls and optionally fail either operation."""

    def __init__(
        self, *, create_file: bool = True, fail_load: bool = False
    ) -> None:
        self.create_file = create_file
        self.fail_load = fail_load
        self.calls: list[tuple[str, str, int | None]] = []

    def save(self, filename: str) -> None:
        """Record and optionally materialize a synthetic session file."""
        self.calls.append(("save", filename, None))
        if self.create_file:
            Path(filename).write_bytes(b"recovery")

    def load(self, filename: str, *, partial: int) -> None:
        """Record a replacement load or raise the scripted failure."""
        self.calls.append(("load", filename, partial))
        if self.fail_load:
            raise RuntimeError("load failed")


def test_save_enforces_private_directory_and_file_modes(
    tmp_path: Path,
) -> None:
    """Umask cannot weaken POSIX recovery-point privacy."""
    store = RecoveryStore(tmp_path)
    cmd = _FakeCmd()
    original_umask = os.umask(0)
    try:
        path = store.save(cmd, "plan-one")
    finally:
        os.umask(original_umask)

    assert (
        path == tmp_path / ".pymol-copilot" / "recovery" / "plan-plan-one.pse"
    )
    assert cmd.calls == [("save", str(path), None)]
    if os.name != "nt":
        assert stat.S_IMODE(store.directory.stat().st_mode) == DIRECTORY_MODE
        assert stat.S_IMODE(path.stat().st_mode) == FILE_MODE


def test_second_save_replaces_the_previous_retained_point(
    tmp_path: Path,
) -> None:
    """A session retains only the most recent successful apply point."""
    store = RecoveryStore(tmp_path)
    cmd = _FakeCmd()
    first = store.save(cmd, "first")
    second = store.save(cmd, "second")

    assert not first.exists()
    assert second.exists()
    assert store.retained == second


@pytest.mark.parametrize("method", ["consume", "close"])
def test_consume_and_close_remove_the_retained_file(
    tmp_path: Path, method: str
) -> None:
    """Both terminal lifecycle paths delete a retained point."""
    store = RecoveryStore(tmp_path)
    path = store.save(_FakeCmd(), "one")

    getattr(store, method)()

    assert not path.exists()
    assert store.retained is None


def test_preserve_forgets_the_handle_but_keeps_the_file(tmp_path: Path) -> None:
    """A failed restore leaves a manual-recovery artifact in place."""
    store = RecoveryStore(tmp_path)
    path = store.save(_FakeCmd(), "one")

    assert store.preserve() == path
    assert path.exists()
    assert store.retained is None


def test_save_rejects_a_cmd_that_did_not_create_a_file(tmp_path: Path) -> None:
    """A successful return from PyMOL alone is not a trusted save."""
    store = RecoveryStore(tmp_path)

    with pytest.raises(RecoveryPointError, match="did not create"):
        store.save(_FakeCmd(create_file=False), "missing")

    assert store.retained is None
    assert not any(store.directory.glob("*.pse"))


def test_save_rejects_a_file_whose_private_mode_cannot_be_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A point with an unverifiable POSIX mode never becomes retained."""
    if os.name == "nt":
        pytest.skip("Windows uses profile ACLs rather than POSIX modes")
    store = RecoveryStore(tmp_path)
    real_chmod = os.chmod

    def directory_only_chmod(path: str | Path, mode: int) -> None:
        """Leave files permissive while still allowing directory setup."""
        if Path(path) == store.directory:
            real_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", directory_only_chmod)
    with pytest.raises(RecoveryPointError, match="mode 0600"):
        store.save(_FakeCmd(), "wrong-mode")

    assert store.retained is None
    assert not any(store.directory.glob("*.pse"))


def test_restore_wraps_a_pymol_load_failure(tmp_path: Path) -> None:
    """An unsuccessful replacement session has one typed recovery error."""
    store = RecoveryStore(tmp_path)
    path = store.save(_FakeCmd(), "one")
    cmd = _FakeCmd(fail_load=True)

    with pytest.raises(RecoveryPointError, match="could not restore"):
        store.restore(cmd, path)

    assert cmd.calls == [("load", str(path), 0)]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
