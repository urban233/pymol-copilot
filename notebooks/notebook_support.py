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

import atexit
import hashlib
import importlib.metadata
import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Sequence
from dataclasses import dataclass
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

#: Set by the portable Windows bundle's launcher (master plan item 20) to
#: the folder the bundle was extracted to; the bundle then starts its own
#: Lemonade on the CPU.
BUNDLE_VARIABLE = "PMC_BUNDLE_ROOT"

#: Outside the bundle, the backend of the Lemonade already running.
BACKEND_VARIABLE = "PMC_NOTEBOOK_BACKEND"

#: Where the Docker engine (`configs/evaluation/engine`) serves the
#: fine-tuned model: `results/` is mounted at `/models`.
DOCKER_CHECKPOINT = (
    "/models/train-e6c6c4dd8f6caaf9/export/"
    "Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M.gguf"
)

#: The evaluated CPU engine, whose llama.cpp arguments (the chat
#: template's date) the bundle's engine must repeat.
CPU_CONFIG = "configs/evaluation/finetuned_cpu.json"

_RECORD: dict[str, Any] = {}
#: What this kernel started once and reuses: PyMOL's `cmd` ("pymol"), the
#: bundle's engine ("engine") and the job object its children run in
#: ("job").
_STATE: dict[str, Any] = {}


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

    PyMOL launches once per process, so running the notebook's cells
    again returns the PyMOL already running. On Windows, `winstage`
    first stages PyMOL's DLLs to a short path when the folder the
    bundle was extracted to makes theirs too long to load.

    Returns:
        PyMOL's `cmd` module.
    """
    if "pymol" not in _STATE:
        import winstage  # pyrefly: ignore.

        winstage.ensure_importable()
        import pymol  # pyrefly: ignore.
        from pymol import cmd  # pyrefly: ignore.

        pymol.finish_launching(["pymol", "-qc"])
        _STATE["pymol"] = cmd
    return _STATE["pymol"]


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
            # The event of the `run` this call belongs to: a command that
            # outlived its deadline must not release a later `run`.
            finished = self._finished
            try:
                callback(argument)
            finally:
                finished.set()

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
        finished = self._finished = threading.Event()
        started = time.monotonic()
        self._cmd.do(command_line)
        if not finished.wait(self._deadline):
            raise TimeoutError(f"{command_line!r} did not finish")
        return time.monotonic() - started


def start_server(arguments: Sequence[str], handoff: Path) -> subprocess.Popen:
    """Start `pmc_server.main` and wait until it has written its handoff.

    Args:
        arguments: Its command-line flags.
        handoff: Where it writes its port and credential; its log is
            written beside it, as `server.log`.

    Returns:
        The server process.

    Raises:
        RuntimeError: If it exits or writes no handoff within 10 minutes.
    """
    handoff.unlink(missing_ok=True)
    # The server's own log (its startup line, LangGraph's notices) goes to
    # a file beside the handoff, not into the notebook's output.
    log = (handoff.parent / "server.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pmc_server.main",
            *arguments,
            "--handoff",
            str(handoff),
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    if bundle_root() is not None:
        _hold_in_job(process)
    # The child holds its own copy of the file; the notebook needs none.
    log.close()
    deadline = time.monotonic() + 600
    while not handoff.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            process.kill()
            process.wait()
            raise RuntimeError(
                f"the server did not start; see {handoff.parent / 'server.log'}"
            )
        time.sleep(0.5)
    return process


def stop_server(process: subprocess.Popen) -> None:
    """Stop the server as Ctrl+C would (on Windows, end it outright).

    Args:
        process: The server process.
    """
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def plan_id(preview: str) -> str | None:
    """Read the plan id a `copilot` preview offers to apply.

    Args:
        preview: The preview's text.

    Returns:
        The plan id, or None when the preview offers no plan (the model
        abstained, or the request failed).
    """
    first = preview.splitlines()[0] if preview else ""
    if not first.startswith("copilot plan "):
        return None
    return first.removeprefix("copilot plan ").split(" ")[0]


# The engine section 9 serves the model from. On the development machine
# it is the Docker engine, already running; in the portable Windows
# bundle (master plan item 20) the notebook starts its own embedded
# Lemonade on the CPU and stops it again.


@dataclass(frozen=True)
class Engine:
    """The Lemonade engine the server is pointed at.

    Attributes:
        flags: The server's engine flags: the checkpoint, the backend, and
            where Lemonade listens when that is not the default.
        process: The Lemonade process this notebook started, if any.
    """

    flags: tuple[str, ...]
    process: subprocess.Popen | None = None


def bundle_root() -> Path | None:
    """Find the portable bundle this kernel runs from.

    Returns:
        The folder the bundle was extracted to, or None outside it.
    """
    value = os.environ.get(BUNDLE_VARIABLE)
    return Path(value) if value else None


def start_engine(model_name: str, context_size: int) -> Engine:
    """Get the engine that serves the fine-tuned model.

    Outside the bundle the engine is the Docker one, already serving the
    model (`configs/evaluation/engine`), on the GPU unless
    `PMC_NOTEBOOK_BACKEND` names another backend. In the bundle, this
    verifies the model's SHA-256, starts the embedded Lemonade on the
    CPU, loads the model, and refuses it unless llama.cpp was launched
    with the evaluated arguments. A second call returns the engine the
    first one started while it still runs.

    Args:
        model_name: The model's name in Lemonade's catalog.
        context_size: The context size to load it with.

    Returns:
        The engine.
    """
    root = bundle_root()
    if root is None:
        backend = os.environ.get(BACKEND_VARIABLE, "cuda")
        return Engine(("--checkpoint", DOCKER_CHECKPOINT, "--backend", backend))
    running = _STATE.get("engine")
    process = running.process if running is not None else None
    if process is not None and process.poll() is None:
        return running
    _STATE["engine"] = _start_bundled_engine(root, model_name, context_size)
    return _STATE["engine"]


def stop_engine(engine: Engine) -> None:
    """Stop an engine this notebook started, with its llama.cpp server.

    Args:
        engine: The engine `start_engine` returned.
    """
    process = engine.process
    if process is None:
        return
    if process.poll() is None:
        if sys.platform == "win32":
            # The whole tree: Lemonade and the llama-server it launched.
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    if _STATE.get("engine") is engine:
        del _STATE["engine"]


def _stop_current_engine() -> None:
    """Stop the engine still running when the kernel exits."""
    if "engine" in _STATE:
        stop_engine(_STATE["engine"])


atexit.register(_stop_current_engine)


def engine_config(
    *, models_dir: str, log_file: str, llamacpp_args: str
) -> dict[str, Any]:
    """Write down the embedded Lemonade's settings for one start.

    Only these keys override Lemonade's own defaults. It serves only the
    local model, on the CPU, fetches nothing, and does not announce
    itself on the network.

    Args:
        models_dir: The folder holding the model (an ASCII path).
        log_file: Where Lemonade logs (an ASCII path).
        llamacpp_args: The evaluated llama.cpp arguments.

    Returns:
        The content of Lemonade's `config.json`.
    """
    return {
        "auto_check_model_updates": False,
        "broadcast": False,
        "extra_models_dir": models_dir,
        "llamacpp": {
            "args": llamacpp_args,
            "backend": "cpu",
            "prefer_system": False,
        },
        "log_file": log_file,
        "no_fetch_executables": True,
        "offline": True,
    }


def launched_with(command: Sequence[str], llamacpp_args: str) -> bool:
    """Check that llama.cpp was launched with the evaluated arguments.

    The arguments pin the chat template's date. Were they mangled on
    the way (quoting differs between shells), the template would print
    today's date and the prompt would no longer be the one evaluated.

    Args:
        command: The loaded model's `launch_command` from Lemonade.
        llamacpp_args: The evaluated arguments, as one string.

    Returns:
        Whether the command holds them, in order, as separate arguments.
    """
    expected = shlex.split(llamacpp_args)
    return any(
        list(command[start : start + len(expected)]) == expected
        for start in range(len(command) - len(expected) + 1)
    )


def ascii_path(path: Path, short: Callable[[Path], str | None]) -> str | None:
    """Spell a path in ASCII for the embedded Lemonade.

    Lemonade 11.9.0 exits without a message when any of its paths holds
    a character outside ASCII (docs/bundle.md), as a user name such as
    `Jürgen` puts in `Downloads`. Windows' 8.3 short names are ASCII.

    Args:
        path: The path.
        short: Gives a path's 8.3 short form, or None.

    Returns:
        The path itself when it is ASCII, else its short form when that
        is, else None.
    """
    text = str(path)
    if text.isascii():
        return text
    shortened = short(path)
    if shortened is not None and shortened.isascii():
        return shortened
    return None


def _short_path(path: Path) -> str | None:
    """Ask Windows for a path's 8.3 short form.

    Args:
        path: An existing path.

    Returns:
        The short form, or None where the volume makes no short names.
    """
    if sys.platform != "win32":
        return None
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if 0 < length < len(buffer) else None


def _engine_folders(root: Path, gguf: Path, commit: str) -> tuple[str, str]:
    """Find ASCII paths for the embedded Lemonade and the model's folder.

    Where the bundle's own paths have no ASCII spelling, Lemonade and the
    model are staged under the system drive, as `winstage` stages PyMOL;
    the model is hard-linked there, not copied, when the volume allows.

    Args:
        root: The bundle's folder.
        gguf: The verified model file.
        commit: The bundle's commit, which names the staging folder.

    Returns:
        The ASCII paths of the Lemonade folder and of the model's folder.

    Raises:
        RuntimeError: If no ASCII path can be found or made.
    """
    lemonade = ascii_path(root / "lemonade", _short_path)
    models = ascii_path(gguf.parent, _short_path)
    if lemonade is not None and models is not None:
        return lemonade, models
    drive = Path(os.environ.get("SYSTEMDRIVE", "C:") + os.sep)
    stage = drive / f"pmc-engine-{commit[:12]}"
    if not (stage / "lemonade" / "lemond.exe").is_file():
        shutil.copytree(
            root / "lemonade",
            stage / "lemonade",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("config", "*.log"),
        )
    staged_model = stage / "model" / gguf.name
    if not staged_model.is_file():
        staged_model.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(gguf, staged_model)
        except OSError:
            shutil.copy2(gguf, staged_model)
    lemonade = ascii_path(stage / "lemonade", _short_path)
    models = ascii_path(staged_model.parent, _short_path)
    if lemonade is None or models is None:
        raise RuntimeError(
            "Lemonade cannot run from this folder, whose path is not plain "
            "ASCII; extract the bundle to a folder such as C:\\pmc instead."
        )
    return lemonade, models


def _hold_in_job(process: subprocess.Popen) -> None:
    """Make a child end when this kernel ends, however it ends.

    The children join one Windows job object that the kernel holds open
    and that kills everything in it when it is closed, so a restarted or
    crashed kernel leaves no Lemonade, llama-server or server behind.

    Args:
        process: The child.
    """
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _Basic),
            ("IoInfo", ctypes.c_uint64 * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    if "job" not in _STATE:
        job = kernel32.CreateJobObjectW(None, None)
        info = _Extended()
        # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        info.BasicLimitInformation.LimitFlags = 0x2000
        # JobObjectExtendedLimitInformation
        kernel32.SetInformationJobObject(
            wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info)
        )
        _STATE["job"] = job
    handle = getattr(process, "_handle", None)
    if handle is not None:
        kernel32.AssignProcessToJobObject(
            wintypes.HANDLE(_STATE["job"]), wintypes.HANDLE(int(handle))
        )


def _sha256(path: Path) -> str:
    """Hash a file.

    Args:
        path: The file.

    Returns:
        Its SHA-256, in hex.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _free_port() -> int:
    """Pick a loopback port nothing listens on.

    Returns:
        The port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _http(url: str, body: dict[str, Any] | None = None) -> Any:
    """Call the embedded Lemonade's API.

    Args:
        url: The endpoint.
        body: The JSON to post, or None to get.

    Returns:
        The decoded JSON reply.
    """
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=600) as reply:
        return json.loads(reply.read().decode("utf-8"))


def _start_bundled_engine(
    root: Path, model_name: str, context_size: int
) -> Engine:
    """Start the bundle's Lemonade with the verified model loaded.

    Args:
        root: The bundle's folder.
        model_name: The model's name in Lemonade's catalog.
        context_size: The context size to load it with.

    Returns:
        The engine, the server flags that point at it, and its process.

    Raises:
        RuntimeError: If the model is not the bundle's, or Lemonade does
            not start, or it launches llama.cpp with other arguments.
    """
    manifest = json.loads((root / "bundle.json").read_text(encoding="utf-8"))
    gguf = root / "model" / f"{model_name}.gguf"
    if _sha256(gguf) != manifest["model"]["sha256"]:
        raise RuntimeError(f"{gguf} is not the bundle's model")
    llamacpp_args = load_json(CPU_CONFIG)["engine_provenance"]["llamacpp_args"]
    lemonade, models = _engine_folders(root, gguf, manifest["commit"])
    config_dir = Path(lemonade) / "config"
    config_dir.mkdir(exist_ok=True)
    # Written fresh for the folder the bundle was extracted to; Lemonade
    # rescans its models folder only when the setting changes.
    (config_dir / "config.json").write_text(
        json.dumps(
            engine_config(
                models_dir=models,
                log_file=str(Path(lemonade) / "lemonade.log"),
                llamacpp_args=llamacpp_args,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = subprocess.Popen(
        [
            str(Path(lemonade) / "lemond.exe"),
            str(Path(lemonade) / "cache"),
            str(config_dir),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-broadcast",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _hold_in_job(process)
    engine = Engine(
        (
            "--backend",
            "cpu",
            "--lemonade-base-url",
            f"http://127.0.0.1:{port}",
        ),
        process,
    )
    base = f"http://127.0.0.1:{port}/api/v1"
    try:
        deadline = time.monotonic() + 120
        while True:
            if process.poll() is not None:
                raise RuntimeError(
                    f"Lemonade exited with code {process.returncode}; see "
                    f"{Path(lemonade) / 'lemonade.log'}"
                )
            try:
                if _http(f"{base}/health").get("status") == "ok":
                    break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("Lemonade did not become healthy in 120 s")
            time.sleep(0.5)
        # The file Lemonade serves is the verified one, or its staged link
        # or copy.
        served = Path(models) / gguf.name
        checkpoint = _http(f"{base}/models/{model_name}")["checkpoint"]
        if not os.path.samefile(checkpoint, served):
            raise RuntimeError(f"Lemonade found {checkpoint}, not {served}")
        _http(
            f"{base}/load",
            {
                "model_name": model_name,
                "llamacpp_backend": "cpu",
                "ctx_size": context_size,
            },
        )
        loaded = [
            model
            for model in _http(f"{base}/health").get("all_models_loaded", [])
            if model.get("model_name") == model_name
        ]
        command = loaded[0].get("launch_command", []) if loaded else []
        if not launched_with(command, llamacpp_args):
            raise RuntimeError(
                f"llama.cpp was not launched with {llamacpp_args}: {command}"
            )
    except BaseException:
        stop_engine(engine)
        raise
    return Engine(("--checkpoint", checkpoint, *engine.flags), process)


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
        classifiers, else `not declared`; `not installed` when it is not
        in this environment (the bundle has no training stack).
    """
    try:
        metadata = importlib.metadata.metadata(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"
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
    else:
        # Windows and macOS have no /etc/os-release.
        release = platform.platform()
    return {
        "os": release,
        "kernel": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "python": platform.python_version(),
    }
