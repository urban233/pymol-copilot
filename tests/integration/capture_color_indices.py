# Copyright 2026 PyMOL Copilot contributors.
"""Capture real PyMOL colour indices into the frozen pmc_data table.

Run this to regenerate `src/pmc_data/colors.py`:

    bazel run //tests/integration:capture_color_indices

Re-running it against an unchanged PyMOL must leave `git status` clean.

The dataset oracle has to predict `color` as the integer index a snapshot
actually records (`pmc_core.snapshot.AtomRecord.color`), and it has to do
so without PyMOL -- that is the whole point of an independent oracle. The
old verifier asked `cmd.get_color_index()` for the expected value, which
made the colour assertion a PyMOL-versus-PyMOL comparison rather than an
independent one. `pmc_core.plan.COLOR_ALLOWLIST` freezes the 177 accepted
colour *names* for the same no-PyMOL-import reason but records no index,
so the mapping is frozen here instead.

`tests/integration/test_real_pymol_allowlist.py` is the target that fails
when the frozen table stops matching live PyMOL.
"""

from __future__ import annotations

import os
import pathlib
import sys

import winstage

from pmc_core.plan import COLOR_ALLOWLIST

winstage.ensure_importable()

#: Where the frozen table is written, relative to the repository root.
TABLE_RELATIVE_PATH = pathlib.PurePath("src/pmc_data/colors.py")

_HEADER = '''# Copyright 2026 PyMOL Copilot contributors.
"""The frozen PyMOL colour name-to-index table the oracle predicts with.

Generated once from `cmd.get_color_index()` against
pymol-open-source-whl 3.2.0.2 and frozen here, exactly as
`pmc_core.plan.COLOR_ALLOWLIST` freezes the names themselves and for the
same reason: the oracle in `pmc_data.oracle` must predict the integer
`color` a snapshot records without importing PyMOL, so this cannot be
read from PyMOL at runtime.

Do not edit by hand. Regenerate with:

    bazel run //tests/integration:capture_color_indices

`tests/integration/test_real_pymol_allowlist.py` proves every pair below
is still what real PyMOL reports, and `tests/data/test_colors.py` proves
the table still covers the whole accepted allowlist.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

#: Every accepted colour name mapped to the stable index PyMOL assigns it.
COLOR_INDEX_BY_NAME: Mapping[str, int] = MappingProxyType(
    {
'''

_FOOTER = """    }
)
"""


def main() -> int:
    """Write the frozen colour index table into the source tree.

    Returns:
        The process exit code: 0 on success, 1 if PyMOL does not
        recognize a name the allowlist accepts.
    """
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])

    unknown: list[str] = []
    pairs: list[tuple[str, int]] = []
    for name in COLOR_ALLOWLIST:
        index = cmd.get_color_index(name)
        if index < 0:
            unknown.append(name)
            continue
        pairs.append((name, index))

    if unknown:
        print(f"UNKNOWN COLORS: {unknown}", file=sys.stderr)
        return 1

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if workspace is None:
        print("BUILD_WORKSPACE_DIRECTORY is not set", file=sys.stderr)
        return 1

    body = "".join(f'        "{name}": {index},\n' for name, index in pairs)
    destination = pathlib.Path(workspace) / TABLE_RELATIVE_PATH
    destination.write_text(_HEADER + body + _FOOTER, encoding="utf-8")
    print(f"WROTE {destination} ({len(pairs)} colors)")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # PyMOL's own shutdown can clobber a normal exit code, the same
    # reason src/pmc_data/generate_cli.py exits this way.
    os._exit(code)
