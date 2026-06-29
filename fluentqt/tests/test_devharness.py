"""Smoke tests for the development harness."""

from __future__ import annotations

from PyQt6 import QtWidgets


def test_devharness_pages_and_window(
    q_app: QtWidgets.QApplication,
) -> None:
    """Verify that all devharness pages and main window can be instantiated.

    Args:
        q_app: Session-scoped QApplication fixture.
    """
    _ = q_app

    # Import modules inside the test body to ensure QApplication is active
    import fluentqt.devharness.__main__ as main_module
    import fluentqt.devharness.pages.composites_page as composites_page
    import fluentqt.devharness.pages.primitives_page as primitives_page
    import fluentqt.devharness.pages.states_page as states_page
    import fluentqt.devharness.pages.themes_page as themes_page

    tmp_primitives = primitives_page.PrimitivesPage()
    assert tmp_primitives is not None

    tmp_states = states_page.StatesPage()
    assert tmp_states is not None

    tmp_composites = composites_page.CompositesPage()
    assert tmp_composites is not None

    tmp_themes = themes_page.ThemesPage()
    assert tmp_themes is not None

    tmp_main_window = main_module.MainWindow()
    assert tmp_main_window is not None
