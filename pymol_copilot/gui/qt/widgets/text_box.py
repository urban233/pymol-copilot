from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme


class ExpandingTextBox(QtWidgets.QPlainTextEdit):
    """A QPlainTextEdit that auto-grows vertically with the number of
    rendered visual lines (explicit newlines *and* word-wrapped lines),
    up to `max_rows`, then becomes scrollable.
    """

    def __init__(
            self,
            placeholder_text: str = "Ask anything",
            max_rows: int = 10,
            min_rows: int = 1,
            parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._max_rows = max_rows
        self._min_rows = min_rows

        self.setPlaceholderText(placeholder_text)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)

        self.textChanged.connect(self._update_height)
        self.setObjectName(theme.StyleId.INPUT_BAR_TEXT_BOX)
        self._update_height()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # A width change reflows word-wrapping, which changes how many
        # visual lines the content occupies -> recompute height too.
        super().resizeEvent(event)
        self._update_height()

    def _line_height(self) -> float:
        return QtGui.QFontMetrics(self.font()).lineSpacing()

    def _vertical_padding(self) -> float:
        doc_margin = self.document().documentMargin()
        frame_width = self.frameWidth()
        return 2 * (doc_margin + frame_width)

    def _wrapped_line_count(self) -> int:
        """Total number of *visual* lines across all blocks, i.e. explicit
        paragraphs (separated by newlines) each split further by word-wrap.

        QPlainTextEdit's document uses QPlainTextDocumentLayout, whose
        document().size() does not reliably reflect wrapped height. Each
        block's QTextLayout does, though (it's what the widget itself uses
        to paint), so we sum lineCount() per block instead.
        """
        total = 0
        block = self.document().begin()
        while block.isValid():
            layout = block.layout()
            line_count = layout.lineCount() if layout is not None else 1
            total += max(line_count, 1)
            block = block.next()
        return max(total, 1)

    def _content_height(self) -> float:
        """Height of the text as Qt would actually render it at the
        current widget width, including word-wrapped lines."""
        return self._wrapped_line_count() * self._line_height()

    def _update_height(self) -> None:
        line_height = self._line_height()
        padding = self._vertical_padding()

        min_height = self._min_rows * line_height + padding
        max_height = self._max_rows * line_height + padding

        content_height = self._content_height() + padding
        new_height = max(min_height, min(content_height, max_height))

        new_height = int(new_height)
        if new_height != self.height():
            self.setFixedHeight(new_height)
