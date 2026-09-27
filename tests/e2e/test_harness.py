# Copyright 2026 PyMOL Copilot contributors.
"""Prove scenario_support's own fixture and fingerprint before relying on it.

Every later module in this directory assumes the fixture loads with the
documented atom counts, that `ConsoleDriver` genuinely dispatches through
PyMOL's own command registry, that `capture_fingerprint` is sensitive to
every field it claims to compare, and that it never imports the product's
own extraction boundary. This module is where each of those is proven once.
"""

from __future__ import annotations

import inspect
import os
import sys
from typing import Any

import pytest

from scenario_support import ConsoleDriver
from scenario_support import assert_unchanged
from scenario_support import capture_fingerprint


def test_fixture_loads_with_two_atoms_per_chain(loaded_fixture: Any) -> None:
    """The shared two-chain fixture loads with the intended chain split."""
    assert loaded_fixture.count_atoms("all") == 4
    assert loaded_fixture.count_atoms("chain A") == 2
    assert loaded_fixture.count_atoms("chain B") == 2


def test_console_driver_reaches_real_pymols_own_dispatch(
    loaded_fixture: Any,
) -> None:
    """A driven command really goes through PyMOL's own command registry."""
    output: list[str] = []
    driver = ConsoleDriver(loaded_fixture)
    driver.extend("e2e_probe", lambda argument="": output.append(argument))

    elapsed = driver.run("e2e_probe hello")

    assert output == ["hello"]
    assert elapsed >= 0.0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda cmd: cmd.color("blue", "chain A"),
        lambda cmd: cmd.show("spheres", "chain B"),
        lambda cmd: cmd.label("chain A", "'x'"),
        lambda cmd: cmd.set_view(
            (
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                -1.0,
                0.0,
                0.0,
                0.0,
                -50.0,
                0.0,
                0.0,
                0.0,
                40.0,
                60.0,
                -20.0,
            )
        ),
        lambda cmd: cmd.select("copilot_leftover", "chain A"),
        lambda cmd: cmd.delete("two_chain_fixture"),
    ],
    ids=[
        "color",
        "representation",
        "label",
        "view",
        "selection_name",
        "object_name",
    ],
)
def test_fingerprint_catches_every_field_it_claims_to_compare(
    loaded_fixture: Any,
    mutate: Any,
) -> None:
    """Each mutation trips `assert_unchanged` in its own claimed field."""
    before = capture_fingerprint(loaded_fixture)

    mutate(loaded_fixture)

    after = capture_fingerprint(loaded_fixture)
    with pytest.raises(AssertionError):
        assert_unchanged(before, after)


def test_a_genuine_no_op_does_not_trip_the_fingerprint(
    loaded_fixture: Any,
) -> None:
    """The comparison does not reject everything -- only a real change."""
    before = capture_fingerprint(loaded_fixture)

    loaded_fixture.sync()
    loaded_fixture.count_atoms("all")

    after = capture_fingerprint(loaded_fixture)
    assert_unchanged(before, after)


def test_capture_fingerprint_never_calls_product_extraction_code() -> None:
    """The e2e fingerprint reaches only PyMOL's own query surface.

    `pmc_core.snapshot` is this directory's deliberate line: the product's
    own extraction boundary must not be what decides whether a mutation
    happened, or a bug in that boundary would make this suite agree with
    it. This cannot be checked through `sys.modules`: `scenario_support`
    also imports `pmc_agent` for `build_lifecycle`, and `pmc_agent.graph`
    imports `pmc_core.snapshot` for its own, unrelated reason (carrying a
    snapshot through the request graph), so that module is legitimately
    present in this process regardless of what `capture_fingerprint` does.
    The real claim is about `capture_fingerprint`'s own body, so it is
    checked there directly: its source names none of `pmc_core.snapshot`'s
    own API.
    """
    source = inspect.getsource(capture_fingerprint)

    for forbidden in ("pmc_core", "snapshot", "extract(", "structure_digest"):
        assert forbidden not in source, (
            f"capture_fingerprint's own body names {forbidden!r}; it must "
            "reach only PyMOL's own query surface"
        )


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
