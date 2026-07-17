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
#
"""Synthetic dataset generator for the cBioMOL AI assistant.

This script operates in two independent modes:

``generate_prompts``
    Reads the tool schemas and a seed catalogue, then writes self-contained
    prompt batch files (.txt) to ``--output_dir/prompts/``.  Each file
    is a complete, standalone instruction that any LLM can process — no
    API keys or internet access are required by the script itself.

``collect_responses``
    Reads ``.response.txt`` files from ``--input_dir``, validates every
    generated example against the tool schemas, and writes the training
    JSONL files (``train.jsonl``, ``val.jsonl``, ``rejected.jsonl``).

Prompt-file workflow
--------------------
1. Run ``--mode generate_prompts`` to produce batch .txt files.
2. Submit each .txt to any LLM (web UI, CLI agent, local model).
3. Save each LLM response as the matching .response.txt file.
4. Run ``--mode collect_responses`` to validate and build the dataset.

Usage
-----
.. code-block:: bash

    # Step 1
    python generate_dataset.py --mode generate_prompts \\
        --n_positive 1400 --n_negative 800 --n_context 400 \\
        --output_dir data/

    # Step 3 (after submitting and saving responses)
    python generate_dataset.py --mode collect_responses \\
        --input_dir data/prompts/ --output_dir data/

Tool schemas
------------
The script reads tool schemas from ``--schemas_file``, which defaults to
``data/tools.json``.  Export this file from the main project once:

.. code-block:: bash

    python -c "
    import json, sys
    sys.path.insert(0, 'src/python')
    from pymol_copilot.ai.schemas import tool_schemas
    print(json.dumps(tool_schemas.TOOL_SCHEMAS, indent=2))
    " > data/tools.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys
from typing import Optional

import config.training_config as training_config


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_VALID_PDB_ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_VALID_CHAIN_RE = re.compile(r"^[A-Za-z]$")


def _read_text(path: pathlib.Path) -> str:
    """Read a text file, automatically detecting its encoding from its BOM.

    PowerShell's ``>`` redirect operator writes UTF-16 LE (BOM ``0xFF
    0xFE``) by default, which the standard ``open(..., encoding='utf-8')``
    cannot decode.  This function inspects the first two bytes and
    dispatches to the correct codec.

    Supported BOMs:
      - ``\xff\xfe`` → UTF-16 LE  (PowerShell default)
      - ``\xfe\xff`` → UTF-16 BE
      - ``\xef\xbb\xbf`` → UTF-8 with BOM
      - no BOM → UTF-8

    Args:
      path: Path to the text file to read.

    Returns:
      The full decoded text content of the file.
    """
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    return raw.decode("utf-8")


def _load_tool_schemas(schemas_file: pathlib.Path) -> list[dict]:
    """Load tool schemas from a JSON file.

    Args:
      schemas_file: Path to the JSON file containing tool schema dicts.

    Returns:
      A list of tool schema dicts.

    Raises:
      SystemExit: If the file does not exist or is not valid JSON.
    """
    if not schemas_file.exists():
        print(
            f"[ERROR] Schemas file not found: {schemas_file}\n"
            "Export it from the main project with (PowerShell):\n"
            '  python -c "'
            "import json, sys; "
            "sys.path.insert(0, 'src/python'); "
            "from pymol_copilot.ai.schemas import tool_schemas; "
            'print(json.dumps(tool_schemas.TOOL_SCHEMAS, indent=2))"'
            " | Out-File -Encoding utf8 data/tools.json",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        text = _read_text(schemas_file)
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(
            f"[ERROR] Could not parse {schemas_file}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


def _validate_example(
    example: dict,
    tool_schemas: list[dict],
) -> Optional[str]:
    """Validate one generated example against the tool schemas.

    Checks that:
    - Required top-level keys exist.
    - ``tool_calls`` is a list.
    - Every tool name exists in the schema registry.
    - Every required schema parameter is present.
    - ``pdb_id`` values match the 4-character PDB pattern.
    - ``chain`` values are single ASCII letters.

    Args:
      example: A dict with ``user_request`` (str) and
        ``tool_calls`` (list of dicts).
      tool_schemas: List of tool schema dicts used for validation.

    Returns:
      ``None`` if the example is valid; a human-readable rejection
      reason string otherwise.
    """
    if not isinstance(example, dict):
        return "example is not a JSON object"
    if not isinstance(example.get("user_request"), str):
        return "missing or non-string 'user_request'"
    if not isinstance(example.get("tool_calls"), list):
        return "missing or non-list 'tool_calls'"

    schema_map: dict[str, dict] = {s["name"]: s for s in tool_schemas}

    for call in example["tool_calls"]:
        if not isinstance(call, dict):
            return "tool_call entry is not a JSON object"
        name = call.get("name")
        if name not in schema_map:
            known = list(schema_map.keys())
            return f"unknown tool '{name}'; known tools are {known}"
        schema = schema_map[name]
        params = schema.get("parameters", {})
        required = params.get("required", [])
        args = call.get("arguments", {})
        if not isinstance(args, dict):
            return f"'arguments' in call to '{name}' is not a JSON object"
        for req_key in required:
            if req_key not in args:
                return f"required parameter '{req_key}' missing in call to '{name}'"
        # Domain-specific checks
        if "pdb_id" in args:
            pdb = str(args["pdb_id"]).upper()
            if not _VALID_PDB_ID_RE.match(pdb):
                return f"invalid PDB ID '{args['pdb_id']}'"
        if "chain" in args:
            ch = str(args["chain"])
            if not _VALID_CHAIN_RE.match(ch):
                return f"invalid chain identifier '{args['chain']}'"

    return None  # valid


# ---------------------------------------------------------------------------
# Scenario seed catalogue
# ---------------------------------------------------------------------------


def _build_seeds() -> dict[str, list[str]]:
    """Return the full catalogue of scenario seed templates by category.

    Seeds are short descriptions of scenarios.  The LLM that reads the
    prompt file expands each seed into a complete ``{user_request,
    tool_calls}`` example.

    Returns:
      A dict mapping category names to lists of seed strings.
    """
    return {
        "positive_single_tool": [
            "Load hemoglobin from RCSB PDB (4HHB)",
            "Load the SARS-CoV-2 main protease (6LU7)",
            "Load human insulin (4INS) for a presentation",
            "Load adenylate kinase (4AKE)",
            "Load thrombin (1PPB) into the session",
            "Load a local PDB file from disk",
            "Remove the old structure from the session",
            "List all objects currently open",
            "Show the protein as cartoon",
            "Show the protein as sticks",
            "Show everything as surface",
            "Change to ribbon representation",
            "Change to lines representation",
            "Color the structure red",
            "Color chain A blue and chain B green",
            "Color by secondary structure assignment",
            "Set background to white for publication",
            "Add missing hydrogen atoms",
            "Select residues 48, 52, 61 in chain A",
            "Select all atoms within 5 Å of the ligand",
            "Select only chain B of the structure",
            "Select all ligands (HETATM records)",
            "Label all residues with their sequence numbers",
            "Label active site residues with names",
            "Remove all labels from the view",
            "Measure the distance between Asp189 OD1 and His57 NE2",
            "Show contacts between the protein and the ligand within 4 Å",
            "Align mutant onto wildtype",
            "Align only chain A of both structures",
            "Save a preview PNG image",
            "Save a ray-traced figure for a paper",
            "Save the session to a .pse file",
            "Export the active site selection as a PDB file",
            "Export selected atoms to mmCIF format",
        ],
        "positive_multi_step": [
            (
                "Load lysozyme (2LZM), show as cartoon, "
                "color by secondary structure"
            ),
            (
                "Load trypsin (1TIM), set background white, "
                "save a high-resolution PNG"
            ),
            (
                "Load hemoglobin (4HHB), color by chain, "
                "label each chain with its ID"
            ),
            (
                "Load calmodulin (1CLL), show as sticks, "
                "select calcium ions within 3 Å of protein"
            ),
            (
                "Load the kinase (1ATP), select ATP ligand, "
                "show contacts to protein within 3.5 Å"
            ),
            (
                "Load two forms of the same protein, align them, "
                "color mobile red, target blue"
            ),
            (
                "Load insulin receptor (2HR7), select chain A, "
                "export it as a PDB file"
            ),
            (
                "Load a local structure file, color by chain, "
                "save the session"
            ),
            (
                "Load streptavidin (1SWB), show surface, "
                "color by secondary structure, set white background"
            ),
            (
                "Load myoglobin (1MBO), add hydrogens, "
                "measure Tyr146 OH to heme iron distance"
            ),
            (
                "Load the wild-type and mutant, align them, "
                "measure the active site distance in both, "
                "save a comparison image"
            ),
            (
                "Load the complex (7BZ5), select residues "
                "near the inhibitor, label them, save the session"
            ),
            (
                "Load 6LU7, show sticks, select all ligands, "
                "show contacts to protein within 4 Å, "
                "save a ray-traced figure"
            ),
            (
                "Load three structures, align all to the first, "
                "color each a distinct color, set white background"
            ),
            (
                "Load the antibody (6XC2), show as cartoon, "
                "color by chain, select the CDR loops, "
                "label them with residue names"
            ),
            (
                "Load EGFR kinase (1IEP), select the ATP pocket "
                "residues, measure two key distances, export the "
                "pocket as PDB"
            ),
            (
                "Load cytochrome C (1HRC), color by B-factor "
                "spectrum, add hydrogens, save the session"
            ),
            (
                "Load two structures, align chain A of each, "
                "show contacts at the interface, save the image"
            ),
            (
                "Load ferritin (3F32), list all chains, "
                "select chain A, show it as surface, "
                "color red, set white background"
            ),
            (
                "Load the ribosome subunit (4V9D), show as cartoon, "
                "color RNA blue, protein grey, save preview PNG"
            ),
            (
                "Load 1ATP, select residues Lys72 and Asp184, "
                "measure the salt-bridge distance, label both residues"
            ),
            (
                "Load a local CIF file, show as cartoon, "
                "color by chain, export as PDB, save session"
            ),
            (
                "Load Hsp90 (1YES), remove waters, show protein as "
                "ribbon, show ligand as sticks, measure 3 contacts"
            ),
            (
                "Load thrombin (2BXT), select the catalytic triad, "
                "label residues, show contacts with the inhibitor"
            ),
        ],
        # Deep-workflow seeds: 10–25 sequential tool calls expected.
        # These represent complex, realistic multi-step requests that a
        # structural biologist would write as a single prompt to the
        # LangGraph agent planner.  The generating LLM must produce a
        # correspondingly long tool_calls array — truncation is an error.
        "positive_deep_workflow": [
            (
                "Load 6LU7, select the catalytic dyad (His41 and "
                "Cys145), show those residues as sticks, label them "
                "by residue name, select all HETATM within 5 Å "
                "excluding water, show the ligand as sticks too, "
                "measure the distance from Cys145 SG to the closest "
                "ligand atom, show all contacts between the catalytic "
                "residues and the ligand within 4.5 Å, set the "
                "background to white, and save a ray-traced "
                "publication PNG"
            ),
            (
                "Load the open (4AKE) and closed (1AKE) forms of "
                "adenylate kinase, align the closed onto the open, "
                "select the LID domain (chain A residues 118-160) in "
                "both structures, color the open form cyan and the "
                "closed form orange, measure three inter-domain "
                "distances in each conformation, export the LID domain "
                "selection from each structure as separate PDB files, "
                "and save the session"
            ),
            (
                "Load the GroEL chaperonin (1AON), color each of the "
                "seven chains in the ring a distinct color, show the "
                "ring as surface, select all residues within 8 Å of "
                "the central cavity aperture, show those as sticks, "
                "label them by residue name, and save a ray-traced "
                "figure with a black background"
            ),
            (
                "Load antibody 6XC2, select all six CDR loops "
                "(L1, L2, L3 on the light chain; H1, H2, H3 on the "
                "heavy chain) individually, color each CDR a different "
                "color, show contacts at the CDR-antigen interface "
                "within 4 Å, label all CDR residues with their three- "
                "letter codes, set white background, and export a "
                "high-resolution ray-traced figure"
            ),
            (
                "Load the thrombin–inhibitor complex (2BXT), select "
                "the catalytic triad (His57, Asp102, Ser195), show it "
                "as sticks, label by residue name, select the inhibitor "
                "(HETATM excluding water), show it as sticks, measure "
                "the Ser195 OG to inhibitor distance and the His57 "
                "NE2 to inhibitor distance, show all contacts between "
                "the triad and inhibitor within 3.5 Å, and save a "
                "session plus a ray-traced figure"
            ),
            (
                "Load wild-type and mutant EGFR kinase structures "
                "(1IEP for WT and 2GS7 for the T790M mutant), align "
                "the mutant onto the WT, select the ATP-binding pocket "
                "in each (residues within 6 Å of the co-crystallized "
                "ATP analog), measure three key distances in each "
                "pocket, color the WT blue and the mutant red, export "
                "both pocket selections as PDB files, and save the "
                "comparison session"
            ),
            (
                "Load the beta-2 adrenergic receptor (2RH1), show as "
                "cartoon, color by secondary structure, select the "
                "transmembrane helices individually (seven chains or "
                "helix regions), color each helix a distinct color, "
                "select the ligand (carazolol) and show it as sticks, "
                "select all residues within 5 Å of the ligand, show "
                "contacts at 4 Å, label the binding-site residues by "
                "name, set white background, and save a ray-traced PNG"
            ),
            (
                "Load the hemoglobin tetramer (1HHO), select each of "
                "the four chains (two alpha, two beta) individually, "
                "color each chain differently, select the heme groups "
                "(HETATM), show them as sticks and color them orange, "
                "measure the iron–iron distance between the two alpha "
                "chains, show contacts between each heme and its "
                "surrounding protein residues within 4 Å, label the "
                "proximal histidines by residue name, and save a "
                "session and a ray-traced figure"
            ),
            (
                "Load the ribosome subunit (4V9D), show RNA as cartoon "
                "in blue, show all protein chains as cartoon in grey, "
                "select the decoding center (residues within 8 Å of "
                "the A-site tRNA position), show contacts between the "
                "mRNA and ribosomal RNA within 3.5 Å, label key "
                "ribosomal RNA residues by name, set black background, "
                "and export a high-resolution ray-traced preview PNG"
            ),
            (
                "Load calmodulin bound to a peptide (1CLL), add "
                "hydrogens, select the four calcium-binding EF-hand "
                "loops individually, color each loop a distinct color, "
                "measure the Ca–Ca distances between EF hands 1-2 and "
                "3-4, show contacts between the calcium ions and their "
                "coordinating oxygens within 2.5 Å, label all "
                "coordinating residues by name, and save the session"
            ),
            (
                "Load the GroES co-chaperonin cap (1AON), then load "
                "the GroEL ring (1AON) separately, align GroES onto "
                "the apical domain of GroEL, show contacts at the "
                "GroEL–GroES interface within 5 Å, color GroEL marine "
                "and GroES orange, select mobile loop residues (GGIVLTGSAA "
                "region) and label by name, measure three interface "
                "distances, and save a ray-traced figure of the complex"
            ),
            (
                "Load the proteasome 20S core (1YAL), list all chains, "
                "select the catalytic beta subunits by chain, show them "
                "as surface, color each beta subunit a distinct color, "
                "select the active-site threonine residues (Thr1 in "
                "each beta subunit), show them as sticks, measure the "
                "inter-subunit distances between active sites, label "
                "all Thr1 residues by name, and save the session plus "
                "a ray-traced figure"
            ),
            (
                "Load P450cam in the substrate-bound form (2CPP), add "
                "hydrogens, select the heme iron and its axial "
                "cysteine ligand (Cys357), show them as sticks, select "
                "the substrate (camphor, HETATM), show it as sticks, "
                "measure the Fe–substrate carbon distance, show all "
                "contacts between the substrate and active-site "
                "residues within 4 Å, label active-site residues by "
                "name, set white background, and export a ray-traced PNG"
            ),
            (
                "Load the HIV protease dimer with inhibitor (1HVR), "
                "select chain A and chain B separately and color them "
                "differently, select the inhibitor (HETATM excluding "
                "water), show it as sticks in yellow, select all "
                "residues from both chains within 5 Å of the inhibitor, "
                "show contacts at 4 Å, label binding-site residues by "
                "name, measure two key dimer-interface distances, and "
                "save a session and a ray-traced publication figure"
            ),
            (
                "Load myosin S1 fragment (1MND), show as cartoon, "
                "select the nucleotide-binding P-loop (residues 175-185 "
                "in chain A), show it as sticks, select the ATP "
                "analog (HETATM), show it as sticks, measure the Lys185 "
                "NZ to ATP gamma-phosphate distance, measure the Gly457 "
                "CA to ATP distance, show contacts within 3.5 Å, label "
                "all P-loop residues by name, and save the session"
            ),
            (
                "Load the ion channel KcsA (1BL8) in its closed state, "
                "select each of the four identical subunits individually, "
                "color each subunit a distinct color, select the "
                "selectivity filter (residues TVGYG, approximately "
                "residues 74-78 in each chain), show them as sticks, "
                "select the potassium ions (HETATM), show them as "
                "spheres, measure ion–ion distances along the pore, "
                "show contacts between ions and filter residues within "
                "3 Å, and save a ray-traced figure"
            ),
            (
                "Load the insulin hexamer (4INS), list all loaded "
                "objects, select all six insulin chains and color each "
                "a distinct color, select the zinc ions (HETATM), show "
                "them as spheres in grey, select all residues within "
                "4 Å of any zinc ion, show those as sticks, measure "
                "two Zn–His coordination distances, label all zinc- "
                "coordinating histidines by residue name, and save a "
                "session and a ray-traced publication figure"
            ),
            (
                "Load the triosephosphate isomerase dimer (1TIM), "
                "align the two subunits on each other, select the "
                "active-site residues in both subunits (His95 and "
                "Glu165 and their neighbors), show them as sticks, "
                "label them by residue name, measure the His95 NE2 "
                "to Glu165 OE1 distance in each subunit, show contacts "
                "between active-site residues within 4 Å, set white "
                "background, and export both active-site selections as "
                "PDB files, then save the session"
            ),
            (
                "Load the voltage-gated potassium channel (2A79), "
                "show as cartoon, select the voltage sensor domain "
                "(S1-S4 helices, approximately residues 1-145 in each "
                "chain), color the voltage sensor orange and the pore "
                "domain blue, select the gating charge residues "
                "(arginines in S4), show them as sticks, label by "
                "residue name and number, measure three S4-arginine "
                "to S2-glutamate distances, and save a ray-traced figure"
            ),
            (
                "Load the ubiquitin-proteasome degradation signal "
                "complex (1UBQ plus 1YAL), align the structures, select "
                "the C-terminus of ubiquitin (last 5 residues), select "
                "the 26S proteasome receptor site, show contacts "
                "between them at 5 Å, color ubiquitin yellow and the "
                "receptor marine, label all interface residues by "
                "residue name, export the interface as a PDB, and save "
                "a ray-traced comparison figure"
            ),
            (
                "Load the whole antibody–antigen complex (1IGT), show "
                "as cartoon, color Fc region grey, color Fab1 marine, "
                "color Fab2 orange, select the antigen chain and color "
                "it red, select all residues at the Fab1-antigen "
                "interface within 5 Å, show contacts at 4 Å, label "
                "interface residues by name, measure three epitope "
                "distances, export the epitope as PDB, and save a "
                "session plus a ray-traced publication figure"
            ),
            (
                "Load the ABC transporter (1OYA), list all chains, "
                "select the two NBD (nucleotide-binding domain) "
                "subunits, color NBD1 teal and NBD2 salmon, select the "
                "ATP-binding sites in each NBD (HETATM within 6 Å), "
                "show ATP analogs as sticks, measure the Walker-A "
                "lysine to ATP gamma-phosphate distances in both NBDs, "
                "show contacts between each ATP and its NBD within "
                "4 Å, label key Walker-A residues by name, and save a "
                "ray-traced figure plus session"
            ),
            (
                "Load the PCNA sliding clamp trimer (1AXC), select "
                "each of the three identical subunits and color them "
                "differently, select the inter-subunit interfaces, "
                "show contacts at each interface within 4 Å, measure "
                "three inter-subunit distances, label key interface "
                "residues by name, show the inner DNA-binding surface "
                "as surface representation, set black background, and "
                "save a ray-traced figure"
            ),
            (
                "Load the caspase-3 homodimer (2XYZ), add hydrogens, "
                "select the two active sites (Cys163 and His121 in "
                "each chain), show them as sticks, select the "
                "substrate peptide analog (HETATM), show it as sticks, "
                "measure Cys163 SG to substrate P1 carbonyl distances "
                "in both active sites, show contacts between each "
                "active site and the substrate within 4 Å, label all "
                "key residues by name, and export both active sites "
                "as PDB files plus save a session"
            ),
            (
                "Load three structures of the same kinase in different "
                "states: apo (1ATP), ADP-bound (2PHK), and ATP-analog- "
                "bound (1CDK), align all three onto the apo structure, "
                "color each a distinct color, select the activation "
                "loop in all three (chain A, residues 150-172), measure "
                "the DFG-motif Phe to C-helix Glu distances in each "
                "state, show contacts between the activation loop and "
                "the nucleotide in each bound state, label key residues "
                "by name in each structure, and save the comparative "
                "session plus a ray-traced figure"
            ),
        ],
        "negative_viewport": [
            "Rotate the molecule so I can see the active site",
            "Spin the protein around the Y axis",
            "Zoom into the binding pocket",
            "Tilt the view 45 degrees to the left",
            "Center the camera on the ligand",
            "Zoom out to see the full protein",
            "Rotate 180 degrees to see the back",
            "Clip the front half of the protein away",
            "Pan the view to the right",
            "Reset the view to the default orientation",
            "Orient the molecule so the active site faces me",
            "Move the camera to see the N-terminus",
            "Switch to a top-down view of the binding site",
            "Make the molecule spin slowly",
            "Focus the view on chain A",
            "Adjust the clipping planes to expose the interior",
            "Navigate to a side view of the dimer interface",
            "Take a screenshot from the current angle",
            "Zoom to fit the whole complex in the viewport",
            "Rotate the view to match this reference figure",
            "Centre the display on the selected residues",
            "Toggle perspective projection",
            "Adjust the depth-of-field setting",
            "Move the structure so it is centred in the frame",
            "Show the molecule from behind",
        ],
        "negative_out_of_scope": [
            "Run a 10 ns molecular dynamics simulation",
            "Dock this ligand into the binding site automatically",
            "Calculate the free energy of binding",
            "Predict the structure from the sequence",
            "Perform a normal mode analysis",
            "Calculate the protein's pKa values",
            "Align the protein sequences",
            "Search for similar structures in the PDB",
            "Build a homology model",
            "Calculate RMSD over a trajectory",
            "Perform energy minimisation on this structure",
            "Run quantum mechanical calculations on the active site",
            "Generate conformer ensembles for this ligand",
            "Calculate the solvent-accessible surface area",
            "Predict the effect of this mutation on stability",
            "Cluster the MD trajectory frames",
            "Extract the pharmacophore model from these actives",
            "Calculate the electrostatic potential surface",
            "Parameterise the small molecule for AMBER",
            "Compute the protein-protein docking score",
            "Run a virtual screening campaign against this pocket",
            "Calculate binding free energy with FEP",
            "Perform de novo structure prediction",
            "Generate a contact map from a trajectory",
            "Identify all druggable pockets in this structure",
        ],
        "positive_context_aware": [
            "Now color the structure I just loaded red",
            "Align the second structure onto the first one",
            "Select residues near the ligand we highlighted",
            "Save the structure I just selected as PDB",
            "Add hydrogens to the protein we just loaded",
            "Measure the distance in the structure that's open",
            "Color all currently loaded objects by chain",
            "Remove the first structure and keep the second",
            "Export the selection we just made to mmCIF",
            "Label the residues in the selection from before",
        ],
    }


# ---------------------------------------------------------------------------
# Mode: generate_prompts
# ---------------------------------------------------------------------------

# Two separate system prompts — positive and negative seeds are NEVER
# batched together.  Mixing them lets the LLM "bleed" tool-call patterns
# into negative seeds when it sees both types in the same context window.

# IMPORTANT: deep-workflow seeds (category positive_deep_workflow) require
# 10–25 sequential tool calls.  The generating LLM MUST produce the full
# sequence without truncating.  A 5-call answer for a 15-call seed is wrong.
_SYSTEM_PROMPT_POSITIVE = (
    "You are generating training data for a PyMOL AI assistant that acts\n"
    "as a LangGraph agent planner.  Given one user prompt it produces the\n"
    "complete sequential plan of ALL required tool calls.  It is NOT a\n"
    "chatbot — it never asks follow-up questions.\n\n"
    "AVAILABLE TOOLS (JSON):\n"
    "{tools_json}\n\n"
    "PYMOL SELECTION ALGEBRA (used in reference_selection, selection1,\n"
    "selection2, and target string arguments):\n"
    "  object_name                   — all atoms in a named object\n"
    "  chain A                       — chain A of any object\n"
    "  object and chain A            — chain A of a specific object\n"
    "  object and hetatm             — all HETATM in object\n"
    "  object and hetatm and not resn HOH+HOH2  — ligand, no water\n"
    "  byres (object and chain A and resi 48+52+61)  — full residues\n"
    "  byres (object and chain A and resn HIS+ASP+SER) — by residue name\n"
    "  byres (object and polymer within 5.0 of (ligand)) — pocket\n"
    "  object and chain A or object and chain B  — two chains\n\n"
    "YOUR TASK:\n"
    "For each scenario seed below, produce one complete training example.\n"
    "Output a single JSON array with one object per seed.\n"
    "Each object must have exactly two keys:\n"
    '  "user_request": A natural-language sentence a lab scientist might say.\n'
    '  "tool_calls": A JSON array of objects, each with:\n'
    '    "name": (string) - must be one of the tool names above\n'
    '    "arguments": (object) - must match the tool\'s parameter schema\n\n'
    "CRITICAL RULES:\n"
    "- Deep-workflow seeds (marked [deep_workflow]) REQUIRE 10-25 calls.\n"
    "  A short answer for a deep seed is WRONG.  Include every step.\n"
    "- Use only tool names from the list above.\n"
    "- Use realistic PDB IDs: start with a digit, 4 chars (e.g. 1TIM, 4HHB).\n"
    "- Chain identifiers must be a single letter (A, B, C, ...).\n"
    "- Residue IDs must be integers.\n"
    "- reference_selection, selection1, selection2 MAY be selection-algebra\n"
    "  strings (e.g. 'byres (1ubq and chain A and resn HIS+ASP)').\n"
    "- Do NOT invent tool names. Do NOT add fields not in the schema.\n"
    "- Output ONLY the JSON array. No markdown fences, no extra text.\n\n"
    "SCENARIO SEEDS TO EXPAND:\n"
)

_SYSTEM_PROMPT_NEGATIVE = (
    "You are generating NEGATIVE training examples for a PyMOL AI assistant.\n"
    "These examples teach the model to REFUSE and produce NO tool calls.\n\n"
    "AVAILABLE TOOLS (JSON - shown only so you know what tools exist):\n"
    "{tools_json}\n\n"
    "YOUR TASK:\n"
    "For each scenario seed below, produce one training example where the\n"
    "assistant correctly refuses to call any tool.\n"
    "Output a single JSON array with one object per seed.\n"
    "Each object must have exactly two keys:\n"
    '  "user_request": A natural-language sentence a lab scientist might say.\n'
    '  "tool_calls": []  <- ALWAYS EMPTY. NO EXCEPTIONS.\n\n'
    "CRITICAL RULES - READ CAREFULLY:\n"
    '- EVERY single example MUST have "tool_calls": [].\n'
    "- Do NOT generate any tool calls, not even save_session or "
    "list_loaded_objects.\n"
    "- Do NOT try to be helpful by partially completing the request.\n"
    "- The seeds below are EITHER viewport operations (rotate, zoom, pan,\n"
    "  clip, tilt, orient) OR computational tasks (MD, docking, pKa, NMA,\n"
    "  homology modelling, free energy, RMSD, virtual screening). NONE of\n"
    "  them can be automated with the available tools.\n"
    "- Output ONLY the JSON array. No markdown fences, no extra text.\n"
    "- If you produce a single non-empty tool_calls list, the entire batch\n"
    "  is discarded and must be resubmitted.\n\n"
    "SCENARIO SEEDS TO EXPAND:\n"
)


def _generate_prompts(
    seeds_by_category: dict[str, list[str]],
    n_positive: int,
    n_negative: int,
    n_context: int,
    n_deep: int,
    output_dir: pathlib.Path,
    tool_schemas: list[dict],
) -> None:
    """Write categorised prompt batch files to ``output_dir/prompts/``.

    Four batch-file types are produced:

    - ``batch_pos_NNN.txt``: positive + context-aware seeds.
      Every example MUST have non-empty ``tool_calls``.
    - ``batch_deep_NNN.txt``: deep-workflow seeds (10-25 calls each).
      The generating LLM must NOT truncate the tool-call sequence.
    - ``batch_neg_NNN.txt``: negative seeds only.
      Every example MUST have ``tool_calls: []``.

    Separating categories prevents the LLM from bleeding tool-call
    patterns into negative seeds when both appear in the same batch.

    Scaling to 100 k examples
    -------------------------
    Set n_positive=60000, n_deep=30000, n_negative=10000 and run on
    a machine with multiple GPUs and a Dask cluster.  The NeMo Data
    Designer backend will distribute LLM inference across parallel
    workers.  Increase max_parallel_requests in workflow.py accordingly
    (e.g. 32 for a 4-GPU box).  The NeMo Curator dedup step should be
    run with a multi-GPU LocalCUDACluster to handle the larger dataset.

    Args:
      seeds_by_category: Dict of category -> list of seed strings.
      n_positive: Total positive (tool-calling) examples to request.
      n_negative: Total negative (empty tool_calls) examples to request.
      n_context: Total context-aware examples to request.
      n_deep: Total deep-workflow (10-25 tool calls) examples.
      output_dir: Root output directory; prompt files go in ``prompts/``.
      tool_schemas: Tool schema dicts to embed in each prompt file.
    """
    tmp_prompts_dir = output_dir / "prompts"
    tmp_prompts_dir.mkdir(parents=True, exist_ok=True)

    tmp_n_single = n_positive // 4
    tmp_n_multi = n_positive - tmp_n_single
    tmp_n_neg_vp = n_negative // 2
    tmp_n_neg_oos = n_negative - tmp_n_neg_vp

    def _sample(category: str, count: int) -> list[str]:
        """Sample ``count`` seeds from ``category`` with replacement.

        Args:
          category: Key in ``seeds_by_category``.
          count: Number of seeds to sample.

        Returns:
          A list of sampled seed strings.
        """
        tmp_pool = seeds_by_category[category]
        tmp_rng = random.Random(42)
        return [tmp_rng.choice(tmp_pool) for _ in range(count)]

    # -------- positive pool (single + multi + context) --------
    tmp_pos_seeds: list[tuple[str, str]] = []
    for tmp_seed in _sample("positive_single_tool", tmp_n_single):
        tmp_pos_seeds.append(("positive_single_tool", tmp_seed))
    for tmp_seed in _sample("positive_multi_step", tmp_n_multi):
        tmp_pos_seeds.append(("positive_multi_step", tmp_seed))
    for tmp_seed in _sample("positive_context_aware", n_context):
        tmp_pos_seeds.append(("positive_context_aware", tmp_seed))
    random.Random(99).shuffle(tmp_pos_seeds)

    # -------- deep-workflow pool --------
    tmp_deep_seeds: list[tuple[str, str]] = []
    for tmp_seed in _sample("positive_deep_workflow", n_deep):
        tmp_deep_seeds.append(("positive_deep_workflow", tmp_seed))
    random.Random(77).shuffle(tmp_deep_seeds)

    # -------- negative pool (viewport + out_of_scope) --------
    tmp_neg_seeds: list[str] = []
    tmp_neg_seeds.extend(_sample("negative_viewport", tmp_n_neg_vp))
    tmp_neg_seeds.extend(
        _sample("negative_out_of_scope", tmp_n_neg_oos)
    )
    random.Random(55).shuffle(tmp_neg_seeds)

    tmp_tools_json = json.dumps(tool_schemas, indent=2)
    tmp_batch_size = training_config.BATCH_SIZE_PER_PROMPT_FILE

    # Write positive batch files
    tmp_pos_batch_idx = 0
    for tmp_start in range(0, len(tmp_pos_seeds), tmp_batch_size):
        tmp_batch = tmp_pos_seeds[
            tmp_start: tmp_start + tmp_batch_size
        ]
        tmp_pos_batch_idx += 1
        tmp_seed_block = "\n".join(
            f"{tmp_i + 1}. [{tmp_cat}] {tmp_seed}"
            for tmp_i, (tmp_cat, tmp_seed) in enumerate(tmp_batch)
        )
        tmp_content = (
            _SYSTEM_PROMPT_POSITIVE.format(tools_json=tmp_tools_json)
            + tmp_seed_block
        )
        tmp_out = (
            tmp_prompts_dir / f"batch_pos_{tmp_pos_batch_idx:03d}.txt"
        )
        with open(tmp_out, "w", encoding="utf-8") as tmp_fh:
            tmp_fh.write(tmp_content)

    # Write deep-workflow batch files (higher expected output length).
    tmp_deep_batch_idx = 0
    for tmp_start in range(0, len(tmp_deep_seeds), tmp_batch_size):
        tmp_batch = tmp_deep_seeds[
            tmp_start: tmp_start + tmp_batch_size
        ]
        tmp_deep_batch_idx += 1
        tmp_seed_block = "\n".join(
            f"{tmp_i + 1}. [deep_workflow] {tmp_seed}"
            for tmp_i, (_cat, tmp_seed) in enumerate(tmp_batch)
        )
        tmp_content = (
            _SYSTEM_PROMPT_POSITIVE.format(tools_json=tmp_tools_json)
            + tmp_seed_block
        )
        tmp_out = (
            tmp_prompts_dir
            / f"batch_deep_{tmp_deep_batch_idx:03d}.txt"
        )
        with open(tmp_out, "w", encoding="utf-8") as tmp_fh:
            tmp_fh.write(tmp_content)

    # Write negative batch files
    tmp_neg_batch_idx = 0
    for tmp_start in range(0, len(tmp_neg_seeds), tmp_batch_size):
        tmp_batch = tmp_neg_seeds[
            tmp_start: tmp_start + tmp_batch_size
        ]
        tmp_neg_batch_idx += 1
        tmp_seed_block = "\n".join(
            f"{tmp_i + 1}. {tmp_seed}"
            for tmp_i, tmp_seed in enumerate(tmp_batch)
        )
        tmp_content = (
            _SYSTEM_PROMPT_NEGATIVE.format(tools_json=tmp_tools_json)
            + tmp_seed_block
        )
        tmp_out = (
            tmp_prompts_dir / f"batch_neg_{tmp_neg_batch_idx:03d}.txt"
        )
        with open(tmp_out, "w", encoding="utf-8") as tmp_fh:
            tmp_fh.write(tmp_content)

    print(
        f"[generate_prompts] Wrote {tmp_pos_batch_idx} positive, "
        f"{tmp_deep_batch_idx} deep-workflow, and "
        f"{tmp_neg_batch_idx} negative batch files to "
        f"{tmp_prompts_dir}/"
    )
    print(
        "Next step: submit each .txt to your LLM and save the "
        "response as the matching .response.txt file."
    )


# ---------------------------------------------------------------------------
# Mode: collect_responses
# ---------------------------------------------------------------------------


def _collect_responses(
    input_dir: pathlib.Path,
    output_dir: pathlib.Path,
    tool_schemas: list[dict],
) -> None:
    """Validate .response.txt files and write JSONL training datasets.

    For each ``batch_*.response.txt`` file in ``input_dir``:
    1. Parse the JSON array.
    2. Validate each example against the tool schemas.
    3. Valid examples accumulate into ``train.jsonl`` / ``val.jsonl``.
    4. Invalid examples go to ``rejected.jsonl`` with a reason field.

    The train/validation split is stratified at 90/10.

    Args:
      input_dir: Directory containing ``batch_*.response.txt`` files.
      output_dir: Directory where JSONL files are written.
      tool_schemas: Tool schema dicts used for validation.
    """
    # Accept both new-style categorised files (batch_pos_ / batch_neg_)
    # and legacy mixed files (batch_NNN) from earlier pipeline runs.
    response_files = sorted(
        list(input_dir.glob("batch_pos_*.response.txt"))
        + list(input_dir.glob("batch_deep_*.response.txt"))
        + list(input_dir.glob("batch_neg_*.response.txt"))
        + list(input_dir.glob("batch_[0-9]*.response.txt")),
        key=lambda p: p.name,
    )
    if not response_files:
        print(
            f"[ERROR] No batch_*.response.txt files found in {input_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    system_content = _build_system_content(tool_schemas)

    valid_examples: list[dict] = []
    rejected_examples: list[dict] = []

    for resp_file in response_files:
        # Detect category from filename.
        # Only "batch_neg_*" must have tool_calls: [].
        # "batch_deep_*" must have at least 10 tool calls.
        # Positive and legacy files use schema-only validation.
        tmp_is_negative_batch = resp_file.name.startswith("batch_neg_")
        tmp_is_deep_batch = resp_file.name.startswith("batch_deep_")

        try:
            raw = _read_text(resp_file).strip()
        except (UnicodeDecodeError, OSError) as exc:
            rejected_examples.append(
                {
                    "source": resp_file.name,
                    "reason": f"read error: {exc}",
                }
            )
            continue

        # Strip optional markdown fences
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            rejected_examples.append(
                {
                    "source": resp_file.name,
                    "reason": f"JSON parse error: {exc}",
                    "raw": raw[:500],
                }
            )
            continue

        if not isinstance(parsed, list):
            rejected_examples.append(
                {
                    "source": resp_file.name,
                    "reason": "response is not a JSON array",
                    "raw": raw[:200],
                }
            )
            continue

        for ex in parsed:
            # Negative batches must have empty tool_calls.
            if tmp_is_negative_batch and ex.get("tool_calls"):
                rejected_examples.append(
                    {
                        "source": resp_file.name,
                        "reason": (
                            "negative batch example must have "
                            "tool_calls: [] — got "
                            f"{len(ex['tool_calls'])} call(s)"
                        ),
                        "example": ex,
                    }
                )
                continue

            # Deep-workflow batches must have >= 10 tool calls.
            if tmp_is_deep_batch:
                tmp_n_calls = len(ex.get("tool_calls") or [])
                if tmp_n_calls < 10:
                    rejected_examples.append(
                        {
                            "source": resp_file.name,
                            "reason": (
                                "deep-workflow batch example must "
                                f"have >= 10 tool calls — got "
                                f"{tmp_n_calls}"
                            ),
                            "example": ex,
                        }
                    )
                    continue

            tmp_reason = _validate_example(ex, tool_schemas)
            if tmp_reason:
                rejected_examples.append(
                    {
                        "source": resp_file.name,
                        "reason": tmp_reason,
                        "example": ex,
                    }
                )
            else:
                tmp_msg = _build_messages(ex, system_content)
                valid_examples.append({"messages": tmp_msg})

    # Shuffle and split
    rng = random.Random(2026)
    rng.shuffle(valid_examples)
    split = int(len(valid_examples) * training_config.TRAIN_SPLIT_RATIO)
    train_set = valid_examples[:split]
    val_set = valid_examples[split:]

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "train.jsonl", train_set)
    _write_jsonl(output_dir / "val.jsonl", val_set)
    _write_jsonl(output_dir / "rejected.jsonl", rejected_examples)

    print(
        f"[collect_responses] valid={len(valid_examples)}, "
        f"train={len(train_set)}, val={len(val_set)}, "
        f"rejected={len(rejected_examples)}"
    )
    print(f"  → {output_dir}/train.jsonl")
    print(f"  → {output_dir}/val.jsonl")
    print(f"  → {output_dir}/rejected.jsonl (review & re-submit)")


# ---------------------------------------------------------------------------
# Message building helpers
# ---------------------------------------------------------------------------

_SYSTEM_CONTENT_TEMPLATE = (
    "You are a PyMOL AI assistant for the cBioMOL platform. "
    "You help structural biologists automate protein visualization "
    "workflows using natural language.\n\n"
    "When the user asks you to perform a structural biology operation, "
    "respond with the appropriate tool call. Do not attempt to perform "
    "operations outside the scope of the available tools. For operations "
    "that require mouse interaction (rotating, zooming the viewport), "
    "explain that those must be done manually."
)


def _build_system_content(tool_schemas: list[dict]) -> str:
    """Construct the system message content used in training examples.

    Args:
      tool_schemas: Tool schemas; the Qwen2.5 template embeds these
        automatically via the ``tools`` argument of ``apply_chat_template``,
        so this function returns only the base system prompt.

    Returns:
      The base system prompt string (without tool schemas).
    """
    return _SYSTEM_CONTENT_TEMPLATE


# Eight refusal variants ensure the model sees linguistic diversity in
# negative training examples rather than memorising one fixed string.
# Selected deterministically per example via character-sum modulo so
# results are reproducible across runs.
_REFUSAL_TEXTS: list[str] = [
    (
        "I'm sorry, but this operation requires direct mouse interaction "
        "with the PyMOL viewport and cannot be automated. "
        "Please perform it manually."
    ),
    (
        "This action involves manual viewport navigation and is outside "
        "the scope of the available automation tools."
    ),
    (
        "I can't automate this request. Viewport operations such as "
        "rotation, zooming, and panning must be performed directly in PyMOL."
    ),
    (
        "That operation is not supported by the available tools. "
        "Please perform this step manually in PyMOL."
    ),
    (
        "This is beyond the scope of what I can automate. The cBioMOL tools "
        "cover structural visualisation workflows, not manual viewport "
        "navigation or advanced computational methods."
    ),
    (
        "I'm unable to carry out this request automatically. "
        "Please perform it manually in the PyMOL viewport."
    ),
    (
        "Apologies, but this falls outside the scope of the cBioMOL "
        "automation tools. The requested operation must be done manually."
    ),
    (
        "This operation cannot be automated here. "
        "Please use PyMOL's interface directly to perform it."
    ),
]


def _build_messages(example: dict, system_content: str) -> list[dict]:
    """Convert a validated example dict into the HuggingFace messages format.

    Negative examples (empty tool_calls) are assigned one of eight
    refusal-text variants, chosen deterministically from the user request
    string.  This prevents the model from overfitting to a single memorised
    refusal string while keeping results reproducible across runs.

    Args:
      example: A validated dict with ``user_request`` and ``tool_calls``.
      system_content: The base system prompt string.

    Returns:
      A list of message dicts in OpenAI / HuggingFace format.
    """
    messages: list[dict] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": example["user_request"]},
    ]

    if example["tool_calls"]:
        tool_calls_fmt = [
            {
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc.get("arguments", {})),
                },
            }
            for tc in example["tool_calls"]
        ]
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_fmt,
            }
        )
    else:
        # Choose a refusal variant deterministically from the request text.
        char_sum = sum(ord(c) for c in example["user_request"][:40])
        refusal = _REFUSAL_TEXTS[char_sum % len(_REFUSAL_TEXTS)]
        messages.append(
            {
                "role": "assistant",
                "content": refusal,
            }
        )

    return messages


def _write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    """Write a list of dicts to a JSONL file (one JSON object per line).

    Args:
      path: Output file path.
      records: List of dicts to serialise.
    """
    with open(path, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
      Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="cBioMOL AI dataset generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["generate_prompts", "collect_responses"],
        required=True,
        help="Operation mode.",
    )
    parser.add_argument(
        "--output_dir",
        type=pathlib.Path,
        default=pathlib.Path("data"),
        help="Root directory for output files.",
    )
    parser.add_argument(
        "--input_dir",
        type=pathlib.Path,
        default=pathlib.Path("data/prompts"),
        help=(
            "Directory containing batch_*.response.txt files "
            "(collect_responses mode only)."
        ),
    )
    parser.add_argument(
        "--schemas_file",
        type=pathlib.Path,
        default=pathlib.Path("data/tools.json"),
        help="Path to the tool schemas JSON file.",
    )
    parser.add_argument(
        "--n_positive",
        type=int,
        default=1400,
        help="Total positive (tool-calling) examples.",
    )
    parser.add_argument(
        "--n_negative",
        type=int,
        default=800,
        help="Total negative (no tool call) examples.",
    )
    parser.add_argument(
        "--n_context",
        type=int,
        default=400,
        help="Total context-aware examples.",
    )
    parser.add_argument(
        "--n_deep",
        type=int,
        default=600,
        help=(
            "Total deep-workflow (10-25 tool calls) examples. "
            "Set to 30000 when scaling to 100 k total examples."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the dataset generation script."""
    args = _parse_args()
    tool_schemas = _load_tool_schemas(args.schemas_file)

    if args.mode == "generate_prompts":
        tmp_seeds = _build_seeds()
        _generate_prompts(
            tmp_seeds,
            args.n_positive,
            args.n_negative,
            args.n_context,
            args.n_deep,
            args.output_dir,
            tool_schemas,
        )
    else:
        _collect_responses(
            args.input_dir,
            args.output_dir,
            tool_schemas,
        )


if __name__ == "__main__":
    main()
