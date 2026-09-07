# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL conformance evidence for the chain-A/red gold-case verifier.

Every collaborator here is real: real headless Open-Source PyMOL
(pymol.finish_launching(['pymol', '-qc'])), the real controlled gold-case
fixture, and the real pmc_data.verifier.verify_gold_case grading the real
accepted pmc_core canonical plan. Nothing here is a PyMOL test double.

The true gold case must pass every assertion (M-A4). Separate wrong-chain,
wrong-color, and unintended-change variants of that same case must each fail
their relevant assertion (M-A5), built from the true case with
dataclasses.replace rather than a second hand-authored record. Missing
provenance/parameters and a real PyMOL evaluator error must invalidate the
result instead of passing or defaulting (M-A6).

PyMOL only supports one finish_launching call per interpreter, so it is
launched exactly once for the whole test module (session-scoped fixture) and
shut down at final teardown. The fixture object is loaded and deleted fresh
for every test function so state from one test can never leak into the next
-- same pattern as tests/integration/test_real_pymol_command.py.

This target is excluded on Windows for the same reason as that module: see
issue #12.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import hashlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import pytest
from pmc_core.plan import initial_fixture_plan
from pmc_data.gold_case import DEFAULT_GOLD_CASE_PATH
from pmc_data.gold_case import Assertion
from pmc_data.gold_case import ContractVersions
from pmc_data.gold_case import GoldCase
from pmc_data.gold_case import Provenance
from pmc_data.verifier import PyMOLCmd as VerifierPyMOLCmd
from pmc_data.verifier import verify_gold_case

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "chain_a_gold_fixture.pdb"
)
OBJECT_NAME = "chain_a_gold_fixture"
RENUMBERED_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "testdata"
    / "renumbered_serials_fixture.pdb"
)


class PyMOLCmd(Protocol):
    """Subset of PyMOL's real cmd module used to drive this test module.

    A structural superset of pmc_data.verifier.PyMOLCmd so the same real
    cmd object satisfies both this module's fixtures and verify_gold_case's
    own parameter type.
    """

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
def loaded_fixture(real_pymol: PyMOLCmd) -> Iterator[PyMOLCmd]:
    """Load the gold-case fixture fresh for one test and delete it after.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module with the fixture object loaded.
    """
    real_pymol.load(str(FIXTURE_PATH), OBJECT_NAME)
    try:
        yield real_pymol
    finally:
        real_pymol.delete(OBJECT_NAME)


@pytest.fixture
def gold_case() -> GoldCase:
    """Load the one hand-authored gold case for this fixture.

    Returns:
        The recorded GoldCase for the chain-A/red fixture.
    """
    return GoldCase.from_json_file(DEFAULT_GOLD_CASE_PATH)


def test_true_gold_case_passes_every_assertion(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """The true gold case passes chain-membership, color, and no-change."""
    result = verify_gold_case(gold_case, FIXTURE_PATH, loaded_fixture)

    assert result.valid
    assert result.task_success
    assert all(assertion.passed for assertion in result.assertion_results)
    assert len(result.assertion_results) == len(gold_case.assertions)


@pytest.fixture
def loaded_renumbered_fixture(real_pymol: PyMOLCmd) -> Iterator[PyMOLCmd]:
    """Load a structure whose atom serials are not 1..N, fresh for one test.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module with the renumbered fixture loaded.
    """
    object_name = "renumbered_serials_fixture"
    real_pymol.load(str(RENUMBERED_FIXTURE_PATH), object_name)
    try:
        yield real_pymol
    finally:
        real_pymol.delete(object_name)


def test_chain_membership_matches_by_real_serial_not_session_ordinal(
    loaded_renumbered_fixture: PyMOLCmd,
) -> None:
    """A structure whose chain-A atom serials are 101-103 (not 1..N) still passes chain_membership, proving the comparison uses PyMOL's real per-atom ID rather than its session-local index -- confirmed as a real, previously-reachable defect: comparing by index would report this correct selection as failed, since index would read 1-3 here regardless of the real serials."""
    case = GoldCase(
        case_id="renumbered_serials_probe_case",
        intent="Select chain A and color it red.",
        category="selection_and_color",
        difficulty="basic",
        provenance=Provenance(
            source="Self-authored synthetic development structure.",
            license="Public domain (CC0-equivalent).",
            structure_relpath="tests/data/testdata/renumbered_serials_fixture.pdb",
            structure_sha256=hashlib.sha256(
                RENUMBERED_FIXTURE_PATH.read_bytes()
            ).hexdigest(),
        ),
        contract_versions=ContractVersions(
            plan_version="1", pymol_version="3.2.0.2"
        ),
        canonical_plan_pml=initial_fixture_plan().render_pml(),
        target_chain="A",
        non_target_chains=("B",),
        assertions=(
            Assertion(
                kind="chain_membership",
                params={
                    "selection_name": "copilot_selection",
                    "chain_id": "A",
                },
            ),
            Assertion(
                kind="color_state",
                params={"selection_name": "copilot_selection", "color": "red"},
            ),
            Assertion(kind="no_unintended_change", params={"chain_id": "B"}),
        ),
    )

    result = verify_gold_case(
        case, RENUMBERED_FIXTURE_PATH, loaded_renumbered_fixture
    )

    assert result.valid
    assert result.task_success
    by_kind = {
        assertion.kind: assertion for assertion in result.assertion_results
    }
    assert by_kind["chain_membership"].passed
    assert (
        by_kind["chain_membership"].detail
        == "expected=[101, 102, 103] actual=[101, 102, 103]"
    )


def test_wrong_chain_case_fails_chain_membership(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """Declaring the wrong target chain fails chain_membership, not the other assertions, and never reports TaskSuccess."""
    corrupted_assertions = tuple(
        dataclasses.replace(
            assertion, params={**assertion.params, "chain_id": "B"}
        )
        if assertion.kind == "chain_membership"
        else assertion
        for assertion in gold_case.assertions
    )
    wrong_chain_case = dataclasses.replace(
        gold_case, assertions=corrupted_assertions
    )

    result = verify_gold_case(wrong_chain_case, FIXTURE_PATH, loaded_fixture)

    assert result.valid
    assert not result.task_success
    by_kind = {
        assertion.kind: assertion for assertion in result.assertion_results
    }
    assert not by_kind["chain_membership"].passed
    assert by_kind["color_state"].passed


def test_wrong_color_case_fails_color_state(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """Declaring the wrong expected color fails color_state, not chain_membership, and never reports TaskSuccess."""
    corrupted_assertions = tuple(
        dataclasses.replace(
            assertion, params={**assertion.params, "color": "blue"}
        )
        if assertion.kind == "color_state"
        else assertion
        for assertion in gold_case.assertions
    )
    wrong_color_case = dataclasses.replace(
        gold_case, assertions=corrupted_assertions
    )

    result = verify_gold_case(wrong_color_case, FIXTURE_PATH, loaded_fixture)

    assert result.valid
    assert not result.task_success
    by_kind = {
        assertion.kind: assertion for assertion in result.assertion_results
    }
    assert not by_kind["color_state"].passed
    assert by_kind["chain_membership"].passed


def test_unintended_change_is_detected(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """A deliberate non-target mutation injected mid-run fails no_unintended_change while the intended target assertions still pass."""

    def inject_mutation(cmd: VerifierPyMOLCmd) -> None:
        """Recolor the non-target chain, the deliberate sabotage this test detects.

        Args:
            cmd: The real PyMOL cmd module mid-verification.
        """
        cmd.do("color blue, chain B")

    result = verify_gold_case(
        gold_case,
        FIXTURE_PATH,
        loaded_fixture,
        inject_after_execution=inject_mutation,
    )

    assert result.valid
    assert not result.task_success
    by_kind = {
        assertion.kind: assertion for assertion in result.assertion_results
    }
    assert not by_kind["no_unintended_change"].passed
    assert by_kind["chain_membership"].passed
    assert by_kind["color_state"].passed


def test_chain_membership_assertion_for_an_absent_chain_invalidates_the_result(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """A chain_membership assertion naming a chain absent from the structure invalidates the run rather than vacuously passing if expected and actual ever happened to both be empty."""
    corrupted_assertions = tuple(
        dataclasses.replace(
            assertion, params={**assertion.params, "chain_id": "Z"}
        )
        if assertion.kind == "chain_membership"
        else assertion
        for assertion in gold_case.assertions
    )
    invalid_case = dataclasses.replace(
        gold_case, assertions=corrupted_assertions
    )

    result = verify_gold_case(invalid_case, FIXTURE_PATH, loaded_fixture)

    assert not result.valid
    assert not result.task_success
    assert result.assertion_results == ()
    assert result.invalid_reason is not None
    assert "no atoms in the structure" in result.invalid_reason


def test_no_unintended_change_assertion_for_an_absent_chain_invalidates_the_result(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """A no_unintended_change assertion naming a chain absent from the structure invalidates the run rather than vacuously passing on two equally empty snapshots."""
    corrupted_assertions = tuple(
        dataclasses.replace(assertion, params={"chain_id": "Z"})
        if assertion.kind == "no_unintended_change"
        else assertion
        for assertion in gold_case.assertions
    )
    invalid_case = dataclasses.replace(
        gold_case,
        assertions=corrupted_assertions,
        non_target_chains=("Z",),
    )

    result = verify_gold_case(invalid_case, FIXTURE_PATH, loaded_fixture)

    assert not result.valid
    assert not result.task_success
    assert result.assertion_results == ()
    assert result.invalid_reason is not None
    assert "no atoms in the structure" in result.invalid_reason


def test_structure_checksum_mismatch_invalidates_the_result(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """A gold case whose recorded checksum no longer matches the structure it is graded against invalidates the run instead of silently grading the wrong file as if it were verified."""
    corrupted_provenance = dataclasses.replace(
        gold_case.provenance, structure_sha256="0" * 64
    )
    invalid_case = dataclasses.replace(
        gold_case, provenance=corrupted_provenance
    )

    result = verify_gold_case(invalid_case, FIXTURE_PATH, loaded_fixture)

    assert not result.valid
    assert not result.task_success
    assert result.assertion_results == ()
    assert result.invalid_reason is not None
    assert "checksum mismatch" in result.invalid_reason


def test_missing_assertion_param_invalidates_the_result(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """An assertion missing a required parameter invalidates the run rather than silently failing or defaulting."""
    corrupted_assertions = tuple(
        dataclasses.replace(assertion, params={})
        if assertion.kind == "chain_membership"
        else assertion
        for assertion in gold_case.assertions
    )
    invalid_case = dataclasses.replace(
        gold_case, assertions=corrupted_assertions
    )

    result = verify_gold_case(invalid_case, FIXTURE_PATH, loaded_fixture)

    assert not result.valid
    assert not result.task_success
    assert result.assertion_results == ()
    assert result.invalid_reason is not None
    assert "missing required param" in result.invalid_reason


def test_real_pymol_evaluator_error_invalidates_the_result(
    loaded_fixture: PyMOLCmd, gold_case: GoldCase
) -> None:
    """An assertion naming a color real PyMOL does not recognize invalidates the run rather than silently failing or crashing the suite."""
    corrupted_assertions = tuple(
        dataclasses.replace(
            assertion,
            params={**assertion.params, "color": "definitely_not_a_real_color"},
        )
        if assertion.kind == "color_state"
        else assertion
        for assertion in gold_case.assertions
    )
    invalid_case = dataclasses.replace(
        gold_case, assertions=corrupted_assertions
    )

    result = verify_gold_case(invalid_case, FIXTURE_PATH, loaded_fixture)

    assert not result.valid
    assert not result.task_success
    assert result.assertion_results == ()
    assert result.invalid_reason is not None
    assert "unknown PyMOL color" in result.invalid_reason


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (confirmed empirically: a deliberately
    # failing assertion here still reported Bazel PASSED under plain
    # `raise SystemExit(...)`). os._exit bypasses that interpreter-shutdown
    # window entirely, so pytest's real result is what Bazel actually sees.
    # os._exit skips the normal stdio flush, so flush explicitly first --
    # otherwise a real failure's traceback and summary can be silently lost
    # from the captured test log (also confirmed empirically).
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
