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

"""Injectable PyMOL session providers for plan execution."""

from __future__ import annotations

import typing


class PyMOLSessionProvider(typing.Protocol):
    """Protocol for handing a PyMOL instance to the execution bridge."""

    def get_instance(self) -> typing.Any:
        """Return the underlying ``pymol2.PyMOL`` instance.

        Returns:
          Active PyMOL instance object.
        """
        ...

    def get_cmd(self) -> typing.Any:
        """Return the command API bound to the session.

        Returns:
          ``pymol.cmd`` module or ``pymol2.cmd2.Cmd`` instance.
        """
        ...

    def is_ready(self) -> bool:
        """Return whether the session is started and usable.

        Returns:
          True when commands may be dispatched safely.
        """
        ...

    def shutdown(self) -> None:
        """Release PyMOL session resources."""
        ...


class HeadlessPyMOLSession:
    """Default headless ``pymol2.PyMOL`` session for standalone execution."""

    def __init__(self) -> None:
        """Create an unstarted headless PyMOL instance."""
        import pymol2

        self._instance = pymol2.PyMOL()
        options = self._instance.invocation.options
        options.internal_gui = 0
        options.external_gui = 0
        options.show_splash = 0
        options.quiet = 1
        self._started = False

    def start(self) -> None:
        """Start the headless PyMOL instance once."""
        if not self._started:
            self._instance.start()
            self._started = True

    def get_instance(self) -> typing.Any:
        """Return the underlying PyMOL instance.

        Returns:
          ``pymol2.PyMOL`` instance created at construction time.
        """
        return self._instance

    def get_cmd(self) -> typing.Any:
        """Return the instance command API.

        Returns:
          ``Cmd`` object attached to the PyMOL instance.
        """
        return self._instance.cmd

    def is_ready(self) -> bool:
        """Return whether ``start`` has completed.

        Returns:
          True after ``start`` was called successfully.
        """
        return self._started

    def shutdown(self) -> None:
        """Stop the PyMOL instance if it was started."""
        if self._started:
            self._instance.stop()
            self._started = False


class InjectedPyMOLSession:
    """Wrap a caller-supplied ``pymol2.PyMOL`` (or compatible) instance."""

    def __init__(self, instance: typing.Any) -> None:
        """Store an externally owned PyMOL instance.

        Args:
          instance: Pre-constructed PyMOL object with a ``cmd`` attribute.
        """
        self._instance = instance
        self._owns_lifecycle = False

    def start(self) -> None:
        """Start the injected instance when it exposes ``start``."""
        start_fn = getattr(self._instance, "start", None)
        if callable(start_fn):
            start_fn()
            self._owns_lifecycle = True

    def get_instance(self) -> typing.Any:
        """Return the injected PyMOL instance.

        Returns:
          Caller-supplied PyMOL object.
        """
        return self._instance

    def get_cmd(self) -> typing.Any:
        """Return the command API from the injected instance.

        Returns:
          ``cmd`` attribute of the injected PyMOL object.
        """
        return self._instance.cmd

    def is_ready(self) -> bool:
        """Return whether the injected instance appears usable.

        Returns:
          True when a ``cmd`` handle is present.
        """
        return getattr(self._instance, "cmd", None) is not None

    def shutdown(self) -> None:
        """Stop the instance only when this provider started it."""
        if not self._owns_lifecycle:
            return
        stop_fn = getattr(self._instance, "stop", None)
        if callable(stop_fn):
            stop_fn()
        self._owns_lifecycle = False
