# build_conversations.py
"""
Deterministically assembles the ChatML `conversations` field from the raw
Data Designer output, and validates every assistant turn against the real
tool_schemas.TOOL_SCHEMAS_BY_NAME (22 tools, including nested
atom-selector objects) before it's allowed into the training set.

Why this lives in Python and not in a Data Designer expression column
----------------------------------------------------------------------
The tool-only parameters (atom names, residue-id lists, measurement and
object names, radii, cutoffs) don't come from the LLM or from simple
category samplers — they're synthesized here from a per-row seeded RNG so
the dataset is reproducible, and every generated call is checked against
the JSON Schema it will actually be graded/parsed against at inference.

LangGraph agent context
-----------------------
The fine-tuned model is the *planner* of a LangGraph agent.  Given a
single user prompt the model must emit the complete ordered sequence of
tool calls — up to 25 calls for the deepest scenarios.  The training
examples produced here are the ground-truth plans the model learns from.

PyMOL selection algebra
-----------------------
The wrapper functions in pymol_wrapper.py accept ``reference_selection``
and related string parameters that are passed verbatim to
``pymol.cmd.select``.  The builders here compose realistic selection-
algebra strings (using ``and``, ``or``, ``not``, ``byres``, ``hetatm``,
``resn``, ``within``) so the model learns that those arguments are
PyMOL selection expressions, not bare object names.

Usage:
    python build_conversations.py \\
        --input  output_raw/cbiomol_pymol_sft.jsonl \\
        --output output_raw/cbiomol_pymol_sft_conversations.jsonl \\
        --rejects output_raw/rejects.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys

from jsonschema import Draft7Validator

from tool_schemas import TOOL_SCHEMAS_BY_NAME

VALIDATORS = {
    name: Draft7Validator(schema["parameters"])
    for name, schema in TOOL_SCHEMAS_BY_NAME.items()
}

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

AMINO_ATOMS: list[str] = [
    "CA", "CB", "N", "O", "CG", "CD1", "OG1", "NZ", "OE1", "ND2",
    "NE2", "OD1", "CE1", "SG", "OH",
]

RESIDUE_LABELS: list[str] = [
    "active_site", "binding_pocket", "interface_residues",
    "mutation_site", "catalytic_triad", "cdr_loop",
]

CATALYTIC_RESIDUES: list[str] = [
    "HIS", "ASP", "SER", "CYS", "GLU", "LYS", "ARG", "TYR",
]

# Extended 20-color palette for multi-chain coloring scenarios.
EXTENDED_COLORS: list[str] = [
    "marine", "firebrick", "forest", "slate", "orange", "purple",
    "teal", "hotpink", "wheat", "cyan", "yellow", "magenta",
    "salmon", "limon", "brightorange", "blue", "red", "green",
    "violet", "deepteal",
]

# CDR loop residue ranges in sequential PDB numbering (Kabat-approximate).
# The biologically meaningful names ("H1 loop", "CDR-L3") are used in the
# user-facing prompt; these ranges seed realistic residue-ID lists.
CDR_LOOP_RANGES: list[tuple[str, str, int, int]] = [
    ("light", "L", 27, 32),   # CDR-L1
    ("light", "L", 50, 52),   # CDR-L2
    ("light", "L", 89, 96),   # CDR-L3
    ("heavy", "H", 26, 32),   # CDR-H1
    ("heavy", "H", 52, 56),   # CDR-H2
    ("heavy", "H", 95, 102),  # CDR-H3
]

_ALL_PDB_IDS: list[str] = [
    "7BZ5", "1BL8", "1A2U", "4PZB", "6LU7", "3HHR", "1QLY", "6VXX",
    "1HHO", "2RH1", "1AKE", "4HHB", "1CRN", "6M0J", "3POZ", "1IGT",
    "2GS6", "1STP", "5XNL", "1UBQ", "3EML", "1XQ8", "6YB7", "1LYZ",
    "2VGB", "4EY7", "1B0Y", "6XC2", "5XSZ", "4V9D", "7K00", "6J8J",
    "2ZW3", "6S9T", "4GH8", "1AON", "1G9I", "3SN6", "6CMO", "1YHT",
    "4HVP", "2HHB", "4AKE", "2BXT", "1IEP",
]

# ---------------------------------------------------------------------------
# Deterministic synthesis helpers
# (seeded per-row — reproducible, not from the LLM, schema-legal by design)
# ---------------------------------------------------------------------------


def _obj_name(pdb_id: str) -> str:
    """Return the canonical PyMOL object name for a PDB ID.

    Args:
      pdb_id: 4-letter PDB accession code.

    Returns:
      Lowercase version of the PDB ID used as the PyMOL object name.
    """
    return pdb_id.lower()


def _atom_selector(
    rng: random.Random,
    object_name: str,
    chain: str,
) -> dict:
    """Generate a random but schema-valid AtomSelector dict.

    Args:
      rng: Seeded random instance for reproducibility.
      object_name: PyMOL object name.
      chain: Chain identifier letter.

    Returns:
      Dict with keys object_name, chain, residue_id, atom_name.
    """
    return {
        "object_name": object_name,
        "chain": chain,
        "residue_id": rng.randint(1, 400),
        "atom_name": rng.choice(AMINO_ATOMS),
    }


def _residue_ids(
    rng: random.Random,
    n: int | None = None,
) -> list[int]:
    """Sample a sorted list of distinct residue sequence numbers.

    Args:
      rng: Seeded random instance.
      n: Number of residues to sample; defaults to a random value 3–8.

    Returns:
      Sorted list of distinct integer residue IDs.
    """
    tmp_n = n if n is not None else rng.randint(3, 8)
    return sorted(rng.sample(range(1, 400), k=tmp_n))


def _unique_pdb_pair(
    pdb_a: str,
    pdb_b: str,
    rng: random.Random,
) -> tuple[str, str]:
    """Ensure two PDB IDs are distinct, re-rolling pdb_b if needed.

    Args:
      pdb_a: Primary PDB accession code.
      pdb_b: Secondary PDB accession code (may equal pdb_a).
      rng: Seeded random instance for the re-roll.

    Returns:
      Tuple (pdb_a, unique_pdb_b) where unique_pdb_b != pdb_a.
    """
    if pdb_b == pdb_a:
        pdb_b = rng.choice([p for p in _ALL_PDB_IDS if p != pdb_a])
    return pdb_a, pdb_b


def _unique_pdb_triple(
    pdb_a: str,
    pdb_b: str,
    pdb_c: str,
    rng: random.Random,
) -> tuple[str, str, str]:
    """Ensure three PDB IDs are all mutually distinct.

    Args:
      pdb_a: First PDB accession code.
      pdb_b: Second PDB accession code.
      pdb_c: Third PDB accession code.
      rng: Seeded random instance for any re-rolls.

    Returns:
      Tuple of three mutually distinct PDB accession codes.
    """
    pdb_a, pdb_b = _unique_pdb_pair(pdb_a, pdb_b, rng)
    tmp_pool = [p for p in _ALL_PDB_IDS if p not in {pdb_a, pdb_b}]
    if pdb_c in {pdb_a, pdb_b}:
        pdb_c = rng.choice(tmp_pool)
    return pdb_a, pdb_b, pdb_c


# ---------------------------------------------------------------------------
# Selection algebra string builders
# ---------------------------------------------------------------------------


def _sel_byres(obj: str, chain: str, resi_list: list[int]) -> str:
    """Build a byres-expanded selection for complete residue coverage.

    Using ``byres`` ensures the selection includes backbone atoms even when
    the original hit was a sidechain atom.  This is the correct pattern
    for labeling, coloring, and exporting complete residues.

    Args:
      obj: PyMOL object name.
      chain: Chain identifier letter.
      resi_list: List of residue sequence numbers.

    Returns:
      PyMOL selection string using byres expansion.
    """
    tmp_resi = "+".join(str(r) for r in resi_list)
    return f"byres ({obj} and chain {chain} and resi {tmp_resi})"


def _sel_ligand_no_water(obj: str) -> str:
    """Build a selection for HETATM records excluding water molecules.

    Crystallographic waters (resn HOH and HOH2) are excluded so that only
    genuine ligands and cofactors are selected.

    Args:
      obj: PyMOL object name.

    Returns:
      PyMOL selection string for non-water heterogen atoms.
    """
    return f"{obj} and hetatm and not resn HOH+HOH2"


def _sel_by_resname(obj: str, chain: str, resnames: list[str]) -> str:
    """Build a selection for residues matching given 3-letter codes.

    Useful for selecting catalytic triads, binding-pocket residues, or any
    set of amino acids by chemical identity rather than sequence number.

    Args:
      obj: PyMOL object name.
      chain: Chain identifier letter.
      resnames: List of 3-letter residue names (e.g. ['HIS', 'ASP', 'SER']).

    Returns:
      PyMOL selection string using resn matching.
    """
    tmp_resn = "+".join(resnames)
    return f"byres ({obj} and chain {chain} and resn {tmp_resn})"


def _sel_within(
    obj: str,
    reference: str,
    radius: float,
    exclude_water: bool = True,
) -> str:
    """Build a within-radius selection around a reference selection.

    Args:
      obj: PyMOL object name to restrict the search to.
      reference: Named selection or object to measure from.
      radius: Distance cutoff in Angstroms.
      exclude_water: If True, append ``and not resn HOH+HOH2``.

    Returns:
      PyMOL selection string using the within operator.
    """
    tmp_base = (
        f"byres ({obj} and polymer within {radius} of ({reference}))"
    )
    if exclude_water:
        return f"{tmp_base} and not resn HOH+HOH2"
    return tmp_base


def _chain_color_sequence(
    n: int,
    rng: random.Random,
) -> list[str]:
    """Sample n distinct colors from the extended palette.

    Args:
      n: Number of distinct colors to return.
      rng: Seeded random instance.

    Returns:
      List of n color name strings drawn without replacement.
    """
    tmp_pool = list(EXTENDED_COLORS)
    rng.shuffle(tmp_pool)
    return tmp_pool[:n]


# ---------------------------------------------------------------------------
# Scenario builders: scenario name -> f(row, rng) -> list[tool_call]
# ---------------------------------------------------------------------------


def _load_and_visualize(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load, set representation, color.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": tmp_obj,
                "style": row["representation_style"],
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": tmp_obj,
                "color": row["pymol_color"],
            },
        },
    ]


def _load_only(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load only.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
    ]


def _chain_coloring(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load, color by chain.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "color_by_chain",
            "parameters": {"object_name": tmp_obj},
        },
    ]


def _secondary_structure_and_background(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build tool calls for: load, representation, SS color, background.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": tmp_obj,
                "style": row["representation_style"],
            },
        },
        {
            "name": "color_by_secondary_structure",
            "parameters": {"object_name": tmp_obj},
        },
        {
            "name": "set_background_color",
            "parameters": {"color": row["background_color"]},
        },
    ]


def _hydrogens_workflow(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load, add hydrogens.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "add_hydrogens",
            "parameters": {"target": tmp_obj},
        },
    ]


def _active_site_selection(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load, select active-site residues, label.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_sel_name = rng.choice(RESIDUE_LABELS)
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_residues",
            "parameters": {
                "name": tmp_sel_name,
                "object_name": tmp_obj,
                "chain": row["chain_letter"],
                "residue_ids": _residue_ids(rng),
            },
        },
        {
            "name": "label_residues",
            "parameters": {
                "target": tmp_sel_name,
                "label_type": row["label_type"],
            },
        },
    ]


def _local_file_workflow(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load local file, set representation.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_stub = row["file_path_stub"]
    tmp_obj = tmp_stub.split("/")[-1].rsplit(".", 1)[0]
    return [
        {
            "name": "load_local_file",
            "parameters": {
                "file_path": tmp_stub,
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": tmp_obj,
                "style": row["representation_style"],
            },
        },
    ]


def _housekeeping_workflow(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load two structures, list, remove one.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_pdb_a, tmp_pdb_b = _unique_pdb_pair(
        row["pdb_id"], row["pdb_id_secondary"], rng
    )
    tmp_obj_a = _obj_name(tmp_pdb_a)
    tmp_obj_b = _obj_name(tmp_pdb_b)
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_a,
                "object_name": tmp_obj_a,
            },
        },
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_b,
                "object_name": tmp_obj_b,
            },
        },
        {"name": "list_loaded_objects", "parameters": {}},
        {
            "name": "remove_object",
            "parameters": {"object_name": tmp_obj_b},
        },
    ]


def _chain_isolation_export(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load, select chain, export coordinates.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_sel_name = f"chain_{row['chain_letter']}"
    tmp_fmt = rng.choice(["pdb", "mmcif", "mol2"])
    tmp_ext = {"pdb": "pdb", "mmcif": "cif", "mol2": "mol2"}[tmp_fmt]
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_chain",
            "parameters": {
                "name": tmp_sel_name,
                "object_name": tmp_obj,
                "chain": row["chain_letter"],
            },
        },
        {
            "name": "export_coordinates",
            "parameters": {
                "target": tmp_sel_name,
                "file_path": (
                    f"./exports/{tmp_obj}_{tmp_sel_name}.{tmp_ext}"
                ),
                "format": tmp_fmt,
            },
        },
    ]


def _binding_site_proximity(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load, select ligand, select pocket, show.

    The pocket selection uses the within operator (selection algebra) as
    the reference_selection argument, teaching the model that this field
    accepts a full PyMOL selection expression.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_lig_sel = _sel_ligand_no_water(tmp_obj)
    tmp_radius = round(rng.uniform(4.0, 8.0), 1)
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_ligands",
            "parameters": {
                "name": "ligands",
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "binding_site",
                "reference_selection": tmp_lig_sel,
                "radius_angstrom": tmp_radius,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": "binding_site",
                "style": row["representation_style"],
            },
        },
    ]


def _measure_distance_workflow(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build tool calls for: load, measure inter-atom distance.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_a1 = _atom_selector(rng, tmp_obj, row["chain_letter"])
    tmp_a2 = _atom_selector(rng, tmp_obj, row["chain_letter"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "measure_distance",
            "parameters": {
                "atom1": tmp_a1,
                "atom2": tmp_a2,
                "measurement_name": (
                    f"dist_{tmp_obj}_"
                    f"{tmp_a1['residue_id']}_{tmp_a2['residue_id']}"
                ),
            },
        },
    ]


def _measure_angle_workflow(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build tool calls for: load, measure bond angle.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_a1 = _atom_selector(rng, tmp_obj, row["chain_letter"])
    tmp_a2 = _atom_selector(rng, tmp_obj, row["chain_letter"])
    tmp_a3 = _atom_selector(rng, tmp_obj, row["chain_letter"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "measure_angle",
            "parameters": {
                "atom1": tmp_a1,
                "atom2_vertex": tmp_a2,
                "atom3": tmp_a3,
                "measurement_name": (
                    f"angle_{tmp_obj}_{tmp_a2['residue_id']}"
                ),
            },
        },
    ]


def _contacts_workflow(row: dict, rng: random.Random) -> list[dict]:
    """Build tool calls for: load, select ligand, show contacts.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_ligands",
            "parameters": {
                "name": "ligands",
                "object_name": tmp_obj,
            },
        },
        {
            "name": "show_contacts",
            "parameters": {
                "selection1": "ligands",
                "selection2": tmp_obj,
                "cutoff_angstrom": round(rng.uniform(3.0, 5.0), 1),
                "name": f"contacts_{tmp_obj}",
            },
        },
    ]


def _align_structures_workflow(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build tool calls for: load two structures, align mobile to target.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_pdb_a, tmp_pdb_b = _unique_pdb_pair(
        row["pdb_id"], row["pdb_id_secondary"], rng
    )
    tmp_obj_a = _obj_name(tmp_pdb_a)
    tmp_obj_b = _obj_name(tmp_pdb_b) + "_mobile"
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_a,
                "object_name": tmp_obj_a,
            },
        },
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_b,
                "object_name": tmp_obj_b,
            },
        },
        {
            "name": "align_structures",
            "parameters": {
                "mobile": tmp_obj_b,
                "target": tmp_obj_a,
            },
        },
    ]


def _export_image_and_session(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build tool calls for: load, representation, save image + session.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": tmp_obj,
                "style": row["representation_style"],
            },
        },
        {
            "name": "save_image",
            "parameters": {
                "file_path": f"./figures/{tmp_obj}.png",
                "ray_trace": rng.choice([True, False]),
            },
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": f"./sessions/{tmp_obj}.pse",
            },
        },
    ]


# ---------------------------------------------------------------------------
# Deep-workflow builders (8–25 tool calls each)
# ---------------------------------------------------------------------------


def _antibody_cdr_analysis(row: dict, rng: random.Random) -> list[dict]:
    """Build 13-call CDR loop selection, coloring, contact, label, export.

    Selects each of the 6 CDR loops by residue range, colors each a
    distinct color, shows contacts at the interface, labels all CDR
    residues by name, and saves a ray-traced figure.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 13 tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_colors = _chain_color_sequence(6, rng)
    tmp_calls: list[dict] = [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
    ]
    # Select each CDR loop; use Kabat-approximate sequential ranges.
    tmp_cdr_names: list[str] = []
    for tmp_idx, (tmp_ab_chain, tmp_chain, tmp_resi_lo, tmp_resi_hi) in (
        enumerate(CDR_LOOP_RANGES)
    ):
        tmp_loop_name = (
            f"cdr_{tmp_ab_chain[0]}{tmp_idx % 3 + 1}"
        )
        tmp_cdr_names.append(tmp_loop_name)
        tmp_ids = list(range(tmp_resi_lo, tmp_resi_hi + 1))
        tmp_calls.append(
            {
                "name": "select_residues",
                "parameters": {
                    "name": tmp_loop_name,
                    "object_name": tmp_obj,
                    "chain": tmp_chain,
                    "residue_ids": tmp_ids,
                },
            }
        )
        tmp_calls.append(
            {
                "name": "color_by_scheme",
                "parameters": {
                    "target": tmp_loop_name,
                    "color": tmp_colors[tmp_idx],
                },
            }
        )
    # Show contacts across the CDR-antigen interface.
    # The antigen is modelled as the partner chain (chain C in most Fabs).
    tmp_calls.append(
        {
            "name": "show_contacts",
            "parameters": {
                "selection1": f"{tmp_obj} and chain L",
                "selection2": f"{tmp_obj} and chain H",
                "cutoff_angstrom": round(rng.uniform(3.5, 5.0), 1),
                "name": f"cdr_contacts_{tmp_obj}",
            },
        }
    )
    # Label all CDR residues by residue name.
    tmp_calls.append(
        {
            "name": "label_residues",
            "parameters": {
                "target": tmp_obj,
                "label_type": "residue_name",
            },
        }
    )
    tmp_calls.append(
        {
            "name": "set_background_color",
            "parameters": {"color": row["background_color"]},
        }
    )
    tmp_calls.append(
        {
            "name": "save_image",
            "parameters": {
                "file_path": f"./figures/{tmp_obj}_cdr.png",
                "ray_trace": True,
            },
        }
    )
    return tmp_calls


def _comparative_binding_site(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 16-call comparative binding-site analysis between two structs.

    Loads two structures, aligns them, selects binding sites in each,
    measures three distances in each, exports both sites, saves session.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of ~16 tool-call dicts.
    """
    tmp_pdb_a, tmp_pdb_b = _unique_pdb_pair(
        row["pdb_id"], row["pdb_id_secondary"], rng
    )
    tmp_obj_a = _obj_name(tmp_pdb_a)
    tmp_obj_b = _obj_name(tmp_pdb_b) + "_alt"
    tmp_lig_a = _sel_ligand_no_water(tmp_obj_a)
    tmp_lig_b = _sel_ligand_no_water(tmp_obj_b)
    tmp_radius = round(rng.uniform(5.0, 7.0), 1)

    tmp_calls: list[dict] = [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_a,
                "object_name": tmp_obj_a,
            },
        },
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_b,
                "object_name": tmp_obj_b,
            },
        },
        {
            "name": "align_structures",
            "parameters": {
                "mobile": tmp_obj_b,
                "target": tmp_obj_a,
            },
        },
        # Select binding sites using within-algebra.
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "site_ref",
                "reference_selection": tmp_lig_a,
                "radius_angstrom": tmp_radius,
            },
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "site_alt",
                "reference_selection": tmp_lig_b,
                "radius_angstrom": tmp_radius,
            },
        },
    ]
    # Three distances in each binding site.
    for tmp_i in range(3):
        tmp_a1 = _atom_selector(rng, tmp_obj_a, row["chain_letter"])
        tmp_a2 = _atom_selector(rng, tmp_obj_a, row["chain_letter"])
        tmp_calls.append(
            {
                "name": "measure_distance",
                "parameters": {
                    "atom1": tmp_a1,
                    "atom2": tmp_a2,
                    "measurement_name": (
                        f"ref_dist{tmp_i + 1}_{tmp_obj_a}"
                    ),
                },
            }
        )
        tmp_b1 = _atom_selector(rng, tmp_obj_b, row["chain_letter"])
        tmp_b2 = _atom_selector(rng, tmp_obj_b, row["chain_letter"])
        tmp_calls.append(
            {
                "name": "measure_distance",
                "parameters": {
                    "atom1": tmp_b1,
                    "atom2": tmp_b2,
                    "measurement_name": (
                        f"alt_dist{tmp_i + 1}_{tmp_obj_b}"
                    ),
                },
            }
        )
    # Export both sites.
    tmp_calls += [
        {
            "name": "export_coordinates",
            "parameters": {
                "target": "site_ref",
                "file_path": f"./exports/{tmp_obj_a}_site.pdb",
                "format": "pdb",
            },
        },
        {
            "name": "export_coordinates",
            "parameters": {
                "target": "site_alt",
                "file_path": f"./exports/{tmp_obj_b}_site.pdb",
                "format": "pdb",
            },
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": (
                    f"./sessions/{tmp_obj_a}_vs_{tmp_obj_b}.pse"
                ),
            },
        },
    ]
    return tmp_calls


def _full_active_site_workflow(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 11-call active-site selection, labeling, measurement workflow.

    Selects catalytic residues by 3-letter code, shows them as sticks,
    labels them, selects ligand (no water), shows contacts, measures two
    distances, and saves the session.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 11 tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_chain = row["chain_letter"]
    # Catalytic triad: primary residue + two partners drawn from constants.
    tmp_primary = row.get("residue_name_3letter", "HIS")
    tmp_partners = [
        r for r in CATALYTIC_RESIDUES
        if r != tmp_primary
    ][:2]
    tmp_triad = [tmp_primary] + tmp_partners
    tmp_triad_sel = _sel_by_resname(tmp_obj, tmp_chain, tmp_triad)
    tmp_lig_sel = _sel_ligand_no_water(tmp_obj)
    tmp_contact_cutoff = round(rng.uniform(3.0, 4.5), 1)
    tmp_a1 = _atom_selector(rng, tmp_obj, tmp_chain)
    tmp_a2 = _atom_selector(rng, tmp_obj, tmp_chain)
    tmp_a3 = _atom_selector(rng, tmp_obj, tmp_chain)
    tmp_a4 = _atom_selector(rng, tmp_obj, tmp_chain)
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "catalytic_triad",
                "reference_selection": tmp_triad_sel,
                "radius_angstrom": 1.0,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": "catalytic_triad",
                "style": "sticks",
            },
        },
        {
            "name": "label_residues",
            "parameters": {
                "target": "catalytic_triad",
                "label_type": "residue_name",
            },
        },
        {
            "name": "select_ligands",
            "parameters": {
                "name": "active_ligand",
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": "active_ligand",
                "style": "sticks",
            },
        },
        {
            "name": "measure_distance",
            "parameters": {
                "atom1": tmp_a1,
                "atom2": tmp_a2,
                "measurement_name": f"active_dist1_{tmp_obj}",
            },
        },
        {
            "name": "measure_distance",
            "parameters": {
                "atom1": tmp_a3,
                "atom2": tmp_a4,
                "measurement_name": f"active_dist2_{tmp_obj}",
            },
        },
        {
            "name": "show_contacts",
            "parameters": {
                "selection1": "catalytic_triad",
                "selection2": "active_ligand",
                "cutoff_angstrom": tmp_contact_cutoff,
                "name": f"triad_contacts_{tmp_obj}",
            },
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": f"./sessions/{tmp_obj}_active_site.pse",
            },
        },
    ]


def _multi_chain_coloring_export(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 8-call workflow: load, show surface, color chains, export two.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 8 tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_chain_a = row["chain_letter"]
    tmp_chain_b = row.get("chain_letter_b", "B")
    tmp_colors = _chain_color_sequence(2, rng)
    tmp_fmt = rng.choice(["pdb", "mmcif"])
    tmp_ext = {"pdb": "pdb", "mmcif": "cif"}[tmp_fmt]
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": tmp_obj,
                "style": row["representation_style"],
            },
        },
        {
            "name": "color_by_chain",
            "parameters": {"object_name": tmp_obj},
        },
        {
            "name": "select_chain",
            "parameters": {
                "name": f"ch_{tmp_chain_a}",
                "object_name": tmp_obj,
                "chain": tmp_chain_a,
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": f"ch_{tmp_chain_a}",
                "color": tmp_colors[0],
            },
        },
        {
            "name": "select_chain",
            "parameters": {
                "name": f"ch_{tmp_chain_b}",
                "object_name": tmp_obj,
                "chain": tmp_chain_b,
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": f"ch_{tmp_chain_b}",
                "color": tmp_colors[1],
            },
        },
        {
            "name": "export_coordinates",
            "parameters": {
                "target": f"ch_{tmp_chain_a}",
                "file_path": (
                    f"./exports/{tmp_obj}_chain{tmp_chain_a}.{tmp_ext}"
                ),
                "format": tmp_fmt,
            },
        },
        {
            "name": "export_coordinates",
            "parameters": {
                "target": f"ch_{tmp_chain_b}",
                "file_path": (
                    f"./exports/{tmp_obj}_chain{tmp_chain_b}.{tmp_ext}"
                ),
                "format": tmp_fmt,
            },
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": f"./sessions/{tmp_obj}_chains.pse",
            },
        },
    ]


def _ligand_environment_deep(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 12-call deep ligand environment analysis.

    Selects ligand (no water), pocket residues, waters near ligand, shows
    contacts, labels pocket, exports pocket, saves ray-traced figure.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 12 tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_lig_sel = _sel_ligand_no_water(tmp_obj)
    tmp_radius_large = float(
        row.get("radius_angstrom_large", str(rng.choice([5.0, 6.0, 8.0])))
    )
    tmp_radius_small = float(
        row.get("radius_angstrom_small", str(rng.choice([3.0, 3.5, 4.0])))
    )
    tmp_contact_cutoff = round(rng.uniform(3.0, 4.5), 1)
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_ligands",
            "parameters": {
                "name": "ligand",
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "pocket_residues",
                "reference_selection": tmp_lig_sel,
                "radius_angstrom": tmp_radius_large,
            },
        },
        # Waters near the ligand (include water this time).
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "waters_near_ligand",
                "reference_selection": tmp_lig_sel,
                "radius_angstrom": tmp_radius_small,
            },
        },
        {
            "name": "set_representation",
            "parameters": {"target": "ligand", "style": "sticks"},
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": "pocket_residues",
                "style": row["representation_style"],
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": "pocket_residues",
                "color": row["pymol_color"],
            },
        },
        {
            "name": "show_contacts",
            "parameters": {
                "selection1": "ligand",
                "selection2": "pocket_residues",
                "cutoff_angstrom": tmp_contact_cutoff,
                "name": f"pocket_contacts_{tmp_obj}",
            },
        },
        {
            "name": "label_residues",
            "parameters": {
                "target": "pocket_residues",
                "label_type": "residue_name",
            },
        },
        {
            "name": "export_coordinates",
            "parameters": {
                "target": "pocket_residues",
                "file_path": f"./exports/{tmp_obj}_pocket.pdb",
                "format": "pdb",
            },
        },
        {
            "name": "set_background_color",
            "parameters": {"color": row["background_color"]},
        },
        {
            "name": "save_image",
            "parameters": {
                "file_path": f"./figures/{tmp_obj}_pocket.png",
                "ray_trace": True,
            },
        },
    ]


def _interface_analysis(row: dict, rng: random.Random) -> list[dict]:
    """Build 14-call protein-protein interface analysis.

    Loads dimer, selects each chain, shows contacts at interface, measures
    four cross-chain distances, colors each chain, sets background, saves
    session and ray-traced figure.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 14 tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_ch_a = row["chain_letter"]
    tmp_ch_b = row.get("chain_letter_b", "B")
    tmp_contact_cutoff = float(
        row.get("radius_angstrom_small", "4.0")
    )
    tmp_calls: list[dict] = [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "select_chain",
            "parameters": {
                "name": f"chain_{tmp_ch_a}",
                "object_name": tmp_obj,
                "chain": tmp_ch_a,
            },
        },
        {
            "name": "select_chain",
            "parameters": {
                "name": f"chain_{tmp_ch_b}",
                "object_name": tmp_obj,
                "chain": tmp_ch_b,
            },
        },
        {
            "name": "show_contacts",
            "parameters": {
                "selection1": f"chain_{tmp_ch_a}",
                "selection2": f"chain_{tmp_ch_b}",
                "cutoff_angstrom": tmp_contact_cutoff,
                "name": f"interface_{tmp_obj}",
            },
        },
    ]
    # Four cross-chain distance measurements.
    for tmp_i in range(4):
        tmp_a1 = _atom_selector(rng, tmp_obj, tmp_ch_a)
        tmp_a2 = _atom_selector(rng, tmp_obj, tmp_ch_b)
        tmp_calls.append(
            {
                "name": "measure_distance",
                "parameters": {
                    "atom1": tmp_a1,
                    "atom2": tmp_a2,
                    "measurement_name": (
                        f"iface_dist{tmp_i + 1}_{tmp_obj}"
                    ),
                },
            }
        )
    tmp_calls += [
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": f"chain_{tmp_ch_a}",
                "color": row["pymol_color"],
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": f"chain_{tmp_ch_b}",
                "color": "slate",
            },
        },
        {
            "name": "set_background_color",
            "parameters": {"color": row["background_color"]},
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": f"./sessions/{tmp_obj}_interface.pse",
            },
        },
        {
            "name": "save_image",
            "parameters": {
                "file_path": f"./figures/{tmp_obj}_interface.png",
                "ray_trace": True,
            },
        },
    ]
    return tmp_calls


def _structure_comparison_full(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 19-call WT vs mutant structure comparison.

    Loads two structures, aligns, selects active sites in both, measures
    three distances in each, colors each, sets background, saves image and
    session.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of ~19 tool-call dicts.
    """
    tmp_pdb_wt, tmp_pdb_mut = _unique_pdb_pair(
        row["pdb_id"], row["pdb_id_secondary"], rng
    )
    tmp_wt = _obj_name(tmp_pdb_wt)
    tmp_mut = _obj_name(tmp_pdb_mut) + "_mutant"
    tmp_chain = row["chain_letter"]
    tmp_primary = row.get("residue_name_3letter", "HIS")
    tmp_partners = [
        r for r in CATALYTIC_RESIDUES if r != tmp_primary
    ][:2]
    tmp_triad = [tmp_primary] + tmp_partners
    tmp_wt_triad_sel = _sel_by_resname(tmp_wt, tmp_chain, tmp_triad)
    tmp_mut_triad_sel = _sel_by_resname(tmp_mut, tmp_chain, tmp_triad)
    tmp_radius = 1.0

    tmp_calls: list[dict] = [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_wt,
                "object_name": tmp_wt,
            },
        },
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_mut,
                "object_name": tmp_mut,
            },
        },
        {
            "name": "align_structures",
            "parameters": {
                "mobile": tmp_mut,
                "target": tmp_wt,
            },
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "wt_active_site",
                "reference_selection": tmp_wt_triad_sel,
                "radius_angstrom": tmp_radius,
            },
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "mut_active_site",
                "reference_selection": tmp_mut_triad_sel,
                "radius_angstrom": tmp_radius,
            },
        },
    ]
    # Three distances in each active site.
    for tmp_i in range(3):
        tmp_a1 = _atom_selector(rng, tmp_wt, tmp_chain)
        tmp_a2 = _atom_selector(rng, tmp_wt, tmp_chain)
        tmp_calls.append(
            {
                "name": "measure_distance",
                "parameters": {
                    "atom1": tmp_a1,
                    "atom2": tmp_a2,
                    "measurement_name": f"wt_dist{tmp_i + 1}",
                },
            }
        )
        tmp_b1 = _atom_selector(rng, tmp_mut, tmp_chain)
        tmp_b2 = _atom_selector(rng, tmp_mut, tmp_chain)
        tmp_calls.append(
            {
                "name": "measure_distance",
                "parameters": {
                    "atom1": tmp_b1,
                    "atom2": tmp_b2,
                    "measurement_name": f"mut_dist{tmp_i + 1}",
                },
            }
        )
    tmp_calls += [
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": tmp_wt,
                "color": row["pymol_color"],
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": tmp_mut,
                "color": "firebrick",
            },
        },
        {
            "name": "set_background_color",
            "parameters": {"color": row["background_color"]},
        },
        {
            "name": "save_image",
            "parameters": {
                "file_path": (
                    f"./figures/{tmp_wt}_vs_{tmp_mut}.png"
                ),
                "ray_trace": True,
            },
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": (
                    f"./sessions/{tmp_wt}_vs_{tmp_mut}.pse"
                ),
            },
        },
    ]
    return tmp_calls


def _publication_figure(row: dict, rng: random.Random) -> list[dict]:
    """Build 11-call publication-quality figure generation workflow.

    Loads, sets representation, colors by SS, white background, selects
    ligand, shows sticks, selects pocket, colors pocket, shows sticks for
    pocket, labels, and saves ray-traced PNG.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 11 tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_lig_sel = _sel_ligand_no_water(tmp_obj)
    tmp_radius = float(
        row.get("radius_angstrom_large", str(rng.choice([5.0, 6.0, 8.0])))
    )
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": tmp_obj,
                "style": row["representation_style"],
            },
        },
        {
            "name": "color_by_secondary_structure",
            "parameters": {"object_name": tmp_obj},
        },
        {
            "name": "set_background_color",
            "parameters": {"color": "white"},
        },
        {
            "name": "select_ligands",
            "parameters": {
                "name": "ligand",
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {"target": "ligand", "style": "sticks"},
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "pocket",
                "reference_selection": tmp_lig_sel,
                "radius_angstrom": tmp_radius,
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": "pocket",
                "color": row["pymol_color"],
            },
        },
        {
            "name": "set_representation",
            "parameters": {"target": "pocket", "style": "sticks"},
        },
        {
            "name": "label_residues",
            "parameters": {
                "target": "pocket",
                "label_type": "residue_name",
            },
        },
        {
            "name": "save_image",
            "parameters": {
                "file_path": f"./figures/{tmp_obj}_publication.png",
                "ray_trace": True,
                "dpi": 300,
            },
        },
    ]


def _batch_measurement_workflow(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 11-call batch distance measurement + label workflow.

    Loads structure, selects four residue pairs, measures the distance for
    each, labels all residues by name and number, and saves the session.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 11 tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_chain = row["chain_letter"]
    tmp_calls: list[dict] = [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
    ]
    tmp_all_resi: list[int] = []
    for tmp_i in range(4):
        tmp_a1 = _atom_selector(rng, tmp_obj, tmp_chain)
        tmp_a2 = _atom_selector(rng, tmp_obj, tmp_chain)
        tmp_all_resi.extend(
            [tmp_a1["residue_id"], tmp_a2["residue_id"]]
        )
        tmp_calls.append(
            {
                "name": "measure_distance",
                "parameters": {
                    "atom1": tmp_a1,
                    "atom2": tmp_a2,
                    "measurement_name": (
                        f"batch_dist{tmp_i + 1}_{tmp_obj}"
                    ),
                },
            }
        )
    # Select all measured residues and label them.
    tmp_sorted_resi = sorted(set(tmp_all_resi))
    tmp_calls += [
        {
            "name": "select_residues",
            "parameters": {
                "name": "measured_residues",
                "object_name": tmp_obj,
                "chain": tmp_chain,
                "residue_ids": tmp_sorted_resi,
            },
        },
        {
            "name": "label_residues",
            "parameters": {
                "target": "measured_residues",
                "label_type": "residue_name",
            },
        },
        {
            "name": "label_residues",
            "parameters": {
                "target": "measured_residues",
                "label_type": "residue_number",
            },
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": f"./sessions/{tmp_obj}_distances.pse",
            },
        },
    ]
    return tmp_calls


def _hydrogen_bond_network(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 9-call H-bond network visualization workflow.

    Loads, adds hydrogens, selects donor residues by residue name,
    shows contacts within H-bond range, shows donor residues as sticks,
    labels by name, and exports selection.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 9 tool-call dicts.
    """
    tmp_obj = _obj_name(row["pdb_id"])
    tmp_chain = row["chain_letter"]
    tmp_primary = row.get("residue_name_3letter", "HIS")
    tmp_donors = [tmp_primary, "ASN", "GLN", "SER", "THR"][:3]
    tmp_donor_sel = _sel_by_resname(tmp_obj, tmp_chain, tmp_donors)
    tmp_cutoff = float(
        row.get("radius_angstrom_small", "3.5")
    )
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": row["pdb_id"],
                "object_name": tmp_obj,
            },
        },
        {
            "name": "add_hydrogens",
            "parameters": {"target": tmp_obj},
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "hbond_donors",
                "reference_selection": tmp_donor_sel,
                "radius_angstrom": 1.0,
            },
        },
        {
            "name": "show_contacts",
            "parameters": {
                "selection1": "hbond_donors",
                "selection2": tmp_obj,
                "cutoff_angstrom": tmp_cutoff,
                "name": f"hbonds_{tmp_obj}",
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": "hbond_donors",
                "style": "sticks",
            },
        },
        {
            "name": "label_residues",
            "parameters": {
                "target": "hbond_donors",
                "label_type": "residue_name",
            },
        },
        {
            "name": "set_background_color",
            "parameters": {"color": "white"},
        },
        {
            "name": "export_coordinates",
            "parameters": {
                "target": "hbond_donors",
                "file_path": f"./exports/{tmp_obj}_donors.pdb",
                "format": "pdb",
            },
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": f"./sessions/{tmp_obj}_hbonds.pse",
            },
        },
    ]


def _multi_structure_session(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 11-call three-structure comparative session.

    Loads three structures, aligns second and third onto the first,
    colors each distinctly, sets representation, saves session.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 11 tool-call dicts.
    """
    tmp_pdb_a, tmp_pdb_b, tmp_pdb_c = _unique_pdb_triple(
        row["pdb_id"],
        row["pdb_id_secondary"],
        row.get("pdb_id_tertiary", row["pdb_id_secondary"]),
        rng,
    )
    tmp_obj_a = _obj_name(tmp_pdb_a)
    tmp_obj_b = _obj_name(tmp_pdb_b) + "_2"
    tmp_obj_c = _obj_name(tmp_pdb_c) + "_3"
    tmp_colors = _chain_color_sequence(3, rng)
    return [
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_a,
                "object_name": tmp_obj_a,
            },
        },
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_b,
                "object_name": tmp_obj_b,
            },
        },
        {
            "name": "load_structure",
            "parameters": {
                "pdb_id": tmp_pdb_c,
                "object_name": tmp_obj_c,
            },
        },
        {
            "name": "align_structures",
            "parameters": {
                "mobile": tmp_obj_b,
                "target": tmp_obj_a,
            },
        },
        {
            "name": "align_structures",
            "parameters": {
                "mobile": tmp_obj_c,
                "target": tmp_obj_a,
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": tmp_obj_a,
                "color": tmp_colors[0],
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": tmp_obj_b,
                "color": tmp_colors[1],
            },
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": tmp_obj_c,
                "color": tmp_colors[2],
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": "all",
                "style": row["representation_style"],
            },
        },
        {
            "name": "set_background_color",
            "parameters": {"color": row["background_color"]},
        },
        {
            "name": "save_session",
            "parameters": {
                "file_path": (
                    f"./sessions/"
                    f"{tmp_obj_a}_{tmp_obj_b}_{tmp_obj_c}.pse"
                ),
            },
        },
    ]


def _cryo_em_refinement_view(
    row: dict,
    rng: random.Random,
) -> list[dict]:
    """Build 10-call cryo-EM model visualization workflow.

    Loads a local CIF file, shows cartoon backbone, shows ligand as
    sticks, colors by chain, colors ligand distinctly, selects density-
    supported environment, labels it, and saves a ray-traced figure.

    Args:
      row: Raw Data Designer row dict.
      rng: Seeded random instance.

    Returns:
      Ordered list of 10 tool-call dicts.
    """
    tmp_stub = row["file_path_stub"]
    tmp_obj = tmp_stub.split("/")[-1].rsplit(".", 1)[0]
    tmp_lig_sel = _sel_ligand_no_water(tmp_obj)
    tmp_radius = float(
        row.get("radius_angstrom_large", str(rng.choice([5.0, 6.0, 8.0])))
    )
    return [
        {
            "name": "load_local_file",
            "parameters": {
                "file_path": tmp_stub,
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {"target": tmp_obj, "style": "cartoon"},
        },
        {
            "name": "select_ligands",
            "parameters": {
                "name": "cryo_ligand",
                "object_name": tmp_obj,
            },
        },
        {
            "name": "set_representation",
            "parameters": {
                "target": "cryo_ligand",
                "style": "sticks",
            },
        },
        {
            "name": "color_by_chain",
            "parameters": {"object_name": tmp_obj},
        },
        {
            "name": "color_by_scheme",
            "parameters": {
                "target": "cryo_ligand",
                "color": row["pymol_color"],
            },
        },
        {
            "name": "select_by_proximity",
            "parameters": {
                "name": "density_env",
                "reference_selection": tmp_lig_sel,
                "radius_angstrom": tmp_radius,
            },
        },
        {
            "name": "label_residues",
            "parameters": {
                "target": "density_env",
                "label_type": "residue_name",
            },
        },
        {
            "name": "set_background_color",
            "parameters": {"color": row["background_color"]},
        },
        {
            "name": "save_image",
            "parameters": {
                "file_path": f"./figures/{tmp_obj}_cryoem.png",
                "ray_trace": True,
            },
        },
    ]


# ---------------------------------------------------------------------------
# Scenario dispatch table
# ---------------------------------------------------------------------------

SCENARIO_BUILDERS: dict[str, object] = {
    # Lightweight
    "load_and_visualize": _load_and_visualize,
    "load_only": _load_only,
    "chain_coloring": _chain_coloring,
    "secondary_structure_and_background": (
        _secondary_structure_and_background
    ),
    "hydrogens_workflow": _hydrogens_workflow,
    "active_site_selection": _active_site_selection,
    "local_file_workflow": _local_file_workflow,
    "housekeeping_workflow": _housekeeping_workflow,
    "chain_isolation_export": _chain_isolation_export,
    # Medium
    "binding_site_proximity": _binding_site_proximity,
    "measure_distance_workflow": _measure_distance_workflow,
    "measure_angle_workflow": _measure_angle_workflow,
    "contacts_workflow": _contacts_workflow,
    "align_structures_workflow": _align_structures_workflow,
    "export_image_and_session": _export_image_and_session,
    # Deep
    "antibody_cdr_analysis": _antibody_cdr_analysis,
    "comparative_binding_site": _comparative_binding_site,
    "full_active_site_workflow": _full_active_site_workflow,
    "multi_chain_coloring_export": _multi_chain_coloring_export,
    "ligand_environment_deep": _ligand_environment_deep,
    "interface_analysis": _interface_analysis,
    "structure_comparison_full": _structure_comparison_full,
    "publication_figure": _publication_figure,
    "batch_measurement_workflow": _batch_measurement_workflow,
    "hydrogen_bond_network": _hydrogen_bond_network,
    "multi_structure_session": _multi_structure_session,
    "cryo_em_refinement_view": _cryo_em_refinement_view,
}

# ---------------------------------------------------------------------------
# Validation & cleaning helpers
# ---------------------------------------------------------------------------


def validate_tool_calls(calls: list[dict]) -> list[str]:
    """Validate a list of tool-call dicts against the registered schemas.

    Args:
      calls: List of tool-call dicts, each with 'name' and 'parameters'.

    Returns:
      A list of human-readable error strings; empty if all calls are valid.
    """
    tmp_errors: list[str] = []
    for tmp_call in calls:
        tmp_name = tmp_call.get("name")
        tmp_validator = VALIDATORS.get(tmp_name)
        if tmp_validator is None:
            tmp_errors.append(f"unknown tool name: {tmp_name!r}")
            continue
        for tmp_err in tmp_validator.iter_errors(
            tmp_call.get("parameters", {})
        ):
            tmp_path = (
                ".".join(str(p) for p in tmp_err.path) or "<root>"
            )
            tmp_errors.append(
                f"{tmp_name}: {tmp_path}: {tmp_err.message}"
            )
    return tmp_errors


def clean_user_query(text: str) -> str:
    """Strip common preamble phrases free-tier models slip in.

    Args:
      text: Raw user-query string from the LLM.

    Returns:
      Cleaned query string with preamble prefixes removed.
    """
    tmp_text = text.strip().strip('"').strip()
    for tmp_preamble in (
        "Here is your query:",
        "Here's your request:",
        "Request:",
        "Query:",
    ):
        if tmp_text.lower().startswith(tmp_preamble.lower()):
            tmp_text = tmp_text[len(tmp_preamble):].strip()
    return tmp_text


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Read raw Data Designer rows, build and validate conversations, write.

    Raises:
      SystemExit: If reading the input file fails at the OS level.
    """
    tmp_parser = argparse.ArgumentParser()
    tmp_parser.add_argument("--input", required=True)
    tmp_parser.add_argument("--output", required=True)
    tmp_parser.add_argument(
        "--rejects",
        default=None,
        help="Optional path to write dropped rows and reasons.",
    )
    tmp_args = tmp_parser.parse_args()

    tmp_kept = 0
    tmp_dropped = 0
    tmp_rejects: list[dict] = []

    with (
        open(tmp_args.input, "r", encoding="utf-8") as tmp_fin,
        open(tmp_args.output, "w", encoding="utf-8") as tmp_fout,
    ):
        for tmp_line_no, tmp_line in enumerate(tmp_fin, start=1):
            tmp_line = tmp_line.strip()
            if not tmp_line:
                continue
            try:
                tmp_row = json.loads(tmp_line)
            except json.JSONDecodeError as tmp_exc:
                tmp_dropped += 1
                tmp_rejects.append(
                    {
                        "line": tmp_line_no,
                        "reason": f"raw JSON decode error: {tmp_exc}",
                    }
                )
                continue

            tmp_user_query = clean_user_query(
                tmp_row.get("user_query", "")
            )
            if not tmp_user_query:
                tmp_dropped += 1
                tmp_rejects.append(
                    {
                        "line": tmp_line_no,
                        "reason": "empty user_query after cleaning",
                    }
                )
                continue

            tmp_scenario = tmp_row.get("scenario")
            tmp_builder = SCENARIO_BUILDERS.get(tmp_scenario)
            if tmp_builder is None:
                tmp_dropped += 1
                tmp_rejects.append(
                    {
                        "line": tmp_line_no,
                        "reason": (
                            f"unknown scenario: {tmp_scenario!r}"
                        ),
                    }
                )
                continue

            # Seed deterministically from the row UUID so tool-only
            # parameters are reproducible across reruns on the same data.
            tmp_rng = random.Random(tmp_row["row_uid"])
            tmp_tool_calls = tmp_builder(tmp_row, tmp_rng)

            tmp_errors = validate_tool_calls(tmp_tool_calls)
            if tmp_errors:
                tmp_dropped += 1
                tmp_rejects.append(
                    {
                        "line": tmp_line_no,
                        "reason": "; ".join(tmp_errors),
                    }
                )
                continue

            tmp_record = {
                "id": tmp_row["row_uid"],
                "scenario": tmp_scenario,
                # Flat text field used ONLY by curate.py for exact/fuzzy
                # dedup.  NeMo Curator's text_field must be a plain string;
                # the thing we dedup on is the user-facing phrasing (where
                # free-tier LLM paraphrase-repeats show up), not the
                # deterministic tool-call JSON.
                "dedup_text": tmp_user_query,
                "conversations": [
                    {"role": "user", "content": tmp_user_query},
                    {
                        "role": "assistant",
                        "content": json.dumps(tmp_tool_calls),
                    },
                ],
            }
            tmp_fout.write(
                json.dumps(tmp_record, ensure_ascii=False) + "\n"
            )
            tmp_kept += 1

    print(
        f"Kept {tmp_kept} rows, dropped {tmp_dropped} rows.",
        file=sys.stderr,
    )

    if tmp_args.rejects and tmp_rejects:
        with open(
            tmp_args.rejects, "w", encoding="utf-8"
        ) as tmp_frej:
            for tmp_r in tmp_rejects:
                tmp_frej.write(json.dumps(tmp_r) + "\n")
        print(
            f"Reject reasons written to {tmp_args.rejects}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
