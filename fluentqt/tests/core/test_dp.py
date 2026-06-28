"""Tests for density-independent pixel scaling."""

from __future__ import annotations

import unittest.mock

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets
import pytest

import fluentqt.core.dp as dp_module


@pytest.mark.parametrize(
    "dpi,value,expected",
    [
        (96.0, 10, 10),
        (96.0, 10.5, 10),
        (120.0, 10, 12),
        (120.0, 10.5, 13),
        (144.0, 10, 15),
        (144.0, 10.5, 16),
        (192.0, 10, 20),
        (192.0, 10.5, 21),
    ],
)
def test_dp_with_screen_parameter(
    dpi: float, value: float | int, expected: int
) -> None:
    """Test the dp() function when a screen is passed explicitly.

    Args:
        dpi: The logical DPI of the screen.
        value: The density-independent pixel value.
        expected: The expected physical pixel output.
    """
    tmp_mock_screen = unittest.mock.create_autospec(QtGui.QScreen)
    tmp_mock_screen.logicalDotsPerInch.return_value = dpi

    tmp_result = dp_module.dp(value, screen=tmp_mock_screen)
    assert tmp_result == expected


@pytest.mark.parametrize(
    "dpi,value,expected",
    [
        (96.0, 10, 10),
        (120.0, 10, 12),
        (144.0, 10, 15),
        (192.0, 10, 20),
    ],
)
def test_dp_with_primary_screen(
    dpi: float,
    value: float | int,
    expected: int,
    q_app: QtWidgets.QApplication,  # noqa: ARG001
) -> None:
    """Test the dp() function when defaulting to the primary screen.

    Args:
        dpi: The logical DPI of the screen.
        value: The density-independent pixel value.
        expected: The expected physical pixel output.
        q_app: The QApplication fixture.
    """
    tmp_mock_screen = unittest.mock.create_autospec(QtGui.QScreen)
    tmp_mock_screen.logicalDotsPerInch.return_value = dpi

    # We patch QApplication.primaryScreen to return our mock screen.
    with unittest.mock.patch.object(
        QtWidgets.QApplication, "primaryScreen", return_value=tmp_mock_screen
    ):
        tmp_result = dp_module.dp(value)
        assert tmp_result == expected


def test_dp_no_screen_or_app() -> None:
    """Test the dp() function when no screen or QApplication is available."""
    # We patch QApplication.instance to return None.
    with unittest.mock.patch.object(
        QtWidgets.QApplication, "instance", return_value=None
    ):
        # Without any screen, it should just round the value.
        assert dp_module.dp(10.4) == 10
        assert dp_module.dp(10.6) == 11


def test_screen_change_notifier_emits_on_dpi_change(
    q_app: QtWidgets.QApplication,  # noqa: ARG001
) -> None:
    """Test that ScreenChangeNotifier emits scale_changed on DPI changes.

    Args:
        q_app: The QApplication fixture.
    """
    tmp_notifier = dp_module.ScreenChangeNotifier()
    tmp_mock_screen = unittest.mock.MagicMock(spec=QtGui.QScreen)
    tmp_mock_screen.logicalDotsPerInch.return_value = 96.0
    tmp_mock_screen.logicalDotsPerInchChanged = unittest.mock.MagicMock()

    # Patch the primary screen to return our mock
    with unittest.mock.patch.object(
        QtWidgets.QApplication, "primaryScreen", return_value=tmp_mock_screen
    ):
        # Connect primary screen signals by calling the internal helper
        tmp_notifier._connect_primary_screen_signals()

        # Connect a spy to the scale_changed signal
        tmp_signals_received: list[float] = []

        def tmp_slot(scale: float) -> None:
            """Track scale change signal emission.

            Args:
                scale: The scaling factor emitted.
            """
            tmp_signals_received.append(scale)

        tmp_notifier.scale_changed.connect(tmp_slot)

        # Trigger DPI change on the mock screen
        tmp_notifier._handle_dpi_change(120.0)

        # Assert scale_changed emitted with 1.25 (120 / 96)
        assert len(tmp_signals_received) == 1
        assert tmp_signals_received[0] == 1.25


def test_screen_change_notifier_event_filter(
    q_app: QtWidgets.QApplication,  # noqa: ARG001
) -> None:
    """Test that the eventFilter intercepts DevicePixelRatioChange events.

    Args:
        q_app: The QApplication fixture.
    """
    tmp_notifier = dp_module.ScreenChangeNotifier()
    tmp_mock_screen = unittest.mock.MagicMock(spec=QtGui.QScreen)
    tmp_mock_screen.logicalDotsPerInch.return_value = 144.0
    tmp_mock_screen.logicalDotsPerInchChanged = unittest.mock.MagicMock()

    # Spy on scale_changed signal
    tmp_signals_received: list[float] = []

    def tmp_slot(scale: float) -> None:
        """Track scale change signal emission.

        Args:
            scale: The scaling factor emitted.
        """
        tmp_signals_received.append(scale)

    tmp_notifier.scale_changed.connect(tmp_slot)

    # Mock the screen of the watched widget
    tmp_mock_widget = unittest.mock.create_autospec(QtWidgets.QWidget)
    tmp_mock_window = unittest.mock.create_autospec(QtWidgets.QWidget)
    tmp_mock_window_handle = unittest.mock.create_autospec(QtGui.QWindow)

    tmp_mock_widget.window.return_value = tmp_mock_window
    tmp_mock_window.windowHandle.return_value = tmp_mock_window_handle
    tmp_mock_window_handle.screen.return_value = tmp_mock_screen

    tmp_event = QtCore.QEvent(QtCore.QEvent.Type.DevicePixelRatioChange)

    # Let eventFilter process it
    with unittest.mock.patch.object(
        QtWidgets.QApplication, "primaryScreen", return_value=tmp_mock_screen
    ):
        tmp_notifier._handle_event(tmp_mock_widget, tmp_event)

    # Assert scale_changed was emitted with 1.5 (144 / 96)
    assert len(tmp_signals_received) == 1
    assert tmp_signals_received[0] == 1.5
