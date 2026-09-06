# Copyright 2026 PyMOL Copilot contributors.
"""Independent oracle deriving expected chain membership from structure data.

This module never imports PyMOL and never calls a PyMOL selection query. It
computes expected atom identities directly from the controlled structure
file's own records (via `pmc_data.pdb`), so the verifier in
`pmc_data.verifier` can compare a real PyMOL selection against ground truth
that was not produced by the same selection machinery being tested.
"""

from __future__ import annotations

from pathlib import Path

from pmc_data.pdb import atom_ids_for_chain
from pmc_data.pdb import read_atoms


def expected_chain_atom_ids(pdb_path: Path, chain_id: str) -> frozenset[int]:
    """Derive the expected atom identities for one chain, independently.

    Args:
        pdb_path: Path to the controlled structure file.
        chain_id: The chain identifier to compute expected membership for.

    Returns:
        The frozen set of atom identities independently derived from the
        structure file's own chain field, never from a PyMOL selection.
    """
    atoms = read_atoms(pdb_path)
    return atom_ids_for_chain(atoms, chain_id)
