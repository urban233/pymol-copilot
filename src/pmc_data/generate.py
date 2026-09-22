# Copyright 2026 PyMOL Copilot contributors.
"""Bounded, no-teacher program-first generation of new gold cases.

This module reapplies the one accepted, unchanged canonical plan (chain A
selected and colored red -- see pmc_data.gold_case.CHAIN_A_RED_PLAN) to
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
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pmc_core.executor import DEFAULT_DEADLINE_SECONDS
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import REASON_FIDELITY_MISMATCH
from pmc_core.executor import REASON_OK
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import execute
from pmc_core.prompt import build_for_data
from pmc_core.protocol import encode_plan
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.gold_case import ASSERTION_KIND_CHAIN_MEMBERSHIP
from pmc_data.gold_case import ASSERTION_KIND_COLOR_STATE
from pmc_data.gold_case import ASSERTION_KIND_NO_UNINTENDED_CHANGE
from pmc_data.gold_case import CHAIN_A_RED_PLAN
from pmc_data.gold_case import Assertion
from pmc_data.gold_case import ContractVersions
from pmc_data.gold_case import GoldCase
from pmc_data.gold_case import InvalidGoldCaseError
from pmc_data.gold_case import Provenance
from pmc_data.gold_case import required_string
from pmc_data.oracle import apply_plan
from pmc_data.oracle import expected_chain_atom_ids
from pmc_data.sample import ASSERTION_COMMANDS_SUCCEEDED
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import ASSERTION_SELECTION_COUNTS
from pmc_data.sample import FINGERPRINT_PREFIX
from pmc_data.sample import REASON_NOT_GRADABLE
from pmc_data.sample import STATUS_UNSUPPORTED
from pmc_data.sample import Assertion as SampleAssertion
from pmc_data.sample import Rejection
from pmc_data.sample import Sample
from pmc_data.sample import StructureIdentity
from pmc_data.sample import VerificationRecord
from pmc_data.sample import current_versions
from pmc_data.structures import StructureSpec
from pmc_data.taxonomy import PlanCandidate
from pmc_data.verifier import PyMOLCmd
from pmc_data.verifier import VerifierResult
from pmc_data.verifier import verify_gold_case

#: The fixed selection/color the accepted canonical plan always produces.
_SELECTION_NAME = "copilot_selection"
_TARGET_COLOR = "red"
#: The fixed target chain: the canonical plan's selection expression is the
#: literal "chain A", so any structure lacking it can never succeed.
_TARGET_CHAIN = "A"


class GenerationRejectedError(ValueError):
    """Raised when code asks to persist a generation that was not verified.

    A rejected or not-yet-verified candidate can never be written as a gold
    record; this error enforces that at the write boundary rather than
    relying on every caller to check first.
    """


class InvalidGenerationRequestError(ValueError):
    """Raised when a request names a chain absent from its own structure.

    Declaring the target chain or a non-target chain that the structure does
    not actually contain would let verification pass vacuously (an absent
    chain's before/after snapshots are both empty, so no_unintended_change
    trivially "passes" for a chain that was never really observed). Building
    a candidate rejects this before ever touching PyMOL, using the same
    independent, PyMOL-free oracle the rest of pmc_data relies on.
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

    Raises:
        InvalidGenerationRequestError: If the structure has no atoms on the
            fixed target chain "A", or on any declared non-target chain.
    """
    if not expected_chain_atom_ids(request.structure_path, _TARGET_CHAIN):
        raise InvalidGenerationRequestError(
            f"{request.case_id!r}: structure {request.structure_relpath!r} "
            f"has no atoms on chain {_TARGET_CHAIN!r}, the accepted plan's "
            "fixed target"
        )
    for chain_id in request.non_target_chains:
        if not expected_chain_atom_ids(request.structure_path, chain_id):
            raise InvalidGenerationRequestError(
                f"{request.case_id!r}: declared non-target chain "
                f"{chain_id!r} has no atoms in structure "
                f"{request.structure_relpath!r}"
            )
    provenance = Provenance(
        source=request.source,
        license=request.license,
        structure_relpath=request.structure_relpath,
        structure_sha256=_sha256_of(request.structure_path),
    )
    assertions = (
        Assertion(
            kind=ASSERTION_KIND_CHAIN_MEMBERSHIP,
            params={
                "selection_name": _SELECTION_NAME,
                "chain_id": _TARGET_CHAIN,
            },
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
        canonical_plan_pml=CHAIN_A_RED_PLAN.render_pml(),
        target_chain=_TARGET_CHAIN,
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
        mistake. A request naming a chain absent from its own structure is
        rejected without ever touching cmd -- it could not possibly succeed
        against the fixed plan, so there is nothing for PyMOL to grade.
    """
    try:
        candidate = build_candidate_gold_case(request)
    except InvalidGenerationRequestError as error:
        return GenerationResult(
            case_id=request.case_id,
            verifier_result=VerifierResult(
                case_id=request.case_id,
                valid=False,
                invalid_reason=str(error),
                assertion_results=(),
                task_success=False,
            ),
            gold_case=None,
        )
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
        InvalidGoldCaseError: If a required field is missing, empty, or the
            wrong shape -- the same validation gold_case.py's own decoding
            already applies to a hand-authored gold record.
    """
    if "contract_versions" not in data or not isinstance(
        data["contract_versions"], Mapping
    ):
        raise InvalidGoldCaseError(
            "missing required field: 'contract_versions'"
        )
    non_target_chains = data.get("non_target_chains")
    if not isinstance(non_target_chains, list) or not all(
        isinstance(chain_id, str) and chain_id for chain_id in non_target_chains
    ):
        raise InvalidGoldCaseError(
            "'non_target_chains' must be a list of non-empty strings"
        )
    structure_relpath = required_string(data, "structure_relpath")
    return GenerationRequest(
        case_id=required_string(data, "case_id"),
        intent=required_string(data, "intent"),
        category=required_string(data, "category"),
        difficulty=required_string(data, "difficulty"),
        structure_path=(repo_root / structure_relpath).resolve(),
        structure_relpath=structure_relpath,
        source=required_string(data, "source"),
        license=required_string(data, "license"),
        contract_versions=ContractVersions.from_dict(data["contract_versions"]),
        non_target_chains=tuple(non_target_chains),
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


#: The type of the execution seam verify_sample() drives. Injectable so
#: a hermetic test can prove the promotion guard without spawning real
#: PyMOL -- the same shape pmc_server.validation already uses.
type EXECUTOR = Callable[[ExecutionRequest], ExecutionReport]


#: The reason recorded when a run was clean but the oracle's predicted
#: selection counts and the executor's observed ones disagree.
REASON_SELECTION_COUNT_MISMATCH = "selection_count_mismatch"


def _fingerprint_of(snapshot: ObjectSnapshot) -> str:
    """Compute the fingerprint the executor compares a run against.

    Must match `pmc_sidecar.child` exactly: "sha256:" followed by the
    hex digest of the canonical snapshot JSON's UTF-8 bytes.

    Args:
        snapshot: The predicted resulting snapshot.

    Returns:
        The fingerprint text.
    """
    return (
        FINGERPRINT_PREFIX
        + hashlib.sha256(to_json(snapshot).encode("utf-8")).hexdigest()
    )


def verify_sample(
    snapshot: ObjectSnapshot,
    spec: StructureSpec,
    candidate: PlanCandidate,
    *,
    sample_id: str,
    executor: EXECUTOR = execute,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
) -> Sample | Rejection:
    """Generate one sample and keep it only if every assertion passes.

    The oracle predicts the whole resulting snapshot first, and its
    fingerprint is handed to the executor as
    `expected_resulting_fingerprint`. The boundary then fails the run
    closed with `REASON_FIDELITY_MISMATCH` if real PyMOL disagrees, so
    the verdict is the executor's own, computed against an expectation
    it did not produce.

    A plan the oracle cannot predict a snapshot for -- one that
    orients -- passes no fingerprint and is graded on its selection
    counts instead, recording `camera_view` as unsupported. A plan the
    oracle cannot grade at all is not a sample and is returned as a
    rejection with status `unsupported`, so it appears in the report
    rather than vanishing.

    Args:
        snapshot: The controlled structure to run against.
        spec: The spec that structure was built from.
        candidate: The plan, category, difficulty and intent.
        sample_id: The identity to record.
        executor: The execution seam to drive.
        deadline_seconds: Wall-clock deadline for the child process.

    Returns:
        The verified Sample, or the Rejection explaining why not.
    """
    expected = apply_plan(snapshot, candidate.plan)
    if expected.snapshot is None and not expected.selection_counts:
        # Nothing about the result can be checked. "The command ran" is
        # not verification, so this is reported rather than promoted.
        return Rejection(
            sample_id=sample_id,
            category=candidate.category,
            difficulty=candidate.difficulty,
            status=STATUS_UNSUPPORTED,
            reason=REASON_NOT_GRADABLE,
            detail=f"unsupported: {', '.join(expected.unsupported)}",
        )

    snapshot_json = to_json(snapshot)
    input_digest = structure_digest(snapshot)
    fingerprint = (
        None
        if expected.snapshot is None
        else _fingerprint_of(expected.snapshot)
    )
    prompt = build_for_data(snapshot, candidate.intent)

    report = executor(
        ExecutionRequest(
            executor_version=EXECUTOR_VERSION,
            plan=candidate.plan,
            snapshot_json=snapshot_json,
            expected_snapshot_digest=input_digest,
            expected_resulting_fingerprint=fingerprint,
            deadline_seconds=deadline_seconds,
        )
    )

    observed_counts = tuple(
        (count.name, count.atom_count) for count in report.selection_counts
    )
    if report.reason != REASON_OK:
        failing = [
            f"#{outcome.index} {outcome.verb}: {outcome.error}"
            for outcome in report.command_outcomes
            if outcome.status == OUTCOME_ERROR
        ]
        if report.reason == REASON_FIDELITY_MISMATCH:
            # The fidelity gate fails a run in which every command
            # reported success, so there is no failing outcome to name
            # and the detail would otherwise repeat the reason code and
            # say nothing else. This is the one rejection that is real
            # PyMOL disagreeing with the oracle -- the finding this
            # whole pipeline exists to surface -- so it records what
            # the two sides actually produced, which is the only thing
            # rejections.jsonl can be diagnosed from afterwards.
            failing.append(
                f"expected {fingerprint} but the run produced "
                f"{report.resulting_fingerprint}"
            )
        return Rejection(
            sample_id=sample_id,
            category=candidate.category,
            difficulty=candidate.difficulty,
            status=report.status,
            reason=report.reason,
            detail="; ".join(failing) or report.reason,
        )
    if observed_counts != expected.selection_counts:
        # The boundary reported success, but the counts it observed are
        # not the ones the oracle predicted. Never repaired: a
        # disagreement is the finding, not a thing to paper over.
        return Rejection(
            sample_id=sample_id,
            category=candidate.category,
            difficulty=candidate.difficulty,
            status=report.status,
            reason=REASON_SELECTION_COUNT_MISMATCH,
            detail=(
                f"predicted={expected.selection_counts} "
                f"observed={observed_counts}"
            ),
        )

    assertions: list[SampleAssertion] = []
    if fingerprint is not None:
        assertions.append(
            SampleAssertion(
                kind=ASSERTION_RESULTING_SNAPSHOT, detail=fingerprint
            )
        )
    if expected.selection_counts:
        assertions.append(
            SampleAssertion(
                kind=ASSERTION_SELECTION_COUNTS,
                detail=str(list(expected.selection_counts)),
            )
        )
    assertions.append(
        SampleAssertion(
            kind=ASSERTION_COMMANDS_SUCCEEDED,
            detail=f"{len(report.command_outcomes)} commands",
        )
    )

    return Sample(
        sample_id=sample_id,
        intent=candidate.intent,
        category=candidate.category,
        difficulty=candidate.difficulty,
        structure=StructureIdentity(
            spec_id=spec.spec_id,
            seed=spec.seed,
            spec=spec.to_dict(),
            snapshot_sha256=hashlib.sha256(
                snapshot_json.encode("utf-8")
            ).hexdigest(),
            structure_digest=input_digest,
        ),
        versions=current_versions(
            card_version=prompt.card_version,
            prompt_version=prompt.prompt_version,
        ),
        plan_pml=candidate.plan.render_pml(),
        plan_json=tuple(encode_plan(candidate.plan)),
        prompt_text=prompt.text(),
        assertions=tuple(assertions),
        unsupported_assertions=expected.unsupported,
        verification=VerificationRecord(
            status=report.status,
            reason=report.reason,
            expected_fingerprint=fingerprint,
            resulting_fingerprint=report.resulting_fingerprint,
            selection_counts=observed_counts,
            command_verbs=tuple(
                outcome.verb for outcome in report.command_outcomes
            ),
        ),
    )
