# cBioMOL - open C++ and Python platform for BioMOLecular visualization and analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
# Source code is available at <https://github.com/urban233/cBioMOL>
# -------------------------------------------------------------------
# It is unlawful to modify or remove this copyright notice.
# -------------------------------------------------------------------
# Please see the accompanying LICENSE file for further information.
# -------------------------------------------------------------------
# Primary author of this source file:
#
# ==============================================================================

"""PyMOL abstraction layer for the cBioMOL AI assistant.

This module provides a thin, typed Python API that sits between the AI
assistant's tool-call engine and the live ``pymol.cmd`` session.

Design contract
---------------
* Every public function maps to exactly one entry in
  ``pymol_copilot.ai.schemas.tool_schemas.TOOL_SCHEMAS``.
* Parameter validation is performed before any ``pymol.cmd`` call, so the
  verification UI in Phase 4 always reflects the actual operation that will
  execute.
* All ``pymol.cmd`` calls are synchronous (blocking).  ``cmd.fetch`` is
  invoked with ``async_=0`` to guarantee that subsequent tool calls operate
  on a fully loaded session state.
* Viewport manipulation (rotate, zoom, clip) is intentionally absent.
  Those operations are handled by the mouse and must not be modelled.

PyMOL API sources (all verified 2026-06-23):
  https://pymolwiki.org/index.php/Fetch
  https://pymolwiki.org/index.php/Load
  https://pymolwiki.org/index.php/Delete
  https://pymolwiki.org/index.php/Get_Names
  https://pymolwiki.org/index.php/Show_as
  https://pymolwiki.org/index.php/Color
  https://pymolwiki.org/index.php/CBC
  https://pymolwiki.org/index.php/Bg_Color
  https://pymolwiki.org/index.php/H_Add
  https://pymolwiki.org/index.php/Select
  https://pymolwiki.org/index.php/Label
  https://pymolwiki.org/index.php/Distance
  https://pymolwiki.org/index.php/Get_Angle
  https://pymolwiki.org/index.php/Align
  https://pymolwiki.org/index.php/Ray
  https://pymolwiki.org/index.php/Png
  https://pymolwiki.org/index.php/Save
  https://pymolwiki.org/index.php/Reinitialize
"""

from __future__ import annotations

import re
from typing import Optional

import pymol.cmd as _default_cmd
import pymol.util

import pymol_copilot.ai.execution.session_context as session_context_module


def _cmd():
    """Return the active PyMOL cmd API for wrapper dispatch.

    Returns:
      Context-bound cmd object, or the process-default ``pymol.cmd``.
    """
    active = session_context_module.get_active_cmd()
    if active is not None:
        return active
    return _default_cmd


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_VALID_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VALID_CHAIN_RE = re.compile(r"^[A-Za-z]$")
_VALID_PDB_ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")

_VALID_REPRESENTATIONS: frozenset[str] = frozenset(
    {
        "cartoon",
        "sticks",
        "spheres",
        "surface",
        "ribbon",
        "lines",
        "dots",
    }
)

_VALID_LABEL_TYPES: frozenset[str] = frozenset(
    {
        "residue_name",
        "residue_number",
        "chain",
        "b_factor",
        "none",
    }
)

_VALID_COORDINATE_FORMATS: frozenset[str] = frozenset(
    {
        "pdb",
        "mmcif",
        "mol2",
    }
)

_LABEL_EXPRESSIONS: dict[str, str] = {
    "residue_name": '"%s%s" % (resn, resi)',
    "residue_number": "resi",
    "chain": "chain",
    "b_factor": "b",
    "none": '""',
}


class WrapperError(ValueError):
    """Raised when a wrapper function receives an invalid argument.

    Callers (the verification UI and the tool-call dispatcher) must catch
    this exception and surface its message to the user before any PyMOL
    state is modified.
    """


def _require_non_empty_string(value: str, param_name: str) -> None:
    """Validate that a string parameter is non-empty.

    Args:
      value: The string value to check.
      param_name: The parameter name used in the error message.

    Raises:
      WrapperError: If ``value`` is empty or contains only whitespace.
    """
    if not value or not value.strip():
        raise WrapperError(
            f"Parameter '{param_name}' must be a non-empty string."
        )


def _require_valid_chain(chain: str) -> None:
    """Validate that a chain identifier is a single ASCII letter.

    Args:
      chain: The chain identifier to validate.

    Raises:
      WrapperError: If ``chain`` is not a single ASCII letter.
    """
    if not _VALID_CHAIN_RE.match(chain):
        raise WrapperError(
            f"Chain identifier must be a single letter; got '{chain}'."
        )


def _require_valid_pdb_id(pdb_id: str) -> None:
    """Validate that a PDB accession code follows the 4-character format.

    Args:
      pdb_id: The PDB accession code to validate.

    Raises:
      WrapperError: If ``pdb_id`` does not match the expected pattern.
    """
    if not _VALID_PDB_ID_RE.match(pdb_id.upper()):
        raise WrapperError(
            f"'{pdb_id}' is not a valid 4-letter PDB accession code."
        )


def _build_residue_selection(
    object_name: str,
    chain: str,
    residue_ids: list[int],
) -> str:
    """Compose a PyMOL selection-algebra string from typed components.

    The model never writes raw selection algebra; the wrapper builds it
    from validated typed arguments.

    Args:
      object_name: Name of the PyMOL object to select within.
      chain: Chain identifier letter.
      residue_ids: List of integer residue sequence numbers.

    Returns:
      A PyMOL selection-algebra string that selects the specified residues.
    """
    resi_list = "+".join(str(r) for r in residue_ids)
    return f"{object_name} and chain {chain} and resi {resi_list}"


def _build_atom_selection(
    object_name: str,
    chain: str,
    residue_id: int,
    atom_name: str,
) -> str:
    """Compose a PyMOL atom-level selection string from typed components.

    Args:
      object_name: Name of the PyMOL object.
      chain: Chain identifier letter.
      residue_id: Residue sequence number.
      atom_name: Atom name as it appears in the PDB file.

    Returns:
      A PyMOL full-atom selection string.
    """
    return f"/{object_name}//{chain}/{residue_id}/{atom_name}"


# ---------------------------------------------------------------------------
# Category A — Structure Loading
# ---------------------------------------------------------------------------


def load_structure(
    pdb_id: str,
    object_name: Optional[str] = None,
) -> str:
    """Download and load a structure from the RCSB PDB by accession code.

    Wraps ``pymol.cmd.fetch`` with ``async_=0`` (synchronous) so that
    subsequent tool calls can safely reference the loaded object.

    Args:
      pdb_id: 4-letter RCSB PDB accession code (case-insensitive).
      object_name: Name for the PyMOL object; defaults to the PDB code.

    Returns:
      The name of the object as loaded into the PyMOL session.

    Raises:
      WrapperError: If ``pdb_id`` does not match the expected format.
    """
    pdb_id_upper = pdb_id.upper()
    _require_valid_pdb_id(pdb_id_upper)
    name = object_name.strip() if object_name else pdb_id_upper
    _cmd().fetch(pdb_id_upper, name=name, async_=0)
    return name


def load_local_file(
    file_path: str,
    object_name: Optional[str] = None,
) -> str:
    """Load a molecular structure from a file on disk.

    Wraps ``pymol.cmd.load``.  Supported formats: PDB, mmCIF, MOL2.

    Args:
      file_path: Absolute or relative path to the structure file.
      object_name: Name for the PyMOL object; defaults to the filename stem.

    Returns:
      The name of the object as loaded into the PyMOL session.

    Raises:
      WrapperError: If ``file_path`` is empty.
    """
    _require_non_empty_string(file_path, "file_path")
    name = object_name.strip() if object_name else ""
    _cmd().load(file_path, object=name)
    # cmd.load derives the object name from the filename when object="".
    # Return the effective object name by querying loaded objects.
    names = _cmd().get_names(type="objects")
    return names[-1] if names else (name or file_path)


def remove_object(object_name: str) -> None:
    """Delete a named object or selection from the PyMOL session.

    Wraps ``pymol.cmd.delete``.

    Args:
      object_name: Exact name of the object or selection to delete.

    Raises:
      WrapperError: If ``object_name`` is empty.
    """
    _require_non_empty_string(object_name, "object_name")
    _cmd().delete(object_name)


def list_loaded_objects() -> list[str]:
    """Return the names of all objects loaded in the current PyMOL session.

    Wraps ``pymol.cmd.get_names`` with ``type="objects"``.

    Returns:
      A list of object name strings; empty if no objects are loaded.
    """
    return _cmd().get_names(type="objects")


# ---------------------------------------------------------------------------
# Category B — Representation
# ---------------------------------------------------------------------------


def set_representation(target: str, style: str) -> None:
    """Replace all representations of a target with a single visual style.

    Calls ``cmd.hide("everything", target)`` followed by
    ``cmd.show(style, target)`` so that accumulated representations are
    cleared before the new one is applied.

    Args:
      target: PyMOL object name, selection name, or 'all'.
      style: Representation name; must be one of the valid enum values.

    Raises:
      WrapperError: If ``target`` is empty or ``style`` is not in the enum.
    """
    _require_non_empty_string(target, "target")
    if style not in _VALID_REPRESENTATIONS:
        raise WrapperError(
            f"'{style}' is not a valid representation.  Choose from:"
            f" {sorted(_VALID_REPRESENTATIONS)}."
        )
    _cmd().hide("everything", target)
    _cmd().show(style, target)


def color_by_scheme(target: str, color: str) -> None:
    """Apply a color or color scheme to a PyMOL object or selection.

    Scheme keywords ('spectrum', 'b', 'chainbows') are dispatched to
    ``cmd.spectrum``; named colors are dispatched to ``cmd.color``.

    Args:
      target: PyMOL object name, selection name, or 'all'.
      color: Named PyMOL color (e.g. 'red') or scheme keyword.

    Raises:
      WrapperError: If ``target`` or ``color`` is empty.
    """
    _require_non_empty_string(target, "target")
    _require_non_empty_string(color, "color")
    _SCHEME_KEYWORDS: frozenset[str] = frozenset({"spectrum", "b", "chainbows"})
    if color in _SCHEME_KEYWORDS:
        _cmd().spectrum(color, target)
    else:
        _cmd().color(color, target)


def color_by_chain(object_name: str) -> None:
    """Assign a distinct color to each chain in a PyMOL object.

    Wraps ``pymol.util.cbc`` (chain-based coloring), which cycles through
    a predefined color palette assigning each chain a unique color.

    Args:
      object_name: Name of the PyMOL object to color, or 'all'.

    Raises:
      WrapperError: If ``object_name`` is empty.
    """
    _require_non_empty_string(object_name, "object_name")
    pymol.util.cbc(object_name)


def color_by_secondary_structure(object_name: str) -> None:
    """Color residues by secondary structure assignment.

    Wraps ``pymol.util.ss``, which assigns helix, sheet, and loop residues
    distinct colors using PyMOL's secondary-structure coloring scheme.

    Args:
      object_name: Name of the PyMOL object to color.

    Raises:
      WrapperError: If ``object_name`` is empty.
    """
    _require_non_empty_string(object_name, "object_name")
    pymol.util.ss(object_name)


def set_background_color(color: str) -> None:
    """Set the PyMOL viewport background color.

    Wraps ``pymol.cmd.bg_color``.

    Args:
      color: Named PyMOL color for the background (e.g. 'white', 'black').

    Raises:
      WrapperError: If ``color`` is empty.
    """
    _require_non_empty_string(color, "color")
    _cmd().bg_color(color)


def add_hydrogens(target: str) -> None:
    """Add missing hydrogen atoms to a structure.

    Wraps ``pymol.cmd.h_add``.  The algorithm uses valence rules to
    determine the appropriate number and positions of hydrogen atoms.

    Args:
      target: PyMOL object name, selection name, or 'all'.

    Raises:
      WrapperError: If ``target`` is empty.
    """
    _require_non_empty_string(target, "target")
    _cmd().h_add(target)


# ---------------------------------------------------------------------------
# Category C — Selection & Annotation
# ---------------------------------------------------------------------------


def select_residues(
    name: str,
    object_name: str,
    chain: str,
    residue_ids: list[int],
) -> str:
    """Create a named selection from a list of residue sequence numbers.

    Wraps ``pymol.cmd.select`` with a composed selection-algebra string.
    The model never writes raw selection algebra; this function builds it
    from typed, validated components.

    Args:
      name: Label for the selection (must be a valid Python identifier).
      object_name: Name of the PyMOL object to select within.
      chain: Single chain identifier letter (e.g. 'A').
      residue_ids: List of integer residue sequence numbers.

    Returns:
      The name of the created selection.

    Raises:
      WrapperError: If any argument fails validation or residue_ids is empty.
    """
    _require_non_empty_string(name, "name")
    _require_non_empty_string(object_name, "object_name")
    _require_valid_chain(chain)
    if not residue_ids:
        raise WrapperError("'residue_ids' must contain at least one residue.")
    selection = _build_residue_selection(object_name, chain, residue_ids)
    _cmd().select(name, selection)
    return name


def select_by_proximity(
    name: str,
    reference_selection: str,
    radius_angstrom: float,
) -> str:
    """Create a named selection of atoms within a radius of a reference.

    Wraps ``pymol.cmd.select`` with an ``expand`` selection-algebra operator.

    Args:
      name: Label for the resulting selection.
      reference_selection: Existing PyMOL object or selection to expand around.
      radius_angstrom: Expansion radius in Angstroms (0.1 – 30.0).

    Returns:
      The name of the created selection.

    Raises:
      WrapperError: If any argument fails validation.
    """
    _require_non_empty_string(name, "name")
    _require_non_empty_string(reference_selection, "reference_selection")
    if not (0.1 <= radius_angstrom <= 30.0):
        raise WrapperError(
            f"'radius_angstrom' must be between 0.1 and 30.0; got {radius_angstrom}."
        )
    selection = f"({reference_selection}) expand {radius_angstrom}"
    _cmd().select(name, selection)
    return name


def select_chain(name: str, object_name: str, chain: str) -> str:
    """Create a named selection containing all atoms in a single chain.

    Wraps ``pymol.cmd.select`` with a chain-scoped expression.

    Args:
      name: Label for the selection.
      object_name: Name of the PyMOL object to select from.
      chain: Chain identifier letter.

    Returns:
      The name of the created selection.

    Raises:
      WrapperError: If any argument fails validation.
    """
    _require_non_empty_string(name, "name")
    _require_non_empty_string(object_name, "object_name")
    _require_valid_chain(chain)
    _cmd().select(name, f"{object_name} and chain {chain}")
    return name


def select_ligands(name: str, object_name: str) -> str:
    """Create a named selection of all HETATM records in an object.

    Wraps ``pymol.cmd.select`` with the ``hetatm`` selector keyword, which
    matches all heterogen atoms (ligands, cofactors, waters, ions).

    Args:
      name: Label for the selection.
      object_name: Name of the PyMOL object to select from.

    Returns:
      The name of the created selection.

    Raises:
      WrapperError: If any argument fails validation.
    """
    _require_non_empty_string(name, "name")
    _require_non_empty_string(object_name, "object_name")
    _cmd().select(name, f"{object_name} and hetatm")
    return name


def label_residues(target: str, label_type: str) -> None:
    """Add or remove text labels on atoms in a selection or object.

    Wraps ``pymol.cmd.label`` with a Python expression derived from the
    ``label_type`` enum.  Passing 'none' removes all labels.

    Args:
      target: PyMOL object name or selection name to label.
      label_type: One of the valid label-type enum values.

    Raises:
      WrapperError: If ``target`` is empty or ``label_type`` is not in enum.
    """
    _require_non_empty_string(target, "target")
    if label_type not in _VALID_LABEL_TYPES:
        raise WrapperError(
            f"'{label_type}' is not a valid label type.  Choose from:"
            f" {sorted(_VALID_LABEL_TYPES)}."
        )
    expr = _LABEL_EXPRESSIONS[label_type]
    _cmd().label(target, expr)


# ---------------------------------------------------------------------------
# Category D — Measurement
# ---------------------------------------------------------------------------


def measure_distance(
    atom1: dict,
    atom2: dict,
    measurement_name: str,
) -> str:
    """Measure and display the distance between two atoms.

    Wraps ``pymol.cmd.distance``.  The result is shown as a dashed line in
    the viewport labeled with the distance in Angstroms.

    Each atom is specified as a dict with keys:
      ``object_name`` (str), ``chain`` (str), ``residue_id`` (int),
      ``atom_name`` (str).

    Args:
      atom1: AtomSelector dict for the first atom.
      atom2: AtomSelector dict for the second atom.
      measurement_name: Name for the distance object in PyMOL.

    Returns:
      The name of the created distance measurement object.

    Raises:
      WrapperError: If any argument fails validation.
    """
    _require_non_empty_string(measurement_name, "measurement_name")
    sel1 = _build_atom_selection(
        atom1["object_name"],
        atom1["chain"],
        atom1["residue_id"],
        atom1["atom_name"],
    )
    sel2 = _build_atom_selection(
        atom2["object_name"],
        atom2["chain"],
        atom2["residue_id"],
        atom2["atom_name"],
    )
    _cmd().distance(measurement_name, sel1, sel2)
    return measurement_name


def measure_angle(
    atom1: dict,
    atom2_vertex: dict,
    atom3: dict,
    measurement_name: str,
) -> str:
    """Measure and display the angle defined by three atoms.

    Wraps ``pymol.cmd.angle``.  The central atom (``atom2_vertex``) is the
    vertex of the angle.  The result is shown as an arc in the viewport.

    Each atom is specified as a dict with keys:
      ``object_name`` (str), ``chain`` (str), ``residue_id`` (int),
      ``atom_name`` (str).

    Args:
      atom1: AtomSelector dict for the first arm atom.
      atom2_vertex: AtomSelector dict for the central vertex atom.
      atom3: AtomSelector dict for the second arm atom.
      measurement_name: Name for the angle object in PyMOL.

    Returns:
      The name of the created angle measurement object.

    Raises:
      WrapperError: If any argument fails validation.
    """
    _require_non_empty_string(measurement_name, "measurement_name")
    sel1 = _build_atom_selection(
        atom1["object_name"],
        atom1["chain"],
        atom1["residue_id"],
        atom1["atom_name"],
    )
    sel2 = _build_atom_selection(
        atom2_vertex["object_name"],
        atom2_vertex["chain"],
        atom2_vertex["residue_id"],
        atom2_vertex["atom_name"],
    )
    sel3 = _build_atom_selection(
        atom3["object_name"],
        atom3["chain"],
        atom3["residue_id"],
        atom3["atom_name"],
    )
    _cmd().angle(measurement_name, sel1, sel2, sel3)
    return measurement_name


def show_contacts(
    selection1: str,
    selection2: str,
    cutoff_angstrom: float,
    name: str,
) -> str:
    """Display inter-atomic contacts between two selections.

    Wraps ``pymol.cmd.distance`` with ``mode=0`` (all contacts within the
    cutoff, not just hydrogen bonds).  Each contact is rendered as a
    dashed line in the viewport.

    Args:
      selection1: First PyMOL object or selection name.
      selection2: Second PyMOL object or selection name.
      cutoff_angstrom: Maximum distance in Angstroms (0.5 – 10.0).
      name: Name for the contact-distance object.

    Returns:
      The name of the created contact-distance object.

    Raises:
      WrapperError: If any argument fails validation.
    """
    _require_non_empty_string(selection1, "selection1")
    _require_non_empty_string(selection2, "selection2")
    _require_non_empty_string(name, "name")
    if not (0.5 <= cutoff_angstrom <= 10.0):
        raise WrapperError(
            f"'cutoff_angstrom' must be between 0.5 and 10.0; got {cutoff_angstrom}."
        )
    _cmd().distance(
        name, selection1, selection2, cutoff=cutoff_angstrom, mode=0
    )
    return name


# ---------------------------------------------------------------------------
# Category E — Comparison & Alignment
# ---------------------------------------------------------------------------


def align_structures(
    mobile: str,
    target: str,
    mobile_chain: Optional[str] = None,
    target_chain: Optional[str] = None,
) -> None:
    """Structurally superpose a mobile object onto a fixed target.

    Uses ``pymol.cmd.super`` (sequence-independent structural alignment)
    rather than ``cmd.align`` so that the function works correctly for
    homologs and structures with low sequence identity.

    When chain arguments are provided, alignment is restricted to the
    specified chains.

    Args:
      mobile: Name of the PyMOL object to move (the structure being aligned).
      target: Name of the PyMOL object to use as the fixed reference.
      mobile_chain: Restrict to this chain in the mobile object; None = all.
      target_chain: Restrict to this chain in the target object; None = all.

    Raises:
      WrapperError: If object names are empty or chain identifiers are invalid.
    """
    _require_non_empty_string(mobile, "mobile")
    _require_non_empty_string(target, "target")
    if mobile_chain is not None:
        _require_valid_chain(mobile_chain)
    if target_chain is not None:
        _require_valid_chain(target_chain)

    mobile_sel = (
        f"{mobile} and chain {mobile_chain}" if mobile_chain else mobile
    )
    target_sel = (
        f"{target} and chain {target_chain}" if target_chain else target
    )
    _cmd().super(mobile_sel, target_sel)


# ---------------------------------------------------------------------------
# Category F — Export & Session
# ---------------------------------------------------------------------------


def save_image(
    file_path: str,
    width: int = 1920,
    height: int = 1080,
    dpi: int = 300,
    ray_trace: bool = False,
) -> None:
    """Save the current viewport as a PNG image file.

    When ``ray_trace`` is True, ``cmd.ray`` is called first to produce a
    high-quality rendered image with shadows and ambient occlusion.
    When False, the rasterized view is saved directly (fast preview).

    Args:
      file_path: Output file path; must end with '.png'.
      width: Image width in pixels (100 – 8000).
      height: Image height in pixels (100 – 8000).
      dpi: Dots per inch for the output file (72 – 600).
      ray_trace: If True, run ray-tracing before saving.

    Raises:
      WrapperError: If arguments fail validation.
    """
    _require_non_empty_string(file_path, "file_path")
    if not file_path.lower().endswith(".png"):
        raise WrapperError("'file_path' must end with '.png'.")
    if not (100 <= width <= 8000):
        raise WrapperError(
            f"'width' must be between 100 and 8000; got {width}."
        )
    if not (100 <= height <= 8000):
        raise WrapperError(
            f"'height' must be between 100 and 8000; got {height}."
        )
    if not (72 <= dpi <= 600):
        raise WrapperError(f"'dpi' must be between 72 and 600; got {dpi}.")
    if ray_trace:
        _cmd().ray(width, height)
    _cmd().png(file_path, dpi=dpi)


def save_session(file_path: str) -> None:
    """Save the entire PyMOL session to a .pse file.

    Wraps ``pymol.cmd.save`` with a .pse extension.  All loaded objects,
    selections, representations, and measurements are preserved.

    Args:
      file_path: Output file path; must end with '.pse'.

    Raises:
      WrapperError: If ``file_path`` is empty or has the wrong extension.
    """
    _require_non_empty_string(file_path, "file_path")
    if not file_path.lower().endswith(".pse"):
        raise WrapperError("'file_path' must end with '.pse'.")
    _cmd().save(file_path)


def export_coordinates(
    target: str,
    file_path: str,
    format: str,  # noqa: A002
) -> None:
    """Export atomic coordinates to a molecular structure file.

    Wraps ``pymol.cmd.save`` with the appropriate file extension.
    Supported formats: pdb, mmcif, mol2.

    Args:
      target: PyMOL object name or selection to export.
      file_path: Output file path including the correct extension.
      format: File format; one of 'pdb', 'mmcif', 'mol2'.

    Raises:
      WrapperError: If any argument fails validation.
    """
    _require_non_empty_string(target, "target")
    _require_non_empty_string(file_path, "file_path")
    if format not in _VALID_COORDINATE_FORMATS:
        raise WrapperError(
            f"'{format}' is not a valid coordinate format.  Choose from:"
            f" {sorted(_VALID_COORDINATE_FORMATS)}."
        )
    _cmd().save(file_path, target)
