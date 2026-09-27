# Copyright 2026 PyMOL Copilot contributors.
"""The sabotage test SPECIFICATION.md:723 asks for by name.

docs/master_plan.md item 12. Every "zero unapproved mutation" assertion
in this whole item rests on `scenario_support.SessionFingerprint` and
`assert_unchanged` actually being able to fail. `test_harness.py`'s own
parametrized smoke check proves a first cut of this; this module is the
complete, dedicated matrix: one real PyMOL mutation of exactly each field
the fingerprint compares, plus the negative case that a genuine no-op does
not trip it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import fields
from typing import Any

import pytest

from scenario_support import OBJECT_NAME
from scenario_support import SessionFingerprint
from scenario_support import assert_unchanged
from scenario_support import capture_fingerprint

#: One tuple per field `SessionFingerprint` compares: a real mutation of
#: exactly that field, and nothing else. Order matches the dataclass's own
#: field order. Every id but the two `object_names_*` variants names the
#: one field its mutation must be isolated to; those two (deleting the
#: object, creating a copy) necessarily move every per-atom field too, so
#: only `object_names` itself is required to change for them.
_NOT_ISOLATED = {
    "object_names_delete": "object_names",
    "object_names_create": "object_names",
}
_MUTATIONS: tuple[tuple[str, Any], ...] = (
    ("object_names", lambda cmd: cmd.select("copilot_leftover", "chain A")),
    ("object_names_delete", lambda cmd: cmd.delete(OBJECT_NAME)),
    ("object_names_create", lambda cmd: cmd.create("copilot_copy", "chain A")),
    (
        "chain_a_atom_count",
        # Reassigning one atom's chain, not removing it: confirmed
        # empirically that every per-atom field (coordinates, colors,
        # representations, labels, and their index order) stays exactly
        # the same for every atom -- this is the one mutation that
        # isolates the atom-count fields from the rest of the
        # fingerprint. Two rejected alternatives, in order: `cmd.remove`
        # also shrinks every per-atom array, so it cannot by itself prove
        # the atom-count fields carry information the others do not
        # already catch; `cmd.alter` followed by `cmd.sort()` reorders
        # the object's own atoms by the new chain, which changes every
        # per-atom tuple's own order too, hiding the same problem again.
        lambda cmd: cmd.alter(
            f"{OBJECT_NAME} and chain A and resi 1", "chain='Z'"
        ),
    ),
    (
        "chain_b_atom_count",
        # Same isolation technique, the other chain: confirmed no other
        # mutation case in this matrix touches chain B's own atom count,
        # so this field had no dedicated coverage until this case was
        # added.
        lambda cmd: cmd.alter(
            f"{OBJECT_NAME} and chain B and resi 1", "chain='Y'"
        ),
    ),
    ("coordinates", lambda cmd: cmd.translate([1.0, 0.0, 0.0], "chain A")),
    ("colors", lambda cmd: cmd.color("blue", "chain A")),
    ("representations", lambda cmd: cmd.show("spheres", "chain B")),
    (
        "labels",
        # `cmd.alter(..., "label=...")` sets the label property directly;
        # confirmed empirically that, unlike the `label` command itself,
        # this does not also enable the label representation bit -- the
        # `label` command was tried first and rejected, since it changes
        # `representations` too, hiding whether `labels` carries any
        # information the other fields do not already catch.
        lambda cmd: cmd.alter("chain A and name CA", "label='x'"),
    ),
    (
        "view",
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
    ),
)


def _changed_fields(
    before: SessionFingerprint, after: SessionFingerprint
) -> set[str]:
    """Name every fingerprint field that differs between two captures."""
    return {
        field.name
        for field in fields(SessionFingerprint)
        if getattr(before, field.name) != getattr(after, field.name)
    }


@pytest.mark.parametrize(
    ("case", "mutate"),
    list(_MUTATIONS),
    ids=[name for name, _ in _MUTATIONS],
)
def test_a_real_mutation_of_each_field_trips_the_fingerprint(
    loaded_fixture: Any, case: str, mutate: Any
) -> None:
    """Each field's own real mutation makes `assert_unchanged` raise.

    And it does so through that field: a mutation that also moved some
    other field would still trip `assert_unchanged` even if capturing its
    own named field were broken, so each isolated case checks that its
    named field is the only one that changed.
    """
    before = capture_fingerprint(loaded_fixture)

    mutate(loaded_fixture)

    after = capture_fingerprint(loaded_fixture)
    with pytest.raises(AssertionError):
        assert_unchanged(before, after)
    changed = _changed_fields(before, after)
    if case in _NOT_ISOLATED:
        assert _NOT_ISOLATED[case] in changed
    else:
        assert changed == {case}


def test_a_genuine_no_op_never_trips_the_fingerprint(
    loaded_fixture: Any,
) -> None:
    """The matrix above does not pass by rejecting everything.

    A real no-op leaves `assert_unchanged` silent.
    """
    before = capture_fingerprint(loaded_fixture)

    loaded_fixture.sync()
    loaded_fixture.count_atoms("all")
    loaded_fixture.get_names("all")
    loaded_fixture.get_view()
    loaded_fixture.iterate("all", "pass")

    after = capture_fingerprint(loaded_fixture)
    assert_unchanged(before, after)


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
