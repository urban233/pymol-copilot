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
                "Load lysozyme (2LZM), show as cartoon, color by secondary structure"
            ),
            (
                "Load trypsin (1TIM), set background white, save a high-resolution PNG"
            ),
            (
                "Load hemoglobin (4HHB), color by chain, label each chain with its ID"
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
                "Load two forms of the same protein, "
                "align them, color mobile red, target blue"
            ),
            (
                "Load insulin receptor (2HR7), select chain A, export it as a PDB file"
            ),
            ("Load a local structure file, color by chain, save the session"),
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

_SYSTEM_PROMPT_POSITIVE = (
    "You are generating training data for a PyMOL AI assistant.\n"
    "The assistant helps structural biologists automate protein visualization\n"
    "using natural language.\n\n"
    "AVAILABLE TOOLS (JSON):\n"
    "{tools_json}\n\n"
    "YOUR TASK:\n"
    "For each scenario seed below, produce one complete training example.\n"
    "Output a single JSON array with one object per seed.\n"
    "Each object must have exactly two keys:\n"
    '  "user_request": A natural-language sentence a lab scientist might say.\n'
    '  "tool_calls": A JSON array of objects, each with:\n'
    '    "name": (string) - must be one of the tool names above\n'
    '    "arguments": (object) - must match the tool\'s parameter schema\n\n'
    "RULES:\n"
    "- Use only tool names from the list above.\n"
    "- Use realistic PDB IDs: start with a digit, 4 chars (e.g. 1TIM, 4HHB).\n"
    "- Chain identifiers must be a single letter (A, B, C, ...).\n"
    "- Residue IDs must be integers.\n"
    "- Every seed below REQUIRES at least one tool call.\n"
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
    output_dir: pathlib.Path,
    tool_schemas: list[dict],
) -> None:
    """Write categorised prompt batch files to ``output_dir/prompts/``.

    Positive and negative seeds are written to SEPARATE batch files:

    - ``batch_pos_NNN.txt``: positive + context-aware seeds only.
      Every example in the response MUST have non-empty ``tool_calls``.
    - ``batch_neg_NNN.txt``: negative seeds only.
      Every example in the response MUST have ``tool_calls: []``.

    Separating the categories prevents the LLM from "bleeding" tool-call
    patterns into negative seeds when both appear in the same batch.

    Args:
      seeds_by_category: Dict of category -> list of seed strings.
      n_positive: Total positive (tool-calling) examples to request.
      n_negative: Total negative (empty tool_calls) examples to request.
      n_context: Total context-aware examples to request.
      output_dir: Root output directory; prompt files go in ``prompts/``.
      tool_schemas: Tool schema dicts to embed in each prompt file.
    """
    prompts_dir = output_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    n_single = n_positive // 4
    n_multi = n_positive - n_single
    n_neg_vp = n_negative // 2
    n_neg_oos = n_negative - n_neg_vp

    def _sample(category: str, count: int) -> list[str]:
        """Sample ``count`` seeds from ``category`` with replacement.

        Args:
          category: Key in ``seeds_by_category``.
          count: Number of seeds to sample.

        Returns:
          A list of sampled seed strings.
        """
        pool = seeds_by_category[category]
        rng = random.Random(42)
        return [rng.choice(pool) for _ in range(count)]

    # --------------- positive pool (single + multi + context) ---------------
    pos_seeds: list[tuple[str, str]] = []
    for seed in _sample("positive_single_tool", n_single):
        pos_seeds.append(("positive_single_tool", seed))
    for seed in _sample("positive_multi_step", n_multi):
        pos_seeds.append(("positive_multi_step", seed))
    for seed in _sample("positive_context_aware", n_context):
        pos_seeds.append(("positive_context_aware", seed))
    random.Random(99).shuffle(pos_seeds)

    # --------------- negative pool (viewport + out_of_scope) ----------------
    neg_seeds: list[str] = []
    neg_seeds.extend(_sample("negative_viewport", n_neg_vp))
    neg_seeds.extend(_sample("negative_out_of_scope", n_neg_oos))
    random.Random(77).shuffle(neg_seeds)

    tools_json = json.dumps(tool_schemas, indent=2)
    batch_size = training_config.BATCH_SIZE_PER_PROMPT_FILE

    # Write positive batch files
    pos_batch_idx = 0
    for start in range(0, len(pos_seeds), batch_size):
        batch = pos_seeds[start : start + batch_size]
        pos_batch_idx += 1
        seed_block = "\n".join(
            f"{i + 1}. [{cat}] {seed}" for i, (cat, seed) in enumerate(batch)
        )
        content = (
            _SYSTEM_PROMPT_POSITIVE.format(tools_json=tools_json) + seed_block
        )
        out_file = prompts_dir / f"batch_pos_{pos_batch_idx:03d}.txt"
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write(content)

    # Write negative batch files
    neg_batch_idx = 0
    for start in range(0, len(neg_seeds), batch_size):
        batch = neg_seeds[start : start + batch_size]
        neg_batch_idx += 1
        seed_block = "\n".join(
            f"{i + 1}. {seed}" for i, seed in enumerate(batch)
        )
        content = (
            _SYSTEM_PROMPT_NEGATIVE.format(tools_json=tools_json) + seed_block
        )
        out_file = prompts_dir / f"batch_neg_{neg_batch_idx:03d}.txt"
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write(content)

    print(
        f"[generate_prompts] Wrote {pos_batch_idx} positive batch files and "
        f"{neg_batch_idx} negative batch files to {prompts_dir}/"
    )
    print(
        "Next step: submit each .txt to your LLM and save the response as "
        "the matching .response.txt file."
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
        # Detect category from filename.  Only "batch_neg_*" files are
        # required to have tool_calls: [].  Positive and legacy files use
        # the existing schema-only validation.
        is_negative_batch = resp_file.name.startswith("batch_neg_")

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
            # Category-level gate: negative batches must have empty tool_calls.
            # This catches contamination where the LLM generated a valid tool
            # call for a negative seed, which would pass schema validation but
            # poison the boundary-learning signal.
            if is_negative_batch and ex.get("tool_calls"):
                rejected_examples.append(
                    {
                        "source": resp_file.name,
                        "reason": (
                            "negative batch example must have tool_calls: [] — "
                            f"got {len(ex['tool_calls'])} call(s)"
                        ),
                        "example": ex,
                    }
                )
                continue

            reason = _validate_example(ex, tool_schemas)
            if reason:
                rejected_examples.append(
                    {
                        "source": resp_file.name,
                        "reason": reason,
                        "example": ex,
                    }
                )
            else:
                msg = _build_messages(ex, system_content)
                valid_examples.append({"messages": msg})

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
    return parser.parse_args()


def main() -> None:
    """Entry point for the dataset generation script."""
    args = _parse_args()
    tool_schemas = _load_tool_schemas(args.schemas_file)

    if args.mode == "generate_prompts":
        seeds = _build_seeds()
        _generate_prompts(
            seeds,
            args.n_positive,
            args.n_negative,
            args.n_context,
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
