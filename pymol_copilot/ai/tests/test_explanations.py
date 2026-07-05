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
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================

"""Unit tests for human-readable plan step explanations."""

from __future__ import annotations

import pytest

import pymol_copilot.ai.app.models.session as session_module
import pymol_copilot.ai.explanations as explanations_module
import pymol_copilot.ai.schemas.tool_schemas as tool_schemas_module

_ATOM = {
    "object_name": "7BZ5",
    "chain": "A",
    "residue_id": 48,
    "atom_name": "CA",
}

_SAMPLE_ARGUMENTS: dict[str, dict] = {
    "load_structure": {"pdb_id": "7BZ5"},
    "load_local_file": {"file_path": "/tmp/7BZ5.pdb"},
    "remove_object": {"object_name": "7BZ5"},
    "list_loaded_objects": {},
    "set_representation": {"target": "7BZ5", "style": "cartoon"},
    "color_by_scheme": {"target": "7BZ5", "color": "red"},
    "color_by_chain": {"object_name": "7BZ5"},
    "color_by_secondary_structure": {"object_name": "7BZ5"},
    "set_background_color": {"color": "white"},
    "add_hydrogens": {"target": "7BZ5"},
    "select_residues": {
        "name": "active_site",
        "object_name": "7BZ5",
        "chain": "A",
        "residue_ids": [48, 52, 61],
    },
    "select_by_proximity": {
        "name": "near_ligand",
        "reference_selection": "ligand",
        "radius_angstrom": 4.0,
    },
    "select_chain": {
        "name": "chain_a",
        "object_name": "7BZ5",
        "chain": "A",
    },
    "select_ligands": {"name": "ligands", "object_name": "7BZ5"},
    "label_residues": {"target": "7BZ5", "label_type": "residue_number"},
    "measure_distance": {
        "atom1": _ATOM,
        "atom2": _ATOM,
        "measurement_name": "dist1",
    },
    "measure_angle": {
        "atom1": _ATOM,
        "atom2_vertex": _ATOM,
        "atom3": _ATOM,
        "measurement_name": "angle1",
    },
    "show_contacts": {
        "selection1": "7BZ5",
        "selection2": "ligand",
        "cutoff_angstrom": 4.0,
        "name": "contacts1",
    },
    "align_structures": {"mobile": "4HHB", "target": "1CRN"},
    "save_image": {"file_path": "/tmp/view.png"},
    "save_session": {"file_path": "/tmp/session.pse"},
    "export_coordinates": {
        "target": "7BZ5",
        "file_path": "/tmp/7BZ5.pdb",
        "format": "pdb",
    },
}


@pytest.mark.parametrize(
    "schema",
    tool_schemas_module.TOOL_SCHEMAS,
    ids=lambda schema: schema["name"],
)
@pytest.mark.unit
def test_explain_step_for_every_tool(schema: dict) -> None:
    """Each schema tool should produce a non-empty explanation."""
    name = schema["name"]
    arguments = _SAMPLE_ARGUMENTS[name]
    label = explanations_module.explain_step(name, arguments)
    assert label
    assert "{" not in label
    assert len(label) < 120


@pytest.mark.unit
def test_explain_plan_populates_display_labels() -> None:
    """explain_plan should copy steps with display_label set."""
    steps = [
        session_module.PlanStep(
            index=1,
            name="load_structure",
            arguments={"pdb_id": "7BZ5"},
        )
    ]
    explained = explanations_module.explain_plan(steps)
    assert len(explained) == 1
    assert explained[0].display_label == "Load structure 7BZ5 from the PDB"


@pytest.mark.unit
def test_explain_step_unknown_tool_falls_back() -> None:
    """Unknown tool names should fall back to compact labels."""
    label = explanations_module.explain_step(
        "unknown_tool",
        {"value": "x"},
    )
    assert "unknown_tool" in label
