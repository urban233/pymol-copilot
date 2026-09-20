# Copyright 2026 PyMOL Copilot contributors.
"""Conformance: the checked-in error corpus still matches live PyMOL.

`tests/contract/test_errors.py` proves the normalizer against the captured
corpus without launching PyMOL. Nothing in that test can notice when PyMOL
itself rewords a message, renames an exception type, or stops raising for
a case altogether -- at which point the corpus quietly describes a PyMOL
that no longer exists and every category counted downstream is wrong.

This module closes that gap. It re-drives every case in
`pymol_error_cases.py` against a live PyMOL process and asserts the raised
type and the raw message still match what is checked in, byte for byte. It
shares the case table with `capture_pymol_errors.py`, so a case added to
the capture is covered here without a second edit.

Regenerate the corpus with:

    bazel run //tests/integration:capture_pymol_errors
"""

import json
import os
import pathlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

import winstage

from pmc_core.errors import exception_type_name
from pymol_error_cases import FIXTURE_OBJECT
from pymol_error_cases import LAUNCH_ARGUMENTS
from pymol_error_cases import cases

#: The captured corpus, reached from this file rather than from the
#: working directory, which a Bazel test does not control.
_CORPUS_DIRECTORY = (
    pathlib.Path(__file__).parent.parent
    / "contract"
    / "testdata"
    / "pymol_errors"
)


def _captured() -> dict[tuple[str, str], dict[str, object]]:
    """Load the corpus, keyed by verb and case.

    Returns:
        Every captured case, keyed by its (verb, case) identity.
    """
    captured: dict[tuple[str, str], dict[str, object]] = {}
    for path in sorted(_CORPUS_DIRECTORY.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for case in payload["cases"]:
            captured[(str(case["verb"]), str(case["case"]))] = case
    return captured


def _captured_version() -> str:
    """Report the PyMOL version the corpus was captured against.

    Returns:
        The recorded version string.

    Raises:
        AssertionError: If the corpus files disagree about the version,
            which would mean a partial recapture.
    """
    versions = set()
    for path in sorted(_CORPUS_DIRECTORY.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        versions.add(str(payload["pymol_version"]))
    assert len(versions) == 1, f"corpus files disagree on version: {versions}"
    return versions.pop()


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[Any]:
    """Launch real headless PyMOL exactly once for this test module.

    Shaped exactly like the other real-PyMOL fixtures in this package, so
    the one headless launch an interpreter permits is torn down the same
    way everywhere, but launched with `pymol_error_cases.LAUNCH_ARGUMENTS`
    rather than this package's usual `-qc`. The corpus this module
    re-derives was captured under those arguments, and replaying it under
    any others compares a live PyMOL against evidence gathered somewhere
    else: the user's pymolrc could pre-create the undefined selection or
    monkeypatch a `cmd` method, and the result would say nothing about
    PyMOL drift either way.

    Yields:
        The real PyMOL cmd module, with the fixture object loaded.
    """
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(list(LAUNCH_ARGUMENTS))
    try:
        cmd.fragment("ala", FIXTURE_OBJECT)
        yield cmd
    finally:
        cmd.do("quit")


def test_the_corpus_records_the_running_pymol_version(
    real_pymol: Any,
) -> None:
    """A PyMOL upgrade must fail here first, naming the version.

    Without this, an upgrade that reworded several messages would produce
    a scatter of message mismatches rather than one legible cause.
    """
    running = str(real_pymol.get_version()[0])
    assert running == _captured_version(), (
        f"corpus was captured against PyMOL {_captured_version()} but this "
        f"is PyMOL {running}; rerun "
        "`bazel run //tests/integration:capture_pymol_errors`"
    )


def test_the_run_is_isolated_from_the_user_environment(
    real_pymol: Any,
) -> None:
    """The `-k` in LAUNCH_ARGUMENTS must have actually taken effect.

    Passing the flag and having it take effect are two claims, and only
    the second is what keeps this run comparable to the capture. Without
    it a user's pymolrc or a loaded plugin could pre-create the undefined
    selection, define the unknown color or representation, or monkeypatch
    a `cmd` method, and every assertion below would be about that
    environment rather than about PyMOL.
    """
    del real_pymol  # Needed for its launch, not for its value.
    import pymol  # pyrefly: ignore.

    options = pymol.invocation.options
    assert not options.plugins, "plugins were loaded; this run is not isolated"
    assert options.pymolrc is None, (
        f"pymolrc was loaded ({options.pymolrc}); this run is not isolated"
    )


def test_every_case_still_fails_the_same_way(real_pymol: Any) -> None:
    """Each case still raises, with the same type and the same bytes."""
    captured = _captured()
    for case in cases():
        key = (case.verb, case.case)
        assert key in captured, f"{key} is driven but not captured"
        expected = captured[key]
        try:
            case.drive(real_pymol)
        except BaseException as error:  # Any raised type is the point.
            assert exception_type_name(error) == expected["exception_type"], (
                f"{key} changed exception type"
            )
            assert str(error) == expected["raw_message"], (
                f"{key} changed its message"
            )
            continue
        pytest.fail(f"{key} no longer fails at all")


def test_every_captured_case_is_still_driven() -> None:
    """A corpus entry no case drives would be evidence of nothing."""
    driven = {(case.verb, case.case) for case in cases()}
    assert set(_captured()) == driven


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (see the same __main__ block in
    # tests/integration/test_real_pymol_allowlist.py). Verified here rather
    # than copied on faith: with `raise SystemExit(pytest.main(...))` a
    # deliberately corrupted corpus message made pytest report "1 failed"
    # while Bazel still reported the target PASSED.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
