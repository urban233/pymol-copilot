# Copyright 2026 PyMOL Copilot contributors.
"""Unit tests for the independent, dependency-free PDB reader.

These tests never import PyMOL. They prove read_atoms parses the known
controlled fixture correctly and rejects malformed input -- a non-integer
serial field and a line truncated before the chain identifier column --
instead of silently producing a wrong or invisible atom record, and that
atom_ids_for_chain filters by exact chain identity.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pmc_data.pdb import MalformedPdbRecordError
from pmc_data.pdb import PdbAtom
from pmc_data.pdb import atom_ids_for_chain
from pmc_data.pdb import read_atoms

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "chain_a_gold_fixture.pdb"
)


def test_read_atoms_parses_the_known_fixture_layout() -> None:
    """The known fixture's five ATOM records are read in file order with their real serial and chain fields, by direct inspection of the controlled file's own bytes."""
    atoms = read_atoms(FIXTURE_PATH)

    assert atoms == (
        PdbAtom(serial=1, chain_id="A"),
        PdbAtom(serial=2, chain_id="A"),
        PdbAtom(serial=3, chain_id="A"),
        PdbAtom(serial=4, chain_id="B"),
        PdbAtom(serial=5, chain_id="B"),
    )


def test_read_atoms_ignores_non_atom_records(tmp_path: Path) -> None:
    """A non-ATOM/HETATM line (a header or the END record) is skipped rather than misparsed as an atom."""
    pdb_path = tmp_path / "with_header.pdb"
    pdb_path.write_text(
        "HEADER    TEST\n"
        "ATOM      1  CA  ALA A   1      11.104  13.207   2.000  1.00  0.00           C\n"
        "END\n",
        encoding="ascii",
    )

    atoms = read_atoms(pdb_path)

    assert atoms == (PdbAtom(serial=1, chain_id="A"),)


def test_read_atoms_rejects_a_non_integer_serial(tmp_path: Path) -> None:
    """A non-integer atom serial field is rejected rather than silently coerced or skipped."""
    pdb_path = tmp_path / "bad_serial.pdb"
    pdb_path.write_text(
        "ATOM    ???  CA  ALA A   1      11.104  13.207   2.000  1.00  0.00           C\n",
        encoding="ascii",
    )

    with pytest.raises(
        MalformedPdbRecordError, match="non-integer atom serial"
    ):
        read_atoms(pdb_path)


def test_read_atoms_rejects_a_line_truncated_before_the_chain_column(
    tmp_path: Path,
) -> None:
    """A line shorter than the fixed-column chain identifier position is rejected rather than silently reading an empty chain id, which would make that atom disappear from every real chain's expected set instead of surfacing an error."""
    pdb_path = tmp_path / "truncated.pdb"
    # Real column 22 (index 21) holds the chain id; this line ends at
    # index 20, one character too short to contain it at all.
    pdb_path.write_text("ATOM      1  CA  ALA\n", encoding="ascii")

    with pytest.raises(MalformedPdbRecordError, match="line too short"):
        read_atoms(pdb_path)


def test_atom_ids_for_chain_filters_by_exact_chain_identity() -> None:
    """atom_ids_for_chain returns only the serials whose chain_id exactly matches, and an empty set for a chain no atom has."""
    atoms = (
        PdbAtom(serial=1, chain_id="A"),
        PdbAtom(serial=2, chain_id="A"),
        PdbAtom(serial=3, chain_id="B"),
    )

    assert atom_ids_for_chain(atoms, "A") == frozenset({1, 2})
    assert atom_ids_for_chain(atoms, "B") == frozenset({3})
    assert atom_ids_for_chain(atoms, "Z") == frozenset()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
