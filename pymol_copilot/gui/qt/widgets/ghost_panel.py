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
"""Provides a semi-transparent ghost panel that fades in on hover."""

from __future__ import annotations

from pymol_copilot.gui.qt import QtCore
from pymol_copilot.gui.qt import QtGui
from pymol_copilot.gui.qt import QtWidgets
from pymol_copilot.gui.qt import theme
from pymol_copilot.gui.qt.widgets import command_bar


class GhostPanel(QtWidgets.QWidget):
    """A visual container panel that fades in on mouse hover."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the ghost panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        # 1. Root layout for HoverOverlay itself
        self._root_layout = QtWidgets.QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)

        # 2. Visual content container
        self._content_frame = QtWidgets.QFrame()
        self._main_layout = QtWidgets.QVBoxLayout(self._content_frame)
        # Padding inside the panel
        self._main_layout.setContentsMargins(10, 10, 10, 10)

        # Add the visual frame to the root layout
        self._root_layout.addWidget(self._content_frame)

        self.opacity_effect: QtWidgets.QGraphicsOpacityEffect | None = None
        self.animation: QtCore.QPropertyAnimation | None = None

        self._setup_opacity_animation()
        self._set_style()

    def set_content(self, content: QtWidgets.QWidget) -> None:
        """Set the content widget displayed inside the panel.

        Args:
            content: The content widget to display.
        """
        self._main_layout.addWidget(content)
        # Force the overlay to shrink-wrap strictly to what its content demands
        self.adjustSize()

    def _set_style(self) -> None:
        """Apply styles to the visual frame."""
        self._content_frame.setObjectName(theme.StyleId.PANEL_SURFACE)

    def _setup_opacity_animation(self) -> None:
        """Set up the graphics opacity effect and hover fade animations."""
        # 2. Create an opacity effect and apply it to this widget
        self.opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # Set default idle opacity (Semi-transparent)
        self.opacity_effect.setOpacity(0.2)

        # 3. Set up the fade animation
        self.animation = QtCore.QPropertyAnimation(
            self.opacity_effect, b"opacity"
        )
        # 250ms (Standard Material Design speed)
        self.animation.setDuration(350)
        self.animation.setEasingCurve(QtCore.QEasingCurve.Type.InOutQuad)

    def enterEvent(  # noqa: N802 (Qt override)
        self, event: QtGui.QEnterEvent | None
    ) -> None:
        """Triggered when mouse enters the widget.

        Args:
            event: The enter event.
        """
        if self.animation is not None:
            self.animation.stop()
            self.animation.setEndValue(0.90)  # Fade to near-solid
            self.animation.start()
        super().enterEvent(event)

    def leaveEvent(  # noqa: N802 (Qt override)
        self, event: QtCore.QEvent | None
    ) -> None:
        """Triggered when mouse leaves the widget.

        Args:
            event: The leave event.
        """
        if self.animation is not None:
            self.animation.stop()
            self.animation.setEndValue(0.2)  # Fade back to semi-transparent
            self.animation.start()
        super().leaveEvent(event)


class GhostBar(GhostPanel):
    """A hover-responsive action bar that floats on top of content."""

    def __init__(
        self,
        command_buttons: list[command_bar.CommandBarButton],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the ghost bar.

        Args:
            command_buttons: The list of buttons to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._command_bar = command_bar.CommandBar(command_buttons, parent=self)
        self.set_content(self._command_bar)
