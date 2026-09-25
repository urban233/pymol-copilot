# Copyright 2026 PyMOL Copilot contributors.
"""`pmc_core.versions.contract_versions()` must never fall behind.

Two properties are proven independently. First, `APPLICATION_VERSION`
tracks `pyproject.toml`'s own `[project].version`, because a health
response quoting a stale application version would be worse than quoting
none. Second, `contract_versions()` names every module-level `*_VERSION`
constant `pmc_core` actually defines -- found by parsing the source with
`ast`, never from a hand-written list here that could itself drift -- plus
`pmc_core.plan`'s one exception: it has no version constant of its own, so
its compatibility is carried by `CURRENT_CONTRACT_MANIFEST.plan_version`
instead, and that is asserted explicitly.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import re
import tomllib

import pmc_core
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_core.protocol import HEALTH_CONTRACT_KEYS
from pmc_core.versions import APPLICATION_VERSION
from pmc_core.versions import contract_versions

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

#: A module-level constant is treated as a contract version when its name
#: matches this shape. `REASON_*` codes (for example
#: `REASON_UNSUPPORTED_SCHEMA_VERSION`) also end in `_VERSION` but name an
#: executor outcome, not a contract; they are excluded by name rather than
#: by this pattern, since the pattern alone cannot tell the two apart.
_VERSION_CONSTANT = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_VERSION$")

#: Names that match `_VERSION_CONSTANT` but are not contract versions.
_NOT_A_CONTRACT_VERSION = frozenset({"REASON_UNSUPPORTED_SCHEMA_VERSION"})


def _wire_key(constant_name: str) -> str:
    """Derive a version constant's expected `contract_versions()` key.

    Args:
        constant_name: A module-level name matching `_VERSION_CONSTANT`,
            for example `ERROR_ENVELOPE_VERSION`.

    Returns:
        The lower-camel-case wire key it must appear under, for example
        `errorEnvelope`.
    """
    stem = constant_name.removesuffix("_VERSION")
    first, *rest = stem.split("_")
    return "".join([first.lower(), *(word.title() for word in rest)])


def _pmc_core_sources() -> list[pathlib.Path]:
    """List every source `pmc_core` ships, from its own `__path__`.

    Reading from the imported package's own path, rather than a
    repository-relative one, keeps this working unchanged under Bazel's
    runfiles tree.

    Returns:
        Every `pmc_core` source file, in a stable order.
    """
    sources: list[pathlib.Path] = []
    for directory in pmc_core.__path__:
        sources.extend(sorted(pathlib.Path(directory).glob("*.py")))
    return sources


def _declared_version_constants() -> dict[str, tuple[str, object]]:
    """Find every module-level `*_VERSION` constant `pmc_core` defines.

    Returns:
        Each constant's own name mapped to a pair of the module it was
        found in (for error messages) and its literal value.
    """
    found: dict[str, tuple[str, object]] = {}
    for source in _pmc_core_sources():
        tree = ast.parse(
            source.read_text(encoding="utf-8"), filename=str(source)
        )
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if not _VERSION_CONSTANT.match(name):
                continue
            if name in _NOT_A_CONTRACT_VERSION:
                continue
            if not isinstance(node.value, ast.Constant):
                continue
            found[name] = (source.name, node.value.value)
    return found


def test_declared_version_constants_finds_the_known_eight() -> None:
    """The scan itself must see every constant this item was written against.

    A regression here means the scan stopped walking a module, which
    would silently make the coverage assertion below vacuous.
    """
    assert set(_declared_version_constants()) == {
        "PROTOCOL_VERSION",
        "POLICY_VERSION",
        "SNAPSHOT_VERSION",
        "CARD_VERSION",
        "PROMPT_VERSION",
        "GRAMMAR_VERSION",
        "ERROR_ENVELOPE_VERSION",
        "EXECUTOR_VERSION",
    }


def test_contract_versions_covers_every_declared_constant() -> None:
    """Every `pmc_core` version constant must appear, correctly, by name.

    Adding a new `FOO_VERSION = 1` anywhere in `pmc_core` without also
    adding it to `contract_versions()` must fail here, naming the
    constant that was missed -- proven by hand for this item by adding
    exactly that to `pmc_core/card.py`, confirming this test names
    `FOO_VERSION`, then reverting it.
    """
    versions = contract_versions()
    for constant_name, (
        module_name,
        value,
    ) in _declared_version_constants().items():
        key = _wire_key(constant_name)
        assert key in versions, (
            f"{constant_name} (defined in {module_name}) has no "
            f"contract_versions() entry under the expected key {key!r}"
        )
        assert versions[key] == str(value), (
            f"contract_versions()[{key!r}] == {versions[key]!r}, "
            f"but {module_name}'s {constant_name} == {value!r}"
        )


def test_contract_versions_carries_no_unexplained_extra_keys() -> None:
    """Every key besides `plan` must trace back to a declared constant."""
    declared_keys = {_wire_key(name) for name in _declared_version_constants()}
    extra = set(contract_versions()) - declared_keys - {"plan"}
    assert not extra, f"contract_versions() has unexplained keys: {extra}"


def test_plan_version_comes_from_the_contract_manifest() -> None:
    """`plan` has no module constant; it is `pmc_core.plan`'s one exception."""
    assert contract_versions()["plan"] == CURRENT_CONTRACT_MANIFEST.plan_version
    module = importlib.import_module("pmc_core.plan")
    assert module.__file__ is not None
    plan_source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    assert "_VERSION" not in plan_source, (
        "pmc_core.plan now defines a version constant; give it its own "
        "contract_versions() key derived from that constant instead of "
        "the manifest fallback this test expects."
    )


def test_contract_versions_values_are_all_strings() -> None:
    """A caller must never special-case one field's underlying type."""
    for key, value in contract_versions().items():
        assert isinstance(value, str), (
            f"contract_versions()[{key!r}] is {type(value)}"
        )


def test_application_version_matches_pyproject() -> None:
    """A stale `APPLICATION_VERSION` would make a health report lie."""
    with PYPROJECT_PATH.open("rb") as handle:
        pyproject = tomllib.load(handle)
    assert pyproject["project"]["version"] == APPLICATION_VERSION


def test_health_contract_keys_matches_contract_versions_exactly() -> None:
    """`HealthResponseV1`'s own hand-listed key set never falls behind.

    `HEALTH_CONTRACT_KEYS` is hand-listed in `pmc_core.protocol` rather
    than imported from this module, because `pmc_core.versions` imports
    `pmc_core.protocol` and the reverse import would cycle. This is the
    one place both are read together.
    """
    assert set(contract_versions()) == HEALTH_CONTRACT_KEYS
