# Copyright 2026 PyMOL Copilot contributors.
"""Pure-Python tests for the bounded, no-teacher gold-case generator.

These tests never import PyMOL. They prove the generator's config loading
and candidate-construction logic in isolation from real-PyMOL verification,
and that write_generated_gold_case refuses to persist anything that was not
actually verified -- the real-PyMOL conformance evidence that a candidate
passes verification lives in test_generate_real_pymol.py instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pmc_core.plan import initial_fixture_plan
from pmc_data.gold_case import GoldCase
from pmc_data.generate import GenerationRejectedError
from pmc_data.generate import GenerationRequest
from pmc_data.generate import GenerationResult
from pmc_data.generate import InvalidGenerationRequestError
from pmc_data.generate import build_candidate_gold_case
from pmc_data.generate import generate_gold_case
from pmc_data.generate import load_generation_requests
from pmc_data.generate import write_generated_gold_case
from pmc_data.gold_case import ContractVersions
from pmc_data.gold_case import InvalidGoldCaseError
from pmc_data.verifier import VerifierResult

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = (
    REPO_ROOT / "configs" / "generation" / "chain_a_red_structures.json"
)
SECOND_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "second_gold_fixture.pdb"
)
NO_CHAIN_A_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "no_chain_a_fixture.pdb"
)


class _NeverTouched:
    """A stub PyMOLCmd that fails the test if any of its methods are called.

    Used to prove a rejection path never touches cmd at all, rather than
    merely returning a result consistent with rejection for another reason.
    """

    def do(self, command: str) -> None:
        """Fail immediately -- see class docstring.

        Args:
            command: Unused; this stub must never be called.

        Raises:
            AssertionError: Always.
        """
        raise AssertionError(f"cmd.do({command!r}) was called unexpectedly")

    def iterate(
        self, selection: str, expression: str, *, space: dict[str, object]
    ) -> None:
        """Fail immediately -- see class docstring.

        Args:
            selection: Unused; this stub must never be called.
            expression: Unused; this stub must never be called.
            space: Unused; this stub must never be called.

        Raises:
            AssertionError: Always.
        """
        raise AssertionError(
            f"cmd.iterate({selection!r}, {expression!r}, space={space!r}) "
            "was called unexpectedly"
        )

    def get_color_index(self, color: str) -> int:
        """Fail immediately -- see class docstring.

        Args:
            color: Unused; this stub must never be called.

        Raises:
            AssertionError: Always.
        """
        raise AssertionError(
            f"cmd.get_color_index({color!r}) was called unexpectedly"
        )


def test_load_generation_requests_resolves_the_checked_in_config() -> None:
    """The checked-in config declares the second-structure request with its structure path resolved relative to the repository root."""
    requests = load_generation_requests(CONFIG_PATH, repo_root=REPO_ROOT)

    by_case_id = {request.case_id: request for request in requests}
    request = by_case_id["chain_a_red_second_fixture_gold_case"]
    assert request.structure_path == SECOND_FIXTURE_PATH.resolve()
    assert request.non_target_chains == ("C",)


def test_load_generation_requests_rejects_a_malformed_entry(
    tmp_path: Path,
) -> None:
    """A config entry missing a required field is rejected rather than silently coerced into a wrong request."""
    malformed_config = tmp_path / "malformed.json"
    malformed_config.write_text(
        json.dumps({"requests": [{"intent": "Select chain A."}]}),
        encoding="utf-8",
    )

    with pytest.raises(InvalidGoldCaseError):
        load_generation_requests(malformed_config, repo_root=REPO_ROOT)


def _sample_request() -> GenerationRequest:
    """Build one in-memory generation request against the second fixture.

    Returns:
        A GenerationRequest usable without reading configs/generation/.
    """
    return GenerationRequest(
        case_id="sample_gold_case",
        intent="Select chain A and color it red.",
        category="selection_and_color",
        difficulty="basic",
        structure_path=SECOND_FIXTURE_PATH,
        structure_relpath="tests/data/testdata/second_gold_fixture.pdb",
        source="Self-authored synthetic development structure.",
        license="Public domain (CC0-equivalent).",
        contract_versions=ContractVersions(
            plan_version="1", pymol_version="3.2.0.2"
        ),
        non_target_chains=("C",),
    )


def test_build_candidate_gold_case_rejects_an_absent_target_chain() -> None:
    """A structure with no atoms on chain A is rejected before verification, closing the vacuous-pass risk color_state would otherwise catch only incidentally."""
    request = GenerationRequest(
        case_id="rejected_no_chain_a",
        intent="Select chain A and color it red.",
        category="selection_and_color",
        difficulty="basic",
        structure_path=NO_CHAIN_A_FIXTURE_PATH,
        structure_relpath="tests/data/testdata/no_chain_a_fixture.pdb",
        source="Self-authored synthetic development structure.",
        license="Public domain (CC0-equivalent).",
        contract_versions=ContractVersions(
            plan_version="1", pymol_version="3.2.0.2"
        ),
        non_target_chains=("Z",),
    )

    with pytest.raises(InvalidGenerationRequestError, match="chain 'A'"):
        build_candidate_gold_case(request)


def test_build_candidate_gold_case_rejects_an_absent_non_target_chain() -> None:
    """A declared non-target chain absent from the structure is rejected, since no_unintended_change would otherwise pass vacuously for a chain that was never actually observed."""
    request = GenerationRequest(
        case_id="rejected_typo_non_target",
        intent="Select chain A and color it red.",
        category="selection_and_color",
        difficulty="basic",
        structure_path=SECOND_FIXTURE_PATH,
        structure_relpath="tests/data/testdata/second_gold_fixture.pdb",
        source="Self-authored synthetic development structure.",
        license="Public domain (CC0-equivalent).",
        contract_versions=ContractVersions(
            plan_version="1", pymol_version="3.2.0.2"
        ),
        non_target_chains=("Q",),
    )

    with pytest.raises(InvalidGenerationRequestError, match="'Q'"):
        build_candidate_gold_case(request)


def test_generate_gold_case_rejects_an_invalid_request_without_touching_cmd() -> (
    None
):
    """generate_gold_case short-circuits an invalid request before ever calling cmd, and never returns a gold_case for it."""
    request = GenerationRequest(
        case_id="rejected_no_chain_a",
        intent="Select chain A and color it red.",
        category="selection_and_color",
        difficulty="basic",
        structure_path=NO_CHAIN_A_FIXTURE_PATH,
        structure_relpath="tests/data/testdata/no_chain_a_fixture.pdb",
        source="Self-authored synthetic development structure.",
        license="Public domain (CC0-equivalent).",
        contract_versions=ContractVersions(
            plan_version="1", pymol_version="3.2.0.2"
        ),
        non_target_chains=("Z",),
    )

    result = generate_gold_case(request, _NeverTouched())

    assert not result.verifier_result.valid
    assert not result.verifier_result.task_success
    assert result.gold_case is None
    assert result.verifier_result.assertion_results == ()


def test_build_candidate_gold_case_reuses_the_one_accepted_canonical_plan() -> (
    None
):
    """The candidate's canonical plan is exactly pmc_core's own rendering, not a re-derivation, so drift there is caught the same way the hand-authored gold record is checked."""
    candidate = build_candidate_gold_case(_sample_request())

    assert candidate.canonical_plan_pml == initial_fixture_plan().render_pml()
    assert candidate.target_chain == "A"
    assert candidate.non_target_chains == ("C",)
    kinds = {assertion.kind for assertion in candidate.assertions}
    assert kinds == {"chain_membership", "color_state", "no_unintended_change"}


def test_build_candidate_gold_case_checksum_matches_the_structure_file() -> (
    None
):
    """The candidate's recorded checksum is the structure file's actual SHA-256, computed independently in this test."""
    import hashlib

    candidate = build_candidate_gold_case(_sample_request())

    expected_checksum = hashlib.sha256(
        SECOND_FIXTURE_PATH.read_bytes()
    ).hexdigest()
    assert candidate.provenance.structure_sha256 == expected_checksum


def test_write_generated_gold_case_refuses_an_unverified_result(
    tmp_path: Path,
) -> None:
    """A GenerationResult with gold_case=None (a rejected generation) is never written, even if a caller tries to force it."""
    rejected = GenerationResult(
        case_id="sample_gold_case",
        verifier_result=VerifierResult(
            case_id="sample_gold_case",
            valid=True,
            invalid_reason=None,
            assertion_results=(),
            task_success=False,
        ),
        gold_case=None,
    )

    with pytest.raises(GenerationRejectedError):
        write_generated_gold_case(rejected, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_write_generated_gold_case_persists_a_verified_result(
    tmp_path: Path,
) -> None:
    """A verified GenerationResult is written as a round-trippable gold-record JSON file named after its case_id."""
    candidate = build_candidate_gold_case(_sample_request())
    verified = GenerationResult(
        case_id=candidate.case_id,
        verifier_result=VerifierResult(
            case_id=candidate.case_id,
            valid=True,
            invalid_reason=None,
            assertion_results=(),
            task_success=True,
        ),
        gold_case=candidate,
    )

    written_path = write_generated_gold_case(verified, tmp_path)

    assert written_path == tmp_path / "sample_gold_case.json"
    round_tripped = GoldCase.from_json_file(written_path)
    assert round_tripped == candidate
    # The file is valid, indented JSON with a trailing newline, matching the
    # convention of the hand-authored gold_cases/chain_a_red.json record.
    assert written_path.read_text(encoding="utf-8").endswith("}\n")
    json.loads(written_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
