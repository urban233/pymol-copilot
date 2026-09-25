# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for `pmc_agent.warnings.derive_warnings`."""

from __future__ import annotations

import pytest

from pmc_agent.warnings import derive_warnings
from pmc_core.executor import SelectionCount
from pmc_core.protocol import MAX_VALIDATION_WARNINGS
from pmc_core.protocol import MAX_VALIDATION_WARNING_BYTES


def test_no_warnings_for_an_unremarkable_plan() -> None:
    """A plan with ordinary, partial selections and no repairs is silent."""
    warnings = derive_warnings(
        selection_counts=(SelectionCount("copilot_selection", 5),),
        target_atom_count=20,
        repair_attempts=0,
        sidecar_warnings=(),
    )
    assert warnings == ()


def test_zero_match_selection_is_named() -> None:
    """A selection matching no atoms is reported by name."""
    warnings = derive_warnings(
        selection_counts=(SelectionCount("copilot_selection", 0),),
        target_atom_count=20,
        repair_attempts=0,
        sidecar_warnings=(),
    )
    assert warnings == ("selection copilot_selection matched 0 atoms",)


def test_full_match_selection_is_named() -> None:
    """A selection matching every atom of the target object is named."""
    warnings = derive_warnings(
        selection_counts=(SelectionCount("copilot_selection", 20),),
        target_atom_count=20,
        repair_attempts=0,
        sidecar_warnings=(),
    )
    assert warnings == (
        "selection copilot_selection matches every atom of the target object",
    )


def test_an_empty_target_object_is_reported_as_zero_match_only() -> None:
    """0 == 0 fires the zero-match template, never the full-match one too."""
    warnings = derive_warnings(
        selection_counts=(SelectionCount("copilot_selection", 0),),
        target_atom_count=0,
        repair_attempts=0,
        sidecar_warnings=(),
    )
    assert warnings == ("selection copilot_selection matched 0 atoms",)


def test_repair_attempts_use_singular_and_plural_forms() -> None:
    """One repair reads as singular; more than one reads as plural."""
    singular = derive_warnings(
        selection_counts=(),
        target_atom_count=20,
        repair_attempts=1,
        sidecar_warnings=(),
    )
    plural = derive_warnings(
        selection_counts=(),
        target_atom_count=20,
        repair_attempts=2,
        sidecar_warnings=(),
    )
    assert singular == (
        "this plan needed 1 repair attempt before it validated",
    )
    assert plural == ("this plan needed 2 repair attempts before it validated",)


def test_sidecar_warnings_are_prefixed_and_normalized() -> None:
    """Captured sidecar stderr is reported under a fixed prefix, normalized."""
    warnings = derive_warnings(
        selection_counts=(),
        target_atom_count=20,
        repair_attempts=0,
        sidecar_warnings=("Selector-Error: bad selection 'chain A'",),
    )
    assert len(warnings) == 1
    assert warnings[0].startswith("sidecar: ")
    # normalize_message lowercases and redacts quoted spans.
    assert "chain a" not in warnings[0]
    assert "<redacted>" in warnings[0] or "redacted" in warnings[0]


def test_warning_order_is_fixed() -> None:
    """Selections, then repair attempts, then sidecar warnings, in order."""
    warnings = derive_warnings(
        selection_counts=(
            SelectionCount("copilot_selection", 0),
            SelectionCount("other_selection", 20),
        ),
        target_atom_count=20,
        repair_attempts=1,
        sidecar_warnings=("boom",),
    )
    assert warnings == (
        "selection copilot_selection matched 0 atoms",
        "selection other_selection matches every atom of the target object",
        "this plan needed 1 repair attempt before it validated",
        "sidecar: boom",
    )


def test_output_is_capped_at_the_wire_limit() -> None:
    """No more than MAX_VALIDATION_WARNINGS strings are ever returned."""
    counts = tuple(
        SelectionCount(f"selection_{i}", 0)
        for i in range(MAX_VALIDATION_WARNINGS + 5)
    )
    warnings = derive_warnings(
        selection_counts=counts,
        target_atom_count=20,
        repair_attempts=2,
        sidecar_warnings=("boom",),
    )
    assert len(warnings) == MAX_VALIDATION_WARNINGS


@pytest.mark.parametrize(
    "sidecar_warnings",
    [("x" * 5000,), ("\x00\x01 control chars \x1b",), ("a" * 300,)],
)
def test_every_warning_stays_within_the_byte_bound(
    sidecar_warnings: tuple[str, ...],
) -> None:
    """No generated warning ever exceeds MAX_VALIDATION_WARNING_BYTES."""
    warnings = derive_warnings(
        selection_counts=(),
        target_atom_count=20,
        repair_attempts=0,
        sidecar_warnings=sidecar_warnings,
    )
    for warning in warnings:
        assert len(warning.encode("utf-8")) <= MAX_VALIDATION_WARNING_BYTES
        assert warning.isascii() and warning.isprintable()
