# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL conformance evidence for the bounded gold-case generator.

Every collaborator here is real: real headless Open-Source PyMOL, the real
checked-in generation config, and the real pmc_data.generate/pmc_data.verifier
grading path. A generation request against a structure that actually has the
requested chain layout must be verified and produce a gold case that matches
the checked-in gold_cases/chain_a_red_second_fixture_gold_case.json record
exactly (this test regenerates it and compares, so drift between the two is
caught rather than silently tolerated). A generation request against a
structure lacking chain A must be rejected by the independent pre-check
before any PyMOL selection or color assertion runs -- gold_case is None --
rather than silently written as a false positive.

Same real-PyMOL launch/fixture pattern as test_gold_case_verifier.py, and
excluded on Windows for the same reason (issue #12).
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import pytest
from pmc_data.gold_case import GoldCase
from pmc_data.generate import GenerationRequest
from pmc_data.generate import generate_gold_case
from pmc_data.generate import load_generation_requests
from pmc_data.gold_case import ContractVersions

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = (
    REPO_ROOT / "configs" / "generation" / "chain_a_red_structures.json"
)
CHECKED_IN_GOLD_CASE_PATH = (
    REPO_ROOT
    / "src"
    / "pmc_data"
    / "gold_cases"
    / "chain_a_red_second_fixture_gold_case.json"
)
NO_CHAIN_A_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "no_chain_a_fixture.pdb"
)
NO_CHAIN_A_OBJECT_NAME = "no_chain_a_fixture"


class PyMOLCmd(Protocol):
    """Subset of PyMOL's real cmd module used to drive this test module."""

    def load(self, filename: str, name: str) -> None:
        """Load a structure file into a named object.

        Args:
            filename: Path to the structure file to load.
            name: Name of the object to create.
        """

    def delete(self, name: str) -> None:
        """Delete a named object or selection.

        Args:
            name: Name of the object or selection to delete.
        """

    def do(self, command: str) -> None:
        """Execute one PML command line exactly as a user would type it.

        Args:
            command: The command line text to execute.
        """

    def sync(self) -> None:
        """Block until every previously queued PML command has finished."""

    def iterate(
        self, selection: str, expression: str, *, space: dict[str, object]
    ) -> None:
        """Run a per-atom Python expression over a selection.

        Args:
            selection: The selection expression to iterate over.
            expression: The Python expression evaluated once per atom.
            space: The namespace exposed to the expression.
        """

    def get_color_index(self, color: str) -> int:
        """Resolve a PyMOL color name to its stable color index.

        Args:
            color: The PyMOL color name to resolve.

        Returns:
            The resolved color index.
        """


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[PyMOLCmd]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL cmd module.
    """
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


@pytest.fixture
def generation_request() -> GenerationRequest:
    """Load the one checked-in generation request for the second fixture.

    Returns:
        The GenerationRequest declared in configs/generation.
    """
    requests = load_generation_requests(CONFIG_PATH, repo_root=REPO_ROOT)
    by_case_id = {request.case_id: request for request in requests}
    return by_case_id["chain_a_red_second_fixture_gold_case"]


@pytest.fixture
def loaded_second_fixture(
    real_pymol: PyMOLCmd, generation_request: GenerationRequest
) -> Iterator[PyMOLCmd]:
    """Load the second fixture fresh for one test and delete it after.

    Args:
        real_pymol: The real PyMOL cmd module.
        generation_request: The request naming the structure to load.

    Yields:
        The real PyMOL cmd module with the second fixture object loaded.
    """
    object_name = "second_gold_fixture"
    real_pymol.load(str(generation_request.structure_path), object_name)
    try:
        yield real_pymol
    finally:
        real_pymol.delete(object_name)


def test_generation_of_the_second_fixture_matches_the_checked_in_record(
    loaded_second_fixture: PyMOLCmd, generation_request: GenerationRequest
) -> None:
    """Regenerating the checked-in second-structure gold case reproduces it exactly, proving it is reproducible rather than hand-edited."""
    result = generate_gold_case(generation_request, loaded_second_fixture)

    assert result.verifier_result.valid
    assert result.verifier_result.task_success
    assert result.gold_case is not None

    checked_in_case = GoldCase.from_json_file(CHECKED_IN_GOLD_CASE_PATH)
    assert result.gold_case == checked_in_case


@pytest.fixture
def loaded_no_chain_a_fixture(real_pymol: PyMOLCmd) -> Iterator[PyMOLCmd]:
    """Load a structure with no chain A at all, fresh for one test.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module with the no-chain-A fixture loaded.
    """
    real_pymol.load(str(NO_CHAIN_A_FIXTURE_PATH), NO_CHAIN_A_OBJECT_NAME)
    try:
        yield real_pymol
    finally:
        real_pymol.delete(NO_CHAIN_A_OBJECT_NAME)


def test_generation_against_a_structure_with_no_chain_a_is_rejected(
    loaded_no_chain_a_fixture: PyMOLCmd,
) -> None:
    """A structure lacking chain A entirely is rejected by the independent pre-check before any PyMOL selection or color assertion ever runs, so the rejection is provably about the structure file having no chain A -- not an ambiguous "nothing was loaded" outcome. The real fixture object being loaded (or not) is irrelevant to this check: it reads the structure file directly, the same independence the rest of pmc_data's oracle relies on."""
    request = GenerationRequest(
        case_id="rejected_no_chain_a_case",
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

    result = generate_gold_case(request, loaded_no_chain_a_fixture)

    assert not result.verifier_result.valid
    assert not result.verifier_result.task_success
    assert result.gold_case is None
    assert result.verifier_result.assertion_results == ()
    assert "chain 'A'" in (result.verifier_result.invalid_reason or "")


if __name__ == "__main__":
    # See test_gold_case_verifier.py's identical block for why os._exit with
    # an explicit flush is required instead of a plain SystemExit here.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
