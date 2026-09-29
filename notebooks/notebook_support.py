# Copyright 2026 PyMOL Copilot contributors.
"""Helpers the deliverable notebook calls, so its own cells stay readable.

The notebook (`pymol_copilot.ipynb`, master plan item 18) shows the real
code of each stage. What it hides here is plumbing: putting the
repository's packages on the path, launching headless PyMOL, running a
`copilot` command synchronously, starting and stopping the server, and
rendering tables. Every number the notebook reports also goes through
`record`, so `tests/notebook/test_notebook_record.py` can recompute it
from the committed evidence and fail if the executed notebook ever
disagrees with it.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: The repository root: this file lives in `notebooks/`.
ROOT = Path(__file__).resolve().parents[1]

#: What `sys.path` needs for the repository's own packages: `src/` for
#: the packages and `tools/winstage` for the module `pmc_sidecar` imports,
#: as Bazel arranges for its own targets.
IMPORT_PATHS = (ROOT / "src", ROOT / "tools" / "winstage")

#: The line that heads the notebook's final record of every number.
RECORD_HEADER = "pmc-notebook-record"

_RECORD: dict[str, Any] = {}


def setup_paths() -> None:
    """Make the repository's packages importable in this kernel."""
    for path in reversed(IMPORT_PATHS):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    os.environ["PYTHONPATH"] = os.pathsep.join(str(p) for p in IMPORT_PATHS)


def record(key: str, value: Any) -> Any:
    """Remember one reported number for the notebook's final record.

    Args:
        key: A stable name, such as `task_success.test_gold.grammar`.
        value: The value as the notebook reports it (JSON-serializable).

    Returns:
        The value, so a cell can record and use it in one expression.
    """
    _RECORD[key] = value
    return value


def print_record() -> None:
    """Print every recorded value as one JSON document, for the test."""
    print(RECORD_HEADER)
    print(json.dumps(_RECORD, indent=1, sort_keys=True))


def markdown_table(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Any:
    """Build a Markdown table the notebook displays.

    Args:
        header: The column titles.
        rows: The rows.

    Returns:
        An IPython `Markdown` object.
    """
    from IPython.display import Markdown

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += [
        "| " + " | ".join(str(cell) for cell in row) + " |" for row in rows
    ]
    return Markdown("\n".join(lines))


def load_json(relative: str) -> Any:
    """Read one committed JSON file.

    Args:
        relative: Its path from the repository root.

    Returns:
        The decoded JSON.
    """
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_jsonl(relative: str) -> list[dict[str, Any]]:
    """Read one committed JSON-lines file.

    Args:
        relative: Its path from the repository root.

    Returns:
        One decoded object per non-empty line.
    """
    text = (ROOT / relative).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def rate(k: int, n: int) -> str:
    """Render a proportion with its Wilson 95% interval.

    Args:
        k: The count.
        n: The denominator.

    Returns:
        `k/n (p%, lo-hi%)`.
    """
    from pmc_data.audit import wilson_interval

    low, high = wilson_interval(k, n)
    return f"{k}/{n} ({100 * k / n:.1f}%, {100 * low:.1f}-{100 * high:.1f}%)"


def launch_pymol() -> Any:
    """Launch headless PyMOL once in this kernel.

    Returns:
        PyMOL's `cmd` module.
    """
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    return cmd


class ConsoleDriver:
    """Run `copilot*` commands through PyMOL's own dispatch, synchronously.

    `cmd.do()` only queues a command on PyMOL's thread. The client
    registers its commands through this object's `extend`, which wraps
    each one to signal when it has finished, so `run` can wait for it.
    The same pattern as `tests/e2e/scenario_support.ConsoleDriver`.
    """

    def __init__(self, cmd: Any, deadline_seconds: float = 900.0) -> None:
        """Wrap PyMOL's `cmd`.

        Args:
            cmd: PyMOL's `cmd` module.
            deadline_seconds: How long one command may take.
        """
        self._cmd = cmd
        self._deadline = deadline_seconds
        self._finished = threading.Event()

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register one command, wrapped to signal completion.

        Args:
            name: The command's name.
            callback: What it runs.
        """

        def synchronized(argument: str = "") -> None:
            try:
                callback(argument)
            finally:
                self._finished.set()

        self._cmd.extend(name, synchronized)

    def __getattr__(self, name: str) -> Any:
        """Forward everything else to PyMOL's `cmd`.

        Args:
            name: The attribute.

        Returns:
            `cmd`'s attribute.
        """
        return getattr(self._cmd, name)

    def run(self, command_line: str) -> float:
        """Dispatch one command line and wait for it to finish.

        Args:
            command_line: What a user would type at PyMOL's prompt.

        Returns:
            Seconds it took.

        Raises:
            TimeoutError: If it did not finish within the deadline.
        """
        self._finished.clear()
        started = time.monotonic()
        self._cmd.do(command_line)
        if not self._finished.wait(self._deadline):
            raise TimeoutError(f"{command_line!r} did not finish")
        return time.monotonic() - started


def start_server(arguments: Sequence[str], handoff: Path) -> subprocess.Popen:
    """Start `pmc_server.main` and wait until it has written its handoff.

    Args:
        arguments: Its command-line flags.
        handoff: Where it writes its port and credential.

    Returns:
        The server process.

    Raises:
        RuntimeError: If it exits or writes no handoff within 10 minutes.
    """
    handoff.unlink(missing_ok=True)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pmc_server.main",
            *arguments,
            "--handoff",
            str(handoff),
        ],
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")},
    )
    deadline = time.monotonic() + 600
    while not handoff.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            process.kill()
            raise RuntimeError("the server did not start")
        time.sleep(0.5)
    return process


def stop_server(process: subprocess.Popen) -> None:
    """Stop the server as Ctrl+C would.

    Args:
        process: The server process.
    """
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()


def package_versions(names: Iterable[str]) -> list[tuple[str, str]]:
    """Read installed package versions.

    Args:
        names: Distribution names.

    Returns:
        Each name with its version, or `not installed`.
    """
    rows = []
    for name in names:
        try:
            rows.append((name, importlib.metadata.version(name)))
        except importlib.metadata.PackageNotFoundError:
            rows.append((name, "not installed"))
    return rows


def package_licence(name: str) -> str:
    """Read a package's declared licence from its metadata.

    Args:
        name: The distribution name.

    Returns:
        Its `License-Expression`, else its `License`, else its licence
        classifiers, else `not declared`.
    """
    metadata = importlib.metadata.metadata(name)
    expression = metadata.get("License-Expression")
    if expression:
        return expression
    declared = metadata.get("License")
    if declared and len(declared) < 80:
        return declared
    classifiers = [
        c.split("::")[-1].strip()
        for c in metadata.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    return ", ".join(classifiers) if classifiers else "not declared"


def host_description() -> dict[str, str]:
    """Describe the machine this kernel runs on.

    Returns:
        The OS release, kernel, architecture and Python.
    """
    release = "unknown"
    os_release = Path("/etc/os-release")
    if os_release.is_file():
        for line in os_release.read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                release = line.split("=", 1)[1].strip('"')
    return {
        "os": release,
        "kernel": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "python": platform.python_version(),
    }
