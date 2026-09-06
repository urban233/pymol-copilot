# Copyright 2026 PyMOL Copilot contributors.
"""Independent-oracle tests against the controlled gold-case fixture.

These tests never import PyMOL. They prove the oracle's expected atom sets
are derived directly from the controlled structure file's own chain field,
by comparing against atom identities read independently in this test module.
"""

from __future__ import annotations

from pathlib import Path

from pmc_data.oracle import expected_chain_atom_ids

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "chain_a_gold_fixture.pdb"
)


def test_expected_chain_a_atom_ids_match_the_known_fixture_layout() -> None:
    """Chain A's expected identities are exactly the fixture's first three atoms, by direct inspection of the controlled file."""
    assert expected_chain_atom_ids(FIXTURE_PATH, "A") == frozenset({1, 2, 3})


def test_expected_chain_b_atom_ids_match_the_known_fixture_layout() -> None:
    """Chain B's expected identities are exactly the fixture's last two atoms, by direct inspection of the controlled file."""
    assert expected_chain_atom_ids(FIXTURE_PATH, "B") == frozenset({4, 5})


def test_expected_atom_ids_for_an_absent_chain_are_empty() -> None:
    """A chain identifier absent from the fixture yields an empty set rather than an error, since the oracle only reports observed membership."""
    assert expected_chain_atom_ids(FIXTURE_PATH, "Z") == frozenset()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__]))
