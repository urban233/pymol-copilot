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

"""Generate GBNF grammars from Hermes tool schemas."""

from __future__ import annotations

import argparse
import pathlib
import sys

import pymol_copilot.ai.schemas.tool_schemas as tool_schemas_module


def _rule_name(raw: str) -> str:
    """Convert an internal identifier to a GBNF-safe rule name.

    llama.cpp corrupts rule names containing underscores when re-parsing
    grammars during token sampling.  Hyphenated identifiers avoid that bug.

    Args:
      raw: Internal rule name, often using underscores.

    Returns:
      Hyphenated GBNF rule identifier.
    """
    return raw.replace("_", "-")


def _quote_literal(value: str) -> str:
    """Return a GBNF double-quoted literal with escapes.

    Args:
      value: Raw string value.

    Returns:
      Escaped GBNF string literal.
    """
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _enum_rule(name: str, values: list[str]) -> str:
    """Build an alternation rule for string enums.

    Args:
      name: Rule identifier.
      values: Allowed string literals.

    Returns:
      GBNF rule definition.
    """
    alts = " | ".join(_quote_literal(v) for v in values)
    return f"{name} ::= {alts}"


def _pattern_to_rule(name: str, pattern: str) -> str:
    """Approximate a JSON-schema regex pattern as a GBNF rule.

    Args:
      name: Rule identifier.
      pattern: Regex pattern string from the schema.

    Returns:
      GBNF rule definition.
    """
    if pattern == "^[0-9][A-Za-z0-9]{3}$":
        return (
            f'{name} ::= "\\"" [0-9] [A-Za-z0-9] [A-Za-z0-9] [A-Za-z0-9] "\\""'
        )
    if pattern == "^[A-Za-z]$":
        return f'{name} ::= "\\"" [A-Za-z] "\\""'
    return f'{name} ::= "\\"" char+ "\\""'


def _schema_to_rule(
    name: str,
    schema: dict,
    rules: dict[str, str],
) -> str:
    """Convert a JSON-schema fragment to a GBNF rule name.

    Args:
      name: Desired GBNF rule name.
      schema: JSON-schema dict.
      rules: Accumulator for generated helper rules.

    Returns:
      Rule name referencing generated productions.
    """
    name = _rule_name(name)
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        non_null = [t for t in schema_type if t != "null"]
        schema_type = non_null[0] if non_null else "string"

    if "enum" in schema:
        rules[name] = _enum_rule(name, list(schema["enum"]))
        return name

    if "pattern" in schema:
        rules[name] = _pattern_to_rule(name, schema["pattern"])
        return name

    if schema_type == "integer":
        rules[name] = f'{name} ::= "-"? [0-9]+'
        return name

    if schema_type == "number":
        rules[name] = f'{name} ::= "-"? [0-9]+ ("." [0-9]+)?'
        return name

    if schema_type == "boolean":
        rules[name] = f'{name} ::= "true" | "false"'
        return name

    if schema_type == "array":
        item_schema = schema.get("items", {"type": "string"})
        item_rule = _rule_name(f"{name}_item")
        _schema_to_rule(item_rule, item_schema, rules)
        rules[name] = (
            f'{name} ::= "[" ws {item_rule} (ws "," ws {item_rule})* ws "]"'
        )
        return name

    if schema_type == "object":
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        parts: list[str] = ['"{" ws']
        first = True
        for prop_name, prop_schema in props.items():
            prop_rule = _rule_name(f"{name}_{prop_name}")
            _schema_to_rule(prop_rule, prop_schema, rules)
            comma = "" if first else ' ws "," ws '
            first = False
            optional = "" if prop_name in required else "?"
            parts.append(
                f'{comma}"\\"{prop_name}\\":" ws {prop_rule}{optional}'
            )
        parts.append(' ws "}"')
        rules[name] = f"{name} ::= " + "".join(parts)
        return name

    rules[name] = f'{name} ::= "\\"" char+ "\\""'
    return name


def generate_grammar(
    tool_schemas: list[dict] | None = None,
) -> str:
    """Build a GBNF grammar constraining assistant tool-call output.

    Args:
      tool_schemas: Tool schema list; defaults to ``TOOL_SCHEMAS``.

    Returns:
      Full GBNF grammar text.
    """
    schemas = tool_schemas or tool_schemas_module.TOOL_SCHEMAS
    rules: dict[str, str] = {}

    tool_names = [schema["name"] for schema in schemas]
    rules["tool-name"] = _enum_rule("tool-name", tool_names)

    arg_rules: list[str] = []
    for schema in schemas:
        rule_name = _rule_name(f"args_{schema['name']}")
        params = schema.get("parameters", {"type": "object", "properties": {}})
        _schema_to_rule(rule_name, params, rules)
        arg_rules.append(rule_name)

    args_union = " | ".join(arg_rules)
    rules["args-object"] = f"args-object ::= {args_union}"

    rules["ws"] = "ws ::= [ \\t\\n]*"
    rules["char"] = (
        'char ::= [^"\\\\] | "\\\\" (["\\\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])'
    )
    rules["tool-json"] = (
        'tool-json ::= "{" ws "\\"name\\":" ws tool-name ws "," ws '
        '"\\"arguments\\":" ws args-object ws "}"'
    )
    rules["tool-call-block"] = (
        'tool-call-block ::= "<tool_call>" ws tool-json ws "</tool_call>"'
    )
    rules["text-char"] = 'text-char ::= [^\\x00<] | "<" [^t]'
    rules["text"] = "text ::= text-char+"
    rules["root"] = "root ::= (text | tool-call-block)*"

    ordered = [
        "root",
        "text",
        "text-char",
        "tool-call-block",
        "tool-json",
        "tool-name",
        "args-object",
        "ws",
        "char",
    ]
    for name in arg_rules:
        if name not in ordered:
            ordered.append(name)

    for rule_name, _body in rules.items():
        if rule_name not in ordered:
            ordered.append(rule_name)

    lines = [rules[name] for name in ordered if name in rules]
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
      argv: Optional argument vector override.

    Returns:
      Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description="Generate GBNF grammar from cBioMOL tool schemas.",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help="Optional output file path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for grammar generation.

    Args:
      argv: Optional argument vector override.

    Returns:
      Process exit code.
    """
    args = _parse_args(argv)
    grammar = generate_grammar()
    if args.output is None:
        sys.stdout.write(grammar)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(grammar, encoding="utf-8")
    print(f"[gbnf_generator] Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
