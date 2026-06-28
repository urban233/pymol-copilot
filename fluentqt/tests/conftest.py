"""Pytest configuration and shared fixtures for fluentqt tests."""

from __future__ import annotations

import os
import typing

from PyQt6 import QtCore
from PyQt6 import QtWidgets
import pytest


@pytest.fixture(scope="session", autouse=True)
def q_app() -> typing.Generator[QtWidgets.QApplication, None, None]:
    """Provide a session-scoped QApplication with offscreen rendering.

    This fixture configures the environment to run Qt tests in
    headless mode, sets the DPI rounding policy to PassThrough,
    and yields the QApplication singleton.

    Yields:
        The session-scoped QApplication instance.
    """
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    tmp_app = QtWidgets.QApplication.instance()
    if tmp_app is None:
        tmp_app = QtWidgets.QApplication([])

    yield tmp_app
