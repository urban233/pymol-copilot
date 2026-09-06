# Copyright 2026 PyMOL Copilot contributors.
"""Bounded, no-teacher program-first generation of new gold cases.

This module reapplies the one accepted, unchanged canonical plan (chain A
selected and colored red -- see pmc_core.plan.initial_fixture_plan) to
additional controlled structures, and verifies each candidate through the
same real-PyMOL, independent-oracle path that grades the hand-authored gold
case in pmc_data.verifier. A candidate is never written as a gold record
unless verification reports both a valid run and TaskSuccess; a rejected
generation is returned to the caller instead, never silently discarded or
promoted. This intentionally does not implement teacher back-translation,
curation, or a hermetic execution service -- those remain out of scope for
this task's containment (see the wave plan's M-01 entry).
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pmc_core.plan import initial_fixture_plan
from pmc_data.gold_case import ASSERTION_KIND_CHAIN_MEMBERSHIP
from pmc_data.gold_case import ASSERTION_KIND_COLOR_STATE
from pmc_data.gold_case import ASSERTION_KIND_NO_UNINTENDED_CHANGE
from pmc_data.gold_case import Assertion
from pmc_data.gold_case import ContractVersions
from pmc_data.gold_case import GoldCase
from pmc_data.gold_case import Provenance
from pmc_data.verifier import PyMOLCmd
from pmc_data.verifier import VerifierResult
from pmc_data.verifier import verify_gold_case

#: The fixed selection/color the accepted canonical plan always produces.
_SELECTION_NAME = "copilot_selection"
_TARGET_COLOR = "red"


class GenerationRejectedError(ValueError):
    """Raised when code asks to persist a generation that was not verified.

    A rejected or not-yet-verified candidate can never be written as a gold
    record; this error enforces that at the write boundary rather than
    relying on every caller to check first.
    """


@dataclass(frozen=True)
class GenerationRequest:
    """One request to generate a gold case for a new controlled structure.

    Attributes:
        case_id: The stable identity the resulting gold case will use.
        intent: The natural-language intent this case represents.
        category: The taxonomy category this case belongs to.
        difficulty: The taxonomy difficulty label for this case.
        structure_path: Path to the controlled structure file, already
            resolved to an absolute or repository-relative location.
        structure_relpath: Repository-relative path recorded in provenance.
        source: A short description of where the structure came from.
        license: The license or provenance basis permitting its use here.
        contract_versions: The plan/PyMOL contract versions in effect.
        non_target_chains: Chain identifiers that must show no unintended
            change. The target chain is always "A": the canonical plan's
            selection expression is fixed and structure-independent.
    """

    case_id: str
    intent: str
    category: str
    difficulty: str
    structure_path: Path
    structure_relpath: str
    source: str
    license: str
    contract_versions: ContractVersions
    non_target_chains: tuple[str, ...]


@dataclass(frozen=True)
class GenerationResult:
    """The outcome of one attempted gold-case generation.

    Attributes:
        case_id: The identity of the candidate that was attempted.
        verifier_result: The full grading outcome for the candidate.
        gold_case: The verified GoldCase, present only when
            verifier_result.valid and verifier_result.task_success are both
            True. None means the generation was rejected and must never be
            written as a gold record.
    """

    case_id: str
    verifier_result: VerifierResult
    gold_case: GoldCase | None


def _sha256_of(path: Path) -> str:
    """Compute the hex SHA-256 checksum of a file's bytes.

    Args:
        path: Path to the file to checksum.

    Returns:
        The lowercase hex-encoded digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_candidate_gold_case(request: GenerationRequest) -> GoldCase:
    """Build an unverified candidate gold case for one generation request.

    The candidate always reuses the one accepted canonical plan and its
    fixed "copilot_selection"/"red" outcome; only provenance, identity, and
    the non-target chains vary by structure. Building a candidate never
    runs PyMOL -- it only requires the structure file's bytes, for the
    checksum, and pmc_core's own canonical plan rendering.

    Args:
        request: The generation request describing the new structure.

    Returns:
        The candidate GoldCase, not yet verified against real PyMOL.
    """
    provenance = Provenance(
        source=request.source,
        license=request.license,
        structure_relpath=request.structure_relpath,
        structure_sha256=_sha256_of(request.structure_path),
    )
    assertions = (
        Assertion(
            kind=ASSERTION_KIND_CHAIN_MEMBERSHIP,
            params={"selection_name": _SELECTION_NAME, "chain_id": "A"},
        ),
        Assertion(
            kind=ASSERTION_KIND_COLOR_STATE,
            params={
                "selection_name": _SELECTION_NAME,
                "color": _TARGET_COLOR,
            },
        ),
        *(
            Assertion(
                kind=ASSERTION_KIND_NO_UNINTENDED_CHANGE,
                params={"chain_id": chain_id},
            )
            for chain_id in request.non_target_chains
        ),
    )
    return GoldCase(
        case_id=request.case_id,
        intent=request.intent,
        category=request.category,
        difficulty=request.difficulty,
        provenance=provenance,
        contract_versions=request.contract_versions,
        canonical_plan_pml=initial_fixture_plan().render_pml(),
        target_chain="A",
        non_target_chains=request.non_target_chains,
        assertions=assertions,
    )


def generate_gold_case(
    request: GenerationRequest, cmd: PyMOLCmd
) -> GenerationResult:
    """Generate and verify one candidate gold case through real PyMOL.

    Args:
        request: The generation request describing the new structure.
        cmd: The real PyMOL cmd module, with request.structure_path already
            loaded and no prior plan executed against it.

    Returns:
        The GenerationResult. gold_case is populated only when the real run
        was both valid and TaskSuccess; otherwise the rejected candidate is
        never returned as a gold_case, so a caller cannot promote it by
        mistake.
    """
    candidate = build_candidate_gold_case(request)
    result = verify_gold_case(candidate, request.structure_path, cmd)
    verified_case = candidate if result.valid and result.task_success else None
    return GenerationResult(
        case_id=candidate.case_id,
        verifier_result=result,
        gold_case=verified_case,
    )


def write_generated_gold_case(
    result: GenerationResult, destination_dir: Path
) -> Path:
    """Persist a verified generation result as a gold-record JSON file.

    Args:
        result: The generation result to persist.
        destination_dir: Directory the new gold-record JSON file is written
            into, named "<case_id>.json".

    Returns:
        The path of the written gold-record file.

    Raises:
        GenerationRejectedError: If result.gold_case is None -- a rejected
            or unverified generation is never written as a gold record.
    """
    if result.gold_case is None:
        raise GenerationRejectedError(
            f"generation {result.case_id!r} was not verified "
            f"(invalid_reason={result.verifier_result.invalid_reason!r}, "
            f"task_success={result.verifier_result.task_success}) and "
            "cannot be written as a gold record"
        )
    destination_path = destination_dir / f"{result.case_id}.json"
    destination_path.write_text(
        json.dumps(result.gold_case.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return destination_path


def _request_from_dict(
    data: Mapping[str, object], *, repo_root: Path
) -> GenerationRequest:
    """Decode one GenerationRequest from a raw generation-config mapping.

    Args:
        data: The raw request mapping, one entry of a generation config's
            "requests" list.
        repo_root: Repository root structure_relpath is resolved against,
            matching the same repository-relative convention gold-case
            provenance already records.

    Returns:
        The decoded GenerationRequest.

    Raises:
        KeyError: If a required field is absent.
    """
    contract_versions = data["contract_versions"]
    assert isinstance(contract_versions, Mapping)
    non_target_chains = data["non_target_chains"]
    assert isinstance(non_target_chains, list)
    structure_relpath = str(data["structure_relpath"])
    return GenerationRequest(
        case_id=str(data["case_id"]),
        intent=str(data["intent"]),
        category=str(data["category"]),
        difficulty=str(data["difficulty"]),
        structure_path=(repo_root / structure_relpath).resolve(),
        structure_relpath=structure_relpath,
        source=str(data["source"]),
        license=str(data["license"]),
        contract_versions=ContractVersions(
            plan_version=str(contract_versions["plan_version"]),
            pymol_version=str(contract_versions["pymol_version"]),
        ),
        non_target_chains=tuple(
            str(chain_id) for chain_id in non_target_chains
        ),
    )


def load_generation_requests(
    config_path: Path, *, repo_root: Path
) -> tuple[GenerationRequest, ...]:
    """Load generation requests from a configs/generation/*.json file.

    Args:
        config_path: Path to the generation config JSON file.
        repo_root: Repository root structure_relpath entries are resolved
            against. Callers derive this the same way existing test modules
            anchor repository-relative fixture paths from their own
            __file__, since Bazel's runfiles tree mirrors the repository
            layout below the workspace root.

    Returns:
        The ordered generation requests the config declares.
    """
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return tuple(
        _request_from_dict(entry, repo_root=repo_root)
        for entry in data["requests"]
    )
