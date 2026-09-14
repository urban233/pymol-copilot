# Copyright 2026 PyMOL Copilot contributors.
"""Windows-only staging shim so real PyMOL's extension can be imported.

`pymol-open-source-whl`'s Windows wheel bundles delvewheel-repaired DLLs
in a sibling `pymol_open_source_whl.libs` directory. Their absolute paths,
combined with Bazel's generated repository name and this repository's own
directory depth, routinely exceed Windows' 260-character `MAX_PATH`.
Windows' long-path policy already covers ordinary file APIs (confirmed on
a real `windows-2025` runner: a 317-character path was written and read
back successfully in the same process that then failed to import
`pymol`), but the Windows DLL loader does not honor it, so `import pymol`
still fails there with an opaque native error. Copying `pymol/` and its
sibling `.libs` directory to a short root, registering that root's
`.libs` directory with `os.add_dll_directory`, and inserting the root at
the front of `sys.path` avoids the DLL loader's own path limit entirely,
without any change to `pymol-open-source-whl` itself.

Every process that imports real PyMOL on Windows calls
`ensure_importable()` immediately before doing so. It is a no-op, by
construction, everywhere else: it returns `None` immediately whenever
`sys.platform` is not `"win32"`, so Linux and macOS behavior is
unchanged.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

#: Windows' own path-length ceiling that the DLL loader enforces, unlike
#: the file APIs the OS-level long-path policy already covers.
_MAX_PATH = 260

#: The delvewheel-repaired dependency directory `pymol-open-source-whl`
#: installs as a sibling of the `pymol` package itself, never inside it.
_LIBS_DIR_NAME = "pymol_open_source_whl.libs"

#: The short, fixed destination every staged copy is moved into, rooted
#: directly under the drive so a second target or process that also calls
#: `ensure_importable()` finds it already there instead of staging its
#: own redundant copy.
_STAGE_DIR_NAME = "pmcw-pymol-stage"


def _longest_path_length(directory: Path) -> int:
    """Find the longest absolute path length under a directory.

    Args:
        directory: The directory to scan, recursively.

    Returns:
        The longest absolute path length among `directory` itself and
        every file and directory under it.
    """
    longest = len(str(directory))
    for path in directory.rglob("*"):
        longest = max(longest, len(str(path)))
    return longest


def _drive_root() -> Path:
    """Return the short, writable drive root to stage a copy under.

    Returns:
        The system drive's root directory (for example, `C:\\`), so the
        staged copy and its process-private staging directory share one
        filesystem and can be moved into place with a single atomic
        rename.
    """
    return Path(f"{os.environ.get('SYSTEMDRIVE', 'C:')}\\")


def ensure_importable() -> str | None:
    """Stage `pymol` to a short path if Windows' DLL loader needs one.

    Locates the installed `pymol` package with `importlib.util.find_spec`
    rather than importing it -- executing its `__init__` is exactly what
    fails when the bundled DLLs' paths are too long. When the sibling
    `pymol_open_source_whl.libs` directory already fits within Windows'
    `MAX_PATH`, nothing is staged and this function is inert.

    Otherwise, `pymol/` and `pymol_open_source_whl.libs/` are copied into
    a process-private temporary directory, then moved into place at a
    short, fixed destination with a single atomic rename. A concurrent or
    prior caller that already completed that same move is treated as
    success, not an error; either way, the staged `.libs` directory is
    then registered with `os.add_dll_directory` and its root inserted at
    the front of `sys.path`.

    Returns:
        The short staged root now at the front of `sys.path`, or `None`
        when running on a non-Windows platform or when no staging was
        needed.

    Raises:
        ImportError: If `pymol` cannot be located at all, or if staging a
            copy of it fails, so a caller never falls through to the
            native DLL loader's own opaque failure.
    """
    if sys.platform != "win32":
        return None

    spec = importlib.util.find_spec("pymol")
    if spec is None:
        raise ImportError(
            "winstage: cannot locate an installed 'pymol' package to "
            "stage; check that @pypi//pymol_open_source_whl is a "
            "dependency of the running target."
        )
    # Pyrefly does not narrow `spec` past the raise above on its own; the
    # asserts below are redundant at runtime (the raise already guarantees
    # them) but resolve that, without weakening the ImportError's own more
    # readable, non-assert message above.
    assert spec is not None
    search_locations = spec.submodule_search_locations
    if not search_locations:
        raise ImportError(
            "winstage: 'pymol' was found but is not a regular package "
            "(no submodule_search_locations); cannot locate its "
            "directory to stage."
        )
    assert search_locations is not None
    pymol_dir = Path(next(iter(search_locations)))
    libs_dir = pymol_dir.parent / _LIBS_DIR_NAME

    if not libs_dir.is_dir() or _longest_path_length(libs_dir) <= _MAX_PATH:
        return None

    final_root = _drive_root() / _STAGE_DIR_NAME
    if not final_root.is_dir():
        staging_dir = Path(
            tempfile.mkdtemp(
                dir=str(_drive_root()), prefix=f"{_STAGE_DIR_NAME}-tmp-"
            )
        )
        try:
            shutil.copytree(pymol_dir, staging_dir / "pymol")
            shutil.copytree(libs_dir, staging_dir / _LIBS_DIR_NAME)
            os.rename(staging_dir, final_root)
        except FileExistsError:
            # A concurrent caller finished staging first; its destination
            # is what this call also needs, so this is success too.
            shutil.rmtree(staging_dir, ignore_errors=True)
        except OSError as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ImportError(
                f"winstage: failed to stage 'pymol' to {final_root}: {exc}"
            ) from exc

    os.add_dll_directory(str(final_root / _LIBS_DIR_NAME))  # pyrefly: ignore.
    sys.path.insert(0, str(final_root))
    return str(final_root)
