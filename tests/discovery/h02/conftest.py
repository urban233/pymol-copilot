# Copyright 2026 PyMOL Copilot contributors.
"""Shared pytest fixtures for every H-02 slice-2 candidate test module.

`real_pymol` and `loaded_fixture` are defined once in harness.py (slice 2's
shared, candidate-agnostic differential harness) and re-exported here so
pytest's own directory-scoped conftest.py discovery makes them available
to every candidate test module in this directory, without any of those
modules importing the fixture names into their own namespace.

That per-module import was tried first and rejected: every test function
in this directory takes a same-named parameter (`loaded_fixture`) by
pytest's own fixture-by-parameter-name convention, and an imported name
shadowed by a same-named parameter in a different scope is flagged by
`ruff`'s pyflakes-derived F811 ("redefinition of unused name") -- confirmed
empirically, not a hypothetical lint nit. Defining the re-export exactly
once here, where no function parameter ever shadows it, avoids that
without weakening or duplicating any fixture logic.
"""

from __future__ import annotations

from harness import loaded_fixture  # noqa: F401
from harness import real_pymol  # noqa: F401
