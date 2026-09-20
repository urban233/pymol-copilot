# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL evidence that extract() and render() compose end to end.

Every collaborator here is real: real headless Open-Source PyMOL, the
production `pmc_core.snapshot.extract` and the production
`pmc_core.card.render`. This is the one piece of card evidence that
cannot live in `tests/contract`, which is PyMOL-free by charter -- every
other card property (golden bytes, ordering/signed-zero invariance,
per-field mutation, truncation, and fail-closed handling) is covered
there over hand-built snapshots.

`loaded_fixture` (a pytest fixture defined in snapshot_support.py) is not
imported here: this directory's conftest.py re-exports it once so
pytest's directory-scoped fixture discovery makes it available to this
module without a same-named import that this test's own `loaded_fixture`
parameter would otherwise shadow (ruff's F811, confirmed empirically --
see conftest.py's own docstring).
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
import sys
from typing import Any

import pytest

from pmc_core.card import render
from pmc_core.snapshot import extract


def test_extracted_snapshot_renders_as_a_complete_card(
    loaded_fixture: Any,
) -> None:
    """A real extracted fixture feeds the same pure renderer."""
    card = render(extract(loaded_fixture, "fx"))

    assert "status=complete" in card
    assert "unsupported state=measurement-objects route=plan-report" in card
    assert "states=2" in card
    assert 'chain="A"' in card
    assert 'resn="ZN"' in card


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (the same defect documented and
    # fixed the same way in tests/integration/test_real_pymol_command.py
    # and tests/data/test_gold_case_verifier.py). os._exit bypasses that
    # interpreter-shutdown window entirely, so pytest's real result is what
    # Bazel actually sees. os._exit skips the normal stdio flush, so flush
    # explicitly first -- otherwise a real failure's traceback and summary
    # can be silently lost from the captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
