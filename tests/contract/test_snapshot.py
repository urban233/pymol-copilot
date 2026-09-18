# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the canonical snapshot format: no PyMOL required.

Covers the parts of pmc_core.snapshot that never touch a live PyMOL
session: the deterministic JSON codec, the declared-unsupported marker,
the structure digest, and the field-by-field diff. The real-PyMOL
extraction/reconstruction round trip lives in
tests/integration/test_snapshot_round_trip.py, since it needs a real
PyMOL process to produce anything to compare against.
"""

import dataclasses
import json

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ATOM_REP_NAMES
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import BondRecord
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import SnapshotDecodeError
from pmc_core.snapshot import StateSnapshot
from pmc_core.snapshot import diff
from pmc_core.snapshot import from_json
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json

#: A hand-built snapshot exercising every full-V1 state category: two
#: states, an altloc pair, an insertion code, a hetero atom, a labeled
#: atom, and multi-representation membership -- without launching PyMOL.
_ATOMS_STATE_1 = (
    AtomRecord(
        serial=1,
        name="N",
        alt="",
        resn="ALA",
        chain="A",
        resv=1,
        ins_code="",
        elem="N",
        hetatm=False,
        q=1.0,
        b=20.0,
        color=5,
        reps=("lines",),
        label=None,
        coord=(11.0, 13.0, 2.0),
    ),
    AtomRecord(
        serial=2,
        name="CA",
        alt="",
        resn="ALA",
        chain="A",
        resv=1,
        ins_code="",
        elem="C",
        hetatm=False,
        q=1.0,
        b=20.0,
        color=5,
        reps=("sticks", "lines"),
        label="CA",
        coord=(12.0, 13.0, 2.5),
    ),
    AtomRecord(
        serial=6,
        name="OG",
        alt="A",
        resn="SER",
        chain="A",
        resv=2,
        ins_code="",
        elem="O",
        hetatm=False,
        q=0.6,
        b=20.0,
        color=5,
        reps=("sticks",),
        label=None,
        coord=(15.5, 14.0, 3.0),
    ),
    AtomRecord(
        serial=7,
        name="OG",
        alt="B",
        resn="SER",
        chain="A",
        resv=2,
        ins_code="",
        elem="O",
        hetatm=False,
        q=0.4,
        b=20.0,
        color=5,
        reps=("sticks",),
        label=None,
        coord=(15.5, 12.0, 3.0),
    ),
    AtomRecord(
        serial=8,
        name="N",
        alt="",
        resn="GLY",
        chain="A",
        resv=3,
        ins_code="A",
        elem="N",
        hetatm=False,
        q=1.0,
        b=20.0,
        color=5,
        reps=("lines",),
        label=None,
        coord=(16.0, 13.0, 2.0),
    ),
    AtomRecord(
        serial=13,
        name="ZN",
        alt="",
        resn="ZN",
        chain="A",
        resv=101,
        ins_code="",
        elem="ZN",
        hetatm=True,
        q=1.0,
        b=20.0,
        color=9,
        reps=("spheres",),
        label=None,
        coord=(20.0, 13.0, 2.0),
    ),
)
_ATOMS_STATE_2 = tuple(
    dataclasses.replace(
        atom, coord=(atom.coord[0], atom.coord[1], atom.coord[2] + 0.5)
    )
    for atom in _ATOMS_STATE_1
)
_BONDS = (BondRecord(0, 1, 1), BondRecord(2, 3, 1))
_VIEW = (
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    -0.5,
    0.5,
    -20.0,
)
_SETTINGS = (("sphere_scale", "0.35000"), ("cartoon_transparency", "0.25000"))


def _sample_snapshot() -> ObjectSnapshot:
    """Build a hand-constructed snapshot covering every state category.

    Returns:
        A snapshot equivalent to what extract() would produce for the H-02
        full-V1 discovery fixture, without requiring a live PyMOL session.
    """
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="fx",
        enabled=False,
        states=(
            StateSnapshot(atoms=_ATOMS_STATE_1),
            StateSnapshot(atoms=_ATOMS_STATE_2),
        ),
        bonds=_BONDS,
        view=_VIEW,
        settings=_SETTINGS,
        unsupported=DECLARED_UNSUPPORTED,
    )


def test_to_json_is_independent_of_construction_order() -> None:
    """Two structurally equal snapshots serialize to identical bytes.

    Field order in the emitted JSON comes from sort_keys, never from the
    order fields happened to be passed to the dataclass constructor.
    """
    built_in_declared_order = _sample_snapshot()
    built_in_reversed_kwarg_order = ObjectSnapshot(
        unsupported=DECLARED_UNSUPPORTED,
        settings=_SETTINGS,
        view=_VIEW,
        bonds=_BONDS,
        states=(
            StateSnapshot(atoms=_ATOMS_STATE_1),
            StateSnapshot(atoms=_ATOMS_STATE_2),
        ),
        enabled=False,
        name="fx",
        schema_version=SNAPSHOT_VERSION,
    )

    assert to_json(built_in_declared_order) == to_json(
        built_in_reversed_kwarg_order
    )


def test_to_json_emits_sorted_compact_golden_bytes() -> None:
    """to_json's key order and separators are pinned, not incidental."""
    minimal = ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="fx",
        enabled=True,
        states=(),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )

    text = to_json(minimal)

    # Compact separators, not the space-padded json.dumps default -- checked
    # by substring rather than a blanket absence of " ", since a string
    # *value* (e.g. one of the declared-unsupported markers) legitimately
    # contains spaces of its own.
    assert ", " not in text
    assert ": " not in text
    parsed_keys = list(json.loads(text).keys())
    assert parsed_keys == sorted(parsed_keys)


def test_to_json_rejects_a_nan_coordinate() -> None:
    """A NaN coordinate is a hard serialization error, not silent JSON."""
    nan_atom = dataclasses.replace(
        _ATOMS_STATE_1[0], coord=(float("nan"), 0.0, 0.0)
    )
    snapshot = dataclasses.replace(
        _sample_snapshot(),
        states=(StateSnapshot(atoms=(nan_atom,)),),
    )

    with pytest.raises(ValueError, match="not JSON compliant"):
        to_json(snapshot)


def test_from_json_round_trips_every_state_category() -> None:
    """from_json(to_json(s)) reconstructs an equal snapshot exactly."""
    snapshot = _sample_snapshot()

    assert from_json(to_json(snapshot)) == snapshot


def test_from_json_rejects_an_unsupported_schema_version() -> None:
    """A snapshot from an unknown schema version is rejected, not decoded."""
    payload = json.loads(to_json(_sample_snapshot()))
    payload["schema_version"] = SNAPSHOT_VERSION + 1

    with pytest.raises(
        SnapshotDecodeError, match="unsupported snapshot schema version"
    ):
        from_json(json.dumps(payload))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda payload: payload.pop("unsupported"), id="missing"),
        pytest.param(
            lambda payload: payload.__setitem__("unsupported", ()),
            id="cleared",
        ),
        pytest.param(
            lambda payload: payload.__setitem__(
                "unsupported", ("some-other-marker",)
            ),
            id="altered",
        ),
    ],
)
def test_from_json_rejects_a_wrong_declared_unsupported_set(
    mutate: object,
) -> None:
    """A snapshot claiming a different unsupported set cannot be decoded.

    Args:
        mutate: A callable mutating the decoded JSON payload in place.
    """
    payload = json.loads(to_json(_sample_snapshot()))
    mutate(payload)  # type: ignore[operator]

    with pytest.raises(SnapshotDecodeError, match="unsupported set"):
        from_json(json.dumps(payload))


def test_declared_unsupported_matches_the_structure_card_markers() -> None:
    """The two declared-unsupported markers are pinned byte-for-byte.

    This is what keeps pmc_core.card (item 5) a pure pass-through of this
    module's own declaration, rather than a second place that could drift
    from it.
    """
    assert DECLARED_UNSUPPORTED == (
        "unsupported state=measurement-objects route=plan-report",
        "unsupported state=explicit-polymer-classification "
        "route=contract-freeze",
    )


def test_atom_rep_names_exclude_object_only_display_modes() -> None:
    """Per-atom snapshots never query PyMOL's object-only display modes."""
    assert "slice" not in ATOM_REP_NAMES
    assert "volume" not in ATOM_REP_NAMES
    assert "ellipsoids" in ATOM_REP_NAMES


def test_structure_digest_is_stable_across_display_state_changes() -> None:
    """view/settings/enabled changes never move the structure digest."""
    original = _sample_snapshot()
    display_changed = dataclasses.replace(
        original,
        view=tuple(v + 1.0 for v in original.view),
        settings=(
            ("sphere_scale", "0.99000"),
            ("cartoon_transparency", "0.01000"),
        ),
        enabled=not original.enabled,
    )

    assert structure_digest(original) == structure_digest(display_changed)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda s: dataclasses.replace(
                s,
                states=(
                    StateSnapshot(
                        atoms=(
                            dataclasses.replace(
                                s.states[0].atoms[0], coord=(0.0, 0.0, 0.0)
                            ),
                            *s.states[0].atoms[1:],
                        )
                    ),
                    *s.states[1:],
                ),
            ),
            id="coordinate",
        ),
        pytest.param(
            lambda s: dataclasses.replace(
                s,
                states=(
                    StateSnapshot(
                        atoms=(
                            dataclasses.replace(
                                s.states[0].atoms[0], color=999
                            ),
                            *s.states[0].atoms[1:],
                        )
                    ),
                    *s.states[1:],
                ),
            ),
            id="color",
        ),
        pytest.param(
            lambda s: dataclasses.replace(
                s,
                states=(
                    StateSnapshot(
                        atoms=(
                            dataclasses.replace(s.states[0].atoms[0], reps=()),
                            *s.states[0].atoms[1:],
                        )
                    ),
                    *s.states[1:],
                ),
            ),
            id="reps",
        ),
        pytest.param(
            lambda s: dataclasses.replace(
                s,
                states=(
                    StateSnapshot(
                        atoms=(
                            dataclasses.replace(
                                s.states[0].atoms[1], label="different"
                            ),
                            s.states[0].atoms[0],
                            *s.states[0].atoms[2:],
                        )
                    ),
                    *s.states[1:],
                ),
            ),
            id="label",
        ),
        pytest.param(
            lambda s: dataclasses.replace(
                s, bonds=(BondRecord(0, 1, 2), *s.bonds[1:])
            ),
            id="bond-order",
        ),
        pytest.param(
            lambda s: dataclasses.replace(s, states=(*s.states, s.states[0])),
            id="added-state",
        ),
    ],
)
def test_structure_digest_changes_with_every_structural_field(
    mutate: object,
) -> None:
    """Each structural mutation moves the digest away from the original.

    Args:
        mutate: A callable producing a mutated snapshot from the original.
    """
    original = _sample_snapshot()
    mutated = mutate(original)  # type: ignore[operator]

    assert structure_digest(original) != structure_digest(mutated)


def test_structure_digest_is_a_prefixed_sha256_hex_string() -> None:
    """The digest matches this repository's sha256:<hex> wire convention."""
    digest = structure_digest(_sample_snapshot())

    assert digest.startswith("sha256:")
    hex_part = digest.removeprefix("sha256:")
    assert len(hex_part) == 64
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_diff_reports_identity_and_state_mutations() -> None:
    """Diff reports independent mutations instead of trusting equal extracts."""
    snapshot = _sample_snapshot()
    atom = snapshot.states[0].atoms[0]
    mutated_atom = dataclasses.replace(
        atom,
        coord=(atom.coord[0] + 1.0, atom.coord[1], atom.coord[2]),
        color=atom.color + 1,
        label="mutated label",
        reps=atom.reps[1:],
    )
    mutated = dataclasses.replace(
        snapshot,
        name="other-object",
        enabled=not snapshot.enabled,
        schema_version=SNAPSHOT_VERSION + 1,
        unsupported=(),
        states=(
            dataclasses.replace(
                snapshot.states[0],
                atoms=(mutated_atom, *snapshot.states[0].atoms[1:]),
            ),
            *snapshot.states[1:],
        ),
    )

    mismatches = diff(snapshot, mutated)

    assert any("object.name" in mismatch for mismatch in mismatches)
    assert any("object.enabled" in mismatch for mismatch in mismatches)
    assert any("schema_version" in mismatch for mismatch in mismatches)
    assert any("object.unsupported" in mismatch for mismatch in mismatches)
    assert any("state0.atom0.coord" in mismatch for mismatch in mismatches)
    assert any("state0.atom0.color" in mismatch for mismatch in mismatches)
    assert any("state0.atom0.label" in mismatch for mismatch in mismatches)
    assert any("state0.atom0.reps" in mismatch for mismatch in mismatches)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
