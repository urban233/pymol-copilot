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
# Martin Urban
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================
#
"""Resolve icons for the cBioMOL SDK and third-party plugins.

Provides a centralized, zip-safe mechanism for loading file-based icons that
ship as package data inside each Python distribution. The public surface is
intentionally minimal:

- register_package - declare that an import package supplies icons.
- icon - resolve and return a cached QIcon by (package, name).
- is_registered - introspection used by tests.
- _clear_cache - test helper; clears the in-process icon cache.

Usage (plugin startup):

    from pymol_copilot.gui.qt import icons
    icons.register_package("my_plugin")

Usage (building a toolbar action):

    from pymol_copilot.gui.qt import icons
    action = QtGui.QAction(icons.icon("my_plugin", "open"), "Open")

Asset layout convention
-----------------------
Icons are resolved in this order for icon(pkg, name, theme=T):

1. <pkg>/assets/icons/<T>/<name>.svg
2. <pkg>/assets/icons/<T>/<name>.png
3. <pkg>/assets/icons/<name>.svg (flat v1 fallback)
4. <pkg>/assets/icons/<name>.png

When theme is None the string "default" is used for step 1-2,
enabling a future themed layout without changing call sites.

The name argument must match ^[a-z][a-z0-9_]*$. This prevents
path-traversal attempts from reaching read_bytes() and catches
programmer typos early.
"""

from __future__ import annotations

import importlib.resources
import re
from typing import Final
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymol_copilot.gui.qt import QtGui

__docformat__ = "google"

_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
"""Compiled pattern used to validate icon name arguments."""

_registered: set[str] = set()
"""Set of import-package names that have been registered as icon sources."""

_cache: dict[tuple[str, str, str], QtGui.QIcon] = {}
"""In-process icon cache keyed by (import_name, name, theme)."""

_DEFAULT_THEME: Final[str] = "default"
"""Internal theme string substituted when the caller passes theme=None."""


def register_package(import_name: str) -> None:
    """Register an import package as a source of icon assets.

    Idempotent: calling this more than once for the same package is a no-op.
    The function only records the package name; no filesystem I/O is performed
    here, so it is safe to call before QApplication is created.

    Args:
        import_name: The importable Python package name whose assets/icons/
            directory contains SVG or PNG files. Must not contain .. or
            path separators.

    Raises:
        ValueError: If import_name contains .. or a forward/backward
            slash, indicating an unsafe or malformed package name.
    """
    if ".." in import_name or "/" in import_name or "\\" in import_name:
        raise ValueError(
            f"Invalid package name for icon registration: {import_name!r}"
        )
    _registered.add(import_name)


def icon(
    import_name: str,
    name: str,
    *,
    theme: str | None = None,
) -> QtGui.QIcon:
    """Return a cached QIcon for the given package and icon name.

    On the first call for a given (import_name, name, theme) combination
    the icon is loaded from the package's assets/icons/ tree and stored
    in the module-level cache. Subsequent calls return the cached object
    directly without any I/O.

    Args:
        import_name: The importable package name that owns the icon asset.
        name: Logical icon identifier - the filename stem without extension.
            Must match ^[a-z][a-z0-9_]*$.
        theme: Optional theme subdirectory name. When None the internal
            default "default" is used for the themed lookup, falling back
            to the flat assets/icons/<name>.<ext> layout if the themed path
            does not exist.

    Returns:
        A QIcon loaded from the resolved asset file.

    Raises:
        ValueError: If name does not match the allowed character set.
        FileNotFoundError: If no matching asset file can be found under the
            package's assets/icons/ tree.
    """
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Invalid icon name {name!r}. "
            "Must match ^[a-z][a-z0-9_]*$ "
            "(lowercase letters, digits, underscores)."
        )
    tmp_resolved_theme = theme if theme is not None else _DEFAULT_THEME
    tmp_cache_key = (import_name, name, tmp_resolved_theme)
    if tmp_cache_key in _cache:
        return _cache[tmp_cache_key]
    tmp_loaded = _load_icon(import_name, name, tmp_resolved_theme)
    _cache[tmp_cache_key] = tmp_loaded
    return tmp_loaded


def is_registered(import_name: str) -> bool:
    """Return whether a package has been registered as an icon source.

    Args:
        import_name: The importable package name to check.

    Returns:
        True if register_package has been called for this name.
    """
    return import_name in _registered


def _clear_cache() -> None:
    """Clear the in-process icon cache.

    Intended for use in tests only. Production code must never call this
    because it causes all subsequent icon() calls to re-read from disk.
    """
    _cache.clear()


def _load_icon(import_name: str, name: str, theme: str) -> QtGui.QIcon:
    """Load a QIcon from package data without caching.

    Tries the themed subdirectory first, then falls back to the flat layout.
    Uses read_bytes() throughout to remain zip-safe: no temporary files
    are created and no as_file() context manager is involved. Qt loads
    the pixel data eagerly from the byte buffer, so the buffer can be
    discarded immediately after loadFromData returns.

    Args:
        import_name: The importable package name that owns the asset.
        name: Validated icon name (filename stem).
        theme: Theme subdirectory name (never None at this point).

    Returns:
        A QIcon whose internal pixmap is populated from the asset bytes.

    Raises:
        FileNotFoundError: If no candidate path yields a readable file.
    """
    from pymol_copilot.gui.qt import QtGui

    tmp_candidates = (
        f"assets/icons/{theme}/{name}.svg",
        f"assets/icons/{theme}/{name}.png",
        f"assets/icons/{name}.svg",
        f"assets/icons/{name}.png",
    )
    for tmp_candidate in tmp_candidates:
        tmp_data = _try_read_bytes(import_name, tmp_candidate)
        if tmp_data is not None:
            tmp_pixmap = QtGui.QPixmap()
            tmp_pixmap.loadFromData(tmp_data)
            return QtGui.QIcon(tmp_pixmap)
    raise FileNotFoundError(
        f"Icon not found: package={import_name!r}, "
        f"name={name!r}, theme={theme!r}. "
        f"Searched candidates: {tmp_candidates}"
    )


def _try_read_bytes(import_name: str, rel_path: str) -> bytes | None:
    """Attempt to read bytes from a package-data path.

    Splits rel_path on / and calls joinpath iteratively so the
    function works with both filesystem-backed and zip-backed package roots.

    Args:
        import_name: The importable package name.
        rel_path: Forward-slash-separated relative path inside the package root.

    Returns:
        The raw bytes of the resource, or None if the path does not exist.
    """
    try:
        tmp_traversable = importlib.resources.files(import_name)
        for tmp_part in rel_path.split("/"):
            tmp_traversable = tmp_traversable.joinpath(tmp_part)
        return tmp_traversable.read_bytes()
    except FileNotFoundError:
        return None


# Auto-register the core SDK package so callers never need to do it manually.
register_package("pymol_copilot.gui.qt")
