from __future__ import annotations
from typing import override
import os

import pymol
from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults


class PmlLineEdit(QtWidgets.QLineEdit):
    """Internal line edit component that preserves the original PyMOL drag-and-drop
    behavior and processes keystroke filtering.
    """

    def __init__(self, parent: PmlCommandLine) -> None:
        super().__init__(parent)
        self._cmd_line = parent
        self._saved_pos = -1
        self._saved_text = ""

    @override
    def focusNextPrevChild(self, next: bool) -> bool:
        """CRITICAL FIX: Prevents the Tab key from shifting focus to other UI elements,
        allowing the tab key event to fall through to the autocompletion engine.
        """
        return False

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        """Triggers the history overlay immediately when the field gains focus."""
        super().focusInEvent(event)
        if event.reason() in (
            QtCore.Qt.FocusReason.MouseFocusReason,
            QtCore.Qt.FocusReason.TabFocusReason,
        ):
            self._cmd_line.show_history()

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        """Evaluates focus destination slightly delayed to prevent closing when
        clicking inside the overlay browser scroll bar.
        """
        super().focusOutEvent(event)
        QtCore.QTimer.singleShot(100, self._cmd_line.check_focus_loss)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Ensures the history overlay opens every time the widget is clicked,
        regardless of whether it already has focus.
        """
        super().mousePressEvent(event)
        self._cmd_line.show_history()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        Qt = QtCore.Qt
        key = event.key()

        if key == Qt.Key.Key_Tab:
            self._cmd_line.perform_tab_completion()
            event.accept()
            return
        elif key == Qt.Key.Key_Up:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._cmd_line.history_back_search()
            else:
                self._cmd_line.history_back()
            event.accept()
            return
        elif key == Qt.Key.Key_Down:
            self._cmd_line.history_forward()
            event.accept()
            return
        elif key == Qt.Key.Key_Escape:
            self._cmd_line.hide_history()
            event.accept()
            return
        elif key == Qt.Key.Key_Return or key == Qt.Key_Enter:
            self._cmd_line.doPrompt()
            event.accept()
            return

        super().keyPressEvent(event)

    @override
    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Tab:
            event.accept()
            return
        super().keyReleaseEvent(event)

    @override
    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        pass

    @override
    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    @override
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if not event.mimeData().hasText():
            self._saved_pos = -1
            return

        event.acceptProposedAction()
        urls = event.mimeData().urls()
        droppedtext = (
            urls[0].toLocalFile()
            if urls and urls[0].isLocalFile()
            else event.mimeData().text()
        )

        pos = self.cursorPosition()
        text = self.text()
        self._saved_pos = pos
        self._saved_text = text

        self.setText(text[:pos] + droppedtext + text[pos:])
        self.setSelection(pos, len(droppedtext))

    @override
    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent) -> None:
        if self._saved_pos != -1:
            self.setText(self._saved_text)
            self.setCursorPosition(self._saved_pos)


class PmlHistoryOverlay(QtWidgets.QWidget):
    """Internal log viewer panel that styles itself to overlay cleanly over
    surrounding window layouts without taking up static vertical space.
    """

    def __init__(
        self, parent: QtWidgets.QWidget, lineedit: QtWidgets.QLineEdit
    ) -> None:
        super().__init__(parent)
        self.lineedit = lineedit
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setStyleSheet("""
            PmlHistoryOverlay {
                background-color: #ffffff;
                border: 1px solid #d2d2d2;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(*ui_defaults.EMPTY_CONTENTS_MARGINS)
        layout.setSpacing(ui_defaults.EMPTY_SPACING)

        self.browser = QtWidgets.QPlainTextEdit(self)
        self.browser.setObjectName("feedback_browser")
        self.browser.setReadOnly(True)
        self.browser.setStyleSheet("QPlainTextEdit { border: none; }")
        self.browser.setFocusProxy(self.lineedit)

        try:
            from pymol.Qt.utils import connectFontContextMenu, getMonospaceFont

            self.browser.setFont(getMonospaceFont())
            connectFontContextMenu(self.browser)
        except ImportError:
            pass

        layout.addWidget(self.browser)
        self.hide()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mousePressEvent(event)
        if self.lineedit:
            QtCore.QTimer.singleShot(
                0,
                lambda: self.lineedit.setFocus(
                    QtCore.Qt.FocusReason.OtherFocusReason
                ),
            )


class PmlCommandLine(QtWidgets.QWidget):
    """A completely unified composite layout widget that houses the PyMOL prompt,
    the text input field, and an encapsulated log history polling overlay panel.
    """

    commandSubmitted = QtCore.pyqtSignal(str)
    completionRequested = QtCore.pyqtSignal()

    def __init__(
        self, cmd=None, parent: QtWidgets.QWidget | None = None
    ) -> None:
        """Initialize the unified command line.

        Args:
            cmd: Optional PyMOL command instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._outer_frame: QtWidgets.QFrame = QtWidgets.QFrame(self)
        self._layout_outer_frame: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(
            self
        )
        self._main_layout: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout(
            self._outer_frame
        )

        self.cmd = cmd if cmd is not None else pymol.cmd

        # Local command history index tracking states
        self._history: list[str] = []
        self._history_index = -1
        self._history_buffer = ""
        self._overlay_height = 200

        # Lazy initialize history display overlay canvas layer
        self._history_overlay: PmlHistoryOverlay | None = None

        self.lineedit = PmlLineEdit(self)
        self._feedback_timer = QtCore.QTimer(self)

        self._init_widget()
        self._set_styles()

    def _set_styles(self) -> None:
        """Apply the global theme object names and shadow effects."""
        self._outer_frame.setObjectName(theme.StyleId.COMMAND_BAR_OUTER)
        tmp_shadow_effect = QtWidgets.QGraphicsDropShadowEffect()
        tmp_shadow_effect.setBlurRadius(10)
        tmp_shadow_effect.setOffset(2, 2)
        tmp_shadow_effect.setColor(QtGui.QColor(0, 0, 0, 10))
        self._outer_frame.setGraphicsEffect(tmp_shadow_effect)
        self.lineedit.setObjectName(theme.StyleId.MINIMAL_TEXT_BOX)

    def _init_widget(self) -> None:
        self._main_layout.setContentsMargins(
            *ui_defaults.EMPTY_CONTENTS_MARGINS
        )
        self._main_layout.setSpacing(ui_defaults.default_spacing())
        self._layout_outer_frame.setContentsMargins(
            *ui_defaults.default_contents_margins()
        )

        self.lineedit.setObjectName("command_line")
        self.lineedit.setPlaceholderText("Type PyMOL commands here...")
        self.lineedit.setToolTip("""Command Input Area

Get the list of commands by hitting <TAB>

Get the list of arguments for one command with a question mark:
PyMOL> color ?

Read the online help for a command with "help":
PyMOL> help color

Get autocompletion for many arguments by hitting <TAB>
PyMOL> color ye<TAB>    (will autocomplete "yellow")
""")

        self._main_layout.addWidget(self.lineedit)
        self._outer_frame.setLayout(self._main_layout)
        self._layout_outer_frame.addWidget(self._outer_frame)
        self.setLayout(self._layout_outer_frame)

        # Dynamic visibility management hook links
        self.lineedit.textChanged.connect(self._on_text_changed)

        # Fully encapsulated self-managed polling loop
        self._feedback_timer.timeout.connect(self._poll_pymol_feedback)
        self._feedback_timer.start(100)

        # Prevent parent layout from stretching this widget vertically
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )

    def _ensure_overlay_initialized(self) -> None:
        if self._history_overlay is None:
            top_window = self.window()
            self._history_overlay = PmlHistoryOverlay(top_window, self.lineedit)
            top_window.installEventFilter(self)

    def show_history(self) -> None:
        self._ensure_overlay_initialized()
        top_window = self.window()
        if not top_window or not self._history_overlay:
            return

        # Explicitly calculates position bounds UPWARD from layout coordinates
        local_pos = self.lineedit.mapTo(
            top_window, QtCore.QPoint(-4, -self._overlay_height - 4)
        )
        self._history_overlay.setGeometry(
            local_pos.x(),
            local_pos.y(),
            self.lineedit.width() + 8,
            self._overlay_height,
        )
        self._history_overlay.show()
        self._history_overlay.raise_()

    def hide_history(self) -> None:
        if self._history_overlay:
            self._history_overlay.hide()

    def _on_text_changed(self, text: str) -> None:
        if self.lineedit.hasFocus():
            self.show_history()

    def check_focus_loss(self) -> None:
        if self._history_overlay and self._history_overlay.isVisible():
            focus_w = QtWidgets.QApplication.focusWidget()
            if (
                focus_w != self.lineedit
                and focus_w != self._history_overlay
                and focus_w != self._history_overlay.browser
            ):
                self.hide_history()

    def _poll_pymol_feedback(self) -> None:
        if not self.cmd:
            return
        try:
            feedback = self.cmd._get_feedback()
            if feedback:
                self.append_feedback(feedback)
        except Exception:
            pass

    def perform_tab_completion(self) -> None:
        """Processes partial command and argument autocompletion based on PyMOL's internal dictionaries."""
        self.completionRequested.emit()
        text = self.lineedit.text()
        if not text:
            return

        # Tokenize current text input parameters
        parts = text.split()
        is_command_only = (len(parts) == 1 and not text.endswith(" ")) or len(
            parts
        ) == 0

        candidates = []

        # Case 1: Completing the first word (The core PyMOL command keyword)
        if is_command_only:
            current_word = parts[0] if parts else ""
            if hasattr(self.cmd, "kwhash") and hasattr(
                self.cmd.kwhash, "keywords"
            ):
                candidates = [
                    k
                    for k in self.cmd.kwhash.keywords
                    if k.startswith(current_word)
                ]

        # Case 2: Completing arguments (colors, system settings, or structure object selections)
        else:
            current_word = parts[-1] if not text.endswith(" ") else ""
            command_verb = parts[0].lower()

            # Compile possible match options from colors, names, and settings registries
            color_names = []
            if hasattr(self.cmd, "get_color_indices"):
                try:
                    color_names = [c[0] for c in self.cmd.get_color_indices()]
                except Exception:
                    pass

            object_names = []
            if hasattr(self.cmd, "get_names"):
                try:
                    object_names = self.cmd.get_names()
                except Exception:
                    pass

            setting_names = []
            if hasattr(self.cmd, "setting") and hasattr(
                self.cmd.setting, "_get_setting_names"
            ):
                try:
                    setting_names = self.cmd.setting._get_setting_names()
                except Exception:
                    pass

            # Contextually filter parameters based on commands
            if command_verb in ("color", "set_color", "bg_color"):
                pool = color_names + object_names
            elif command_verb in ("set", "get", "unset"):
                pool = setting_names
            else:
                pool = object_names + color_names + setting_names

            candidates = [
                item for item in pool if item.startswith(current_word)
            ]

        if not candidates:
            return

        # Deduplicate pool choices cleanly
        candidates = list(set(candidates))

        # Extrapolate longest common prefix sequence from candidate matches
        longest_prefix = os.path.commonprefix(candidates)

        if longest_prefix and longest_prefix != (
            parts[-1] if not is_command_only and parts else text
        ):
            # Substitute matching segment inline into lineedit buffer
            if is_command_only:
                self.lineedit.setText(longest_prefix)
            else:
                base_text = (
                    text.rsplit(maxsplit=1)[0]
                    if not text.endswith(" ")
                    else text
                )
                if base_text and not base_text.endswith(" "):
                    base_text += " "
                self.lineedit.setText(base_text + longest_prefix)
        elif len(candidates) > 1:
            # If multiple matching options remain, echo suggestions to history overlay
            self.append_feedback(
                ["\nCompletions:"] + [f"  {c}" for c in sorted(candidates)]
            )

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if watched is self.window() and event.type() in (
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Move,
        ):
            if self._history_overlay and self._history_overlay.isVisible():
                self.show_history()

        if (
            event.type() == QtCore.QEvent.Type.MouseButtonPress
            and self._history_overlay
            and self._history_overlay.isVisible()
        ):
            pos = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else event.globalPos()
            )

            overlay_geo = self._history_overlay.geometry()
            global_overlay_rect = QtCore.QRect(
                self._history_overlay.parentWidget().mapToGlobal(
                    overlay_geo.topLeft()
                ),
                overlay_geo.size(),
            )

            input_geo = self.geometry()
            global_input_rect = QtCore.QRect(
                self.parentWidget().mapToGlobal(input_geo.topLeft()),
                input_geo.size(),
            )

            if not global_overlay_rect.contains(
                pos
            ) and not global_input_rect.contains(pos):
                self.hide_history()

        return super().eventFilter(watched, event)

    # --- Public API Integration Layer ---

    def command_get(self) -> str:
        return self.lineedit.text()

    def command_set(self, text: str) -> None:
        self.lineedit.setText(text)
        self._history_index = -1

    def command_set_cursor(self, position: int) -> None:
        self.lineedit.setCursorPosition(position)

    def append_feedback(self, feedback: list[str]) -> None:
        self._ensure_overlay_initialized()
        if not feedback or not self._history_overlay:
            return

        try:
            from pymol import colorprinting

            html = colorprinting.text2html("\n".join(feedback))
            self._history_overlay.browser.appendHtml(html)
        except ImportError:
            self._history_overlay.browser.appendPlainText("\n".join(feedback))

        scrollbar = self._history_overlay.browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # --- CLI History Pipeline Mechanics ---

    def history_back(self) -> None:
        if not self._history:
            return
        if self._history_index == -1:
            self._history_buffer = self.lineedit.text()
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1

        self.lineedit.setText(self._history[self._history_index])

    def history_forward(self) -> None:
        if self._history_index == -1:
            return

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.lineedit.setText(self._history[self._history_index])
        else:
            self._history_index = -1
            self.lineedit.setText(self._history_buffer)

    def history_back_search(self) -> None:
        prefix = self.lineedit.text()
        start_idx = (
            self._history_index
            if self._history_index != -1
            else len(self._history)
        )

        for i in range(start_idx - 1, -1, -1):
            if (
                self._history[i].startswith(prefix)
                and self._history[i] != prefix
            ):
                self._history_index = i
                self.lineedit.setText(self._history[i])
                return

    def doPrompt(self) -> None:
        text = self.command_get()
        if text.strip():
            if not self._history or self._history[-1] != text:
                self._history.append(text)
            self._history_index = -1

            self.commandSubmitted.emit(text)

            if self.cmd:
                try:
                    self.cmd.do(text, log=1)
                except Exception as e:
                    self.append_feedback([f"Error running command: {e}"])

            win = self.window()
            if hasattr(win, "pymolwidget") and hasattr(
                win.pymolwidget, "_pymolProcess"
            ):
                win.pymolwidget._pymolProcess()

        self.lineedit.clear()
