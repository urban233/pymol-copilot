"""Widget construction factory functions."""

from __future__ import annotations

from typing import Callable

from PyQt6 import QtGui
from PyQt6 import QtWidgets

from fluentqt.enums import roles


class _IconState:
    """Internal state storage for the global icon provider."""

    provider: Callable[[str], QtGui.QIcon] | None = None


_state = _IconState()


def register_icon_provider(
    provider: Callable[[str], QtGui.QIcon],
) -> None:
    """Register a global provider for loading icons.

    Args:
        provider: A callable that takes an icon name string and returns
            a QIcon instance.
    """
    _state.provider = provider


def make_frame(
    elevation: roles.ElevationPreset = roles.ElevationPreset.Flat,
    fill_role: roles.FillRole = roles.FillRole.Transparent,
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QWidget | None:
    """Create a TokenFrame widget with the specified style.

    Args:
        elevation: The semantic elevation preset determining shadow and
            border radius.
        fill_role: The semantic fill role for the background color.
        parent: The optional parent widget.

    Returns:
        The constructed TokenFrame widget, or None as a placeholder.
    """
    _ = (elevation, fill_role, parent)
    return None


def make_label(
    text: str = "",
    role: roles.TextRole = roles.TextRole.Primary,
    style: roles.TypeStyle = roles.TypeStyle.Body,
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QWidget | None:
    """Create a TokenLabel widget with the specified text and style.

    Args:
        text: The text to display on the label.
        role: The semantic text role determining the color.
        style: The typography style determining font configuration.
        parent: The optional parent widget.

    Returns:
        The constructed TokenLabel widget, or None as a placeholder.
    """
    _ = (text, role, style, parent)
    return None


def make_button(
    text: str,
    role: roles.ButtonRole = roles.ButtonRole.Standard,
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QWidget | None:
    """Create a TokenButton widget with the specified text and style.

    Args:
        text: The text of the button.
        role: The semantic button role determining the styling family.
        parent: The optional parent widget.

    Returns:
        The constructed TokenButton widget, or None as a placeholder.
    """
    _ = (text, role, parent)
    return None


def make_input(
    placeholder: str = "",
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QWidget | None:
    """Create a TokenInput widget with the specified placeholder.

    Args:
        placeholder: The placeholder text.
        parent: The optional parent widget.

    Returns:
        The constructed TokenInput widget, or None as a placeholder.
    """
    _ = (placeholder, parent)
    return None


def make_icon(
    icon_name: str,
    size: roles.IconSize = roles.IconSize.Medium,
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QWidget | None:
    """Create a TokenIcon widget with the specified name and size.

    Args:
        icon_name: The name or identifier of the icon to load.
        size: The semantic size of the icon.
        parent: The optional parent widget.

    Returns:
        The constructed TokenIcon widget, or None as a placeholder.
    """
    _ = (icon_name, size, parent)
    return None


def make_divider(
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QWidget | None:
    """Create a TokenDivider widget.

    Args:
        parent: The optional parent widget.

    Returns:
        The constructed TokenDivider widget, or None as a placeholder.
    """
    _ = parent
    return None


def make_dropdown(
    items: list[str],
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QComboBox | None:
    """Create a QComboBox dropdown widget populated with items.

    Args:
        items: The list of string choices.
        parent: The optional parent widget.

    Returns:
        The constructed QComboBox widget, or None as a placeholder.
    """
    _ = (items, parent)
    return None
