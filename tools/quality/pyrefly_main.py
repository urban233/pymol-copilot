# Copyright 2026 PyMOL Copilot contributors.
"""Run the native executable shipped in the locked Pyrefly wheel."""

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main() -> int:
    """Extract and execute Pyrefly without using a host installation.

    Returns:
        The exit status returned by the Pyrefly executable.
    """
    runfiles = next(
        parent
        for parent in Path(__file__).parents
        if parent.name.endswith(".runfiles")
    )
    wheel = next(runfiles.rglob("pyrefly-*.whl"))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(root)
        executable = next(
            path
            for path in root.rglob("pyrefly*")
            if path.is_file() and path.name in ("pyrefly", "pyrefly.exe")
        )
        executable.chmod(executable.stat().st_mode | 0o111)
        environment = os.environ.copy()
        pytest_init = next(runfiles.rglob("pytest/__init__.py"))
        environment["PYTHONPATH"] = str(pytest_init.parent.parent)
        return subprocess.run(
            [str(executable), *sys.argv[1:]],
            cwd=os.environ.get("BUILD_WORKSPACE_DIRECTORY"),
            env=environment,
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
