# Copyright 2026 PyMOL Copilot contributors.
"""Capture real PyMOL error strings into the checked-in corpus.

Run this to regenerate `tests/contract/testdata/pymol_errors/`:

    bazel run //tests/integration:capture_pymol_errors

Re-running it against an unchanged PyMOL must leave `git status` clean.
The corpus it writes is what `tests/contract/test_errors.py` normalizes
hermetically and what `tests/integration/test_errors_real_pymol.py`
re-derives from a live PyMOL to prove the checked-in strings still hold.

Every case is driven through the typed `cmd.*` API rather than `cmd.do()`.
`cmd.do()` returns None for every failure and writes its text from C at
the file-descriptor level on PyMOL's own thread, so it surfaces nothing a
caller can catch; the typed API raises synchronously and writes nothing.

The cases themselves live in `pymol_error_cases.py`, shared with the
conformance test so the two can never drive different commands.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import winstage

from pymol_error_cases import FIXTURE_OBJECT
from pymol_error_cases import capture_case
from pymol_error_cases import cases

winstage.ensure_importable()

#: Where the corpus is written, relative to the repository root.
CORPUS_RELATIVE_PATH = pathlib.PurePath("tests/contract/testdata/pymol_errors")


def corpus_directory() -> pathlib.Path:
    """Resolve the corpus directory in the source tree.

    `bazel run` executes from a runfiles directory, so a bare relative path
    would write the corpus somewhere the repository never sees. Bazel sets
    BUILD_WORKSPACE_DIRECTORY to the source root for exactly this case.

    Returns:
        The absolute corpus directory.

    Raises:
        RuntimeError: If run outside `bazel run`, where the source root
            cannot be determined and writing anywhere would be a guess.
    """
    root = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not root:
        raise RuntimeError(
            "BUILD_WORKSPACE_DIRECTORY is unset: run this through "
            "`bazel run //tests/integration:capture_pymol_errors`"
        )
    return pathlib.Path(root) / CORPUS_RELATIVE_PATH


def main() -> int:
    """Capture every case and write the corpus.

    Returns:
        0 when every case failed as expected, 1 when any case did not
        fail at all.

    Raises:
        RuntimeError: If the source root cannot be determined.
    """
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qck"])
    cmd.fragment("ala", FIXTURE_OBJECT)

    version = str(cmd.get_version()[0])
    by_verb: dict[str, list[dict[str, object]]] = {}
    silent: list[str] = []
    for case in cases():
        recorded = capture_case(cmd, case)
        if recorded is None:
            silent.append(f"{case.verb}/{case.case}")
            continue
        by_verb.setdefault(case.verb, []).append(recorded)

    directory = corpus_directory()
    directory.mkdir(parents=True, exist_ok=True)
    for verb, verb_cases in sorted(by_verb.items()):
        payload = {"pymol_version": version, "cases": verb_cases}
        path = directory / f"{verb}.json"
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path} ({len(verb_cases)} cases)")

    cmd.do("quit")
    if silent:
        print(f"these cases did not fail at all: {', '.join(silent)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
