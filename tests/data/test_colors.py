# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic evidence for the frozen color name-to-index table.

The real-PyMOL half of this table's evidence -- that every frozen index
is still what live PyMOL reports -- lives in
tests/integration/test_real_pymol_allowlist.py. What is checkable
without PyMOL is that the table still covers exactly the color names
the command language accepts, which is the property the oracle relies on
when it predicts a color it was handed by a plan.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.plan import COLOR_ALLOWLIST
from pmc_data.colors import COLOR_INDEX_BY_NAME


def test_table_covers_the_whole_allowlist() -> None:
    """Every accepted color must be predictable without PyMOL.

    A name the parser and policy both accept but the table does not
    carry would make the oracle raise mid-generation on a plan that is
    perfectly legal, which would look like an oracle defect rather than
    the missing table entry it actually is.
    """
    assert set(COLOR_INDEX_BY_NAME) == set(COLOR_ALLOWLIST)


def test_no_color_maps_to_an_unresolved_index() -> None:
    """PyMOL reports -1 for a color it does not know.

    Freezing a -1 would record "unknown" as though it were a real index
    and let a color assertion pass against an atom PyMOL never colored.
    """
    assert [
        name for name, index in COLOR_INDEX_BY_NAME.items() if index < 0
    ] == []


def test_the_table_is_read_only() -> None:
    """A mutable table could be edited by one sample and observed by the next."""
    assert not isinstance(COLOR_INDEX_BY_NAME, dict)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__]))
