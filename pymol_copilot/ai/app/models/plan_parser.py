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

"""Incremental parser for streamed assistant tool-call blocks."""

from __future__ import annotations

import json
import re

import pymol_copilot.ai.app.models.session as session_module
import pymol_copilot.ai.schemas.tool_schemas as tool_schemas_module

_TOOL_CALL_OPEN = "<tool_call>"
_TOOL_CALL_CLOSE = "</tool_call>"

_VALID_TOOL_NAMES = frozenset(
    schema["name"] for schema in tool_schemas_module.TOOL_SCHEMAS
)

_BARE_NAME_RE = re.compile(
    r'("name"\s*:\s*)([A-Za-z_][A-Za-z0-9_]*)',
)

_PDB_ID_FIELD_RE = re.compile(
    r'("pdb_id"\s*:\s*)([0-9][A-Za-z0-9]{3})(?=\s*[,}])',
)

_JSON_LITERALS = frozenset({"true", "false", "null"})

_STRING_PROPERTY_KEYS = frozenset(
    {
        "color",
        "target",
        "object_name",
        "file_path",
        "mobile",
        "name",
        "selection1",
        "selection2",
        "reference_selection",
        "measurement_name",
    }
)


def _collect_enum_property_values(
    schema: dict,
    out: dict[str, set[str]],
) -> None:
    """Accumulate JSON-schema enum values keyed by property name.

    Args:
      schema: JSON-schema fragment to walk.
      out: Mutable map of property name to allowed enum strings.
    """
    props = schema.get("properties", {})
    for prop_name, prop_schema in props.items():
        if "enum" in prop_schema:
            out.setdefault(prop_name, set()).update(prop_schema["enum"])
        prop_type = prop_schema.get("type")
        if prop_type == "object" or (
            isinstance(prop_type, list) and "object" in prop_type
        ):
            _collect_enum_property_values(prop_schema, out)
        items = prop_schema.get("items")
        if isinstance(items, dict):
            _collect_enum_property_values(items, out)


def _build_enum_property_values() -> dict[str, frozenset[str]]:
    """Build a map of schema property names to allowed enum values.

    Returns:
      Property name to frozenset of enum literals.
    """
    prop_enums: dict[str, set[str]] = {}
    for schema in tool_schemas_module.TOOL_SCHEMAS:
        params = schema.get("parameters", {})
        _collect_enum_property_values(params, prop_enums)
    return {key: frozenset(values) for key, values in prop_enums.items()}


_ENUM_PROPERTY_VALUES = _build_enum_property_values()


def format_step_summary(name: str, arguments: dict) -> str:
    """Format a compact action summary for the result view.

    Args:
      name: Tool function name.
      arguments: Parsed argument object.

    Returns:
      Single-line summary such as ``load_structure · pdb_id=7BZ5``.
    """
    if not arguments:
        return name
    arg_bits = []
    for key, value in arguments.items():
        if isinstance(value, str):
            arg_bits.append(f'{key}="{value}"')
        else:
            arg_bits.append(f"{key}={value}")
    return f"{name} · " + ", ".join(arg_bits)


def _extract_json_object(
    text: str,
    start: int,
) -> tuple[str, int] | None:
    """Extract one JSON object starting at ``start``.

    Args:
      text: Source text containing a JSON object.
      start: Index of the opening ``{`` character.

    Returns:
      Tuple of extracted object text and index after the closing brace,
      or ``None`` when the object is incomplete or malformed.
    """
    if start >= len(text) or text[start] != "{":
        return None

    depth = 0
    in_string = False
    escape = False
    index = start
    while index < len(text):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1], index + 1
        index += 1
    return None


def _skip_whitespace(text: str, start: int) -> int:
    """Return the index of the first non-whitespace character.

    Args:
      text: Source text.
      start: Index at which to begin scanning.

    Returns:
      Index of the next non-whitespace character, or ``len(text)``.
    """
    index = start
    while index < len(text) and text[index] in " \t\n\r":
        index += 1
    return index


def iter_tool_call_payloads(text: str) -> list[str]:
    """Extract complete ``<tool_call>`` JSON payloads from assistant text.

    Args:
      text: Raw assistant output, possibly streamed incrementally.

    Returns:
      Ordered list of JSON object strings inside closed tool-call blocks.
    """
    payloads: list[str] = []
    search_from = 0
    while True:
        open_index = text.find(_TOOL_CALL_OPEN, search_from)
        if open_index == -1:
            break

        content_start = open_index + len(_TOOL_CALL_OPEN)
        brace_index = _skip_whitespace(text, content_start)
        extracted = _extract_json_object(text, brace_index)
        if extracted is None:
            break

        payload, after_payload = extracted
        close_index = text.find(_TOOL_CALL_CLOSE, after_payload)
        if close_index == -1:
            break

        payloads.append(payload)
        search_from = close_index + len(_TOOL_CALL_CLOSE)
    return payloads


def strip_tool_call_blocks(text: str) -> str:
    """Remove closed ``<tool_call>`` blocks from assistant text.

    Args:
      text: Raw assistant output.

    Returns:
      Text with complete tool-call blocks removed and edges stripped.
    """
    parts: list[str] = []
    search_from = 0
    while True:
        open_index = text.find(_TOOL_CALL_OPEN, search_from)
        if open_index == -1:
            parts.append(text[search_from:])
            break

        parts.append(text[search_from:open_index])
        content_start = open_index + len(_TOOL_CALL_OPEN)
        brace_index = _skip_whitespace(text, content_start)
        extracted = _extract_json_object(text, brace_index)
        if extracted is None:
            parts.append(text[open_index:])
            break

        _payload, after_payload = extracted
        close_index = text.find(_TOOL_CALL_CLOSE, after_payload)
        if close_index == -1:
            parts.append(text[open_index:])
            break

        search_from = close_index + len(_TOOL_CALL_CLOSE)
    return "".join(parts).strip()


def _quote_bare_string_value(match: re.Match[str]) -> str:
    """Quote an unquoted JSON string value matched by a property regex.

    Args:
      match: Regex match with prefix and bare token groups.

    Returns:
      Rewritten JSON fragment with the value quoted.
    """
    prefix = match.group(1)
    value = match.group(2)
    if value in _JSON_LITERALS:
        return match.group(0)
    if value.lstrip("-").replace(".", "", 1).isdigit():
        return match.group(0)
    return f'{prefix}"{value}"'


def _normalize_tool_call_json(payload: str) -> str:
    """Repair common invalid JSON emitted by constrained decoding.

    Args:
      payload: Raw JSON object text from a tool-call block.

    Returns:
      Payload with bare identifiers quoted where safe.
    """
    normalized = payload

    def _quote_tool_name(match: re.Match[str]) -> str:
        tool_name = match.group(2)
        if tool_name in _VALID_TOOL_NAMES:
            return f'{match.group(1)}"{tool_name}"'
        return match.group(0)

    normalized = _BARE_NAME_RE.sub(_quote_tool_name, normalized)
    normalized = _PDB_ID_FIELD_RE.sub(r'\1"\2"', normalized)

    for prop_name, enum_values in _ENUM_PROPERTY_VALUES.items():
        enum_alt = "|".join(re.escape(value) for value in enum_values)
        prop_re = re.compile(
            rf'("{re.escape(prop_name)}"\s*:\s*)'
            rf"({enum_alt})"
            rf"(?=\s*[,}}])",
        )
        normalized = prop_re.sub(r'\1"\2"', normalized)

    for prop_name in _STRING_PROPERTY_KEYS:
        prop_re = re.compile(
            rf'("{re.escape(prop_name)}"\s*:\s*)'
            rf"([A-Za-z_][A-Za-z0-9_]*)"
            rf"(?=\s*[,}}])",
        )
        normalized = prop_re.sub(_quote_bare_string_value, normalized)

    return normalized


def _loads_tool_call_payload(payload: str) -> dict | None:
    """Parse a tool-call JSON payload with normalization fallback.

    Args:
      payload: Raw JSON object text from a tool-call block.

    Returns:
      Parsed dict when decoding succeeds, otherwise ``None``.
    """
    candidates = (_normalize_tool_call_json(payload), payload)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_tool_call_payload(payload: str) -> dict | None:
    """Parse one tool-call JSON payload with normalization fallback.

    Args:
      payload: Raw JSON object text from a tool-call block.

    Returns:
      Parsed dict when decoding succeeds, otherwise ``None``.
    """
    return _loads_tool_call_payload(payload)


class PlanParser:
    """Stream-safe extractor for ``<tool_call>`` JSON blocks."""

    def __init__(self) -> None:
        """Initialise an empty parser buffer."""
        self._buffer = ""
        self._match_count = 0
        self._steps: list[session_module.PlanStep] = []

    @property
    def steps(self) -> list[session_module.PlanStep]:
        """Return parsed plan steps in order.

        Returns:
          List of plan steps extracted so far.
        """
        return list(self._steps)

    def feed(self, delta: str) -> list[session_module.PlanStep]:
        """Append streamed text and return any newly completed steps.

        Args:
          delta: Incremental assistant output fragment.

        Returns:
          Newly parsed plan steps since the previous feed call.
        """
        self._buffer += delta
        new_steps: list[session_module.PlanStep] = []

        payloads = iter_tool_call_payloads(self._buffer)
        for payload in payloads[self._match_count :]:
            step = self._parse_payload(payload)
            if step is not None:
                self._steps.append(step)
                new_steps.append(step)
        self._match_count = len(payloads)

        return new_steps

    def finalize(self) -> tuple[list[session_module.PlanStep], str]:
        """Mark all steps done and extract summary prose.

        Returns:
          Tuple of final step list and prose with tool-call blocks removed.
        """
        prose = strip_tool_call_blocks(self._buffer)
        finalized: list[session_module.PlanStep] = []
        for step in self._steps:
            finalized.append(
                session_module.PlanStep(
                    index=step.index,
                    name=step.name,
                    arguments=step.arguments,
                    state=session_module.StepState.DONE,
                    warning=step.warning,
                )
            )
        self._steps = finalized
        return finalized, prose

    def reset(self) -> None:
        """Clear parser state for a new generation run."""
        self._buffer = ""
        self._match_count = 0
        self._steps = []

    def _parse_payload(
        self,
        payload: str,
    ) -> session_module.PlanStep | None:
        """Parse one tool-call JSON payload.

        Args:
          payload: Raw JSON object text inside ``<tool_call>`` tags.

        Returns:
          Parsed plan step, or None if JSON is invalid.
        """
        parsed = _loads_tool_call_payload(payload)
        if parsed is None:
            return None

        name = parsed.get("name")
        if not isinstance(name, str):
            return None

        arguments = parsed.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        warning = ""
        if name not in _VALID_TOOL_NAMES:
            warning = f"Unknown tool: {name}"

        index = len(self._steps) + 1
        return session_module.PlanStep(
            index=index,
            name=name,
            arguments=arguments,
            state=session_module.StepState.ACTIVE,
            warning=warning,
        )
