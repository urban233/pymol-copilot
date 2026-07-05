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

"""Human-readable plan step labels for the verification UI."""

from __future__ import annotations

import typing

import pymol_copilot.ai.app.models.session as session_module


def _fmt_atom(atom: dict) -> str:
    """Format an atom selector dict as a compact label.

    Args:
      atom: Atom selector argument dict.

    Returns:
      Human-readable atom reference string.
    """
    return (
        f"{atom.get('object_name', '?')}/"
        f"{atom.get('chain', '?')}/"
        f"{atom.get('residue_id', '?')}/"
        f"{atom.get('atom_name', '?')}"
    )


def _explain_load_structure(arguments: dict) -> str:
    """Explain a load_structure tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    pdb_id = arguments.get("pdb_id", "?")
    return f"Load structure {pdb_id} from the PDB"


def _explain_load_local_file(arguments: dict) -> str:
    """Explain a load_local_file tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    path = arguments.get("file_path", "?")
    return f"Load local structure file {path}"


def _explain_remove_object(arguments: dict) -> str:
    """Explain a remove_object tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("object_name", "?")
    return f"Remove object {name} from the session"


def _explain_list_loaded_objects(arguments: dict) -> str:
    """Explain a list_loaded_objects tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    _ = arguments
    return "List all loaded objects in the session"


def _explain_set_representation(arguments: dict) -> str:
    """Explain a set_representation tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    target = arguments.get("target", "?")
    style = arguments.get("style", "?")
    return f'Show "{target}" as {style}'


def _explain_color_by_scheme(arguments: dict) -> str:
    """Explain a color_by_scheme tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    target = arguments.get("target", "?")
    color = arguments.get("color", "?")
    return f'Color "{target}" {color}'


def _explain_color_by_chain(arguments: dict) -> str:
    """Explain a color_by_chain tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("object_name", "?")
    return f"Color chains in {name} distinctly"


def _explain_color_by_secondary_structure(arguments: dict) -> str:
    """Explain a color_by_secondary_structure tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("object_name", "?")
    return f"Color {name} by secondary structure"


def _explain_set_background_color(arguments: dict) -> str:
    """Explain a set_background_color tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    color = arguments.get("color", "?")
    return f"Set viewport background to {color}"


def _explain_add_hydrogens(arguments: dict) -> str:
    """Explain an add_hydrogens tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    target = arguments.get("target", "?")
    return f"Add hydrogens to {target}"


def _explain_select_residues(arguments: dict) -> str:
    """Explain a select_residues tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("name", "?")
    obj = arguments.get("object_name", "?")
    chain = arguments.get("chain", "?")
    residues = arguments.get("residue_ids", [])
    res_text = ", ".join(str(r) for r in residues)
    return f"Select residues {res_text} on chain {chain} in {obj} as {name}"


def _explain_select_by_proximity(arguments: dict) -> str:
    """Explain a select_by_proximity tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("name", "?")
    ref = arguments.get("reference_selection", "?")
    radius = arguments.get("radius_angstrom", "?")
    return f"Select atoms within {radius} Å of {ref} as {name}"


def _explain_select_chain(arguments: dict) -> str:
    """Explain a select_chain tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("name", "?")
    obj = arguments.get("object_name", "?")
    chain = arguments.get("chain", "?")
    return f"Select chain {chain} in {obj} as {name}"


def _explain_select_ligands(arguments: dict) -> str:
    """Explain a select_ligands tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("name", "?")
    obj = arguments.get("object_name", "?")
    return f"Select ligands in {obj} as {name}"


def _explain_label_residues(arguments: dict) -> str:
    """Explain a label_residues tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    target = arguments.get("target", "?")
    label_type = arguments.get("label_type", "?")
    if label_type == "none":
        return f"Remove labels from {target}"
    return f"Label {target} with {label_type.replace('_', ' ')}"


def _explain_measure_distance(arguments: dict) -> str:
    """Explain a measure_distance tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("measurement_name", "?")
    atom1 = arguments.get("atom1", {})
    atom2 = arguments.get("atom2", {})
    return f"Measure distance {name} between {_fmt_atom(atom1)} and {_fmt_atom(atom2)}"


def _explain_measure_angle(arguments: dict) -> str:
    """Explain a measure_angle tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    name = arguments.get("measurement_name", "?")
    return f"Measure angle {name} between three atoms"


def _explain_show_contacts(arguments: dict) -> str:
    """Explain a show_contacts tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    sel1 = arguments.get("selection1", "?")
    sel2 = arguments.get("selection2", "?")
    cutoff = arguments.get("cutoff_angstrom", "?")
    name = arguments.get("name", "?")
    return (
        f"Show contacts within {cutoff} Å between {sel1} and {sel2} as {name}"
    )


def _explain_align_structures(arguments: dict) -> str:
    """Explain an align_structures tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    mobile = arguments.get("mobile", "?")
    target = arguments.get("target", "?")
    return f"Align {mobile} onto {target}"


def _explain_save_image(arguments: dict) -> str:
    """Explain a save_image tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    path = arguments.get("file_path", "?")
    ray = arguments.get("ray_trace", False)
    quality = "ray-traced" if ray else "preview"
    return f"Save {quality} image to {path}"


def _explain_save_session(arguments: dict) -> str:
    """Explain a save_session tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    path = arguments.get("file_path", "?")
    return f"Save PyMOL session to {path}"


def _explain_export_coordinates(arguments: dict) -> str:
    """Explain an export_coordinates tool call.

    Args:
      arguments: Tool argument dict.

    Returns:
      Human-readable label string.
    """
    target = arguments.get("target", "?")
    path = arguments.get("file_path", "?")
    fmt = arguments.get("format", "?")
    return f"Export {target} as {fmt.upper()} to {path}"


_EXPLANATION_REGISTRY: dict[
    str,
    typing.Callable[[dict], str],
] = {
    "load_structure": _explain_load_structure,
    "load_local_file": _explain_load_local_file,
    "remove_object": _explain_remove_object,
    "list_loaded_objects": _explain_list_loaded_objects,
    "set_representation": _explain_set_representation,
    "color_by_scheme": _explain_color_by_scheme,
    "color_by_chain": _explain_color_by_chain,
    "color_by_secondary_structure": _explain_color_by_secondary_structure,
    "set_background_color": _explain_set_background_color,
    "add_hydrogens": _explain_add_hydrogens,
    "select_residues": _explain_select_residues,
    "select_by_proximity": _explain_select_by_proximity,
    "select_chain": _explain_select_chain,
    "select_ligands": _explain_select_ligands,
    "label_residues": _explain_label_residues,
    "measure_distance": _explain_measure_distance,
    "measure_angle": _explain_measure_angle,
    "show_contacts": _explain_show_contacts,
    "align_structures": _explain_align_structures,
    "save_image": _explain_save_image,
    "save_session": _explain_save_session,
    "export_coordinates": _explain_export_coordinates,
}


def explain_step(name: str, arguments: dict) -> str:
    """Return human-readable prose for one plan step.

    Args:
      name: Tool function name from the model output.
      arguments: Parsed argument object for the tool call.

    Returns:
      A single-line human-readable description of the planned action.
    """
    formatter = _EXPLANATION_REGISTRY.get(name)
    if formatter is None:
        return session_module.PlanStep(
            index=0,
            name=name,
            arguments=arguments,
        ).compact_label()
    return formatter(arguments)


def explain_plan(
    steps: list[session_module.PlanStep],
) -> list[session_module.PlanStep]:
    """Populate display labels for a list of plan steps.

    Args:
      steps: Parsed plan steps from the inference output.

    Returns:
      New plan step objects with ``display_label`` set.
    """
    explained: list[session_module.PlanStep] = []
    for step in steps:
        label = explain_step(step.name, step.arguments)
        explained.append(
            session_module.PlanStep(
                index=step.index,
                name=step.name,
                arguments=step.arguments,
                state=step.state,
                warning=step.warning,
                display_label=label,
                error=step.error,
            )
        )
    return explained
