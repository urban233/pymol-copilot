# Copyright 2026 PyMOL Copilot contributors.
"""Shared pytest fixtures for this package's end-to-end scenarios.

`real_pymol` and `loaded_fixture` are defined once in `scenario_support.py`
and re-exported here so pytest's own directory-scoped conftest.py discovery
makes them available by parameter name to every test module in this
directory that opts in, without any of those modules importing the fixture
names into their own namespace -- the same arrangement, for the same
reason, as [tests/integration/conftest.py](../integration/conftest.py):
an imported name shadowed by a same-named fixture parameter in a different
scope is flagged by ruff's pyflakes-derived F811 ("redefinition of unused
name").

`real_pymol` is module-scoped, and every real-PyMOL module here is its
own `py_test` target and therefore its own process, so no two modules ever
share one PyMOL session.
"""

from __future__ import annotations

import winstage

from scenario_support import loaded_fixture  # noqa: F401
from scenario_support import real_pymol  # noqa: F401

# Stage `pymol` to a short path before any test module in this directory
# gets a chance to import it -- a no-op everywhere but Windows, and inert
# there too whenever the installed wheel's own path already fits. See
# winstage.py's own docstring and issue #12.
winstage.ensure_importable()
