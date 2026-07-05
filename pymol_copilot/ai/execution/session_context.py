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
#
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================

"""Context-local PyMOL cmd handle for injectable sessions."""

from __future__ import annotations

import contextlib
import contextvars
import typing

_ACTIVE_CMD: contextvars.ContextVar[typing.Any | None] = contextvars.ContextVar(
    "active_pymol_cmd",
    default=None,
)


def get_active_cmd() -> typing.Any | None:
    """Return the cmd API object for the current execution context.

    Returns:
      Active cmd module or ``pymol2.cmd2.Cmd`` instance, or None.
    """
    return _ACTIVE_CMD.get()


@contextlib.contextmanager
def use_cmd(cmd: typing.Any) -> typing.Iterator[None]:
    """Temporarily bind the active cmd handle for wrapper dispatch.

    Args:
      cmd: PyMOL command API object to use for wrapper calls.

    Yields:
      None.
    """
    token = _ACTIVE_CMD.set(cmd)
    try:
        yield
    finally:
        _ACTIVE_CMD.reset(token)
