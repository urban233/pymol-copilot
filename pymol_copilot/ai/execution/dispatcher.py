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

"""Dispatch plan steps to the typed PyMOL wrapper layer."""

from __future__ import annotations

import typing

import pymol_copilot.ai.pymol_wrapper as pymol_wrapper_module
import pymol_copilot.ai.schemas.tool_schemas as tool_schemas_module


class DispatcherError(Exception):
    """Raised when a plan step cannot be dispatched."""


def _dispatch_load_structure(arguments: dict) -> str:
    """Dispatch load_structure.

    Args:
      arguments: Tool argument dict.

    Returns:
      Loaded object name from the wrapper.
    """
    return pymol_wrapper_module.load_structure(
        arguments["pdb_id"],
        arguments.get("object_name"),
    )


def _dispatch_load_local_file(arguments: dict) -> str:
    """Dispatch load_local_file.

    Args:
      arguments: Tool argument dict.

    Returns:
      Loaded object name from the wrapper.
    """
    return pymol_wrapper_module.load_local_file(
        arguments["file_path"],
        arguments.get("object_name"),
    )


def _dispatch_remove_object(arguments: dict) -> None:
    """Dispatch remove_object.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.remove_object(arguments["object_name"])


def _dispatch_list_loaded_objects(arguments: dict) -> list[str]:
    """Dispatch list_loaded_objects.

    Args:
      arguments: Tool argument dict (unused).

    Returns:
      Object names from the active session.
    """
    _ = arguments
    return pymol_wrapper_module.list_loaded_objects()


def _dispatch_set_representation(arguments: dict) -> None:
    """Dispatch set_representation.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.set_representation(
        arguments["target"],
        arguments["style"],
    )


def _dispatch_color_by_scheme(arguments: dict) -> None:
    """Dispatch color_by_scheme.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.color_by_scheme(
        arguments["target"],
        arguments["color"],
    )


def _dispatch_color_by_chain(arguments: dict) -> None:
    """Dispatch color_by_chain.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.color_by_chain(arguments["object_name"])


def _dispatch_color_by_secondary_structure(arguments: dict) -> None:
    """Dispatch color_by_secondary_structure.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.color_by_secondary_structure(
        arguments["object_name"],
    )


def _dispatch_set_background_color(arguments: dict) -> None:
    """Dispatch set_background_color.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.set_background_color(arguments["color"])


def _dispatch_add_hydrogens(arguments: dict) -> None:
    """Dispatch add_hydrogens.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.add_hydrogens(arguments["target"])


def _dispatch_select_residues(arguments: dict) -> str:
    """Dispatch select_residues.

    Args:
      arguments: Tool argument dict.

    Returns:
      Selection name from the wrapper.
    """
    return pymol_wrapper_module.select_residues(
        arguments["name"],
        arguments["object_name"],
        arguments["chain"],
        arguments["residue_ids"],
    )


def _dispatch_select_by_proximity(arguments: dict) -> str:
    """Dispatch select_by_proximity.

    Args:
      arguments: Tool argument dict.

    Returns:
      Selection name from the wrapper.
    """
    return pymol_wrapper_module.select_by_proximity(
        arguments["name"],
        arguments["reference_selection"],
        arguments["radius_angstrom"],
    )


def _dispatch_select_chain(arguments: dict) -> str:
    """Dispatch select_chain.

    Args:
      arguments: Tool argument dict.

    Returns:
      Selection name from the wrapper.
    """
    return pymol_wrapper_module.select_chain(
        arguments["name"],
        arguments["object_name"],
        arguments["chain"],
    )


def _dispatch_select_ligands(arguments: dict) -> str:
    """Dispatch select_ligands.

    Args:
      arguments: Tool argument dict.

    Returns:
      Selection name from the wrapper.
    """
    return pymol_wrapper_module.select_ligands(
        arguments["name"],
        arguments["object_name"],
    )


def _dispatch_label_residues(arguments: dict) -> None:
    """Dispatch label_residues.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.label_residues(
        arguments["target"],
        arguments["label_type"],
    )


def _dispatch_measure_distance(arguments: dict) -> str:
    """Dispatch measure_distance.

    Args:
      arguments: Tool argument dict.

    Returns:
      Measurement object name from the wrapper.
    """
    return pymol_wrapper_module.measure_distance(
        arguments["atom1"],
        arguments["atom2"],
        arguments["measurement_name"],
    )


def _dispatch_measure_angle(arguments: dict) -> str:
    """Dispatch measure_angle.

    Args:
      arguments: Tool argument dict.

    Returns:
      Measurement object name from the wrapper.
    """
    return pymol_wrapper_module.measure_angle(
        arguments["atom1"],
        arguments["atom2_vertex"],
        arguments["atom3"],
        arguments["measurement_name"],
    )


def _dispatch_show_contacts(arguments: dict) -> str:
    """Dispatch show_contacts.

    Args:
      arguments: Tool argument dict.

    Returns:
      Contact object name from the wrapper.
    """
    return pymol_wrapper_module.show_contacts(
        arguments["selection1"],
        arguments["selection2"],
        arguments["cutoff_angstrom"],
        arguments["name"],
    )


def _dispatch_align_structures(arguments: dict) -> None:
    """Dispatch align_structures.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.align_structures(
        arguments["mobile"],
        arguments["target"],
        arguments.get("mobile_chain"),
        arguments.get("target_chain"),
    )


def _dispatch_save_image(arguments: dict) -> None:
    """Dispatch save_image.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.save_image(
        arguments["file_path"],
        arguments.get("width", 1920),
        arguments.get("height", 1080),
        arguments.get("dpi", 300),
        arguments.get("ray_trace", False),
    )


def _dispatch_save_session(arguments: dict) -> None:
    """Dispatch save_session.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.save_session(arguments["file_path"])


def _dispatch_export_coordinates(arguments: dict) -> None:
    """Dispatch export_coordinates.

    Args:
      arguments: Tool argument dict.
    """
    pymol_wrapper_module.export_coordinates(
        arguments["target"],
        arguments["file_path"],
        arguments["format"],
    )


_DISPATCH_REGISTRY: dict[str, typing.Callable[[dict], typing.Any]] = {
    "load_structure": _dispatch_load_structure,
    "load_local_file": _dispatch_load_local_file,
    "remove_object": _dispatch_remove_object,
    "list_loaded_objects": _dispatch_list_loaded_objects,
    "set_representation": _dispatch_set_representation,
    "color_by_scheme": _dispatch_color_by_scheme,
    "color_by_chain": _dispatch_color_by_chain,
    "color_by_secondary_structure": _dispatch_color_by_secondary_structure,
    "set_background_color": _dispatch_set_background_color,
    "add_hydrogens": _dispatch_add_hydrogens,
    "select_residues": _dispatch_select_residues,
    "select_by_proximity": _dispatch_select_by_proximity,
    "select_chain": _dispatch_select_chain,
    "select_ligands": _dispatch_select_ligands,
    "label_residues": _dispatch_label_residues,
    "measure_distance": _dispatch_measure_distance,
    "measure_angle": _dispatch_measure_angle,
    "show_contacts": _dispatch_show_contacts,
    "align_structures": _dispatch_align_structures,
    "save_image": _dispatch_save_image,
    "save_session": _dispatch_save_session,
    "export_coordinates": _dispatch_export_coordinates,
}


def known_tool_names() -> frozenset[str]:
    """Return the set of tool names handled by the dispatcher.

    Returns:
      Frozen set of schema tool names.
    """
    return frozenset(_DISPATCH_REGISTRY.keys())


def dispatch_step(name: str, arguments: dict) -> typing.Any:
    """Validate a tool name and invoke the matching wrapper function.

    Args:
      name: Tool function name from the plan step.
      arguments: Parsed argument object for the tool call.

    Returns:
      Wrapper return value when the underlying call produces one.

    Raises:
      DispatcherError: If ``name`` is unknown.
      pymol_wrapper_module.WrapperError: If the wrapper rejects arguments.
    """
    handler = _DISPATCH_REGISTRY.get(name)
    if handler is None:
        raise DispatcherError(f"Unknown tool name: {name}")
    return handler(arguments)


def assert_registry_matches_schemas() -> None:
    """Verify dispatcher coverage against ``TOOL_SCHEMAS``.

    Raises:
      DispatcherError: If registry and schema lists diverge.
    """
    schema_names = {
        schema["name"] for schema in tool_schemas_module.TOOL_SCHEMAS
    }
    registry_names = set(_DISPATCH_REGISTRY.keys())
    missing = schema_names - registry_names
    extra = registry_names - schema_names
    if missing or extra:
        raise DispatcherError(
            f"Dispatcher/schema mismatch. missing={sorted(missing)} extra={sorted(extra)}"
        )
