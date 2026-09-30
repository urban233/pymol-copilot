# Copyright 2026 PyMOL Copilot contributors.
"""The notebook's kernel can run every stage of the project in one process.

The notebook (master plan item 18) imports the runtime packages, the
dataset and evaluation code, the training code and PyMOL itself. They
normally live in two environments: Bazel's Python 3.13 closure and the
Python 3.12 training venv. `.venv-notebook` is the training lock plus
the runtime's pins, and this proves the union works.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import importlib
import importlib.metadata
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _pins(lock: Path) -> dict[str, str]:
    """Read every `name==version` pin out of a lock.

    Args:
        lock: The lock file.

    Returns:
        The locked version of each package, by lower-cased name.
    """
    pins: dict[str, str] = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^ \\]+)", line)
        if match:
            pins[match.group(1).lower()] = match.group(2)
    return pins


def test_python_is_3_12() -> None:
    """The notebook kernel is the training environment's Python."""
    assert sys.version_info[:2] == (3, 12)


def test_the_training_stack_is_the_training_lock() -> None:
    """Every package the training lock pins is pinned identically here."""
    train = _pins(ROOT / "requirements-train.txt")
    notebook = _pins(ROOT / "requirements-notebook.txt")
    assert {k: v for k, v in train.items() if notebook.get(k) != v} == {}


def test_the_runtime_pins_are_the_runtime_lock() -> None:
    """Shared runtime packages match requirements_lock.txt, except numpy."""
    runtime = _pins(ROOT / "requirements_lock.txt")
    notebook = _pins(ROOT / "requirements-notebook.txt")
    drift = {
        name
        for name, version in runtime.items()
        if name in notebook and notebook[name] != version
    }
    assert drift <= {"numpy"}


@pytest.mark.parametrize(
    "package",
    ["torch", "unsloth", "pymol-open-source-whl", "langgraph", "nbclient"],
)
def test_installed_versions_match_the_lock(package: str) -> None:
    """The venv holds exactly the locked versions."""
    locked = _pins(ROOT / "requirements-notebook.txt")[package]
    assert importlib.metadata.version(package).split("+")[0] == locked


@pytest.mark.parametrize(
    "module",
    [
        "pmc_core.snapshot",
        "pmc_data.oracle",
        "pmc_agent.graph",
        "pmc_eval.compare",
        "pmc_server.main",
        "pmc_client.bootstrap",
        "pmc_train.examples",
    ],
)
def test_every_package_imports(module: str) -> None:
    """The runtime, data, evaluation and training code all import here."""
    importlib.import_module(module)


def test_headless_pymol_runs_in_a_notebook_kernel() -> None:
    """PyMOL launches headless in a kernel, and later output still shows.

    In a plain process PyMOL's launch takes over file descriptor 1, so a
    later `print` is lost. A notebook kernel prints through its own
    stream instead; this runs the launch and a later print in two cells
    of a real kernel, as the notebook does, and checks the print shows.
    """
    import nbformat
    from nbclient import NotebookClient

    notebook = nbformat.v4.new_notebook()
    notebook.cells = [
        nbformat.v4.new_code_cell(
            "import pymol\n"
            "from pymol import cmd\n"
            "pymol.finish_launching(['pymol', '-qc'])\n"
            "cmd.fragment('ala')"
        ),
        nbformat.v4.new_code_cell("print('atoms', cmd.count_atoms('all'))"),
    ]
    NotebookClient(notebook, timeout=120, kernel_name="python3").execute()
    text = "".join(
        output.get("text", "") for output in notebook.cells[1].outputs
    )
    assert text.startswith("atoms ")
    assert int(text.split()[1]) > 0
