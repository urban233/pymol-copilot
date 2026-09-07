# Copyright 2026 PyMOL Copilot contributors.
"""Grades a real PyMOL run of the accepted fixture against a GoldCase.

The verifier executes the accepted, unchanged pmc_core canonical plan
through a real (caller-supplied) PyMOL cmd, then compares the resulting
selection membership, color state, and non-target atom state against the
independent oracle in pmc_data.oracle. A gold case is graded TaskSuccess
only when every declared assertion passes; missing provenance, an
unsupported assertion, policy denial of the accepted fixture, or any
real-PyMOL evaluator error invalidates the result instead of silently
counting as a failure or a pass.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pmc_core.plan import initial_fixture_plan
from pmc_core.policy import evaluate_plan
from pmc_data.gold_case import ASSERTION_KIND_CHAIN_MEMBERSHIP
from pmc_data.gold_case import ASSERTION_KIND_COLOR_STATE
from pmc_data.gold_case import ASSERTION_KIND_NO_UNINTENDED_CHANGE
from pmc_data.gold_case import Assertion
from pmc_data.gold_case import GoldCase
from pmc_data.oracle import expected_chain_atom_ids

#: Atom color pairs captured for one chain: (atom index, PyMOL color index).
CHAIN_COLOR_SNAPSHOT = tuple[tuple[int, int], ...]


class PyMOLCmd(Protocol):
    """Subset of PyMOL's real cmd module used by the verifier."""

    def do(self, command: str) -> None:
        """Execute one PML command line exactly as a user would type it.

        Args:
            command: The command line text to execute.
        """

    def sync(self) -> None:
        """Block until every previously queued PML command has finished.

        Headless PyMOL's command loop runs on its own worker thread, so
        do() only enqueues a command; a caller that reads state back out
        immediately afterward has no guarantee the queued command already
        ran unless it calls this first.
        """

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


class VerifierError(Exception):
    """Raised internally to invalidate a gold-case verification run."""


@dataclass(frozen=True)
class AssertionResult:
    """The observed outcome of one evaluated assertion.

    Attributes:
        kind: The assertion kind that was evaluated.
        passed: Whether the assertion's expected and actual state matched.
        detail: A human-readable record of the expected and actual state.
    """

    kind: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerifierResult:
    """The complete grading outcome for one gold-case verification run.

    Attributes:
        case_id: The identity of the gold case that was graded.
        valid: Whether the run completed without an evaluator error, policy
            denial, or contract drift. task_success is only meaningful
            when this is True.
        invalid_reason: Why the run was invalidated, or None when valid.
        assertion_results: The per-assertion results, empty when invalid.
        task_success: True only when valid is True and every assertion in
            assertion_results passed.
    """

    case_id: str
    valid: bool
    invalid_reason: str | None
    assertion_results: tuple[AssertionResult, ...]
    task_success: bool


def _sha256_of(path: Path) -> str:
    """Compute the hex SHA-256 checksum of a file's bytes.

    Args:
        path: Path to the file to checksum.

    Returns:
        The lowercase hex-encoded digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _capture_colors(cmd: PyMOLCmd, selection: str) -> CHAIN_COLOR_SNAPSHOT:
    """Capture a comparable color snapshot for every atom a selection matches.

    Args:
        cmd: The real PyMOL cmd module.
        selection: The selection expression to capture colors for.

    Returns:
        The sorted (atom index, color index) pairs the selection matches.
    """
    colors: list[tuple[int, int]] = []
    cmd.iterate(
        selection, "colors.append((index, color))", space={"colors": colors}
    )
    return tuple(sorted(colors))


def _selection_atom_ids(cmd: PyMOLCmd, selection_name: str) -> frozenset[int]:
    """Capture the stable atom identities a named PyMOL selection matches.

    Uses PyMOL's own "ID" namespace field, which carries the loaded
    structure file's original atom serial number -- the same quantity
    pmc_data.pdb.read_atoms independently parses from the file's own
    fixed-column serial field. PyMOL's "index" is a different quantity (a
    per-session ordinal within the object) that only happens to match the
    serial when a structure numbers its atoms 1..N in file order; comparing
    it against the independent oracle's serial-based expectations would
    silently grade a correct selection as failed on any structure that
    doesn't (confirmed empirically: a structure with serials renumbered to
    101-103 still reports index 1-3).

    Args:
        cmd: The real PyMOL cmd module.
        selection_name: The selection to inspect.

    Returns:
        The frozen set of atom identities (real file serial numbers) the
        selection matches.
    """
    atom_ids: list[int] = []
    cmd.iterate(
        selection_name, "atom_ids.append(ID)", space={"atom_ids": atom_ids}
    )
    return frozenset(atom_ids)


def _require_param(assertion: Assertion, key: str) -> str:
    """Read a required assertion parameter, invalidating the run if absent.

    Args:
        assertion: The assertion whose params are being read.
        key: The required parameter name.

    Returns:
        The parameter's string value.

    Raises:
        VerifierError: If key is absent from assertion.params.
    """
    if key not in assertion.params:
        raise VerifierError(
            f"assertion {assertion.kind!r} missing required param {key!r}"
        )
    return assertion.params[key]


def _evaluate_chain_membership(
    assertion: Assertion, cmd: PyMOLCmd, structure_path: Path
) -> AssertionResult:
    """Grade a chain_membership assertion against the independent oracle.

    Args:
        assertion: The chain_membership assertion to evaluate.
        cmd: The real PyMOL cmd module, after the plan has executed.
        structure_path: Path to the controlled structure file.

    Returns:
        The observed AssertionResult.

    Raises:
        VerifierError: If chain_id has no atoms in the structure at all --
            expected would be empty, so expected == actual could pass
            vacuously against an equally empty actual instead of actually
            checking membership.
    """
    chain_id = _require_param(assertion, "chain_id")
    selection_name = _require_param(assertion, "selection_name")
    expected = expected_chain_atom_ids(structure_path, chain_id)
    if not expected:
        raise VerifierError(
            f"chain_membership assertion names chain {chain_id!r}, which "
            "has no atoms in the structure"
        )
    actual = _selection_atom_ids(cmd, selection_name)
    return AssertionResult(
        kind=assertion.kind,
        passed=expected == actual,
        detail=f"expected={sorted(expected)} actual={sorted(actual)}",
    )


def _evaluate_color_state(
    assertion: Assertion, cmd: PyMOLCmd
) -> AssertionResult:
    """Grade a color_state assertion against the requested fixture color.

    Args:
        assertion: The color_state assertion to evaluate.
        cmd: The real PyMOL cmd module, after the plan has executed.

    Returns:
        The observed AssertionResult.

    Raises:
        VerifierError: If color names a color PyMOL itself does not
            recognize (get_color_index returns a negative index), since
            that names a setup error rather than an observable color state.
    """
    selection_name = _require_param(assertion, "selection_name")
    color = _require_param(assertion, "color")
    expected_index = cmd.get_color_index(color)
    if expected_index < 0:
        raise VerifierError(
            f"assertion names an unknown PyMOL color: {color!r}"
        )
    actual_colors = _capture_colors(cmd, selection_name)
    passed = bool(actual_colors) and all(
        color_index == expected_index for _, color_index in actual_colors
    )
    return AssertionResult(
        kind=assertion.kind,
        passed=passed,
        detail=f"expected_color_index={expected_index} actual={actual_colors}",
    )


def _evaluate_no_unintended_change(
    assertion: Assertion,
    before: Mapping[str, CHAIN_COLOR_SNAPSHOT],
    after: Mapping[str, CHAIN_COLOR_SNAPSHOT],
) -> AssertionResult:
    """Grade a no_unintended_change assertion for one non-target chain.

    Args:
        assertion: The no_unintended_change assertion to evaluate.
        before: Per-chain color snapshots captured before plan execution.
        after: Per-chain color snapshots captured after plan execution.

    Returns:
        The observed AssertionResult.

    Raises:
        VerifierError: If assertion's chain was not snapshotted on both
            sides, or if both snapshots are empty -- before == after could
            pass vacuously for a chain with no atoms to actually observe.
    """
    chain_id = _require_param(assertion, "chain_id")
    if chain_id not in before or chain_id not in after:
        raise VerifierError(f"no captured snapshot for chain {chain_id!r}")
    if not before[chain_id] and not after[chain_id]:
        raise VerifierError(
            f"no_unintended_change assertion names chain {chain_id!r}, "
            "which has no atoms in the structure"
        )
    return AssertionResult(
        kind=assertion.kind,
        passed=before[chain_id] == after[chain_id],
        detail=f"before={before[chain_id]} after={after[chain_id]}",
    )


def verify_gold_case(
    case: GoldCase,
    structure_path: Path,
    cmd: PyMOLCmd,
    *,
    inject_after_execution: Callable[[PyMOLCmd], None] | None = None,
) -> VerifierResult:
    """Grade one real PyMOL run of the accepted fixture against case.

    Executes the accepted, unchanged canonical plan through cmd, then
    evaluates every assertion in case.assertions against the independent
    oracle and the captured non-target chain state. case.provenance's
    recorded checksum is verified against structure_path's actual bytes
    before grading -- otherwise nothing would stop a future caller from
    grading a case against a different file than the one its own
    provenance names while still reporting TaskSuccess. cmd.sync() is called
    after the plan executes, and again after inject_after_execution, before
    any state is read back out -- headless PyMOL's command loop runs on its
    own worker thread, so do() only enqueues a command; without sync(), a
    read-after-write race can mis-grade a genuinely passing or failing run
    (confirmed empirically: a stalled worker thread produced an empty
    post-execution snapshot). inject_after_execution, when given, runs after
    the plan executes and before non-target state is captured -- its sole
    purpose is letting a sabotage or negative test inject a deliberate
    mutation through the same evaluation path used for the positive case.

    Args:
        case: The gold case to grade.
        structure_path: Path to the controlled structure file case's
            provenance describes.
        cmd: The real PyMOL cmd module, with case's structure already
            loaded and no prior plan executed against it.
        inject_after_execution: An optional deliberate-mutation hook run
            after the plan executes, before non-target state capture.

    Returns:
        The complete VerifierResult for case.
    """
    try:
        plan = initial_fixture_plan()
        if plan.render_pml() != case.canonical_plan_pml:
            raise VerifierError(
                "canonical plan drifted from pmc_core's own rendering"
            )
        decision = evaluate_plan(plan)
        if not decision.allowed:
            raise VerifierError("policy denied the accepted fixture plan")

        actual_checksum = _sha256_of(structure_path)
        if actual_checksum != case.provenance.structure_sha256:
            raise VerifierError(
                "structure checksum mismatch: case.provenance names "
                f"{case.provenance.structure_sha256!r} but structure_path "
                f"{structure_path} actually hashes to {actual_checksum!r}"
            )

        before_non_target = {
            chain_id: _capture_colors(cmd, f"chain {chain_id}")
            for chain_id in case.non_target_chains
        }

        for operation in plan.operations:
            cmd.do(operation.render())
        cmd.sync()

        if inject_after_execution is not None:
            inject_after_execution(cmd)
            cmd.sync()

        after_non_target = {
            chain_id: _capture_colors(cmd, f"chain {chain_id}")
            for chain_id in case.non_target_chains
        }

        results: list[AssertionResult] = []
        for assertion in case.assertions:
            if assertion.kind == ASSERTION_KIND_CHAIN_MEMBERSHIP:
                results.append(
                    _evaluate_chain_membership(assertion, cmd, structure_path)
                )
            elif assertion.kind == ASSERTION_KIND_COLOR_STATE:
                results.append(_evaluate_color_state(assertion, cmd))
            elif assertion.kind == ASSERTION_KIND_NO_UNINTENDED_CHANGE:
                results.append(
                    _evaluate_no_unintended_change(
                        assertion, before_non_target, after_non_target
                    )
                )
            else:
                # Defense in depth: broadening the typed contract later must not silently bypass this evaluator, even though GoldCase/Assertion construction already rejects unsupported kinds.
                raise VerifierError(
                    f"unsupported assertion kind: {assertion.kind!r}"
                )
    except VerifierError as error:
        return VerifierResult(
            case_id=case.case_id,
            valid=False,
            invalid_reason=str(error),
            assertion_results=(),
            task_success=False,
        )
    except Exception as error:  # Real PyMOL evaluator errors must invalidate, never crash the suite.
        return VerifierResult(
            case_id=case.case_id,
            valid=False,
            invalid_reason=f"evaluator error: {error}",
            assertion_results=(),
            task_success=False,
        )

    return VerifierResult(
        case_id=case.case_id,
        valid=True,
        invalid_reason=None,
        assertion_results=tuple(results),
        task_success=all(result.passed for result in results),
    )
