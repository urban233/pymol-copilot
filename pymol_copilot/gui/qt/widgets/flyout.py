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
from typing import override

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
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
            theme.dp(8), theme.dp(8), theme.dp(8), theme.dp(8)
        )
        self._content_layout.setSpacing(ui_defaults.default_spacing())

        tmp_m = theme.dp(_SHADOW_MARGIN) if shadow else 0
        tmp_outer_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(self)
        tmp_outer_layout.setContentsMargins(tmp_m, tmp_m, tmp_m, tmp_m)
        tmp_outer_layout.setSpacing(ui_defaults.EMPTY_SPACING)
        tmp_outer_layout.addWidget(self._inner_frame)

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
            tmp_item = self._content_layout.takeAt(0)
            if tmp_item is not None and tmp_item.widget() is not None:
                tmp_item.widget().setParent(None)  # type: ignore[arg-type]
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
        tmp_screen = (
            QtWidgets.QApplication.screenAt(global_pos)
            or QtWidgets.QApplication.primaryScreen()
        )
        if tmp_screen is not None:
            tmp_available = tmp_screen.availableGeometry()
            tmp_x = min(global_pos.x(), tmp_available.right() - self.width())
            tmp_y = min(global_pos.y(), tmp_available.bottom() - self.height())
            tmp_x = max(tmp_x, tmp_available.left())
            tmp_y = max(tmp_y, tmp_available.top())
            global_pos = QtCore.QPoint(tmp_x, tmp_y)
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
        tmp_origin = anchor.mapToGlobal(QtCore.QPoint(0, 0))
        if placement is FlyoutPlacement.BELOW:
            tmp_pos = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height()))
        elif placement is FlyoutPlacement.ABOVE:
            tmp_pos = QtCore.QPoint(
                tmp_origin.x(), tmp_origin.y() - self.height()
            )
        elif placement is FlyoutPlacement.RIGHT:
            tmp_pos = anchor.mapToGlobal(QtCore.QPoint(anchor.width(), 0))
        else:  # LEFT
            tmp_pos = QtCore.QPoint(
                tmp_origin.x() - self.width(), tmp_origin.y()
            )
        self.show_at(tmp_pos)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def showEvent(self, event: QtGui.QShowEvent | None) -> None:  # noqa: N802
        """Emit the about_to_show signal when the flyout is shown."""
        super().showEvent(event)
        self.about_to_show.emit()

    def hideEvent(self, event: QtGui.QHideEvent | None) -> None:  # noqa: N802
        """Emit the about_to_hide signal when the flyout is hidden."""
        self.about_to_hide.emit()
        super().hideEvent(event)


class FloatingFlyout(QtWidgets.QWidget):
    """A floating child panel for displaying Accept and Reject actions.

    Unlike FlyoutFrame, this does not use Popup window flags, allowing it to
    float persistently over the OpenGL canvas without auto-closing during
    camera interactions.
    """

    accepted: QtCore.pyqtSignal = QtCore.pyqtSignal()
    rejected: QtCore.pyqtSignal = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        """Initializes the floating flyout overlay.

        Args:
            parent: The parent widget that will contain this overlay.
        """
        super().__init__(parent)
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self.setAutoFillBackground(False)

        # Visual inner frame styled via global stylesheet
        self._inner_frame = QtWidgets.QFrame()
        self._inner_frame.setObjectName(theme.StyleId.FLYOUT_FRAME)

        # Layout inside the inner frame
        tmp_content_layout = QtWidgets.QHBoxLayout(self._inner_frame)
        tmp_content_layout.setContentsMargins(
            theme.dp(8), theme.dp(4), theme.dp(8), theme.dp(4)
        )
        tmp_content_layout.setSpacing(theme.dp(8))

        # Setup child controls directly
        self.label = QtWidgets.QLabel("AI Suggestion")
        self.accept_button = QtWidgets.QPushButton("Accept")
        self.reject_button = QtWidgets.QPushButton("Reject")

        # Connect signals
        self.accept_button.clicked.connect(self.accepted.emit)
        self.reject_button.clicked.connect(self.rejected.emit)

        # Add to layout
        tmp_content_layout.addWidget(self.label)
        tmp_content_layout.addWidget(self.accept_button)
        tmp_content_layout.addWidget(self.reject_button)

        # Outer layout to support shadow padding
        tmp_outer_layout = QtWidgets.QVBoxLayout(self)
        tmp_shadow_padding = theme.dp(6)
        tmp_outer_layout.setContentsMargins(
            tmp_shadow_padding,
            tmp_shadow_padding,
            tmp_shadow_padding,
            tmp_shadow_padding,
        )
        tmp_outer_layout.addWidget(self._inner_frame)

        self._apply_button_styles()

    def _apply_button_styles(self) -> None:
        """Applies custom QSS styles to the Accept and Reject buttons."""
        tmp_accept_style = """
            QPushButton {
                background-color: #f1faf1;
                color: #107c10;
                border: 1px solid #107c10;
                border-radius: 4px;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #107c10;
                color: white;
            }
            QPushButton:pressed {
                background-color: #0b5b0b;
                color: #dddddd;
            }
        """

        tmp_reject_style = """
            QPushButton {
                background-color: #fdf3f4;
                color: #bc2f32;
                border: 1px solid #bc2f32;
                border-radius: 4px;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #bc2f32;
                color: white;
            }
            QPushButton:pressed {
                background-color: #6e1e1e;
                color: #dddddd;
            }
        """

        self.accept_button.setStyleSheet(tmp_accept_style)
        self.reject_button.setStyleSheet(tmp_reject_style)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent | None) -> None:
        """Paints a custom offset shadow behind the inner frame.

        Args:
            event: The paint event object.
        """
        tmp_painter = QtGui.QPainter(self)
        tmp_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # Translucent shadow settings
        tmp_shadow_color = QtGui.QColor(0, 0, 0, 30)
        tmp_radius = float(theme.dp(6))

        # Get visual frame geometry relative to this widget
        tmp_frame_rect = self._inner_frame.geometry()
        tmp_shadow_rect = QtCore.QRectF(tmp_frame_rect).translated(
            float(theme.dp(2)), float(theme.dp(2))
        )

        tmp_path = QtGui.QPainterPath()
        tmp_path.addRoundedRect(tmp_shadow_rect, tmp_radius, tmp_radius)
        tmp_painter.fillPath(tmp_path, QtGui.QBrush(tmp_shadow_color))
        tmp_painter.end()
