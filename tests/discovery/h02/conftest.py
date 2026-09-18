# Copyright 2026 PyMOL Copilot contributors.
"""Shared pytest fixtures for this directory's execution-boundary probes.

`real_pymol` and `loaded_fixture` are defined once in
tests/integration/snapshot_support.py -- the promoted home of what was
this directory's own harness.py before H-02's snapshot format shipped as
`pmc_core.snapshot` -- and re-exported here so pytest's own
directory-scoped conftest.py discovery makes them available to every test
module in this directory, without any of those modules importing the
fixture names into their own namespace.

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

import winstage

from snapshot_support import loaded_fixture  # noqa: F401
from snapshot_support import real_pymol  # noqa: F401

# Stage `pymol` to a short path before any test module in this directory
# gets a chance to import it -- a no-op everywhere but Windows, and inert
# there too whenever the installed wheel's own path already fits. See
# winstage.py's own docstring and issue #12.
winstage.ensure_importable()
