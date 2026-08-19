# Copyright 2026 PyMOL Copilot contributors.
"""Run the native executable shipped in the locked Ruff wheel."""

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main() -> int:
    """Extract and execute Ruff without using a host installation.

    Returns:
        The exit status returned by the Ruff executable.
    """
    runfiles = next(
        parent
        for parent in Path(__file__).parents
        if parent.name.endswith(".runfiles")
    )
    wheel = next(runfiles.rglob("ruff-*.whl"))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(root)
        executable = next(
            path
            for path in root.rglob("ruff*")
            if path.is_file() and path.name in ("ruff", "ruff.exe")
        )
        executable.chmod(executable.stat().st_mode | 0o111)
        return subprocess.run(
            [str(executable), *sys.argv[1:]],
            cwd=os.environ.get("BUILD_WORKSPACE_DIRECTORY"),
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
