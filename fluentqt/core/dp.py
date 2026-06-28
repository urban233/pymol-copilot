"""Density-independent pixel scaling utilities."""

from __future__ import annotations

import contextlib
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets


def dp(value: int | float, screen: QtGui.QScreen | None = None) -> int:
    """Convert a density-independent pixel value to physical pixels.

    All dimension tokens in Win11Tokens and ElevationLevel are expressed in
    dp at a 96 DPI baseline. Widgets call this function whenever they pass a
    token value to a Qt API that expects physical pixels.

    Always call after QApplication has been created.

    Args:
        value: Size in density-independent pixels (96 DPI = 1x baseline).
        screen: Optional QScreen to use for calculating DPI scaling. If
            None, the primary screen is used.

    Returns:
        The equivalent size in physical pixels for the chosen screen,
        rounded to the nearest integer.
    """
    tmp_app = QtWidgets.QApplication.instance()
    if isinstance(tmp_app, QtWidgets.QApplication):
        notifier._install(tmp_app)

    if screen is None and isinstance(tmp_app, QtWidgets.QApplication):
        screen = tmp_app.primaryScreen()

    if screen is None:
        return round(value)

    tmp_scale = screen.logicalDotsPerInch() / 96.0
    return round(value * tmp_scale)


class _NotifierQObject(QtCore.QObject):
    """Internal QObject subclass for emitting Qt signals."""

    scale_changed = QtCore.pyqtSignal(float)

    def __init__(self, outer: ScreenChangeNotifier) -> None:
        """Initialize the _NotifierQObject.

        Args:
            outer: The ScreenChangeNotifier instance.
        """
        super().__init__()
        self._outer = outer

    @override
    def eventFilter(
        self, a0: QtCore.QObject | None, a1: QtCore.QEvent | None
    ) -> bool:
        """Filter events on QApplication.

        Args:
            a0: The QObject receiving the event.
            a1: The QEvent being sent.

        Returns:
            Always False to allow the event to propagate.
        """
        return self._outer._handle_event(a0, a1)

    @override
    def connectNotify(self, signal: QtCore.QMetaMethod) -> None:
        """Ensure the event filter is installed when a connection is made.

        Args:
            signal: The signal being connected.
        """
        super().connectNotify(signal)
        tmp_app = QtWidgets.QApplication.instance()
        if isinstance(tmp_app, QtWidgets.QApplication):
            self._outer._install(tmp_app)


class ScreenChangeNotifier:
    """Notifier for screen scale factor changes.

    This class monitors for device pixel ratio changes and emits the
    scale_changed signal when a change is detected, allowing widgets
    to dynamically adapt their scaling.
    """

    def __init__(self) -> None:
        """Initialize the ScreenChangeNotifier wrapper."""
        self._qobject: _NotifierQObject | None = None
        self._last_scale: float = 1.0
        self._current_screen: QtGui.QScreen | None = None
        self._installed: bool = False

        tmp_app = QtWidgets.QApplication.instance()
        if isinstance(tmp_app, QtWidgets.QApplication):
            self._install(tmp_app)

    def _get_qobject(self) -> _NotifierQObject:
        """Get the active QObject instance, recreating it if deleted.

        Returns:
            The active _NotifierQObject instance.
        """
        from PyQt6 import sip

        if self._qobject is None or sip.isdeleted(self._qobject):
            self._qobject = _NotifierQObject(self)
            self._installed = False
            tmp_app = QtWidgets.QApplication.instance()
            if isinstance(tmp_app, QtWidgets.QApplication):
                self._install(tmp_app)
        return self._qobject

    @property
    def scale_changed(self) -> QtCore.pyqtBoundSignal:
        """The scale_changed signal bound to the internal QObject.

        Returns:
            The scale_changed signal.
        """
        return self._get_qobject().scale_changed

    def _install(self, app: QtWidgets.QApplication) -> None:
        """Install the event filter and connect signals.

        Args:
            app: The QApplication instance.
        """
        if self._installed:
            return

        tmp_qobj = self._get_qobject()
        app.installEventFilter(tmp_qobj)
        app.primaryScreenChanged.connect(self._handle_primary_screen_change)
        self._connect_primary_screen_signals()

        tmp_screen = app.primaryScreen()
        if tmp_screen is not None:
            self._last_scale = tmp_screen.logicalDotsPerInch() / 96.0

        self._installed = True

    def _connect_primary_screen_signals(self) -> None:
        """Connect to the primary screen's logical DPI change signal."""
        tmp_screen = QtWidgets.QApplication.primaryScreen()
        if tmp_screen == self._current_screen:
            return

        if self._current_screen is not None:
            with contextlib.suppress(TypeError):
                self._current_screen.logicalDotsPerInchChanged.disconnect(
                    self._handle_dpi_change
                )

        self._current_screen = tmp_screen
        if tmp_screen is not None:
            tmp_screen.logicalDotsPerInchChanged.connect(
                self._handle_dpi_change
            )

    def _handle_primary_screen_change(self, screen: QtGui.QScreen) -> None:
        """Handle change of primary screen.

        Args:
            screen: The new primary QScreen.
        """
        self._connect_primary_screen_signals()
        self._handle_dpi_change(screen.logicalDotsPerInch())

    def _handle_dpi_change(self, dpi: float) -> None:
        """Handle logical DPI change and emit signal if scale changed.

        Args:
            dpi: The new logical DPI.
        """
        tmp_scale = dpi / 96.0
        if tmp_scale != self._last_scale:
            self._last_scale = tmp_scale
            self.scale_changed.emit(tmp_scale)

    def _handle_event(
        self, a0: QtCore.QObject | None, a1: QtCore.QEvent | None
    ) -> bool:
        """Process event filter event.

        Args:
            a0: The watched QObject.
            a1: The QEvent to filter.

        Returns:
            Always False to allow the event to propagate.
        """
        if (
            a1 is not None
            and a1.type() == QtCore.QEvent.Type.DevicePixelRatioChange
        ):
            tmp_screen = None
            if isinstance(a0, QtWidgets.QWidget):
                tmp_window = a0.window()
                if tmp_window is not None:
                    tmp_handle = tmp_window.windowHandle()
                    if tmp_handle is not None:
                        tmp_screen = tmp_handle.screen()

            if tmp_screen is None:
                tmp_screen = QtWidgets.QApplication.primaryScreen()

            if tmp_screen is not None:
                self._handle_dpi_change(tmp_screen.logicalDotsPerInch())

        return False


# Module-level singleton, lazily initialized on first import.
notifier: ScreenChangeNotifier = ScreenChangeNotifier()
