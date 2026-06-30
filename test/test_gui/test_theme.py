"""Tests for design system themes."""

from __future__ import annotations

from PyQt6 import QtGui
from PyQt6 import QtWidgets
import pytest

from pymol_copilot.gui.qt import theme


@pytest.fixture
def q_app() -> QtWidgets.QApplication:
    """Fixture for providing a QApplication instance.

    Returns:
        The QApplication instance.
    """
    tmp_app = QtWidgets.QApplication.instance()
    if isinstance(tmp_app, QtWidgets.QApplication):
        return tmp_app
    return QtWidgets.QApplication([])


def test_color_token_to_hex(q_app: QtWidgets.QApplication) -> None:
    """Test ColorToken hex generation.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_color = theme.ColorToken("#aabbcc")

    # Act
    tmp_hex = tmp_color.to_hex()

    # Assert
    assert tmp_hex == "#aabbcc"


def test_color_token_to_qcolor(q_app: QtWidgets.QApplication) -> None:
    """Test ColorToken to QColor conversion.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_color = theme.ColorToken("#aabbcc")

    # Act
    tmp_qcolor = tmp_color.to_qcolor()

    # Assert
    assert isinstance(tmp_qcolor, QtGui.QColor)
    assert tmp_qcolor.name() == "#aabbcc"


def test_size_token_resolves_px(q_app: QtWidgets.QApplication) -> None:
    """Test SizeToken scales to physical pixels.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_size = theme.SizeToken(10)

    # Act
    tmp_px = tmp_size.px

    # Assert
    assert isinstance(tmp_px, int)


def test_compile_stylesheet_substitutes_placeholders(
    q_app: QtWidgets.QApplication,
) -> None:
    """Test compile_stylesheet successfully formats QSS.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_template = "QPushButton { background-color: ${surface}; border-radius: ${corner_radius}; }"

    # Act
    tmp_qss = theme.compile_stylesheet(tmp_template)

    # Assert
    assert "#ffffff" in tmp_qss
    assert "px" in tmp_qss


def test_compile_stylesheet_raises_error_for_invalid_placeholder(
    q_app: QtWidgets.QApplication,
) -> None:
    """Test compile_stylesheet raises KeyError for invalid tokens.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange
    tmp_template = "QPushButton { background-color: ${invalid_token}; }"

    # Act & Assert
    with pytest.raises(KeyError):
        theme.compile_stylesheet(tmp_template)


def test_apply_global_theme_with_scale(
    q_app: QtWidgets.QApplication,
) -> None:
    """Test apply_global_theme accepts scale parameter.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    # Arrange & Act & Assert (Should not raise any exception)
    theme.apply_global_theme(1.5)
