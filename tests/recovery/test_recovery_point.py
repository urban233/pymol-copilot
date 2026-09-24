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
        self,
        *,
        create_file: bool = True,
        fail_load: bool = False,
        save_error: Exception | None = None,
    ) -> None:
        self.create_file = create_file
        self.fail_load = fail_load
        self.save_error = save_error
        self.calls: list[tuple[str, str, int | None]] = []

    def save(self, filename: str) -> None:
        """Record and optionally materialize a synthetic session file."""
        self.calls.append(("save", filename, None))
        if self.save_error is not None:
            raise self.save_error
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
    assert len(cmd.calls) == 1
    assert cmd.calls[0][0] == "save"
    assert cmd.calls[0][1] != str(path)
    assert cmd.calls[0][1].endswith(".pse")
    if os.name != "nt":
        assert stat.S_IMODE(store.directory.stat().st_mode) == DIRECTORY_MODE
        assert stat.S_IMODE(path.stat().st_mode) == FILE_MODE


def test_second_save_keeps_the_previous_point_until_commit(
    tmp_path: Path,
) -> None:
    """A new save alone cannot remove a still-live plan's rollback point."""
    store = RecoveryStore(tmp_path)
    cmd = _FakeCmd()
    first = store.save(cmd, "first")
    second = store.save(cmd, "second")

    assert first.exists()
    assert second.exists()
    assert store.retained == second

    store.commit()

    assert not first.exists()
    assert second.exists()
    assert store.retained == second


@pytest.mark.parametrize("consume_before_close", [False, True])
def test_failed_commit_keeps_old_file_for_cleanup_without_redirecting_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    consume_before_close: bool,
) -> None:
    """A locked old point is retried on close, while B remains active."""
    store = RecoveryStore(tmp_path)
    first = store.save(_FakeCmd(), "first")
    second = store.save(_FakeCmd(), "second")
    real_unlink = Path.unlink
    locked = True

    def fail_first(self: Path, *, missing_ok: bool = False) -> None:
        if self == first and locked:
            raise OSError("locked")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_first)
    with pytest.raises(RecoveryPointError, match="previous recovery point"):
        store.commit()

    assert first.exists()
    assert second.exists()
    assert store.retained == second
    assert store._previous is None
    assert store._obsolete == [first]

    if consume_before_close:
        store.consume()
        assert not second.exists()
        assert store.retained is None
        assert first.exists()

    store.close()
    assert first.exists()
    assert store._obsolete == [first]
    assert not second.exists()

    locked = False
    store.close()
    assert not first.exists()
    assert store._obsolete == []


def test_failed_second_apply_restores_the_previous_point(
    tmp_path: Path,
) -> None:
    """A clean restore of B leaves A available for an explicit rollback."""
    store = RecoveryStore(tmp_path)
    first = store.save(_FakeCmd(), "first")
    second = store.save(_FakeCmd(), "second")

    store.discard()

    assert first.exists()
    assert not second.exists()
    assert store.retained == first


def test_failed_second_apply_keeps_previous_even_if_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A locked B file cannot redirect A's rollback to B's point."""
    store = RecoveryStore(tmp_path)
    first = store.save(_FakeCmd(), "first")
    second = store.save(_FakeCmd(), "second")
    real_unlink = Path.unlink

    def fail_second(self: Path, *, missing_ok: bool = False) -> None:
        if self == second:
            raise OSError("locked")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_second)
    with pytest.raises(RecoveryPointError, match="could not discard"):
        store.discard()

    assert store.retained == first
    assert first.exists()
    assert second.exists()

    monkeypatch.setattr(Path, "unlink", real_unlink)
    store.close()
    assert not first.exists()
    assert not second.exists()


def test_failed_replacement_preserves_the_previous_retained_point(
    tmp_path: Path,
) -> None:
    """A failed new save cannot erase the last known rollback point."""
    store = RecoveryStore(tmp_path)
    first = store.save(_FakeCmd(), "first")

    with pytest.raises(RecoveryPointError, match="could not save"):
        store.save(
            _FakeCmd(save_error=Exception("PyMOL save failed")), "second"
        )

    assert first.exists()
    assert store.retained == first
    assert not (store.directory / "plan-second.pse").exists()


def test_save_wraps_a_non_runtime_pymol_exception(tmp_path: Path) -> None:
    """PyMOL-specific save exceptions use the public recovery error type."""

    class _CmdException(Exception):
        pass

    store = RecoveryStore(tmp_path)
    with pytest.raises(RecoveryPointError, match="could not save"):
        store.save(_FakeCmd(save_error=_CmdException("save failed")), "one")

    assert store.retained is None
    assert not any(store.directory.glob("*.pse"))


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


def test_restore_wraps_a_non_runtime_pymol_exception(tmp_path: Path) -> None:
    """PyMOL-specific load exceptions use the public recovery error type."""

    class _CmdException(Exception):
        pass

    store = RecoveryStore(tmp_path)
    path = store.save(_FakeCmd(), "one")
    cmd = _FakeCmd()

    def fail_load(_filename: str, *, partial: int) -> None:
        assert partial == 0
        raise _CmdException("load failed")

    cmd.load = fail_load  # type: ignore[method-assign]
    with pytest.raises(RecoveryPointError, match="could not restore"):
        store.restore(cmd, path)


def test_discard_keeps_the_handle_when_file_removal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient removal failure remains retriable instead of being lost."""
    store = RecoveryStore(tmp_path)
    path = store.save(_FakeCmd(), "one")

    def fail_unlink(self: Path, *, missing_ok: bool = False) -> None:
        del self, missing_ok
        raise OSError("locked")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(RecoveryPointError, match="could not discard"):
        store.discard()

    assert store.retained == path


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
