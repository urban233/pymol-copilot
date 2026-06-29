"""Dev harness page for showcasing composite widgets."""

from __future__ import annotations

from PyQt6 import QtWidgets

import fluentqt.composites.base as base_module
import fluentqt.composites.input_bar as input_bar_module
import fluentqt.core.factory as factory_module
import fluentqt.enums.roles as roles_module


class CustomDemoComposite(base_module.CompositeWidget):
    """A custom vertical composite layout subclassing CompositeWidget."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the CustomDemoComposite.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(
            elevation=roles_module.ElevationPreset.Card,
            orientation="vertical",
            fill_role=roles_module.FillRole.CardBackground,
            parent=parent,
        )

    def _build_content(self) -> None:
        """Populate the vertical composite layout."""
        tmp_lbl = factory_module.make_label(
            "Custom Vertical Composite (Card Surface)",
            roles_module.TextRole.Primary,
            roles_module.TypeStyle.BodyStrong,
            parent=self.frame,
        )
        tmp_btn1 = factory_module.make_button(
            "Option A", roles_module.ButtonRole.Standard, parent=self.frame
        )
        tmp_btn2 = factory_module.make_button(
            "Option B", roles_module.ButtonRole.Standard, parent=self.frame
        )

        if self.content_layout is not None:
            self.content_layout.addWidget(tmp_lbl)
            self.content_layout.addWidget(tmp_btn1)
            self.content_layout.addWidget(tmp_btn2)


class CompositesPage(QtWidgets.QWidget):
    """Page displaying the compound composite widgets."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the CompositesPage.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent=parent)

        tmp_layout = QtWidgets.QVBoxLayout(self)
        tmp_layout.setContentsMargins(20, 20, 20, 20)
        tmp_layout.setSpacing(25)

        # Title Label
        tmp_title = factory_module.make_label(
            "Composite Widgets",
            roles_module.TextRole.Primary,
            roles_module.TypeStyle.Subtitle,
            parent=self,
        )
        tmp_layout.addWidget(tmp_title)

        # Ported InputBar widget section
        tmp_input_bar_lbl = factory_module.make_label(
            "Ported InputBar composite widget:",
            roles_module.TextRole.Secondary,
            roles_module.TypeStyle.Body,
            parent=self,
        )
        tmp_layout.addWidget(tmp_input_bar_lbl)

        tmp_input_bar = input_bar_module.InputBar(parent=self)
        tmp_layout.addWidget(tmp_input_bar)

        # Custom Composite demo section
        tmp_custom_lbl = factory_module.make_label(
            "CompositeWidget layout container demonstration:",
            roles_module.TextRole.Secondary,
            roles_module.TypeStyle.Body,
            parent=self,
        )
        tmp_layout.addWidget(tmp_custom_lbl)

        tmp_custom = CustomDemoComposite(parent=self)
        tmp_layout.addWidget(tmp_custom)

        # Spacer at the bottom
        tmp_layout.addStretch()
