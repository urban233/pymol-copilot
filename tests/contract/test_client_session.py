# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for target resolution and live extraction: no PyMOL.

Covers `pmc_client.session.resolve_target_object()`'s own deterministic,
fail-closed logic (zero, one, and more than one candidate, and a
measurement object never interfering with resolution) against a small
hand-written fake session, plus one end-to-end proof that
`extract_live_snapshot()` returns a digest matching
`pmc_core.snapshot.structure_digest` of the snapshot it also returns. The
real-PyMOL evidence for `pmc_core.snapshot.extract()`'s own field-by-field
correctness already lives in tests/contract/test_snapshot.py and
tests/integration/test_snapshot_round_trip.py; this module does not
repeat it.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from dataclasses import dataclass
from dataclasses import field

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_client.session import TargetResolutionError
from pmc_client.session import extract_live_snapshot
from pmc_client.session import resolve_target_object
from pmc_core.snapshot import structure_digest


@dataclass(frozen=True)
class _FakeAtom:
    """One in-memory atom record a `_FakeSession` can serve."""

    id: int
    name: str
    alt: str
    resn: str
    chain: str
    resi_number: int
    ins_code: str
    symbol: str
    hetatm: bool
    q: float
    b: float
    coord: tuple[float, float, float]
    color: int
    label: str | None
    reps: tuple[str, ...]


@dataclass(frozen=True)
class _FakeBond:
    """One in-memory bond record a `_FakeSession` can serve."""

    index: tuple[int, int]
    order: int


@dataclass(frozen=True)
class _FakeModel:
    """A minimal chempy-model stand-in exposing `.atom` and `.bond`."""

    atom: list[_FakeAtom] = field(default_factory=list)
    bond: list[_FakeBond] = field(default_factory=list)


class _FakeSession:
    """A minimal `PyMOLSession` stand-in backed by in-memory records.

    `iterate()` evaluates its expression the same way real PyMOL does --
    as a Python statement run once per matching atom against a namespace
    combining the atom's own fields and the caller's `space` -- rather
    than hardcoding the two expressions `pmc_core.snapshot.extract()`
    happens to use today, so this fake stays correct if that module's own
    query pattern changes.
    """

    def __init__(
        self,
        *,
        molecule_names: tuple[str, ...] = (),
        measurement_names: tuple[str, ...] = (),
        atoms: tuple[_FakeAtom, ...] = (),
        bonds: tuple[_FakeBond, ...] = (),
    ) -> None:
        """Build a fake session from a fixed set of names and atoms.

        Args:
            molecule_names: Names resolving to `object:molecule`.
            measurement_names: Names resolving to `object:measurement`.
            atoms: The one state's worth of atoms every molecule shares.
            bonds: The bonds between those atoms.
        """
        self._molecule_names = molecule_names
        self._measurement_names = measurement_names
        self._atoms = atoms
        self._bonds = bonds

    def get_names(
        self,
        kind: str = "objects",  # noqa: ARG002
        *,
        enabled_only: int = 0,
    ) -> list[str]:
        """Return every object name this fake session knows.

        `kind` and `enabled_only` keep `PyMOLSession`'s own parameter
        names, not underscore-prefixed stand-ins: pyrefly's structural
        Protocol check requires a matching name for a parameter callable
        by keyword, and `extract()` genuinely calls this one by keyword
        (`cmd.get_names("objects", enabled_only=1)`).

        Args:
            kind: Ignored; this fake carries only objects.
            enabled_only: Every fake object counts as enabled regardless
                of this value, so 0 and 1 return the same list; PyMOL
                itself accepts no other value here.

        Returns:
            Every molecule and measurement name.
        """
        assert enabled_only in (0, 1)
        return [*self._molecule_names, *self._measurement_names]

    def get_type(self, name: str) -> str:
        """Return the fake type string for one named object.

        Args:
            name: The object name to look up.

        Returns:
            "object:molecule" or "object:measurement".
        """
        if name in self._molecule_names:
            return "object:molecule"
        return "object:measurement"

    def count_states(self, selection: str) -> int:  # noqa: ARG002
        """Return the fixed one-state count this fake session serves.

        Args:
            selection: Ignored; this fake has exactly one state.

        Returns:
            1.
        """
        return 1

    def get_model(self, selection: str, *, state: int) -> _FakeModel:  # noqa: ARG002
        """Return every fake atom and bond as one chempy-like model.

        `selection` and `state` keep `PyMOLSession`'s own parameter names
        for the same reason `get_names()` above does.

        Args:
            selection: Ignored; this fake has one object's worth of atoms.
            state: Must be 1, the only state `count_states()` reports.

        Returns:
            The fake model.
        """
        assert state == 1
        return _FakeModel(atom=list(self._atoms), bond=list(self._bonds))

    def iterate(
        self, selection: str, expression: str, *, space: dict[str, object]
    ) -> None:
        """Evaluate `expression` once per atom matching `selection`.

        Args:
            selection: An object name, optionally followed by
                " and rep <name>" -- the only two selection shapes
                pmc_core.snapshot.extract() builds.
            expression: The Python statement to evaluate per atom.
            space: The namespace mutated by `expression`.
        """
        rep_filter = None
        if " and rep " in selection:
            rep_filter = selection.rsplit(" and rep ", 1)[1]
        for atom in self._atoms:
            if rep_filter is not None and rep_filter not in atom.reps:
                continue
            local_namespace = {
                "ID": atom.id,
                "color": atom.color,
                "label": atom.label,
            }
            exec(expression, {}, {**space, **local_namespace})

    def get_view(self) -> tuple[float, ...]:
        """Return a fixed 18-float view.

        Returns:
            18 zeros.
        """
        return tuple(0.0 for _ in range(18))

    def get(self, setting: str, selection: str) -> str:  # noqa: ARG002
        """Return a fixed setting value.

        `setting` and `selection` keep `PyMOLSession`'s own parameter
        names for the same reason `get_names()` above does.

        Args:
            setting: Ignored.
            selection: Ignored.

        Returns:
            A fixed placeholder value.
        """
        return "1.00000"


def _one_atom_session(*, object_name: str = "fx") -> _FakeSession:
    """Build a fake session carrying exactly one molecule with one atom.

    Args:
        object_name: The molecule's name.

    Returns:
        The fake session.
    """
    atom = _FakeAtom(
        id=1,
        name="CA",
        alt="",
        resn="ALA",
        chain="A",
        resi_number=1,
        ins_code="",
        symbol="C",
        hetatm=False,
        q=1.0,
        b=20.0,
        coord=(1.0, 2.0, 3.0),
        color=0,
        label=None,
        reps=(),
    )
    return _FakeSession(molecule_names=(object_name,), atoms=(atom,))


def test_exactly_one_molecule_resolves_to_its_name() -> None:
    """A session with exactly one molecule resolves to it."""
    session = _FakeSession(molecule_names=("fx",))

    assert resolve_target_object(session) == "fx"


def test_zero_molecules_raises_with_the_bounded_zero_message() -> None:
    """An empty session fails closed with a bounded, specific message."""
    session = _FakeSession()

    with pytest.raises(TargetResolutionError, match="no molecular object"):
        resolve_target_object(session)


def test_two_molecules_raises_and_names_both() -> None:
    """More than one candidate fails closed and names every one."""
    session = _FakeSession(molecule_names=("chain_a", "chain_b"))

    with pytest.raises(TargetResolutionError) as excinfo:
        resolve_target_object(session)

    assert "chain_a" in str(excinfo.value)
    assert "chain_b" in str(excinfo.value)


def test_a_measurement_object_does_not_interfere_with_resolution() -> None:
    """A measurement object alongside one molecule still resolves cleanly.

    `get_type()` is what separates the two; a resolver that only checked
    `get_names()` would see two names and refuse to pick one.
    """
    session = _FakeSession(molecule_names=("fx",), measurement_names=("d1",))

    assert resolve_target_object(session) == "fx"


def test_extract_live_snapshot_returns_a_matching_digest() -> None:
    """The returned digest equals structure_digest of the returned snapshot."""
    session = _one_atom_session()

    snapshot, digest = extract_live_snapshot(session, "fx")

    assert snapshot.name == "fx"
    assert len(snapshot.states) == 1
    assert len(snapshot.states[0].atoms) == 1
    assert digest == structure_digest(snapshot)
    assert digest.startswith("sha256:")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
