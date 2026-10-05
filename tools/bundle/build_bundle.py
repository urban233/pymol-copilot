# Copyright 2026 PyMOL Copilot contributors.
"""Build the portable Windows bundle of the notebook, on Windows.

    uv run --python 3.13 tools\\bundle\\build_bundle.py ^
        --model <the fine-tuned GGUF> --out C:\\pmc-dist

Master plan item 20 (plans/16-portable-bundle.md, docs/bundle.md). It
must run on Windows: it installs Windows wheels into a Windows Python and
lets Lemonade's own CLI install its llama.cpp backend. It needs `git`
and `uv` on the PATH and the network, and builds from the committed
tree only. Every download is pinned in `configs/bundle/pins.json` and
checked against its SHA-256. `--no-model` builds the bundle without the
model, for CI: its notebook runs with the live demo off.

What goes in and the files the bundle writes itself are decided in
`bundle_spec.py`; this script only fetches and assembles them.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import datetime
import hashlib
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bundle_spec

REPOSITORY = Path(__file__).resolve().parents[2]

#: Where Lemonade's CPU backend lives inside the bundle.
BACKEND = Path("lemonade", "cache", "bin", "llamacpp", "cpu")


def _run(*command: str | Path, **options: Any) -> str:
    """Run a command, failing the build if it fails.

    Args:
        *command: The command and its arguments.
        **options: Passed to `subprocess.run`.

    Returns:
        Its standard output.
    """
    print("+", " ".join(str(part) for part in command), flush=True)
    result = subprocess.run(
        [str(part) for part in command],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        **options,
    )
    return result.stdout


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


def _download(url: str, sha256: str, cache: Path) -> Path:
    """Fetch a pinned file once, and check it.

    Args:
        url: Where it is published.
        sha256: Its pinned SHA-256.
        cache: Where downloads are kept between builds.

    Returns:
        The checked file.

    Raises:
        RuntimeError: If the file is not the pinned one.
    """
    target = cache / sha256
    if not target.is_file() or _sha256(target) != sha256:
        cache.mkdir(parents=True, exist_ok=True)
        print("download", url, flush=True)
        partial = target.with_suffix(".partial")
        with (
            urllib.request.urlopen(url, timeout=300) as reply,
            partial.open("wb") as handle,
        ):
            shutil.copyfileobj(reply, handle)
        if _sha256(partial) != sha256:
            partial.unlink()
            raise RuntimeError(f"{url} is not the pinned file {sha256}")
        partial.replace(target)
    return target


def _remove(path: Path) -> None:
    """Delete a previous build's folder, read-only files included.

    Args:
        path: The folder.
    """

    def writable(function: Any, failed: str, _info: Any) -> None:
        os.chmod(failed, stat.S_IWRITE)
        function(failed)

    if path.exists():
        shutil.rmtree(path, onexc=writable)


def _free_port() -> int:
    """Pick a loopback port nothing listens on.

    Returns:
        The port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _add_repository(stage: Path, work: Path) -> None:
    """Put the committed code and evidence into `repo`.

    `git archive` writes the committed bytes, so the files whose hashes
    the evaluation checks keep their line endings.

    Args:
        stage: The bundle's folder.
        work: The build's scratch folder.
    """
    archive = work / "repo.tar"
    _run(
        "git",
        "-C",
        REPOSITORY,
        "-c",
        "core.autocrlf=false",
        "archive",
        "--format=tar",
        "-o",
        archive,
        "HEAD",
        "--",
        *bundle_spec.archive_pathspecs(),
    )
    with tarfile.open(archive) as tar:
        tar.extractall(stage / "repo", filter="data")


def _add_python(stage: Path, pins: dict[str, Any], cache: Path) -> Path:
    """Install the bundle's Python and its locked packages.

    Args:
        stage: The bundle's folder.
        pins: The pinned downloads.
        cache: Where downloads are kept.

    Returns:
        The bundle's `python.exe`.
    """
    archive = _download(pins["python"]["url"], pins["python"]["sha256"], cache)
    with tarfile.open(archive) as tar:
        # The archive's single top folder is `python`.
        tar.extractall(stage, filter="data")
    python = stage / "python" / "python.exe"
    _run(
        "uv",
        "pip",
        "install",
        "--python",
        python,
        "--break-system-packages",
        "--require-hashes",
        "--only-binary",
        ":all:",
        "--requirement",
        REPOSITORY / "requirements-bundle.txt",
    )
    for pruned in bundle_spec.PRUNED:
        _remove(stage / pruned)
    settings = stage / "python" / "share" / "jupyter" / "lab" / "settings"
    settings.mkdir(parents=True, exist_ok=True)
    (settings / "overrides.json").write_text(
        json.dumps(bundle_spec.JUPYTERLAB_OVERRIDES, indent=2), encoding="utf-8"
    )
    return python


def _add_lemonade(
    stage: Path, pins: dict[str, Any], work: Path, cache: Path
) -> None:
    """Install embedded Lemonade with its llama.cpp CPU backend.

    Lemonade's own CLI installs the backend its `backend_versions.json`
    pins, into the cache folder the bundle hands it at run time. The
    Visual C++ runtime that llama.cpp needs and does not ship is copied
    beside it, from packages already in the bundle: CPython's own
    `vcruntime140*.dll`, and Microsoft's `msvcp140.dll` that numpy's
    wheel vendors under a hashed name (docs/bundle.md).

    Args:
        stage: The bundle's folder.
        pins: The pinned downloads.
        work: The build's scratch folder.
        cache: Where downloads are kept.

    Raises:
        RuntimeError: If the backend is not the pinned llama.cpp build.
    """
    lemonade = pins["lemonade"]
    archive = _download(lemonade["url"], lemonade["sha256"], cache)
    unpacked = work / "lemonade"
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(unpacked)
    shutil.move(unpacked / lemonade["top_folder"], stage / "lemonade")
    port = _free_port()
    folder = stage / "lemonade"
    server = subprocess.Popen(
        [
            str(folder / "lemond.exe"),
            str(folder / "cache"),
            str(work / "lemonade-config"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-broadcast",
            "--log-file",
            "disabled",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/v1/health", timeout=5
                ):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        _run(
            folder / "lemonade.exe",
            "--port",
            str(port),
            "backends",
            "install",
            f"llamacpp:{lemonade['llamacpp_backend']}",
        )
    finally:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(server.pid)],
            capture_output=True,
            check=False,
        )
        server.wait()
    backend = stage / BACKEND
    build = (backend / "version.txt").read_text(encoding="utf-8").strip()
    if build != lemonade["llamacpp_build"]:
        raise RuntimeError(f"Lemonade installed llama.cpp {build}")
    python = stage / "python"
    for name in ("vcruntime140.dll", "vcruntime140_1.dll"):
        shutil.copy2(python / name, backend / name)
    (msvcp,) = (python / "Lib" / "site-packages" / "numpy.libs").glob(
        "msvcp140-*.dll"
    )
    shutil.copy2(msvcp, backend / "msvcp140.dll")


def _add_model(stage: Path, pins: dict[str, Any], model: Path) -> None:
    """Copy the fine-tuned model in, and check it.

    Args:
        stage: The bundle's folder.
        pins: The pinned downloads.
        model: The GGUF file.

    Raises:
        RuntimeError: If it is not the pinned model.
    """
    target = stage / "model" / pins["model"]["file"]
    target.parent.mkdir()
    shutil.copy2(model, target)
    if _sha256(target) != pins["model"]["sha256"]:
        raise RuntimeError(f"{model} is not the pinned model")


def _add_tokenizer(stage: Path, pins: dict[str, Any], python: Path) -> None:
    """Fetch the tokenizer's files into the bundle's Hugging Face cache.

    Only the files the notebook reads, not the model weights; at run time
    the launcher sets `HF_HUB_OFFLINE`, so they are read from here.

    Args:
        stage: The bundle's folder.
        pins: The pinned downloads.
        python: The bundle's `python.exe`, which has `huggingface_hub`.
    """
    tokenizer = pins["tokenizer"]
    _run(
        python,
        "-c",
        "import sys; from huggingface_hub import snapshot_download; "
        "snapshot_download(sys.argv[1], revision=sys.argv[2], "
        "allow_patterns=sys.argv[3:])",
        tokenizer["repository"],
        tokenizer["revision"],
        *tokenizer["files"],
        env={
            **os.environ,
            "HF_HOME": str(stage / "hf"),
            "HF_HUB_DISABLE_TELEMETRY": "1",
        },
    )


def _add_licences(stage: Path, pins: dict[str, Any], cache: Path) -> None:
    """Gather every component's licence into `LICENSES`.

    Each Python package's own licence files stay in its `.dist-info`
    folder; `Python-packages.txt` lists every package with the licence
    its metadata declares.

    Args:
        stage: The bundle's folder.
        pins: The pinned downloads.
        cache: Where downloads are kept.
    """
    licences = stage / "LICENSES"
    licences.mkdir()
    shutil.copy2(REPOSITORY / "LICENSE", licences / "PyMOL-Copilot-LICENSE.txt")
    for pinned in pins["licences"].values():
        shutil.copy2(
            _download(pinned["url"], pinned["sha256"], cache),
            licences / pinned["file"],
        )
    shutil.copy2(
        stage / "lemonade" / "LICENSE", licences / "Lemonade-LICENSE.txt"
    )
    shutil.copy2(
        stage / BACKEND / "LICENSE-LLVM-OpenMP",
        licences / "LLVM-OpenMP-LICENSE.txt",
    )
    shutil.copy2(
        stage / "python" / "LICENSE.txt", licences / "CPython-LICENSE.txt"
    )
    _run(
        stage / "python" / "python.exe",
        Path(bundle_spec.__file__),
        "packages",
        licences / "Python-packages.txt",
    )


def _write_zip(stage: Path, target: Path, timestamp: int) -> None:
    """Pack the bundle into one ZIP, deterministically.

    Entries are sorted and carry the commit's time. The model is stored,
    not compressed: a GGUF barely compresses, and storing it is fast. A
    precompiled module too long to extract is left out (`zip_entries`).

    Args:
        stage: The bundle's folder.
        target: The ZIP.
        timestamp: The commit's time, in seconds since the epoch.

    Raises:
        RuntimeError: If an entry's path is too long to extract safely.
    """
    by_name = {
        f"{bundle_spec.ROOT_NAME}/{path.relative_to(stage).as_posix()}": path
        for path in stage.rglob("*")
        if path.is_file()
    }
    names, too_long = bundle_spec.zip_entries(sorted(by_name))
    if too_long:
        raise RuntimeError(f"paths too long to extract safely: {too_long}")
    files = [by_name[name] for name in names]
    moment = datetime.datetime.fromtimestamp(timestamp, datetime.UTC)
    date_time = (
        max(moment.year, 1980),
        moment.month,
        moment.day,
        moment.hour,
        moment.minute,
        moment.second,
    )
    with zipfile.ZipFile(target, "w", allowZip64=True) as zipped:
        for path, name in zip(files, names, strict=True):
            entry = zipfile.ZipInfo(name, date_time=date_time)
            entry.compress_type = (
                zipfile.ZIP_STORED
                if path.suffix == ".gguf"
                else zipfile.ZIP_DEFLATED
            )
            entry.external_attr = 0o644 << 16
            with (
                path.open("rb") as source,
                zipped.open(entry, "w", force_zip64=True) as sink,
            ):
                shutil.copyfileobj(source, sink, 1 << 20)


def build(model: Path | None, out: Path) -> Path:
    """Build the bundle.

    Args:
        model: The fine-tuned GGUF, or None for a bundle without it.
        out: Where the ZIP, and the build's scratch and downloads, go.

    Returns:
        The ZIP.

    Raises:
        RuntimeError: If the tree has uncommitted changes, or the output
            is inside the repository.
    """
    if sys.platform != "win32":
        raise RuntimeError("the bundle is built on Windows")
    out = out.resolve()
    if out.is_relative_to(REPOSITORY):
        raise RuntimeError(f"{out} is inside the repository; build elsewhere")
    if _run(
        "git", "-C", REPOSITORY, "status", "--porcelain", "--untracked-files=no"
    ):
        raise RuntimeError(
            "commit or stash your changes: the bundle is the commit"
        )
    commit = _run("git", "-C", REPOSITORY, "rev-parse", "HEAD").strip()
    timestamp = int(
        _run("git", "-C", REPOSITORY, "log", "-1", "--format=%ct", "HEAD")
    )
    pins = bundle_spec.load_pins(REPOSITORY)
    work, cache = out / "work", out / "downloads"
    _remove(work)
    stage = work / bundle_spec.ROOT_NAME
    stage.mkdir(parents=True)

    _add_repository(stage, work)
    python = _add_python(stage, pins, cache)
    _add_lemonade(stage, pins, work, cache)
    if model is not None:
        _add_model(stage, pins, model)
    _add_tokenizer(stage, pins, python)
    _add_licences(stage, pins, cache)
    (stage / bundle_spec.LAUNCHER_NAME).write_bytes(
        bundle_spec.launcher_text(demo=model is not None).encode("ascii")
    )
    (stage / "README.txt").write_bytes(
        bundle_spec.readme_text(commit).encode("ascii")
    )
    (stage / "bundle.json").write_text(
        json.dumps(
            bundle_spec.manifest(
                commit,
                pins,
                model=model is not None,
                lock_sha256=_sha256(REPOSITORY / "requirements-bundle.txt"),
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    _run(
        python,
        "-m",
        "compileall",
        "-q",
        "--invalidation-mode",
        "unchecked-hash",
        stage / "python" / "Lib",
        stage / "repo" / "src",
        stage / "repo" / "notebooks",
    )

    target = out / bundle_spec.zip_name(commit)
    _write_zip(stage, target, timestamp)
    digest = _sha256(target)
    target.with_name(target.name + ".sha256").write_text(
        f"{digest}  {target.name}\n", encoding="ascii"
    )
    size = target.stat().st_size / 2**30
    print(f"wrote {target} ({size:.2f} GiB, sha256 {digest})")
    return target


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and build.

    Args:
        argv: The arguments, or None for `sys.argv`.

    Returns:
        The exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--model", type=Path, help="the fine-tuned GGUF")
    which.add_argument(
        "--no-model", action="store_true", help="leave the model out (for CI)"
    )
    parser.add_argument("--out", type=Path, required=True, help="output folder")
    args = parser.parse_args(argv)
    build(None if args.no_model else args.model, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
