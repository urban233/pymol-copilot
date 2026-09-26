# Copyright 2026 PyMOL Copilot contributors.
"""Direct behavior tests for `pmc_client.command`'s preview rendering.

The rest of `pmc_client.command`'s own test suite
(`tests/integration/test_command.py`) is deliberately black-box: it drives
`CopilotCommandClient.copilot()` through fakes and reads the printed
console lines back through `preview_support`, the way a real caller would.
This module is the one exception, testing the pure rendering helpers
(`_preview_block`, `_fidelity_line`, `_checked_lines`, `_relative_expiry`)
directly with synthetic typed inputs -- specifically because a mismatch
count past ten, or an expiry a fixed number of minutes away, is much
easier to construct directly than to manufacture through a fake PyMOL
session limited to one atom.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest

from pmc_client.command import _checked_lines
from pmc_client.command import _fidelity_line
from pmc_client.command import _preview_block
from pmc_client.command import _relative_expiry
from pmc_client.fidelity import FidelityOutcome
from pmc_core.executor import REASON_OK
from pmc_core.executor import REASON_TIMEOUT
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import NamedSelection
from pmc_core.plan import SelectionExpression
from pmc_core.plan import SelectOperation
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import FIDELITY_UNAVAILABLE
from pmc_core.protocol import MAX_FIDELITY_MISMATCHES
from pmc_core.protocol import SelectionCountV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1

_NOW = datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC)
_PLAN = ActionPlan(
    operations=(
        SelectOperation(
            selection_name="copilot_selection",
            expression=SelectionExpression(
                clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
            ),
        ),
        ColorOperation(color="red", target=NamedSelection("copilot_selection")),
    )
)


def _response(
    *,
    expires_at: str = "2026-09-24T12:05:00.000Z",
    selection_counts: tuple[SelectionCountV1, ...] = (),
    warnings: tuple[str, ...] = (),
    repair_attempts: int = 0,
) -> ValidatedPlanResponseV1:
    """Build a validated response fixture with the given plan-facing values.

    Args:
        expires_at: The plan's own RFC3339 UTC expiry.
        selection_counts: The sidecar's own per-selection atom counts.
        warnings: Bounded, deterministic validation warnings.
        repair_attempts: How many repairs the plan needed before validating.

    Returns:
        A validated response `_preview_block` accepts.
    """
    return ValidatedPlanResponseV1(
        request_id="11111111-1111-4111-8111-111111111111",
        session_id="22222222-2222-4222-8222-222222222222",
        received_at="2026-09-24T12:00:00.000Z",
        validated_at="2026-09-24T12:00:00.000Z",
        action_plan=_PLAN,
        validation=ValidationReportV1(
            status="passed",
            snapshot_digest="sha256:test",
            applicable=True,
            warnings=warnings,
            selection_counts=selection_counts,
            repair_attempts=repair_attempts,
        ),
        plan_id="33333333-3333-4333-8333-333333333333",
        snapshot_digest="sha256:test",
        expires_at=expires_at,
        model_identity="test-model@test-checkpoint",
        target_object="1abc",
    )


def _exact_outcome() -> FidelityOutcome:
    """Build an exact fidelity outcome.

    Returns:
        A `FidelityOutcome` with no mismatches.
    """
    return FidelityOutcome(
        status=FIDELITY_EXACT,
        reason=REASON_OK,
        mismatches=(),
        live_digest="sha256:live",
        reconstructed_digest="sha256:live",
    )


def test_preview_names_every_section_specification_requires() -> None:
    """Every section SPECIFICATION.md:503-511 names appears, every time."""
    response = _response(
        selection_counts=(SelectionCountV1("copilot_selection", 1020),)
    )

    block = _preview_block(
        response,
        _exact_outcome(),
        object_name="1abc",
        atom_count=2041,
        state_count=1,
        applicable=True,
        now=_NOW,
    )

    assert block.startswith("copilot plan p-33333333")
    assert "expires 2026-09-24T12:05:00.000Z" in block
    assert "1abc" in block
    assert "2,041" in block
    assert "1 | select copilot_selection, chain A" in block
    assert "1,020" in block
    assert "2 | color red, copilot_selection" in block
    assert "warnings:  none" in block
    assert "fidelity:  exact" in block
    assert "checked:" in block
    assert "NOT checked:" in block
    assert "copilot_apply p-33333333" in block
    assert "copilot_reject p-33333333" in block


def test_selection_count_is_attached_only_to_its_own_select_line() -> None:
    """A color command's line carries no selection count of its own."""
    response = _response(
        selection_counts=(SelectionCountV1("copilot_selection", 7),)
    )

    block = _preview_block(
        response,
        _exact_outcome(),
        object_name="1abc",
        atom_count=20,
        state_count=1,
        applicable=True,
        now=_NOW,
    )
    lines = block.splitlines()
    select_line = next(
        line for line in lines if "select copilot_selection" in line
    )
    color_line = next(line for line in lines if "color red" in line)

    assert "-> 7 atoms" in select_line
    assert "->" not in color_line


def test_a_plan_cannot_define_the_same_selection_name_twice() -> None:
    """`_preview_block`'s per-name count lookup relies on this invariant.

    `response.validation.selection_counts` carries one post-execution
    count per selection *name*, matched against `SelectOperation
    .selection_name` in `_preview_block`'s own per-command loop. That
    lookup is only ever unambiguous because `ActionPlan.__post_init__`
    already refuses to construct a plan that defines the same name
    twice, for every plan this system ever builds -- parsed from model
    output, repaired, or decoded off the wire, all through the same
    `pmc_core.parser` functions that end in this same constructor. This
    proves the invariant directly, so `_preview_block` itself never
    needs its own defense against a plan shape the type system already
    forbids.
    """
    with pytest.raises(ValueError, match="defined twice"):
        ActionPlan(
            operations=(
                SelectOperation(
                    selection_name="copilot_s",
                    expression=SelectionExpression(
                        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
                    ),
                ),
                SelectOperation(
                    selection_name="copilot_s",
                    expression=SelectionExpression(
                        clauses=(AndClause(factors=(Factor(ChainTerm("B")),)),)
                    ),
                ),
            )
        )


def test_non_empty_warnings_are_each_listed() -> None:
    """Every derived warning is printed, not summarized away."""
    response = _response(
        warnings=(
            "selection copilot_selection matched 0 atoms",
            "this plan needed 1 repair attempt before it validated",
        )
    )

    block = _preview_block(
        response,
        _exact_outcome(),
        object_name="1abc",
        atom_count=20,
        state_count=1,
        applicable=True,
        now=_NOW,
    )

    assert "selection copilot_selection matched 0 atoms" in block
    assert "this plan needed 1 repair attempt before it validated" in block
    assert "warnings:  none" not in block


def test_not_applicable_never_offers_the_apply_command() -> None:
    """A non-applicable plan still offers reject, never apply."""
    block = _preview_block(
        _response(),
        _exact_outcome(),
        object_name="1abc",
        atom_count=20,
        state_count=1,
        applicable=False,
        now=_NOW,
    )

    assert "apply:     unavailable (inspectable only)" in block
    assert "copilot_apply p-" not in block
    assert "copilot_reject p-33333333" in block


def test_checked_lines_never_claim_a_non_exact_plan_was_not_run() -> None:
    """The known bug this item fixes: a non-exact plan really did run."""
    not_exact = FidelityOutcome(
        status=FIDELITY_NOT_EXACT,
        reason="fidelity_mismatch",
        mismatches=("field x differs",),
        live_digest="sha256:live",
        reconstructed_digest="sha256:reconstructed",
    )

    lines = "\n".join(_checked_lines(not_exact))

    assert "never executed" not in lines
    assert "ran in a fresh PyMOL sidecar" in lines
    assert "cannot be applied" in lines


def test_checked_lines_for_unavailable_fidelity_name_the_reason() -> None:
    """An unavailable check names why, without claiming the plan never ran."""
    unavailable = FidelityOutcome(
        status=FIDELITY_UNAVAILABLE,
        reason=REASON_TIMEOUT,
        mismatches=(),
        live_digest="sha256:live",
        reconstructed_digest=None,
    )

    lines = "\n".join(_checked_lines(unavailable))

    assert "never executed" not in lines
    assert REASON_TIMEOUT in lines


def test_more_than_ten_mismatches_are_truncated_with_a_remaining_count() -> (
    None
):
    """More than MAX_FIDELITY_MISMATCHES mismatches show ten, then a count."""
    mismatches = tuple(f"mismatch {index}" for index in range(25))
    outcome = FidelityOutcome(
        status=FIDELITY_NOT_EXACT,
        reason="fidelity_mismatch",
        mismatches=mismatches,
        live_digest="sha256:live",
        reconstructed_digest="sha256:reconstructed",
    )

    line = _fidelity_line(outcome)

    for index in range(MAX_FIDELITY_MISMATCHES):
        assert f"mismatch {index}" in line
    assert f"mismatch {MAX_FIDELITY_MISMATCHES}" not in line
    assert f"... and {25 - MAX_FIDELITY_MISMATCHES} more" in line


def test_ten_or_fewer_mismatches_are_shown_in_full_with_no_remaining_count() -> (
    None
):
    """Exactly MAX_FIDELITY_MISMATCHES mismatches need no truncation note."""
    mismatches = tuple(
        f"mismatch {index}" for index in range(MAX_FIDELITY_MISMATCHES)
    )
    outcome = FidelityOutcome(
        status=FIDELITY_NOT_EXACT,
        reason="fidelity_mismatch",
        mismatches=mismatches,
        live_digest="sha256:live",
        reconstructed_digest="sha256:reconstructed",
    )

    line = _fidelity_line(outcome)

    assert "more" not in line


@pytest.mark.parametrize(
    ("delta_seconds", "expected"),
    [
        (300, "in 5 min"),
        (60, "in 1 min"),
        (30, "in under a minute"),
        (0, "already expired"),
        (-60, "already expired"),
    ],
)
def test_relative_expiry_reads_naturally(
    delta_seconds: int, expected: str
) -> None:
    """The relative expiry reads as a human would expect, at each boundary."""
    expires_at = (
        (_NOW + timedelta(seconds=delta_seconds))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

    assert _relative_expiry(expires_at, _NOW) == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
