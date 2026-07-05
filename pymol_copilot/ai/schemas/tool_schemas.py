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

"""Tool schema definitions for the cBioMOL AI assistant.

This module is the **single source of truth** for every tool the language
model is allowed to call.  The Hermes/ChatML tool-call convention is used
throughout:

  {
    "name":        str   — the function name the model emits,
    "description": str   — plain-English description shown in the prompt,
    "parameters":  dict  — JSON-Schema object (type, required, properties),
  }

The schema list is consumed by:
  - The system-prompt builder (injected at inference time, Phase 3).
  - The GBNF grammar generator (constrains model output, Phase 3).
  - ``explanations.py`` (JSON → human-readable prose, Phase 4).
  - The synthetic training-data generator (Phase 2).

Design invariant: every ``parameters.properties`` entry **must** contain a
``description`` field.  The model is a small quantized model; rich
per-parameter descriptions are the primary mechanism for reducing hallucination.

Source: PyMOL wiki (https://pymolwiki.org/index.php/Category:Commands),
verified 2026-06-23.
"""

from __future__ import annotations

_REPRESENTATION_ENUM: list[str] = [
    "cartoon",
    "sticks",
    "spheres",
    "surface",
    "ribbon",
    "lines",
    "dots",
]

_LABEL_TYPE_ENUM: list[str] = [
    "residue_name",
    "residue_number",
    "chain",
    "b_factor",
    "none",
]

_COORDINATE_FORMAT_ENUM: list[str] = ["pdb", "mmcif", "mol2"]

# ---------------------------------------------------------------------------
# Category A — Structure Loading
# ---------------------------------------------------------------------------

_LOAD_STRUCTURE: dict = {
    "name": "load_structure",
    "description": (
        "Download a protein or nucleic-acid structure from the RCSB Protein Data"
        " Bank by its 4-letter accession code and load it into the active PyMOL"
        " session.  Use this whenever the user asks to open, fetch, or load a"
        " structure identified by a PDB ID."
    ),
    "parameters": {
        "type": "object",
        "required": ["pdb_id"],
        "properties": {
            "pdb_id": {
                "type": "string",
                "description": (
                    "4-letter RCSB PDB accession code (e.g. '7BZ5', '1BL8')."
                    " Case-insensitive."
                ),
                "pattern": "^[0-9][A-Za-z0-9]{3}$",
            },
            "object_name": {
                "type": ["string", "null"],
                "description": (
                    "Name for the object in the PyMOL session."
                    " Defaults to the PDB code when null."
                ),
                "default": None,
            },
        },
    },
}

_LOAD_LOCAL_FILE: dict = {
    "name": "load_local_file",
    "description": (
        "Load a molecular structure from a local file path into the PyMOL session."
        " Supports PDB (.pdb), mmCIF (.cif), and MOL2 (.mol2) formats."
        " Use when the user refers to a file on disk rather than a PDB ID."
    ),
    "parameters": {
        "type": "object",
        "required": ["file_path"],
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Absolute or relative path to the molecular structure file."
                ),
            },
            "object_name": {
                "type": ["string", "null"],
                "description": (
                    "Name for the PyMOL object. Defaults to the filename stem when null."
                ),
                "default": None,
            },
        },
    },
}

_REMOVE_OBJECT: dict = {
    "name": "remove_object",
    "description": (
        "Delete a named object or selection from the current PyMOL session."
        " Use when the user asks to close, remove, or delete a loaded structure."
    ),
    "parameters": {
        "type": "object",
        "required": ["object_name"],
        "properties": {
            "object_name": {
                "type": "string",
                "description": "Exact name of the PyMOL object or selection to delete.",
            },
        },
    },
}

_LIST_LOADED_OBJECTS: dict = {
    "name": "list_loaded_objects",
    "description": (
        "Return the names of all objects currently loaded in the PyMOL session."
        " Use this to discover what structures are available before referencing"
        " them in other tool calls."
    ),
    "parameters": {
        "type": "object",
        "required": [],
        "properties": {},
    },
}

# ---------------------------------------------------------------------------
# Category B — Representation
# ---------------------------------------------------------------------------

_SET_REPRESENTATION: dict = {
    "name": "set_representation",
    "description": (
        "Change the visual representation of a PyMOL object or selection."
        " Replaces the current representation entirely (hides all others first)."
        " Common representations: cartoon for secondary structure, sticks for"
        " side-chain detail, surface for solvent-accessible surface."
    ),
    "parameters": {
        "type": "object",
        "required": ["target", "style"],
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "Name of the PyMOL object or named selection to apply the"
                    " representation to.  Use 'all' for every loaded object."
                ),
            },
            "style": {
                "type": "string",
                "enum": _REPRESENTATION_ENUM,
                "description": (
                    "Representation style.  One of: cartoon, sticks, spheres, surface,"
                    " ribbon, lines, dots."
                ),
            },
        },
    },
}

_COLOR_BY_SCHEME: dict = {
    "name": "color_by_scheme",
    "description": (
        "Apply a uniform color or a color scheme to a PyMOL object or selection."
        " Use named colors (e.g. 'red', 'cyan', 'forest', 'slate') for solid"
        " coloring, or scheme keywords ('spectrum', 'b', 'chainbows') for"
        " gradient coloring."
    ),
    "parameters": {
        "type": "object",
        "required": ["target", "color"],
        "properties": {
            "target": {
                "type": "string",
                "description": ("PyMOL object name, selection name, or 'all'."),
            },
            "color": {
                "type": "string",
                "description": (
                    "A PyMOL named color (e.g. 'red', 'cyan', 'forest', 'wheat') or"
                    " a color scheme keyword ('spectrum', 'b', 'chainbows')."
                ),
            },
        },
    },
}

_COLOR_BY_CHAIN: dict = {
    "name": "color_by_chain",
    "description": (
        "Assign a distinct color to each chain in an object using PyMOL's"
        " chain-based coloring utility (cmd.util.cbc).  Each chain receives a"
        " unique color drawn from the standard palette."
    ),
    "parameters": {
        "type": "object",
        "required": ["object_name"],
        "properties": {
            "object_name": {
                "type": "string",
                "description": (
                    "Name of the PyMOL object to color.  Use 'all' for every object."
                ),
            },
        },
    },
}

_COLOR_BY_SECONDARY_STRUCTURE: dict = {
    "name": "color_by_secondary_structure",
    "description": (
        "Color residues by secondary structure assignment: helices in one color,"
        " beta-strands in another, and loops in a third.  Uses PyMOL's built-in"
        " secondary-structure coloring utility (cmd.util.ss)."
    ),
    "parameters": {
        "type": "object",
        "required": ["object_name"],
        "properties": {
            "object_name": {
                "type": "string",
                "description": "Name of the PyMOL object to color.",
            },
        },
    },
}

_SET_BACKGROUND_COLOR: dict = {
    "name": "set_background_color",
    "description": (
        "Change the background color of the PyMOL viewport."
        " Common choices: 'white' for publication figures, 'black' for"
        " presentations, 'grey' for neutral backgrounds."
    ),
    "parameters": {
        "type": "object",
        "required": ["color"],
        "properties": {
            "color": {
                "type": "string",
                "description": (
                    "A PyMOL named color for the background (e.g. 'white', 'black',"
                    " 'grey')."
                ),
            },
        },
    },
}

_ADD_HYDROGENS: dict = {
    "name": "add_hydrogens",
    "description": (
        "Add missing hydrogen atoms to a structure using PyMOL's hydrogen-adding"
        " algorithm (cmd.h_add).  Useful before computing hydrogen bonds or"
        " visualizing protonation states."
    ),
    "parameters": {
        "type": "object",
        "required": ["target"],
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "PyMOL object name or selection to add hydrogens to."
                    " Use 'all' for every loaded object."
                ),
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Category C — Selection & Annotation
# ---------------------------------------------------------------------------

_SELECT_RESIDUES: dict = {
    "name": "select_residues",
    "description": (
        "Create a named selection containing specific residues identified by"
        " chain and sequence numbers.  Use this to mark active-site residues,"
        " mutated positions, or any discrete set of residues for further"
        " coloring, measurement, or export."
    ),
    "parameters": {
        "type": "object",
        "required": ["name", "object_name", "chain", "residue_ids"],
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Label for this selection (e.g. 'active_site', 'mutation_K132A')."
                    " Must be a valid Python identifier."
                ),
            },
            "object_name": {
                "type": "string",
                "description": "Name of the loaded PyMOL object to select from.",
            },
            "chain": {
                "type": "string",
                "description": "Single chain identifier letter (e.g. 'A', 'B').",
                "pattern": "^[A-Za-z]$",
            },
            "residue_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 1,
                "maxItems": 500,
                "description": (
                    "List of integer residue sequence numbers to include in the"
                    " selection (e.g. [48, 52, 61, 89])."
                ),
            },
        },
    },
}

_SELECT_BY_PROXIMITY: dict = {
    "name": "select_by_proximity",
    "description": (
        "Create a named selection of all atoms within a given distance (in"
        " Angstroms) of a reference selection.  Typical use: select all residues"
        " near a ligand or cofactor to define a binding-site region."
    ),
    "parameters": {
        "type": "object",
        "required": ["name", "reference_selection", "radius_angstrom"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Label for the resulting selection.",
            },
            "reference_selection": {
                "type": "string",
                "description": (
                    "Name of an existing PyMOL object or selection to expand around."
                ),
            },
            "radius_angstrom": {
                "type": "number",
                "minimum": 0.1,
                "maximum": 30.0,
                "description": (
                    "Expansion radius in Angstroms.  Typical values: 4–8 Å for"
                    " binding-site analysis, 3.5 Å for contact detection."
                ),
            },
        },
    },
}

_SELECT_CHAIN: dict = {
    "name": "select_chain",
    "description": (
        "Create a named selection containing all atoms belonging to a single"
        " chain in a PyMOL object.  Useful for isolating a subunit in a"
        " multimeric complex."
    ),
    "parameters": {
        "type": "object",
        "required": ["name", "object_name", "chain"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Label for the selection (e.g. 'chain_A').",
            },
            "object_name": {
                "type": "string",
                "description": "Name of the PyMOL object to select from.",
            },
            "chain": {
                "type": "string",
                "description": "Chain identifier letter (e.g. 'A').",
                "pattern": "^[A-Za-z]$",
            },
        },
    },
}

_SELECT_LIGANDS: dict = {
    "name": "select_ligands",
    "description": (
        "Create a named selection containing all HETATM records (ligands,"
        " cofactors, crystallographic waters, etc.) in a PyMOL object."
        " Does not include standard amino acid or nucleotide residues."
    ),
    "parameters": {
        "type": "object",
        "required": ["name", "object_name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Label for the selection (e.g. 'ligands', 'cofactors').",
            },
            "object_name": {
                "type": "string",
                "description": "Name of the PyMOL object to select from.",
            },
        },
    },
}

_LABEL_RESIDUES: dict = {
    "name": "label_residues",
    "description": (
        "Add text labels to atoms or residues in an existing selection or object."
        " Labels float in the 3D viewport next to the labeled atoms."
        " Use 'none' to remove all labels from the target."
    ),
    "parameters": {
        "type": "object",
        "required": ["target", "label_type"],
        "properties": {
            "target": {
                "type": "string",
                "description": "PyMOL object name or selection name to label.",
            },
            "label_type": {
                "type": "string",
                "enum": _LABEL_TYPE_ENUM,
                "description": (
                    "What to display as the label text.  One of: residue_name (e.g."
                    " 'ASP'), residue_number (e.g. '189'), chain, b_factor, none"
                    " (removes existing labels)."
                ),
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Category D — Measurement
# ---------------------------------------------------------------------------

_ATOM_SELECTOR_SCHEMA: dict = {
    "type": "object",
    "required": ["object_name", "chain", "residue_id", "atom_name"],
    "properties": {
        "object_name": {
            "type": "string",
            "description": "Name of the PyMOL object the atom belongs to.",
        },
        "chain": {
            "type": "string",
            "description": "Chain identifier letter.",
            "pattern": "^[A-Za-z]$",
        },
        "residue_id": {
            "type": "integer",
            "description": "Residue sequence number.",
        },
        "atom_name": {
            "type": "string",
            "description": (
                "Atom name as it appears in the PDB file (e.g. 'CA', 'CB', 'OG1')."
            ),
        },
    },
}

_MEASURE_DISTANCE: dict = {
    "name": "measure_distance",
    "description": (
        "Measure and display the Euclidean distance in Angstroms between two"
        " specific atoms.  The result is shown as a dashed line in the viewport"
        " and printed as a named measurement object."
    ),
    "parameters": {
        "type": "object",
        "required": ["atom1", "atom2", "measurement_name"],
        "properties": {
            "atom1": {
                **_ATOM_SELECTOR_SCHEMA,
                "description": "The first atom to measure from.",
            },
            "atom2": {
                **_ATOM_SELECTOR_SCHEMA,
                "description": "The second atom to measure to.",
            },
            "measurement_name": {
                "type": "string",
                "description": (
                    "Name for the distance object in PyMOL (e.g. 'dist_Asp189_His57')."
                ),
            },
        },
    },
}

_MEASURE_ANGLE: dict = {
    "name": "measure_angle",
    "description": (
        "Measure and display the bond angle in degrees defined by three atoms."
        " The central atom is the vertex of the angle.  The result is shown as"
        " an arc in the viewport."
    ),
    "parameters": {
        "type": "object",
        "required": ["atom1", "atom2_vertex", "atom3", "measurement_name"],
        "properties": {
            "atom1": {
                **_ATOM_SELECTOR_SCHEMA,
                "description": "First arm atom of the angle.",
            },
            "atom2_vertex": {
                **_ATOM_SELECTOR_SCHEMA,
                "description": "Central vertex atom of the angle.",
            },
            "atom3": {
                **_ATOM_SELECTOR_SCHEMA,
                "description": "Second arm atom of the angle.",
            },
            "measurement_name": {
                "type": "string",
                "description": "Name for the angle object in PyMOL.",
            },
        },
    },
}

_SHOW_CONTACTS: dict = {
    "name": "show_contacts",
    "description": (
        "Display all inter-atomic contacts (non-bonded interactions) between"
        " two selections within a specified distance cutoff.  Each contact is"
        " shown as a dashed line.  Useful for identifying hydrogen-bond donors/"
        "acceptors, salt bridges, or van-der-Waals contacts at an interface."
    ),
    "parameters": {
        "type": "object",
        "required": ["selection1", "selection2", "cutoff_angstrom", "name"],
        "properties": {
            "selection1": {
                "type": "string",
                "description": "First PyMOL object or selection name.",
            },
            "selection2": {
                "type": "string",
                "description": "Second PyMOL object or selection name.",
            },
            "cutoff_angstrom": {
                "type": "number",
                "minimum": 0.5,
                "maximum": 10.0,
                "description": (
                    "Maximum inter-atomic distance in Angstroms to display as a contact."
                    " Typical values: 3.5 Å for hydrogen bonds, 4.0 Å for polar"
                    " contacts, 5.0 Å for van-der-Waals."
                ),
            },
            "name": {
                "type": "string",
                "description": "Name for the contact-distance object in PyMOL.",
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Category E — Comparison & Alignment
# ---------------------------------------------------------------------------

_ALIGN_STRUCTURES: dict = {
    "name": "align_structures",
    "description": (
        "Structurally superpose a mobile object onto a fixed reference object"
        " using sequence-independent structural alignment (cmd.super)."
        " After alignment the RMSD is printed to the PyMOL console."
        " Use when comparing a mutant, homolog, or different conformational state"
        " to a reference structure."
    ),
    "parameters": {
        "type": "object",
        "required": ["mobile", "target"],
        "properties": {
            "mobile": {
                "type": "string",
                "description": (
                    "Name of the PyMOL object to move (the structure being aligned"
                    " onto the reference)."
                ),
            },
            "target": {
                "type": "string",
                "description": (
                    "Name of the PyMOL object to use as the fixed reference."
                ),
            },
            "mobile_chain": {
                "type": ["string", "null"],
                "description": (
                    "Restrict alignment to this chain in the mobile object."
                    " Null uses all chains."
                ),
                "default": None,
            },
            "target_chain": {
                "type": ["string", "null"],
                "description": (
                    "Restrict alignment to this chain in the target object."
                    " Null uses all chains."
                ),
                "default": None,
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Category F — Export & Session
# ---------------------------------------------------------------------------

_SAVE_IMAGE: dict = {
    "name": "save_image",
    "description": (
        "Save the current PyMOL viewport as a PNG image file.  Set ray_trace to"
        " true for publication-quality output with shadows and ambient occlusion"
        " (slower); false for a fast preview screenshot."
    ),
    "parameters": {
        "type": "object",
        "required": ["file_path"],
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Output file path.  Must end with '.png'."
                    " Example: '/home/user/figures/7BZ5_binding_site.png'."
                ),
            },
            "width": {
                "type": "integer",
                "minimum": 100,
                "maximum": 8000,
                "description": "Image width in pixels.  Defaults to 1920.",
                "default": 1920,
            },
            "height": {
                "type": "integer",
                "minimum": 100,
                "maximum": 8000,
                "description": "Image height in pixels.  Defaults to 1080.",
                "default": 1080,
            },
            "dpi": {
                "type": "integer",
                "minimum": 72,
                "maximum": 600,
                "description": (
                    "Dots per inch for the output file.  Use 300 for print-quality,"
                    " 72 for screen.  Defaults to 300."
                ),
                "default": 300,
            },
            "ray_trace": {
                "type": "boolean",
                "description": (
                    "If true, run ray-tracing before saving (high quality, slow)."
                    " If false, save the rasterized view directly (fast preview)."
                ),
                "default": False,
            },
        },
    },
}

_SAVE_SESSION: dict = {
    "name": "save_session",
    "description": (
        "Save the entire PyMOL session (all loaded objects, selections,"
        " representations, and measurements) to a .pse file."
        " Use when the user wants to preserve work for later or share with"
        " a colleague."
    ),
    "parameters": {
        "type": "object",
        "required": ["file_path"],
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Output file path.  Must end with '.pse'."
                    " Example: '/home/user/sessions/insulin_receptor_analysis.pse'."
                ),
            },
        },
    },
}

_EXPORT_COORDINATES: dict = {
    "name": "export_coordinates",
    "description": (
        "Export the atomic coordinates of a PyMOL object or selection to a"
        " molecular structure file.  Use when the user wants to save a modified"
        " or selected subset of atoms as a standalone file for downstream"
        " analysis."
    ),
    "parameters": {
        "type": "object",
        "required": ["target", "file_path", "format"],
        "properties": {
            "target": {
                "type": "string",
                "description": "PyMOL object name or selection to export.",
            },
            "file_path": {
                "type": "string",
                "description": "Output file path including the correct extension.",
            },
            "format": {
                "type": "string",
                "enum": _COORDINATE_FORMAT_ENUM,
                "description": ("File format.  One of: pdb, mmcif, mol2."),
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Public registry — ordered list consumed by all downstream systems
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    # A — Structure Loading
    _LOAD_STRUCTURE,
    _LOAD_LOCAL_FILE,
    _REMOVE_OBJECT,
    _LIST_LOADED_OBJECTS,
    # B — Representation
    _SET_REPRESENTATION,
    _COLOR_BY_SCHEME,
    _COLOR_BY_CHAIN,
    _COLOR_BY_SECONDARY_STRUCTURE,
    _SET_BACKGROUND_COLOR,
    _ADD_HYDROGENS,
    # C — Selection & Annotation
    _SELECT_RESIDUES,
    _SELECT_BY_PROXIMITY,
    _SELECT_CHAIN,
    _SELECT_LIGANDS,
    _LABEL_RESIDUES,
    # D — Measurement
    _MEASURE_DISTANCE,
    _MEASURE_ANGLE,
    _SHOW_CONTACTS,
    # E — Comparison & Alignment
    _ALIGN_STRUCTURES,
    # F — Export & Session
    _SAVE_IMAGE,
    _SAVE_SESSION,
    _EXPORT_COORDINATES,
]
