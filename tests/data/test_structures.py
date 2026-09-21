# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic evidence for the controlled structure builder.

Whether a built structure survives PyMOL's own reconstruct-extract cycle
is the admission gate in test_structures_real_pymol.py. What is
checkable without PyMOL is that the matrix actually covers the features
master plan item 14 names, and that building is deterministic -- a
corpus whose structures drifted between runs could not be reproduced
from its recorded seed.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import pytest

from pmc_core.snapshot import MOLECULE_REP_NAMES
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import to_json
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

#: The seed the matrix is exercised with here.
SEED = 20260921


def test_matrix_covers_every_declared_feature() -> None:
    """Item 14 names four structure features; all four must appear.

    A feature missing from the matrix would not fail anything later --
    it would silently produce a corpus with no coverage of it at all,
    which is the outcome the per-category report exists to make visible.
    """
    built = [build_structure(spec) for spec in enumerate_structures(SEED)]
    atoms = [atom for snapshot in built for atom in snapshot.states[0].atoms]

    assert any(
        len({atom.chain for atom in snapshot.states[0].atoms}) > 1
        for snapshot in built
    ), "no structure has more than one chain"
    assert any(atom.hetatm for atom in atoms), "no structure has hetero atoms"
    assert any(len(snapshot.states) > 1 for snapshot in built), (
        "no structure has more than one state"
    )
    assert any(atom.alt for atom in atoms), (
        "no structure has alternate locations"
    )
    assert any(atom.ins_code for atom in atoms), (
        "no structure has insertion codes"
    )
    assert any(snapshot.bonds for snapshot in built), "no structure has bonds"


def test_building_is_deterministic_for_a_seed() -> None:
    """A recorded seed must reproduce a recorded structure exactly."""
    for spec in enumerate_structures(SEED):
        assert to_json(build_structure(spec)) == to_json(build_structure(spec))


def test_distinct_specs_build_distinct_structures() -> None:
    """A matrix whose entries collided would overstate its own coverage."""
    rendered = [
        to_json(build_structure(spec)) for spec in enumerate_structures(SEED)
    ]

    assert len(set(rendered)) == len(rendered)


def test_every_numeric_field_is_exactly_representable_in_single_precision() -> (
    None
):
    """PyMOL stores coordinates, occupancy and B-factor as C floats.

    A value that changes when narrowed to single precision comes back
    different from reconstruction, so every sample built on that
    structure would fail the executor's fidelity gate for a reason that
    has nothing to do with the plan under test.
    """
    import struct

    def survives_single_precision(value: float) -> bool:
        """Whether a float is unchanged by a round trip through float32.

        Args:
            value: The value to narrow and widen.

        Returns:
            True when narrowing to single precision loses nothing.
        """
        return struct.unpack("f", struct.pack("f", value))[0] == value

    for spec in enumerate_structures(SEED):
        snapshot = build_structure(spec)
        for state in snapshot.states:
            for atom in state.atoms:
                for value in (*atom.coord, atom.q, atom.b):
                    assert survives_single_precision(value), (
                        f"{spec.spec_id}: {value!r} is not exact in float32"
                    )
        for value in snapshot.view:
            assert survives_single_precision(value)


def test_every_starting_representation_is_observable() -> None:
    """An atom starting in an unobservable representation breaks `hide`.

    `pmc_core.snapshot` records membership only for
    MOLECULE_REP_NAMES, so a `hide` of anything else could never be
    seen to have happened.
    """
    for spec in enumerate_structures(SEED):
        for state in build_structure(spec).states:
            for atom in state.atoms:
                assert set(atom.reps) <= set(MOLECULE_REP_NAMES)


def test_states_differ_only_in_coordinates() -> None:
    """Extraction reads colour and reps once, not once per state."""
    spec = next(
        spec
        for spec in enumerate_structures(SEED)
        if spec.spec_id == "three_states"
    )
    snapshot = build_structure(spec)

    first, *rest = snapshot.states
    for state in rest:
        assert len(state.atoms) == len(first.atoms)
        for a, b in zip(first.atoms, state.atoms, strict=True):
            assert (a.serial, a.name, a.alt, a.resn, a.chain, a.resv) == (
                b.serial,
                b.name,
                b.alt,
                b.resn,
                b.chain,
                b.resv,
            )
            assert (a.color, a.reps, a.hetatm, a.q, a.b) == (
                b.color,
                b.reps,
                b.hetatm,
                b.q,
                b.b,
            )


def test_snapshot_declares_the_current_schema_version() -> None:
    """A structure declaring another version would be rejected downstream."""
    for spec in enumerate_structures(SEED):
        assert build_structure(spec).schema_version == SNAPSHOT_VERSION


def test_an_impossible_spec_is_rejected_rather_than_truncated() -> None:
    """Silently clamping a spec would misreport what was covered."""
    with pytest.raises(ValueError, match="unsupported chain count"):
        build_structure(
            StructureSpec(
                spec_id="too_many_chains",
                seed=1,
                chain_count=99,
                residues_per_chain=1,
                hetero_residues=0,
                state_count=1,
                altloc_residues=0,
                insertion_residues=0,
                with_bonds=False,
            )
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
