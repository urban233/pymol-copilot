"""Widget construction factory functions."""

from __future__ import annotations

from typing import Callable

from PyQt6 import QtGui
from PyQt6 import QtWidgets

from fluentqt.enums import roles
import fluentqt.primitives.button as button_module
import fluentqt.primitives.divider as divider_module
import fluentqt.primitives.frame as frame_module
import fluentqt.primitives.icon as icon_module
import fluentqt.primitives.input as input_module
import fluentqt.primitives.label as label_module


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


def get_icon_provider() -> Callable[[str], QtGui.QIcon] | None:
    """Get the currently registered global icon provider.

    Returns:
        The registered icon provider callable, or None if not set.
    """
    return _state.provider


def make_frame(
    elevation: roles.ElevationPreset = roles.ElevationPreset.Flat,
    fill_role: roles.FillRole = roles.FillRole.Transparent,
    parent: QtWidgets.QWidget | None = None,
) -> frame_module.TokenFrame:
    """Create a TokenFrame widget with the specified style.

    Args:
        elevation: The semantic elevation preset determining shadow and
            border radius.
        fill_role: The semantic fill role for the background color.
        parent: The optional parent widget.

    Returns:
        The constructed TokenFrame widget.
    """
    return frame_module.TokenFrame(
        elevation=elevation, fill_role=fill_role, parent=parent
    )


def make_label(
    text: str = "",
    role: roles.TextRole = roles.TextRole.Primary,
    style: roles.TypeStyle = roles.TypeStyle.Body,
    parent: QtWidgets.QWidget | None = None,
) -> label_module.TokenLabel:
    """Create a TokenLabel widget with the specified text and style.

    Args:
        text: The text to display on the label.
        role: The semantic text role determining the color.
        style: The typography style determining font configuration.
        parent: The optional parent widget.

    Returns:
        The constructed TokenLabel widget.
    """
    return label_module.TokenLabel(
        text=text, role=role, style=style, parent=parent
    )


def make_button(
    text: str,
    role: roles.ButtonRole = roles.ButtonRole.Standard,
    parent: QtWidgets.QWidget | None = None,
) -> button_module.TokenButton:
    """Create a TokenButton widget with the specified text and style.

    Args:
        text: The text of the button.
        role: The semantic button role determining the styling family.
        parent: The optional parent widget.

    Returns:
        The constructed TokenButton widget.
    """
    return button_module.TokenButton(text=text, role=role, parent=parent)


def make_input(
    placeholder: str = "",
    parent: QtWidgets.QWidget | None = None,
) -> input_module.TokenInput:
    """Create a TokenInput widget with the specified placeholder.

    Args:
        placeholder: The placeholder text.
        parent: The optional parent widget.

    Returns:
        The constructed TokenInput widget.
    """
    return input_module.TokenInput(placeholder=placeholder, parent=parent)


def make_icon(
    icon_name: str,
    size: roles.IconSize = roles.IconSize.Medium,
    parent: QtWidgets.QWidget | None = None,
) -> icon_module.TokenIcon:
    """Create a TokenIcon widget with the specified name and size.

    Args:
        icon_name: The name or identifier of the icon to load.
        size: The semantic size of the icon.
        parent: The optional parent widget.

    Returns:
        The constructed TokenIcon widget.
    """
    return icon_module.TokenIcon(icon=icon_name, size=size, parent=parent)


def make_divider(
    parent: QtWidgets.QWidget | None = None,
) -> divider_module.TokenDivider:
    """Create a TokenDivider widget.

    Args:
        parent: The optional parent widget.

    Returns:
        The constructed TokenDivider widget.
    """
    return divider_module.TokenDivider(parent=parent)


def make_dropdown(
    items: list[str],
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QComboBox:
    """Create a QComboBox dropdown widget populated with items.

    Args:
        items: The list of string choices.
        parent: The optional parent widget.

    Returns:
        The constructed QComboBox widget.
    """
    tmp_combo = QtWidgets.QComboBox(parent=parent)
    tmp_combo.addItems(items)
    return tmp_combo
