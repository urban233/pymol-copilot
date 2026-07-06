# cBioMOL - open C++ and Python platform for BioMOLecular visualization and
# analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban
# (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
# Source code is available at <https://github.com/urban233/cBioMOL>
# -------------------------------------------------------------------
# It is unlawful to modify or remove this copyright notice.
# -------------------------------------------------------------------
# Please see the accompanying LICENSE file for further information.
# -------------------------------------------------------------------
# Primary author of this source file:
# Martin Urban
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================
#
"""Provides an expanding text box widget that grows dynamically with content."""

from __future__ import annotations

import enum
from typing import override

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme


class AllowedChars(enum.StrEnum):
    """Enum for allowed characters in the text box."""

    NUMERIC = "0123456789"
    ALPHABETIC = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    SPECIAL = "_-"


class TextBox(QtWidgets.QLineEdit):
    """A line edit widget that limits input characters."""

    def __init__(
        self,
        allowed_chars: str = AllowedChars.NUMERIC
        + AllowedChars.ALPHABETIC
        + AllowedChars.SPECIAL,
        max_length: int = 30,
        placeholder_text: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the text box widget.

        Args:
            allowed_chars: A string of characters allowed in the text box.
            max_length: Maximum character length allowed.
            placeholder_text: Placeholder text to show.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._allowed_chars: set[str] = set(allowed_chars)
        self.setMaxLength(max_length)
        self.setPlaceholderText(placeholder_text)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Overrides keyPressEvent of QLineEdit class.

        Args:
            event: The key event to process.
        """
        tmp_key_text = event.text()

        # Block only single printable characters not in the allowed set.
        # Multi-char sequences (IME), empty strings (modifier keys), and
        # standard shortcuts (Ctrl+C/V/X/A) must always propagate.
        if (
            len(tmp_key_text) == 1
            and tmp_key_text not in self._allowed_chars
            and not event.matches(QtGui.QKeySequence.StandardKey.Copy)
            and not event.matches(QtGui.QKeySequence.StandardKey.Paste)
            and not event.matches(QtGui.QKeySequence.StandardKey.Cut)
            and not event.matches(QtGui.QKeySequence.StandardKey.SelectAll)
        ):
            return

        # Call the base class implementation to handle other keys
        super().keyPressEvent(event)


class ExpandingTextBox(QtWidgets.QPlainTextEdit):
    """A QPlainTextEdit that auto-grows vertically with content."""

    returnPressed: QtCore.pyqtSignal = QtCore.pyqtSignal()

    def __init__(
        self,
        placeholder_text: str = "Ask anything",
        max_rows: int = 10,
        min_rows: int = 1,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the expanding text box.

        Args:
            placeholder_text: Placeholder text to display.
            max_rows: Maximum rows before scrollbar appears.
            min_rows: Minimum rows to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._max_rows = max_rows
        self._min_rows = min_rows

        self.setPlaceholderText(placeholder_text)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setTabChangesFocus(True)

        self.textChanged.connect(self._update_height)
        self.setObjectName(theme.StyleId.INPUT_BAR_TEXT_BOX)
        self._update_height()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle key press events to intercept Return key.

        Args:
            event: The key event to process.
        """
        if (
            event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
            and not event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier
        ):
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(  # noqa: N802 (Qt override)
        self, event: QtGui.QResizeEvent | None
    ) -> None:
        """Handle resizing of the text box widget.

        Args:
            event: The resize event.
        """
        # A width change reflows word-wrapping, which changes how many
        # visual lines the content occupies -> recompute height too.
        super().resizeEvent(event)
        self._update_height()

    def _line_height(self) -> float:
        """Calculate the height of a single text line.

        Returns:
            The height of a single line in physical pixels.
        """
        return float(QtGui.QFontMetrics(self.font()).lineSpacing())

    def _vertical_padding(self) -> float:
        """Calculate the vertical padding of the text box.

        Returns:
            The vertical padding in physical pixels.
        """
        tmp_doc = self.document()
        tmp_doc_margin = (
            tmp_doc.documentMargin() if tmp_doc is not None else 0.0
        )
        tmp_frame_width = float(self.frameWidth())
        return 2.0 * (tmp_doc_margin + tmp_frame_width)

    def _wrapped_line_count(self) -> int:
        """Total number of visual lines across all blocks.

        Returns:
            The count of visual lines.
        """
        tmp_total = 0
        tmp_doc = self.document()
        if tmp_doc is not None:
            tmp_block = tmp_doc.begin()
            while tmp_block.isValid():
                tmp_layout = tmp_block.layout()
                tmp_line_count = (
                    tmp_layout.lineCount() if tmp_layout is not None else 1
                )
                tmp_total += max(tmp_line_count, 1)
                tmp_block = tmp_block.next()
        return max(tmp_total, 1)

    def _content_height(self) -> float:
        """Height of the text as Qt would render it.

        Returns:
            The text content height in physical pixels.
        """
        return float(self._wrapped_line_count()) * self._line_height()

    def _update_height(self) -> None:
        """Update the height of the widget based on content."""
        tmp_line_height = self._line_height()
        tmp_padding = self._vertical_padding()

        tmp_min_height = float(self._min_rows) * tmp_line_height + tmp_padding
        tmp_max_height = float(self._max_rows) * tmp_line_height + tmp_padding

        tmp_content_height = self._content_height() + tmp_padding
        tmp_new_height = max(
            tmp_min_height, min(tmp_content_height, tmp_max_height)
        )

        tmp_new_height_int = int(tmp_new_height)
        if tmp_new_height_int != self.height():
            self.setFixedHeight(tmp_new_height_int)
