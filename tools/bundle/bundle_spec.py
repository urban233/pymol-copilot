# Copyright 2026 PyMOL Copilot contributors.
"""What the portable Windows bundle holds, and the files it writes itself.

Master plan item 20 (plans/16-portable-bundle.md). The bundle is one ZIP
that runs the notebook on Windows without any setup: its own Python, its
own Lemonade with the llama.cpp CPU backend, the fine-tuned model, the
tokenizer files the notebook reads, and the repository's code and
evidence. `build_bundle.py` downloads and assembles it on Windows; this
module decides what goes in and writes the launcher, the README and the
manifest, so that all of it is tested without building anything. It
imports only the standard library.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import importlib.metadata
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

#: The folder the ZIP extracts to.
ROOT_NAME = "pymol-copilot"

#: The file a colleague double-clicks.
LAUNCHER_NAME = "Start PyMOL Copilot.bat"

#: The longest path an entry may have inside the ZIP, its root folder
#: included. Windows Explorer cannot extract a path longer than 260
#: characters, so this leaves 100 for the folder the ZIP is extracted to
#: (`C:\Users\<name>\Downloads\pymol-copilot-<commit>-win64\` is about 60).
PATH_BUDGET = 160

#: What the installed packages ship that the bundle never runs and whose
#: paths are among the longest: JupyterLab's UI-testing helper (Galata)
#: and its own tests. Paths from the bundle's folder.
PRUNED = (
    "python/Lib/site-packages/jupyterlab/galata",
    "python/Lib/site-packages/jupyterlab/tests",
)

#: Where the pinned downloads are recorded, from the repository root.
PINS = "configs/bundle/pins.json"

#: What the notebook and its check need from the repository, as `git
#: archive` path specs: the code, the committed evidence it reads, the
#: configs it hashes, and the record test `check_bundle.py` runs.
CONTENTS = (
    "LICENSE",
    "configs",
    "docs/bundle.md",
    "docs/dataset",
    "docs/evaluation",
    "docs/training",
    "notebooks",
    "src",
    "tests/notebook",
    "tools/bundle",
    "tools/winstage",
)

#: Left out of the contents: the notebook's own environment test asserts
#: the Linux training environment, not the bundle's.
EXCLUDED = ("notebooks/tests",)

#: The variables that name folders under `state`, which the launcher
#: creates before anything runs: IPython falls back to a temporary folder
#: when its own does not exist yet.
STATE_VARIABLES = ("MPLCONFIGDIR", "IPYTHONDIR", "JUPYTER_RUNTIME_DIR")

#: Environment variables the launcher clears, so that nothing installed
#: on the colleague's machine reaches the bundle's Python.
CLEARED = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")

#: The JupyterLab settings the bundle overrides: no news feed and no
#: update check, both of which would reach the network.
JUPYTERLAB_OVERRIDES = {
    "@jupyterlab/apputils-extension:notification": {
        "checkForUpdates": False,
        "fetchNews": "false",
    },
}


def load_pins(repository: Path) -> dict[str, Any]:
    """Read the pinned downloads.

    Args:
        repository: The repository root.

    Returns:
        The pins.
    """
    return json.loads((repository / PINS).read_text(encoding="utf-8"))


def archive_pathspecs() -> list[str]:
    """Name what `git archive` puts into the bundle's `repo` folder.

    Returns:
        The path specs, exclusions last.
    """
    return [*CONTENTS, *(f":(exclude){path}" for path in EXCLUDED)]


def environment(root: str, *, demo: bool = True) -> dict[str, str]:
    """Write down the environment the launcher gives the notebook.

    Everything the notebook, Jupyter, the tokenizer and matplotlib write
    stays inside the bundle's `state` folder, and the tokenizer is read
    from the bundle offline.

    Args:
        root: How the launcher spells the bundle's folder.
        demo: Whether the live demo runs (the bundle holds the model).

    Returns:
        Each variable and its value, cleared ones empty.
    """
    state = f"{root}\\state"
    return {
        **dict.fromkeys(CLEARED, ""),
        "PYTHONUTF8": "1",
        "PYTHONNOUSERSITE": "1",
        "HF_HOME": f"{root}\\hf",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_VERBOSITY": "error",
        "MPLCONFIGDIR": f"{state}\\matplotlib",
        "JUPYTER_CONFIG_DIR": f"{state}\\jupyter\\config",
        "JUPYTER_DATA_DIR": f"{state}\\jupyter\\data",
        "JUPYTER_RUNTIME_DIR": f"{state}\\jupyter\\runtime",
        "IPYTHONDIR": f"{state}\\ipython",
        "PMC_NOTEBOOK_DEMO": "1" if demo else "0",
        "PMC_BUNDLE_ROOT": root,
    }


def launcher_text(*, demo: bool = True) -> str:
    """Write the launcher a colleague double-clicks.

    A batch file, because it runs on any Windows without a policy change.
    Every `set` is quoted and nothing is grouped in parentheses, so a
    folder such as `pymol-copilot (1)` (Explorer's name for a second
    copy) works. Windows line endings, as `cmd` expects.

    Args:
        demo: Whether the live demo runs (the bundle holds the model).

    Returns:
        The batch file's text.
    """
    lines = [
        "@echo off",
        "rem PyMOL Copilot, the portable Windows bundle. Built with Llama.",
        "rem Starts JupyterLab on the notebook; close this window to stop.",
        "setlocal",
        'cd /d "%~dp0"',
        'set "PMC_ROOT=%~dp0"',
        'set "PMC_ROOT=%PMC_ROOT:~0,-1%"',
    ]
    variables = environment("%PMC_ROOT%", demo=demo)
    lines += [f'set "{name}={value}"' for name, value in variables.items()]
    lines += [
        f'if not exist "{variables[name]}" mkdir "{variables[name]}"'
        for name in STATE_VARIABLES
    ]
    lines += [
        "echo PyMOL Copilot - Built with Llama",
        "echo.",
        "echo JupyterLab opens in your browser with the notebook.",
        "echo Run it with Run, Run All Cells. Section 9 asks the model on this",
        "echo computer's CPU: each answer takes up to about a minute.",
        "echo.",
        "echo Keep this window open while you work, and close it to stop.",
        "echo Clicking into it pauses JupyterLab; press Esc to continue.",
        "echo.",
        '"%PMC_ROOT%\\python\\python.exe" -m jupyterlab'
        ' --ServerApp.ip=127.0.0.1 --ServerApp.root_dir="%PMC_ROOT%\\repo"'
        ' "%PMC_ROOT%\\repo\\notebooks\\pymol_copilot.ipynb"',
        "endlocal",
    ]
    return "\r\n".join(lines) + "\r\n"


def readme_text(commit: str) -> str:
    """Write the README beside the launcher.

    Args:
        commit: The commit the bundle was built from.

    Returns:
        The README's text, with Windows line endings.
    """
    text = f"""PyMOL Copilot - portable Windows bundle
Built with Llama.

This folder runs the PyMOL Copilot notebook on Windows without installing
anything: its own Python, JupyterLab, PyMOL, the fine-tuned model and the
engine that serves it on this computer's CPU. Nothing is sent to the
internet. Built from commit {commit}.

To start
  1. Before extracting the ZIP: right-click it, Properties, tick
     "Unblock" if it is shown, OK.
  2. Extract it into a folder of your own, for example Downloads or
     C:\\pmc. Not into a folder OneDrive synchronises.
     Explorer's "Extract All" works but is slow for this many files;
     faster, in a terminal:  tar -xf pymol-copilot-...-win64.zip
  3. Double-click "{LAUNCHER_NAME}". JupyterLab opens in your
     browser with the notebook.
  4. Run, Run All Cells. Section 9 asks the model: each answer takes
     from tens of seconds to about a minute on a CPU.
  To stop, close the browser tab and the black window.

If something goes wrong
  - "Windows protected your PC": click "More info", then "Run anyway".
    The files are not signed.
  - Nothing happens in the black window: a click into it pauses it;
    press Esc.
  - The notebook stops at section 9 with "not plain ASCII": extract
    the bundle to C:\\pmc instead.
  - Needs Windows 10 or 11 (64-bit), about 4 GB of free memory and
    3 GB of disk.

To remove it, delete the folder. It writes nowhere else, except
temporary files under %TEMP%.

Licences
  The licence of every component is in the LICENSES folder. The model is
  derived from Llama 3.2 and is distributed under the Llama 3.2
  Community License Agreement (LICENSES\\Llama-3.2-LICENSE.txt) and its
  Acceptable Use Policy (LICENSES\\Llama-3.2-USE_POLICY.md).
"""
    return text.replace("\n", "\r\n")


def manifest(
    commit: str, pins: dict[str, Any], *, model: bool, lock_sha256: str
) -> dict[str, Any]:
    """Describe a bundle: where it came from and what it holds.

    `notebook_support` reads the model's SHA-256 from it and refuses any
    other file.

    Args:
        commit: The commit it was built from.
        pins: The pinned downloads.
        model: Whether it holds the model.
        lock_sha256: The SHA-256 of `requirements-bundle.txt`.

    Returns:
        The content of `bundle.json`.
    """
    return {
        "commit": commit,
        "lemonade": {
            key: pins["lemonade"][key]
            for key in (
                "version",
                "sha256",
                "llamacpp_backend",
                "llamacpp_build",
            )
        },
        "model": pins["model"] if model else None,
        "python": {key: pins["python"][key] for key in ("version", "sha256")},
        "requirements_sha256": lock_sha256,
        "tokenizer": {
            key: pins["tokenizer"][key] for key in ("repository", "revision")
        },
    }


def zip_name(commit: str) -> str:
    """Name the ZIP.

    Args:
        commit: The commit it was built from.

    Returns:
        The file name.
    """
    return f"{ROOT_NAME}-{commit[:12]}-win64.zip"


def over_budget(entries: Iterable[str], budget: int = PATH_BUDGET) -> list[str]:
    """Find the ZIP entries whose paths are too long to extract safely.

    Args:
        entries: The entries' paths inside the ZIP, root folder included.
        budget: The longest path allowed.

    Returns:
        The entries that exceed it.
    """
    return [entry for entry in entries if len(entry) > budget]


def zip_entries(
    entries: Iterable[str], budget: int = PATH_BUDGET
) -> tuple[list[str], list[str]]:
    """Choose what goes into the ZIP, and what is too long to.

    A precompiled `.pyc` adds `__pycache__` and the interpreter's tag to
    its module's path. One too long to extract is left out: Python then
    runs that module from its source, which is always there. Any other
    entry that is too long fails the build.

    Args:
        entries: The bundle's files, as paths inside the ZIP.
        budget: The longest path allowed.

    Returns:
        The entries to pack, and those too long that cannot be left out.
    """
    packed: list[str] = []
    too_long: list[str] = []
    for entry in entries:
        if len(entry) <= budget:
            packed.append(entry)
        elif not entry.endswith(".pyc"):
            too_long.append(entry)
    return packed, too_long


def declared_licence(metadata: Any) -> str:
    """Read the licence a Python package's metadata declares.

    Args:
        metadata: The package's metadata (`importlib.metadata`'s, or a
            mapping).

    Returns:
        Its `License-Expression`, else a one-line `License`, else its
        licence classifiers, else a pointer to its `.dist-info` folder.
    """
    expression = metadata.get("License-Expression")
    if expression:
        return expression
    declared = (metadata.get("License") or "").strip()
    if declared and "\n" not in declared and len(declared) < 80:
        return declared
    classifiers = [
        classifier.split("::")[-1].strip()
        for classifier in getattr(metadata, "get_all", lambda _name: [])(
            "Classifier"
        )
        or []
        if classifier.startswith("License ::")
    ]
    return ", ".join(classifiers) or "see its .dist-info folder"


def package_list(packages: Iterable[tuple[str, str, str]]) -> str:
    """Write `LICENSES\\Python-packages.txt`.

    Args:
        packages: Each package's name, version and declared licence.

    Returns:
        The file's text.
    """
    lines = [
        "The Python packages in python\\Lib\\site-packages, with the licence",
        "each declares. Their full licence texts are in each package's",
        ".dist-info folder.",
        "",
    ]
    lines += [
        f"{name} {version}: {licence}"
        for name, version, licence in sorted(
            packages, key=lambda row: row[0].lower()
        )
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    """Write the package list for the Python running this.

    The build runs it with the bundle's own Python:
    `python.exe bundle_spec.py packages <file>`.

    Args:
        argv: `packages` and the file to write.

    Returns:
        The exit code.
    """
    if len(argv) != 2 or argv[0] != "packages":
        print("usage: bundle_spec.py packages <file>", file=sys.stderr)
        return 2
    packages = [
        (
            distribution.metadata["Name"],
            distribution.version,
            declared_licence(distribution.metadata),
        )
        for distribution in importlib.metadata.distributions()
    ]
    Path(argv[1]).write_text(package_list(packages), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
