# Copyright 2026 PyMOL Copilot contributors.
"""Resolve a consumer package's calls to the shared-core callable they reach.

Master plan items 6 and 13 each require that both consumers -- the dataset
pipeline and the runtime -- call one shared implementation rather than
growing their own. Neither consumer's real call site exists yet, so what
is checkable today is that nothing in `pmc_agent` or `pmc_data` defines a
competing implementation, and that any call one does make resolves to the
shared-core one.

"Resolves" is meant literally. An earlier version of the error envelope's
check looked for the two names co-occurring as strings in a file, which
review rejected: `from another_module import normalize` beside an
unrelated `import pmc_core.errors` passed it, and so did a bare comment.
The scan here parses the source and follows each call target through the
module's own import bindings, so what is compared is the callable the call
reaches. Indirection through a computed target is not followed, and this
module does not claim otherwise.

The scan is shared rather than copied so that the two items cannot drift
into two different notions of what "reaches the shared core" means.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import ast
import importlib
import pathlib

#: The subsystems required to reach shared-core implementations rather
#: than growing their own.
CONSUMER_PACKAGES = ("pmc_agent", "pmc_data")


def consumer_sources() -> list[pathlib.Path]:
    """List every Python source shipped by the consumer packages.

    Read from each package's own `__path__` rather than from a
    repository path, so this works unchanged under Bazel's runfiles
    tree, where the test's working directory is not the source root.

    Returns:
        Every consumer source file, in a stable order.
    """
    sources: list[pathlib.Path] = []
    for name in CONSUMER_PACKAGES:
        package = importlib.import_module(name)
        for directory in package.__path__:
            sources.extend(sorted(pathlib.Path(directory).rglob("*.py")))
    return sources


def bound_names(tree: ast.Module) -> dict[str, str]:
    """Map every name a module's imports bind to what it names.

    Args:
        tree: One parsed consumer module.

    Returns:
        Each bound name against the dotted path it resolves to.
    """
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bound[alias.asname or alias.name] = (
                    f"{node.module}.{alias.name}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                # `import a.b` binds `a`, but `a.b` is reached by
                # attribute from it, so record the dotted path itself.
                bound[alias.asname or alias.name] = alias.name
    return bound


def dotted_name(node: ast.expr) -> str | None:
    """Spell a call's target as a dotted name, when it is one.

    Args:
        node: The expression being called.

    Returns:
        The dotted name, or None when the target is computed rather than
        named -- an indirection this scan cannot follow and does not
        claim to.
    """
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def resolved_name(dotted: str, bound: dict[str, str]) -> str:
    """Rewrite a call target through the module's own imports.

    Args:
        dotted: The target as written at the call site.
        bound: What that module's imports bind.

    Returns:
        The target with its longest bound prefix expanded, which is what
        the call actually reaches.
    """
    parts = dotted.split(".")
    for size in range(len(parts), 0, -1):
        prefix = ".".join(parts[:size])
        if prefix in bound:
            return ".".join([bound[prefix], *parts[size:]])
    return dotted


def foreign_calls(source: str, canonical: str) -> set[str]:
    """Find calls that share the canonical name but not its origin.

    Each call target is resolved through the imports that bind it rather
    than matched as a string, so a consumer importing the name from
    somewhere else is caught even when the file names the shared-core
    module elsewhere, and naming it in a comment buys nothing.

    Args:
        source: One consumer module's text.
        canonical: The dotted path calls must reach, for example
            "pmc_core.errors.normalize". Its last segment is the name
            searched for at each call site.

    Returns:
        What each divergent call reaches; empty when every call to that
        name in the source resolves to canonical.
    """
    tree = ast.parse(source)
    bound = bound_names(tree)
    foreign: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = dotted_name(node.func)
        if dotted is None:
            continue
        resolved = resolved_name(dotted, bound)
        if resolved.rsplit(".", 1)[-1] != canonical.rsplit(".", 1)[-1]:
            continue
        if resolved != canonical:
            foreign.add(resolved)
    return foreign
