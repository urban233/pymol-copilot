# Copyright 2026 PyMOL Copilot contributors.
"""Provenance-complete gold-case schema for the chain-A/red fixture.

A GoldCase records everything the verifier in `pmc_data.verifier` needs to
grade one real PyMOL run against independently derived expectations: stable
identity, structure provenance and checksum, contract/PyMOL versions,
intent/category/difficulty, the canonical typed plan, and a closed set of
assertions. Construction and deserialization reject any record missing a
required provenance field or naming an unsupported assertion kind -- there
is no default-filled or partially valid GoldCase.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

from pmc_core.plan import initial_fixture_plan

#: Assertion kinds this schema and the verifier both understand.
ASSERTION_KIND_CHAIN_MEMBERSHIP = "chain_membership"
ASSERTION_KIND_COLOR_STATE = "color_state"
ASSERTION_KIND_NO_UNINTENDED_CHANGE = "no_unintended_change"

SUPPORTED_ASSERTION_KINDS = frozenset(
    (
        ASSERTION_KIND_CHAIN_MEMBERSHIP,
        ASSERTION_KIND_COLOR_STATE,
        ASSERTION_KIND_NO_UNINTENDED_CHANGE,
    )
)

#: The one hand-authored gold record shipped with this package.
DEFAULT_GOLD_CASE_PATH = (
    Path(__file__).resolve().parent / "gold_cases" / "chain_a_red.json"
)


class InvalidGoldCaseError(ValueError):
    """Raised when a gold case is missing required provenance or names an unsupported assertion kind.

    No gold case is ever silently accepted with a default-filled field.
    """


def _required_string(data: Mapping[str, Any], key: str) -> str:
    """Read a required non-empty string field from a raw gold-case mapping.

    Args:
        data: The raw mapping being decoded.
        key: The required field name.

    Returns:
        The field's string value.

    Raises:
        InvalidGoldCaseError: If key is absent, not a string, or empty.
    """
    if key not in data:
        raise InvalidGoldCaseError(f"missing required field: {key!r}")
    value = data[key]
    if not isinstance(value, str) or not value:
        raise InvalidGoldCaseError(f"field {key!r} must be a non-empty string")
    return value


@dataclass(frozen=True)
class Provenance:
    """Source and checksum provenance for the controlled structure file.

    Attributes:
        source: A short description of where the structure came from.
        license: The license or provenance basis permitting its use here.
        structure_relpath: Repository-relative path to the structure file.
        structure_sha256: The verified SHA-256 checksum of that file.
    """

    source: str
    license: str
    structure_relpath: str
    structure_sha256: str

    def to_dict(self) -> dict[str, str]:
        """Render this provenance as a JSON-safe mapping.

        Returns:
            A plain dict with this provenance's fields.
        """
        return {
            "source": self.source,
            "license": self.license,
            "structure_relpath": self.structure_relpath,
            "structure_sha256": self.structure_sha256,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> Provenance:
        """Decode a Provenance from a raw mapping.

        Args:
            data: The raw provenance mapping.

        Returns:
            The decoded Provenance.

        Raises:
            InvalidGoldCaseError: If a required field is missing or empty.
        """
        return Provenance(
            source=_required_string(data, "source"),
            license=_required_string(data, "license"),
            structure_relpath=_required_string(data, "structure_relpath"),
            structure_sha256=_required_string(data, "structure_sha256"),
        )


@dataclass(frozen=True)
class ContractVersions:
    """Contract versions actually used to produce and grade a gold case.

    Attributes:
        plan_version: The `pmc_core` plan/policy contract version in effect.
        pymol_version: The pinned Open-Source PyMOL version in effect.
    """

    plan_version: str
    pymol_version: str

    def to_dict(self) -> dict[str, str]:
        """Render these contract versions as a JSON-safe mapping.

        Returns:
            A plain dict with this record's fields.
        """
        return {
            "plan_version": self.plan_version,
            "pymol_version": self.pymol_version,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> ContractVersions:
        """Decode ContractVersions from a raw mapping.

        Args:
            data: The raw contract-versions mapping.

        Returns:
            The decoded ContractVersions.

        Raises:
            InvalidGoldCaseError: If a required field is missing or empty.
        """
        return ContractVersions(
            plan_version=_required_string(data, "plan_version"),
            pymol_version=_required_string(data, "pymol_version"),
        )


@dataclass(frozen=True)
class Assertion:
    """One machine-checkable assertion the verifier must evaluate.

    Attributes:
        kind: One of SUPPORTED_ASSERTION_KINDS.
        params: The string-keyed, string-valued parameters this assertion
            kind needs (for example the selection name, chain identifier, or
            expected color).
    """

    kind: str
    params: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject any assertion kind this schema does not support.

        Raises:
            InvalidGoldCaseError: If kind is not in SUPPORTED_ASSERTION_KINDS.
        """
        if self.kind not in SUPPORTED_ASSERTION_KINDS:
            raise InvalidGoldCaseError(
                f"unsupported assertion kind: {self.kind!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Render this assertion as a JSON-safe mapping.

        Returns:
            A plain dict with this assertion's fields.
        """
        return {"kind": self.kind, "params": dict(self.params)}

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> Assertion:
        """Decode an Assertion from a raw mapping.

        Args:
            data: The raw assertion mapping.

        Returns:
            The decoded Assertion.

        Raises:
            InvalidGoldCaseError: If kind is missing, empty, or unsupported.
        """
        kind = _required_string(data, "kind")
        params = data.get("params", {})
        if not isinstance(params, Mapping):
            raise InvalidGoldCaseError("assertion params must be a mapping")
        return Assertion(kind=kind, params=dict(params))


@dataclass(frozen=True)
class GoldCase:
    """A provenance-complete gold case for the chain-A/red fixture.

    Attributes:
        case_id: The stable identity of this gold case.
        intent: The natural-language intent this case represents.
        category: The taxonomy category this case belongs to.
        difficulty: The taxonomy difficulty label for this case.
        provenance: The structure file's source and checksum provenance.
        contract_versions: The plan/PyMOL contract versions actually used.
        canonical_plan_pml: The exact canonical `.pml` bytes this case
            grades, cross-checked against `pmc_core`'s own rendering.
        target_chain: The chain identifier the fixture selects and colors.
        non_target_chains: Chain identifiers that must show no unintended
            change.
        assertions: The ordered, machine-checkable assertions to evaluate.
    """

    case_id: str
    intent: str
    category: str
    difficulty: str
    provenance: Provenance
    contract_versions: ContractVersions
    canonical_plan_pml: str
    target_chain: str
    non_target_chains: tuple[str, ...]
    assertions: tuple[Assertion, ...]

    def __post_init__(self) -> None:
        """Reject a record whose canonical plan drifted from `pmc_core`.

        Raises:
            InvalidGoldCaseError: If canonical_plan_pml no longer matches
                `pmc_core.plan.initial_fixture_plan().render_pml()`, or if
                assertions is empty.
        """
        expected_plan_pml = initial_fixture_plan().render_pml()
        if self.canonical_plan_pml != expected_plan_pml:
            raise InvalidGoldCaseError(
                "canonical_plan_pml does not match pmc_core's canonical "
                "rendering of the accepted fixture plan"
            )
        if not self.assertions:
            raise InvalidGoldCaseError(
                "gold case must declare at least one assertion"
            )

    def to_dict(self) -> dict[str, Any]:
        """Render this gold case as a JSON-safe mapping.

        Returns:
            A plain dict suitable for `json.dumps`.
        """
        return {
            "case_id": self.case_id,
            "intent": self.intent,
            "category": self.category,
            "difficulty": self.difficulty,
            "provenance": self.provenance.to_dict(),
            "contract_versions": self.contract_versions.to_dict(),
            "canonical_plan_pml": self.canonical_plan_pml,
            "target_chain": self.target_chain,
            "non_target_chains": list(self.non_target_chains),
            "assertions": [
                assertion.to_dict() for assertion in self.assertions
            ],
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> GoldCase:
        """Decode a GoldCase from a raw mapping, rejecting incomplete input.

        Args:
            data: The raw gold-case mapping, typically loaded from JSON.

        Returns:
            The decoded, validated GoldCase.

        Raises:
            InvalidGoldCaseError: If a required field is missing, empty, or
                otherwise invalid.
        """
        if "provenance" not in data or not isinstance(
            data["provenance"], Mapping
        ):
            raise InvalidGoldCaseError("missing required field: 'provenance'")
        if "contract_versions" not in data or not isinstance(
            data["contract_versions"], Mapping
        ):
            raise InvalidGoldCaseError(
                "missing required field: 'contract_versions'"
            )
        raw_assertions = data.get("assertions")
        if not isinstance(raw_assertions, list) or not raw_assertions:
            raise InvalidGoldCaseError(
                "missing required non-empty field: 'assertions'"
            )
        non_target_chains = data.get("non_target_chains")
        if not isinstance(non_target_chains, list):
            raise InvalidGoldCaseError(
                "missing required field: 'non_target_chains'"
            )
        return GoldCase(
            case_id=_required_string(data, "case_id"),
            intent=_required_string(data, "intent"),
            category=_required_string(data, "category"),
            difficulty=_required_string(data, "difficulty"),
            provenance=Provenance.from_dict(data["provenance"]),
            contract_versions=ContractVersions.from_dict(
                data["contract_versions"]
            ),
            canonical_plan_pml=_required_string(data, "canonical_plan_pml"),
            target_chain=_required_string(data, "target_chain"),
            non_target_chains=tuple(non_target_chains),
            assertions=tuple(
                Assertion.from_dict(entry) for entry in raw_assertions
            ),
        )

    @staticmethod
    def from_json_file(path: Path) -> GoldCase:
        """Decode a GoldCase from a JSON gold-record file.

        Args:
            path: Path to the JSON gold-record file.

        Returns:
            The decoded, validated GoldCase.

        Raises:
            InvalidGoldCaseError: If a required field is missing, empty, or
                otherwise invalid.
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        return GoldCase.from_dict(data)
