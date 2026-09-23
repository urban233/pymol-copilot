# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL conformance evidence for the frozen command allowlists.

pmc_core.plan freezes 177 color names and 14 representations as literal
tuples, because pmc_core must never import Open-Source PyMOL -- the parser
and policy suites assert that PyMOL is absent from sys.modules, and pmc_core
is imported inside PyMOL's own process where dragging in more would be
worse. A frozen list can drift from the PyMOL it was generated against, and
a drifted list has a nasty failure mode: a plan the parser accepts and the
policy allows, which then fails at execution. The specification requires
denial to happen before execution, so that combination is the thing to rule
out.

This module rules it out in one direction only: everything the allowlists
name must be something real PyMOL knows. The reverse is deliberately not
asserted. A newer PyMOL adding a color must not turn the build red --
widening an allowlist is a reviewed decision under the specification's
"expansion requires security review", not something CI should demand.

Every collaborator here is real headless Open-Source PyMOL. Nothing is a
test double.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
import sys
from collections.abc import Iterator
from typing import Any

import pytest

import winstage

from pmc_core.plan import COLOR_ALLOWLIST
from pmc_core.plan import REPRESENTATION_ALLOWLIST
from pmc_data.colors import COLOR_INDEX_BY_NAME
from pmc_data.sample import PINNED_PYMOL_VERSION


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[Any]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL cmd module.
    """
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


@pytest.fixture
def loaded_object(real_pymol: Any) -> Iterator[Any]:
    """Create a minimal real object for representation checks.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module, with one object named fx loaded.
    """
    real_pymol.fragment("ala", "fx")
    try:
        yield real_pymol
    finally:
        real_pymol.delete("fx")


def test_every_allowlisted_color_is_a_color_pymol_knows(
    real_pymol: Any,
) -> None:
    """No allowlisted color can reach execution and fail as unknown.

    Args:
        real_pymol: The real PyMOL cmd module.
    """
    known = {name for name, _ in real_pymol.get_color_indices()}

    missing = sorted(set(COLOR_ALLOWLIST) - known)

    assert missing == [], (
        "COLOR_ALLOWLIST names colors this PyMOL does not define; the frozen "
        "list has drifted from the PyMOL it was generated against"
    )


def test_every_allowlisted_color_resolves_to_a_color_index(
    real_pymol: Any,
) -> None:
    """Each allowlisted color resolves, not merely appears in a listing.

    Args:
        real_pymol: The real PyMOL cmd module.
    """
    unresolved = [
        color
        for color in COLOR_ALLOWLIST
        if real_pymol.get_color_index(color) == -1
    ]

    assert unresolved == []


def test_every_allowlisted_representation_is_accepted_by_show(
    loaded_object: Any,
) -> None:
    """Each allowlisted representation is one real PyMOL will show.

    Args:
        loaded_object: The real PyMOL cmd module with object fx loaded.
    """
    rejected: list[str] = []
    for representation in REPRESENTATION_ALLOWLIST:
        try:
            loaded_object.show(representation, "fx")
            loaded_object.hide(representation, "fx")
        except Exception:
            rejected.append(representation)

    assert rejected == []


def test_frozen_color_indices_match_real_pymol(
    real_pymol: Any,
) -> None:
    """The dataset oracle predicts color as the index PyMOL records.

    pmc_data.colors freezes the name-to-index mapping so the oracle can
    predict an AtomRecord.color without importing PyMOL. A drifted index
    would not fail loudly: it would make every generated color sample
    mismatch at the executor's fidelity gate and be rejected, which
    looks like a broken oracle rather than a stale table.

    Args:
        real_pymol: The real PyMOL cmd module.
    """
    drifted = [
        (name, index, real_pymol.get_color_index(name))
        for name, index in COLOR_INDEX_BY_NAME.items()
        if real_pymol.get_color_index(name) != index
    ]

    assert drifted == [], (
        "pmc_data.colors has drifted from the PyMOL it was generated "
        "against; regenerate it with "
        "bazel run //tests/integration:capture_color_indices"
    )


def test_the_pinned_pymol_version_matches_the_running_build(
    real_pymol: Any,
) -> None:
    """Every sample records which PyMOL verified it; that must be true.

    `pmc_data.sample` freezes the build string because the dataset
    modules must import without PyMOL present. A sample recording a
    version it was not actually verified against is a false
    provenance claim, which is worse than no claim.

    The frozen value is what PyMOL reports for itself, not the
    wheel's own version string: the wheel is 3.2.0.2 and PyMOL
    reports "3.2.0a". Recording the running build rather than the
    filename it arrived in is what makes the claim checkable here, by
    exact equality.

    Args:
        real_pymol: The real PyMOL cmd module.
    """
    reported = str(real_pymol.get_version()[0])

    assert reported == PINNED_PYMOL_VERSION, (
        f"pmc_data.sample pins {PINNED_PYMOL_VERSION!r} but this PyMOL "
        f"reports {reported!r}"
    )


def test_the_allowlists_hold_no_duplicates() -> None:
    """A duplicated entry would make the allowlist's own count a lie."""
    assert len(set(COLOR_ALLOWLIST)) == len(COLOR_ALLOWLIST)
    assert len(set(REPRESENTATION_ALLOWLIST)) == len(REPRESENTATION_ALLOWLIST)


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (see the same __main__ block in
    # tests/integration/test_real_pymol_command.py). os._exit bypasses that
    # window, and the explicit flushes keep a real failure's traceback from
    # being lost from the captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
