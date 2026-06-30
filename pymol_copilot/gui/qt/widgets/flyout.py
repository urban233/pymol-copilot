"""Flyout panel for displaying arbitrary content near a widget or the cursor.

FlyoutFrame is a floating, frameless popup window styled to match the
CommandBar visual language: white background, rounded corners, subtle
border, and a soft drop shadow.  It closes automatically when the user
clicks outside it (Qt.WindowType.Popup behaviour).

Typical use-cases
-----------------
* Attach to a ``CommandBarSplitButton`` arrow section via ``set_flyout()``.
* Show near the cursor with ``show_at(QCursor.pos())``.
* Show relative to any widget with ``show_for(widget, FlyoutPlacement.BELOW)``.
"""

from __future__ import annotations

import enum

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import styles
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt import ui_defaults

__docformat__ = "google"


# Shadow clearance on every side so the drop-shadow is never clipped by
# the transparent window boundary.
_SHADOW_MARGIN = 16


class FlyoutPlacement(enum.Enum):
    """Anchor position for :meth:`FlyoutFrame.show_for`.

    Attributes:
        BELOW: Open below the anchor widget, left-aligned with it.
        ABOVE: Open above the anchor widget, left-aligned with it.
        LEFT:  Open to the left of the anchor widget, top-aligned with it.
        RIGHT: Open to the right of the anchor widget, top-aligned with it.
    """

    BELOW = "below"
    ABOVE = "above"
    LEFT = "left"
    RIGHT = "right"


class FlyoutFrame(QtWidgets.QWidget):
    """A floating panel styled to match the CommandBar visual language.

    The window is frameless and uses ``Qt.WindowType.Popup`` so it
    auto-closes when the user clicks outside it, mirroring the
    behaviour of a ``QMenu``.

    Signals:
        about_to_show: Emitted from ``showEvent`` — mirrors
            ``QMenu.aboutToShow`` so ``CommandBarSplitButton`` can
            hook in without additional glue code.
        about_to_hide: Emitted from ``hideEvent`` — mirrors
            ``QMenu.aboutToHide``.

    Example:
        >>> flyout = FlyoutFrame()
        >>> flyout.set_content(QLabel("Hello"))
        >>> flyout.show_at(QCursor.pos())
    """

    about_to_show: QtCore.pyqtSignal = QtCore.pyqtSignal()
    about_to_hide: QtCore.pyqtSignal = QtCore.pyqtSignal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        shadow: bool = True,
    ) -> None:
        """Initialise the flyout window.

        Args:
            parent: Optional parent widget.  Passing a parent helps Qt
                choose which screen to display on, but the flyout is
                always a top-level window.
            shadow: When ``True`` (default), a drop-shadow is applied via
                ``QGraphicsDropShadowEffect`` and ``WA_TranslucentBackground``
                is set so the shadow margin is see-through.  Set to ``False``
                when attaching the flyout to a ``CommandBarSplitButton`` or any
                other host that already provides visual depth — this avoids the
                Windows compositing artifact where the shadow-clearance margin
                renders as opaque gray rather than transparent.
        """
        super().__init__(
            parent,
            QtCore.Qt.WindowType.Popup
            | QtCore.Qt.WindowType.FramelessWindowHint,
        )

        if shadow:
            self.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_TranslucentBackground
            )

        self._inner_frame: QtWidgets.QFrame = QtWidgets.QFrame()
        self._inner_frame.setObjectName(theme.StyleId.FLYOUT_FRAME)

        if shadow:
            tmp_shadow = QtWidgets.QGraphicsDropShadowEffect()
            tmp_shadow.setBlurRadius(20)
            tmp_shadow.setOffset(3, 3)
            tmp_shadow.setColor(QtGui.QColor(0, 0, 0, 30))
            self._inner_frame.setGraphicsEffect(tmp_shadow)

        self._content_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(
            self._inner_frame
        )
        self._content_layout.setContentsMargins(
            styles.dp(8), styles.dp(8), styles.dp(8), styles.dp(8)
        )
        self._content_layout.setSpacing(ui_defaults.DEFAULT_SPACING)

        m = styles.dp(_SHADOW_MARGIN) if shadow else 0
        outer_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(m, m, m, m)
        outer_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        outer_layout.addWidget(self._inner_frame)

    # ------------------------------------------------------------------
    # Content management
    # ------------------------------------------------------------------

    def set_content(self, widget: QtWidgets.QWidget) -> None:
        """Replace the flyout content with *widget*.

        Any previously set content widget is removed from the layout and
        its parent is cleared (ownership is returned to the caller).

        Args:
            widget: The widget to display inside the flyout.
        """
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item is not None and item.widget() is not None:
                item.widget().setParent(None)  # type: ignore[arg-type]
        self._content_layout.addWidget(widget)

    # ------------------------------------------------------------------
    # Positioning and display
    # ------------------------------------------------------------------

    def show_at(self, global_pos: QtCore.QPoint) -> None:
        """Show the flyout with its top-left at *global_pos*.

        The position is clamped so the flyout stays within the available
        geometry of the screen it appears on.

        Args:
            global_pos: Desired top-left position in global screen coordinates.
        """
        self.adjustSize()
        screen = (
            QtWidgets.QApplication.screenAt(global_pos)
            or QtWidgets.QApplication.primaryScreen()
        )
        if screen is not None:
            available = screen.availableGeometry()
            x = min(global_pos.x(), available.right() - self.width())
            y = min(global_pos.y(), available.bottom() - self.height())
            x = max(x, available.left())
            y = max(y, available.top())
            global_pos = QtCore.QPoint(x, y)
        self.move(global_pos)
        self.show()

    def show_for(
        self,
        anchor: QtWidgets.QWidget,
        placement: FlyoutPlacement = FlyoutPlacement.BELOW,
    ) -> None:
        """Show the flyout positioned relative to *anchor*.

        Args:
            anchor: The widget to position the flyout next to.
            placement: Which side of *anchor* to open on.
                Defaults to :attr:`FlyoutPlacement.BELOW`.
        """
        self.adjustSize()
        origin = anchor.mapToGlobal(QtCore.QPoint(0, 0))
        if placement is FlyoutPlacement.BELOW:
            pos = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height()))
        elif placement is FlyoutPlacement.ABOVE:
            pos = QtCore.QPoint(origin.x(), origin.y() - self.height())
        elif placement is FlyoutPlacement.RIGHT:
            pos = anchor.mapToGlobal(QtCore.QPoint(anchor.width(), 0))
        else:  # LEFT
            pos = QtCore.QPoint(origin.x() - self.width(), origin.y())
        self.show_at(pos)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def showEvent(self, event: QtGui.QShowEvent | None) -> None:
        super().showEvent(event)
        self.about_to_show.emit()

    def hideEvent(self, event: QtGui.QHideEvent | None) -> None:
        self.about_to_hide.emit()
        super().hideEvent(event)
