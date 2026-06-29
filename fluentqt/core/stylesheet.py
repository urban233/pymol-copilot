"""QSS stylesheet generators and styling logic."""

from __future__ import annotations

from PyQt6 import QtGui

from fluentqt.enums import roles


def _color_to_qss(color: QtGui.QColor) -> str:
    """Convert a QColor to a QSS color string.

    Args:
        color: The QColor to convert.

    Returns:
        A QSS-compatible color representation.
    """
    tmp_alpha = color.alpha()
    if tmp_alpha == 255:
        return color.name(QtGui.QColor.NameFormat.HexRgb)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {tmp_alpha})"


def build_frame_style(
    background: QtGui.QColor,
    radius_px: int,
    border: QtGui.QColor | None,
    border_width_px: int,
) -> str:
    """Build the QSS for any surface background.

    Args:
        background: The background color.
        radius_px: The border radius in physical pixels.
        border: The border color, or None if no border.
        border_width_px: The border width in physical pixels.

    Returns:
        A QSS string.
    """
    tmp_bg_str = _color_to_qss(background)
    if border is None or border_width_px <= 0:
        tmp_border_str = "none"
    else:
        tmp_border_str = f"{border_width_px}px solid {_color_to_qss(border)}"

    return (
        "QFrame {\n"
        f"    background-color: {tmp_bg_str};\n"
        f"    border-radius: {radius_px}px;\n"
        f"    border: {tmp_border_str};\n"
        "}"
    )


def build_label_style(
    color: QtGui.QColor,
    font_size_px: int,
    font_weight: int,
    font_family: str,
) -> str:
    """Build the QSS for text.

    Args:
        color: The text color.
        font_size_px: The font size in physical pixels.
        font_weight: The font weight.
        font_family: The font family name.

    Returns:
        A QSS string.
    """
    tmp_color_str = _color_to_qss(color)
    return (
        "QLabel {\n"
        f"    color: {tmp_color_str};\n"
        f"    font-size: {font_size_px}px;\n"
        f"    font-weight: {font_weight};\n"
        f'    font-family: "{font_family}";\n'
        "}"
    )


def build_button_style(
    states: dict[
        roles.ControlState,
        tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor],
    ],
    radius_px: int,
) -> str:
    """Build the QSS for a button with all pseudo-selectors.

    Args:
        states: Mapping of ControlState to (background, border, text) colors.
        radius_px: The border radius in physical pixels.

    Returns:
        A QSS string containing all state styles.
    """
    tmp_state_selectors = {
        roles.ControlState.Default: "QPushButton",
        roles.ControlState.Hovered: "QPushButton:hover",
        roles.ControlState.Pressed: "QPushButton:pressed",
        roles.ControlState.Focused: "QPushButton:focus",
        roles.ControlState.Disabled: "QPushButton:disabled",
    }

    tmp_blocks = []
    for tmp_state, tmp_selector in tmp_state_selectors.items():
        if tmp_state not in states:
            continue
        tmp_bg, tmp_border, tmp_text = states[tmp_state]
        tmp_bg_str = _color_to_qss(tmp_bg)
        tmp_border_str = _color_to_qss(tmp_border)
        tmp_text_str = _color_to_qss(tmp_text)

        if tmp_state == roles.ControlState.Default:
            tmp_blocks.append(
                f"{tmp_selector} {{\n"
                f"    background-color: {tmp_bg_str};\n"
                f"    border: 1px solid {tmp_border_str};\n"
                f"    color: {tmp_text_str};\n"
                f"    border-radius: {radius_px}px;\n"
                "}"
            )
        else:
            tmp_blocks.append(
                f"{tmp_selector} {{\n"
                f"    background-color: {tmp_bg_str};\n"
                f"    border: 1px solid {tmp_border_str};\n"
                f"    color: {tmp_text_str};\n"
                "}"
            )

    return "\n\n".join(tmp_blocks)


def build_input_style(
    bg: QtGui.QColor,
    border: QtGui.QColor,
    radius_px: int,
    text: QtGui.QColor,
    placeholder: QtGui.QColor,
    focus_border: QtGui.QColor | None = None,
) -> str:
    """Build the QSS for an input field.

    Args:
        bg: The background color.
        border: The border color.
        radius_px: The border radius in physical pixels.
        text: The text color.
        placeholder: The placeholder text color.
        focus_border: The border color when focused.

    Returns:
        A QSS string.
    """
    tmp_bg_str = _color_to_qss(bg)
    tmp_border_str = _color_to_qss(border)
    tmp_text_str = _color_to_qss(text)
    tmp_placeholder_str = _color_to_qss(placeholder)

    tmp_qss = (
        "QFrame {\n"
        f"    background-color: {tmp_bg_str};\n"
        f"    border: 1px solid {tmp_border_str};\n"
        f"    border-radius: {radius_px}px;\n"
        "}\n\n"
    )

    if focus_border is not None:
        tmp_focus_border_str = _color_to_qss(focus_border)
        tmp_qss += (
            'QFrame:focus, QFrame[state="focused"] {\n'
            f"    border: 2px solid {tmp_focus_border_str};\n"
            "}\n\n"
        )

    tmp_qss += (
        "QLineEdit {\n"
        "    background-color: transparent;\n"
        "    border: none;\n"
        f"    color: {tmp_text_str};\n"
        f"    placeholder-text-color: {tmp_placeholder_str};\n"
        "}"
    )
    return tmp_qss


def build_divider_style(color: QtGui.QColor) -> str:
    """Build the QSS for a divider line.

    Args:
        color: The color of the divider line.

    Returns:
        A QSS string representing the divider stylesheet.
    """
    tmp_color_str = _color_to_qss(color)
    return f"QFrame {{\n    color: {tmp_color_str};\n}}"
