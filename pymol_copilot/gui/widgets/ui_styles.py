"""Contains reusable QSS fragments for custom widgets."""

from __future__ import annotations


class UIStyles:
    """Reusable style constants for child widgets."""

    FLAT_ICON_BUTTON = """
        QPushButton {
            border: none;
            font-size: 20px;
            color: #5f6368;
            background: transparent;
        }
        QPushButton:hover {
            color: #1a73e8;
        }
    """

    MODEL_DROPDOWN = """
        QComboBox {
            border: none;
            background: transparent;
            font-size: 14px;
            color: #444746;
            padding-right: 18px;
        }
        QComboBox::drop-down {
            border: none;
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 15px;
        }
    """

    TRANSPARENT_INPUT = """
        QLineEdit {
            border: none;
            background: transparent;
            font-size: 16px;
            color: #1f1f1f;
        }
    """
