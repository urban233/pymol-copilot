# Copyright 2026 PyMOL Copilot contributors.
"""The training environment is the one the lock describes.

Training runs under Python 3.12 from `requirements-train.txt`, outside
Bazel. The code it shares with the runtime -- `pmc_core` and the
dataset reader in `pmc_data` -- has to import there too, and importing
`pmc_train` itself must not pull in Unsloth, which needs a GPU.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import importlib
import importlib.metadata
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / "requirements-train.txt"


def _pins() -> dict[str, str]:
    """Read every `name==version` pin out of the training lock.

    Returns:
        The locked version of each package, by lower-cased name.
    """
    pins: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^ \\]+)", line)
        if match:
            pins[match.group(1).lower()] = match.group(2)
    return pins


def test_python_is_3_12() -> None:
    """The training environment targets Python 3.12."""
    assert sys.version_info[:2] == (3, 12)


@pytest.mark.parametrize(
    "package",
    ["torch", "transformers", "peft", "trl", "unsloth", "gguf", "pytest"],
)
def test_installed_versions_match_the_lock(package: str) -> None:
    """Every training package is installed at its locked version."""
    installed = importlib.metadata.version(package)
    assert installed.split("+")[0] == _pins()[package]


@pytest.mark.parametrize(
    "module",
    ["pmc_core.prompt", "pmc_data.sample", "pmc_data.manifest"],
)
def test_shared_code_imports_under_3_12(module: str) -> None:
    """The runtime code training reuses is 3.12-compatible."""
    importlib.import_module(module)


def test_importing_pmc_train_does_not_import_unsloth() -> None:
    """Unsloth is imported lazily, only by a GPU training run."""
    probe = (
        "import sys, pmc_train, pmc_train.config;"
        "assert 'unsloth' not in sys.modules, 'unsloth imported'"
    )
    subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
    )
