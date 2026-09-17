# Copyright 2026 PyMOL Copilot contributors.
"""Shared pytest fixtures for this package's snapshot round-trip tests.

`real_pymol` and `loaded_fixture` are defined once in snapshot_support.py
and re-exported here so pytest's own directory-scoped conftest.py
discovery makes them available by parameter name to every test module in
this directory that opts in, without any of those modules importing the
fixture names into their own namespace.

That per-module import was tried first and rejected in the H-02 discovery
harness this file continues: every test function that wants the fixture
takes a same-named parameter (`loaded_fixture`) by pytest's own
fixture-by-parameter-name convention, and an imported name shadowed by a
same-named parameter in a different scope is flagged by `ruff`'s
pyflakes-derived F811 ("redefinition of unused name") -- confirmed
empirically, not a hypothetical lint nit. Defining the re-export exactly
once here, where no function parameter ever shadows it, avoids that
without weakening or duplicating any fixture logic.

Every other test module in this directory is unaffected: pytest fixtures
are opt-in by parameter name, and none of them requests `real_pymol` or
`loaded_fixture`. `test_real_pymol_command.py` defines its own
module-scoped `real_pymol` fixture, which simply shadows this one for that
module, exactly as pytest's fixture-scoping rules intend.
"""

from __future__ import annotations

import winstage

from snapshot_support import loaded_fixture  # noqa: F401
from snapshot_support import real_pymol  # noqa: F401

# Stage `pymol` to a short path before any test module in this directory
# gets a chance to import it -- a no-op everywhere but Windows, and inert
# there too whenever the installed wheel's own path already fits. See
# winstage.py's own docstring and issue #12.
winstage.ensure_importable()
