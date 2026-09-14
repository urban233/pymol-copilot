# Copyright 2026 PyMOL Copilot contributors.
"""One-shot Windows MAX_PATH diagnostic for issue #12.

Issue #12 records that `pymol-open-source-whl`'s Windows wheel cannot be
imported under Bazel because the absolute path to its delvewheel-repaired
dependency DLLs exceeds Windows' 260-character `MAX_PATH` limit. Two
mitigations were already tried against real Windows CI and ruled out: a
short Bazel output base and unsandboxed test execution.

This module does not attempt a third fix. It measures which of the three
remaining levers is viable, so the choice between them rests on evidence
rather than on a fourth guess:

1. OS long-path support -- is `LongPathsEnabled` set, and is the hermetic
   interpreter actually able to use paths beyond `MAX_PATH`?
2. Short-path staging -- does copying the package and its `.libs` directory
   to a short path make the import succeed?
3. Upstream naming -- how much of the budget do the wheel's own bundled DLL
   names consume, which is what a shorter delvewheel scheme would recover?

It deliberately never fails: every probe is reported, including its own
errors, and the process always exits zero. It is a throwaway probe and is
not intended to merge.
"""

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_PATH = 260

# This diagnostic sits at a deliberately short Bazel package path so that it
# can run even when the real probes cannot. The two constants below let the
# report restate every measured length as the length the real H-02 target
# would see, which is the number issue #12 actually cares about.
DIAG_RUNFILES = "tools/wd/d.exe.runfiles"
H02_RUNFILES = "tests/discovery/h02/full_v1_snapshot_candidate_a.exe.runfiles"
H02_PENALTY = len(H02_RUNFILES) - len(DIAG_RUNFILES)

SHORT_ROOT = Path("C:/p")


def heading(text: str) -> None:
    """Print one section heading.

    Args:
        text: The heading's text.
    """
    print(f"\n=== {text} ===", flush=True)


def long_paths_enabled() -> str:
    """Read the machine's `LongPathsEnabled` policy value.

    Returns:
        A human-readable description of the registry value, or of why it
        could not be read.
    """
    try:
        winreg = importlib.import_module("winreg")
    except ImportError as error:
        return f"unavailable (not Windows): {error}"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        )
        with key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
        return f"LongPathsEnabled = {value!r}"
    except OSError as error:
        return f"could not read: {error}"


def long_path_file_probe() -> str:
    """Test whether this interpreter can create a path beyond `MAX_PATH`.

    A process only gets long-path behavior when the OS policy is enabled
    *and* its executable's manifest declares `longPathAware`. Rather than
    parse the manifest, this probe simply tries the operation.

    Returns:
        A human-readable result describing the attempted path and outcome.
    """
    root = Path(tempfile.mkdtemp())
    deep = root
    while len(str(deep)) < MAX_PATH + 40:
        deep = deep / "abcdefghijklmnopqrstuvwxyz0123456789"
    target = deep / "probe.txt"
    try:
        deep.mkdir(parents=True, exist_ok=True)
        target.write_text("ok", encoding="utf-8")
        read_back = target.read_text(encoding="utf-8")
        result = f"SUCCESS (wrote and read {len(str(target))} chars)"
    except OSError as error:
        result = f"FAILED at {len(str(target))} chars: {error}"
    else:
        del read_back
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return result


def find_site_packages() -> Path | None:
    """Locate the staged `pymol` package without importing it.

    `import pymol` is precisely what fails on Windows, so this uses the
    import system's finder, which locates the package without executing its
    `__init__`.

    Returns:
        The directory containing the `pymol` package, or None when the
        package cannot be located at all.
    """
    try:
        spec = importlib.util.find_spec("pymol")
    except (ImportError, ValueError) as error:
        print(f"find_spec failed: {error}")
        return None
    if spec is None or not spec.origin:
        return None
    return Path(spec.origin).parent.parent


def report_lengths(site_packages: Path) -> Path | None:
    """Report the path lengths that decide whether the import can work.

    Args:
        site_packages: The directory holding the staged `pymol` package.

    Returns:
        The delvewheel `.libs` directory, or None when it is absent.
    """
    print(f"site-packages: {site_packages}")
    print(f"  length: {len(str(site_packages))}")
    libs = site_packages / "pymol_open_source_whl.libs"
    if not libs.is_dir():
        print("  no pymol_open_source_whl.libs directory found")
        return None
    dlls = sorted(libs.glob("*.dll"), key=lambda p: len(str(p)))
    if not dlls:
        print("  .libs directory contains no DLLs")
        return libs
    longest = dlls[-1]
    measured = len(str(longest))
    print(f"  bundled DLLs: {len(dlls)}")
    print(f"  longest DLL: {longest.name}")
    print(f"    measured here: {measured} chars")
    print(f"    MAX_PATH headroom here: {MAX_PATH - measured}")
    equivalent = measured + H02_PENALTY
    print(
        f"    equivalent under {H02_RUNFILES}: {equivalent} chars "
        f"(headroom {MAX_PATH - equivalent})"
    )
    return libs


def import_in_subprocess(label: str, setup: str) -> None:
    """Attempt `import pymol` in a clean child interpreter.

    Each attempt runs in its own process so that a failed import never
    contaminates a later one through the import cache.

    Args:
        label: Human-readable name for this attempt.
        setup: Python source executed before the import is attempted.
    """
    code = (
        f"{setup}\n"
        "import pymol\n"
        "from pymol import cmd\n"
        "print('IMPORT OK', pymol.__file__)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    status = "SUCCESS" if result.returncode == 0 else "FAILED"
    print(f"{label}: {status} (exit {result.returncode})")
    for stream in (result.stdout, result.stderr):
        for line in stream.splitlines():
            if line.strip():
                print(f"    {line}")


def stage_short(site_packages: Path, libs: Path | None) -> None:
    """Copy the package to a short path and retry the import from there.

    This is lever 2: if the import succeeds from `C:\\p`, then path length
    alone is the whole problem and a staging step would unblock the real
    probes without any upstream change.

    Args:
        site_packages: The directory holding the staged `pymol` package.
        libs: The delvewheel `.libs` directory, when one exists.
    """
    try:
        if SHORT_ROOT.exists():
            shutil.rmtree(SHORT_ROOT, ignore_errors=True)
        SHORT_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            site_packages / "pymol", SHORT_ROOT / "pymol", dirs_exist_ok=True
        )
        if libs is not None:
            shutil.copytree(libs, SHORT_ROOT / libs.name, dirs_exist_ok=True)
    except OSError as error:
        print(f"short-path staging FAILED to copy: {error}")
        return
    staged = SHORT_ROOT / "pymol"
    print(f"staged to {staged} ({len(str(staged))} chars)")
    setup = (
        "import os, sys\n"
        f"sys.path.insert(0, r'{SHORT_ROOT}')\n"
        f"libs = r'{SHORT_ROOT / (libs.name if libs else 'none')}'\n"
        "if os.path.isdir(libs):\n"
        "    os.add_dll_directory(libs)\n"
    )
    import_in_subprocess("short-path import", setup)


def main() -> int:
    """Run every probe and report the results.

    Returns:
        Always zero: this is a diagnostic, never a gate.
    """
    heading("interpreter")
    print(f"sys.executable: {sys.executable}")
    print(f"  length: {len(sys.executable)}")
    print(f"platform: {sys.platform}")
    print(f"cwd: {os.getcwd()} ({len(os.getcwd())} chars)")
    print(f"H-02 target path penalty vs this probe: +{H02_PENALTY} chars")

    heading("lever 1: OS long-path support")
    print(long_paths_enabled())
    print(f"long-path file probe: {long_path_file_probe()}")

    heading("staged wheel layout")
    site_packages = find_site_packages()
    if site_packages is None:
        print("pymol package could not be located; remaining probes skipped")
        return 0
    libs = report_lengths(site_packages)

    heading("baseline import (as the real probes would do it)")
    import_in_subprocess("baseline import", "")

    if sys.platform == "win32":
        heading("lever 2: short-path staging")
        stage_short(site_packages, libs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
