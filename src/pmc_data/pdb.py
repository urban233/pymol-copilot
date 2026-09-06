# Copyright 2026 PyMOL Copilot contributors.
"""Independent, dependency-free reader for PDB ATOM/HETATM records.

This module never imports PyMOL and never delegates to any PyMOL selection
or parsing facility. It exists so the oracle in pmc_data.oracle can derive
expected atom identities directly from controlled structure file bytes,
independently of the PyMOL selection query the verifier later exercises
against the same file. Only the fixed-column fields needed by the current
gold case -- atom serial number and chain identifier -- are read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdbAtom:
    """One independently parsed ATOM/HETATM record.

    Attributes:
        serial: The atom serial number (PDB columns 7-11).
        chain_id: The chain identifier (PDB column 22).
    """

    serial: int
    chain_id: str


class MalformedPdbRecordError(ValueError):
    """Raised when an ATOM/HETATM record cannot be read independently."""


def read_atoms(pdb_path: Path) -> tuple[PdbAtom, ...]:
    """Read every ATOM/HETATM record from a controlled PDB file.

    Args:
        pdb_path: Path to the controlled PDB file.

    Returns:
        The ordered atom records found in the file.

    Raises:
        MalformedPdbRecordError: If an ATOM/HETATM line's serial number
            is not present or not an integer in its fixed-column field.
    """
    atoms: list[PdbAtom] = []
    text = pdb_path.read_text(encoding="ascii")
    for line in text.splitlines():
        if not (line.startswith("ATOM") or line.startswith("HETATM")):
            continue
        serial_field = line[6:11].strip()
        chain_id = line[21:22].strip()
        try:
            serial = int(serial_field)
        except ValueError as error:
            raise MalformedPdbRecordError(
                f"non-integer atom serial field {serial_field!r} in line: "
                f"{line!r}"
            ) from error
        atoms.append(PdbAtom(serial=serial, chain_id=chain_id))
    return tuple(atoms)


def atom_ids_for_chain(
    atoms: tuple[PdbAtom, ...], chain_id: str
) -> frozenset[int]:
    """Return the stable atom identities belonging to one chain.

    Args:
        atoms: The independently parsed atom records to filter.
        chain_id: The chain identifier to select.

    Returns:
        The frozen set of atom serial numbers whose chain matches chain_id.
    """
    return frozenset(atom.serial for atom in atoms if atom.chain_id == chain_id)
