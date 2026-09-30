# Copyright 2026 PyMOL Copilot contributors.
"""The integrated measurement grades, reads and explains correctly.

docs/master_plan.md item 19. Hermetic: no PyMOL and no server. The live
grader must grade exactly as the offline grader does when given the
same readings; the console reader must find the plan and the apply
outcome in what the client prints; and every sample whose integrated
outcome differs from its offline one must get the explanation its
evidence decides.
"""

from __future__ import annotations

from typing import Any

import pytest

from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import ASSERTION_SELECTION_COUNTS
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_eval.integrated import GAP_APPLY_FAILED
from pmc_eval.integrated import GAP_APPLY_VS_SIDECAR
from pmc_eval.integrated import GAP_ENGINE_DRIFT
from pmc_eval.integrated import GAP_FIDELITY
from pmc_eval.integrated import GAP_INTENT_TRANSPORT
from pmc_eval.integrated import GAP_PROMPT_SKEW
from pmc_eval.integrated import GAP_TIMEOUT
from pmc_eval.integrated import GAP_VALIDATION_DRIFT
from pmc_eval.integrated import OUTCOME_APPLIED
from pmc_eval.integrated import OUTCOME_APPLY_REFUSED
from pmc_eval.integrated import OUTCOME_APPLY_RESTORED
from pmc_eval.integrated import OUTCOME_NO_PLAN
from pmc_eval.integrated import OUTCOME_NOT_APPLICABLE
from pmc_eval.integrated import OUTCOME_TIMEOUT
from pmc_eval.integrated import IntegratedRecord
from pmc_eval.integrated import compare_condition
from pmc_eval.integrated import explain
from pmc_eval.integrated import grade_live
from pmc_eval.integrated import previewed_commands
from pmc_eval.integrated import read_apply
from pmc_eval.integrated import read_preview
from pmc_eval.integrated import render_report
from pmc_eval.integrated import selection_names
from pmc_eval.prompt import snapshot_for

SAMPLES = read_samples(DEFAULT_GOLD_SAMPLES_PATH)


def _plan(sample: Sample) -> ActionPlan:
    """Parse a sample's gold plan.

    Args:
        sample: The sample.

    Returns:
        Its plan.
    """
    plan = parse_pml(sample.plan_pml)
    assert isinstance(plan, ActionPlan)
    return plan


def _recorded_counts(sample: Sample) -> tuple[tuple[str, int], ...]:
    """Read the counts the gold plan's own verification recorded.

    Args:
        sample: The sample.

    Returns:
        `(name, atom count)` pairs.
    """
    return tuple(
        (name, count) for name, count in sample.verification.selection_counts
    )


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.sample_id)
def test_the_gold_plans_own_readings_grade_as_a_success(
    sample: Sample,
) -> None:
    """Given what the gold plan's verification saw, every sample passes."""
    graded = grade_live(
        sample,
        _plan(sample),
        snapshot_for(sample),
        fingerprint=sample.verification.resulting_fingerprint or "",
        selection_counts=_recorded_counts(sample),
    )

    assert graded.task_success


def _with(kind: str) -> Sample:
    """Find a gold sample that carries one assertion kind.

    Args:
        kind: The assertion kind.

    Returns:
        The first such sample.
    """
    return next(s for s in SAMPLES if any(a.kind == kind for a in s.assertions))


def test_another_resulting_state_fails() -> None:
    """A live state other than the recorded one is not a success."""
    sample = _with(ASSERTION_RESULTING_SNAPSHOT)

    graded = grade_live(
        sample,
        _plan(sample),
        snapshot_for(sample),
        fingerprint="sha256:" + "0" * 64,
        selection_counts=_recorded_counts(sample),
    )

    assert not graded.task_success
    failed = [a.kind for a in graded.assertions if not a.passed]
    assert failed == [ASSERTION_RESULTING_SNAPSHOT]


def test_a_count_off_by_one_fails() -> None:
    """A selection one atom larger than recorded is not a success."""
    sample = _with(ASSERTION_SELECTION_COUNTS)
    counts = list(_recorded_counts(sample))
    name, count = counts[0]
    counts[0] = (name, count + 1)

    graded = grade_live(
        sample,
        _plan(sample),
        snapshot_for(sample),
        fingerprint=sample.verification.resulting_fingerprint or "",
        selection_counts=counts,
    )

    assert not graded.task_success
    failed = [a.kind for a in graded.assertions if not a.passed]
    assert failed == [ASSERTION_SELECTION_COUNTS]


def test_selection_names_are_the_ones_the_sidecar_counts() -> None:
    """Created and referenced names, once each, in order."""
    plan = parse_pml(
        "select copilot_a, chain A\n"
        "select copilot_b, chain B\n"
        "color red, copilot_a\n"
        "show sticks, copilot_b\n"
        "orient copilot_a\n"
    )
    assert isinstance(plan, ActionPlan)

    assert selection_names(plan) == ("copilot_a", "copilot_b")


_PREVIEW = (
    "copilot plan p-ec25a4fa (expires 2026-09-29T20:57:50.648Z, in 5 min)",
    "  object:    pmc_structure (36 atoms, 1 state)",
    "  commands:",
    "    1 | select copilot_sel0244, name ZN   -> 2 atoms",
    "  apply:     copilot_apply p-ec25a4fa",
    "  reject:    copilot_reject p-ec25a4fa",
)


def test_a_preview_names_its_plan_and_is_approvable() -> None:
    """The plan identifier is the one `copilot_apply` takes."""
    preview = read_preview(["PyMOL>copilot x", "\n".join(_PREVIEW)])

    assert preview.plan_id == "p-ec25a4fa"
    assert preview.applicable


def test_the_previewed_commands_are_read_without_their_counts() -> None:
    """The numbered commands, exactly as the plan renders them."""
    assert previewed_commands(["\n".join(_PREVIEW)]) == (
        "select copilot_sel0244, name ZN",
    )


def test_latency_percentiles_are_nearest_rank() -> None:
    """p50 of 1..5 s is the 3rd value, p90 the 5th."""
    offline = {
        f"gold_00{i}": {**_OFFLINE, "sample_id": f"gold_00{i}"}
        for i in range(1, 6)
    }
    records = [
        _record(sample_id=f"gold_00{i}", task_success=True, preview_seconds=i)
        for i in range(1, 6)
    ]

    latency = compare_condition(records, offline)["latency_seconds"]

    assert (latency["preview_p50"], latency["preview_p90"]) == (3, 5)


def test_an_inspectable_only_preview_is_not_approvable() -> None:
    """A preview whose apply line is unavailable cannot be applied."""
    lines = [
        line.replace(
            "apply:     copilot_apply p-ec25a4fa",
            "apply:     unavailable (inspectable only)",
        )
        for line in _PREVIEW
    ]

    preview = read_preview(lines)

    assert preview.plan_id == "p-ec25a4fa"
    assert not preview.applicable


def test_a_failure_line_is_no_plan() -> None:
    """A bounded failure line carries no plan."""
    preview = read_preview(["copilot: which chain?. Rephrase and retry."])

    assert preview.plan_id is None


@pytest.mark.parametrize(
    ("line", "outcome"),
    [
        (
            "copilot_apply: plan p-1 applied. Recovery point retained at x.",
            OUTCOME_APPLIED,
        ),
        (
            "copilot_apply: plan p-1 failed and the complete session was "
            "restored cleanly.",
            OUTCOME_APPLY_RESTORED,
        ),
        (
            "copilot_apply: the session changed. Nothing was applied.",
            OUTCOME_APPLY_REFUSED,
        ),
        (
            "copilot_apply: plan p-12 applied. Recovery point retained at x.",
            OUTCOME_APPLY_REFUSED,
        ),
    ],
)
def test_the_apply_outcome_is_read_for_this_plan(
    line: str, outcome: str
) -> None:
    """Only this plan's own apply line counts."""
    assert read_apply([line], "p-1") == outcome


def _record(**changes: Any) -> IntegratedRecord:
    """Build an integrated record, applied and wrong unless changed.

    Args:
        **changes: Fields to set.

    Returns:
        The record.
    """
    values: dict[str, Any] = {
        "sample_id": "gold_001",
        "condition": "grammar",
        "category": "color/resn/single",
        "spec_id": "two_chains_hetatm",
        "outcome": OUTCOME_APPLIED,
        "task_success": False,
        "assertions": (),
        "live_snapshot_sha256": "a" * 64,
        "prompt_skew": False,
        "attempts": (
            {"prompt_sha256": "p1", "outcome": "completion", "text": "x\n"},
        ),
        "plan_pml": "x\n",
        "live_fingerprint": None,
        "live_selection_counts": (),
        "output": (),
        "preview_seconds": 1.0,
        "apply_seconds": 1.0,
    }
    values.update(changes)
    return IntegratedRecord(**values)


_OFFLINE = {
    "sample_id": "gold_001",
    "task_success": True,
    "final_outcome": "success",
    "attempts": [{"prompt_sha256": "p1", "completion": "x\n"}],
}


@pytest.mark.parametrize(
    ("changes", "gap"),
    [
        ({"prompt_skew": True}, GAP_PROMPT_SKEW),
        ({"outcome": OUTCOME_TIMEOUT}, GAP_TIMEOUT),
        (
            {"attempts": ({"prompt_sha256": "p2", "text": "x\n"},)},
            GAP_INTENT_TRANSPORT,
        ),
        (
            {"attempts": ({"prompt_sha256": "p1", "text": "y\n"},)},
            GAP_ENGINE_DRIFT,
        ),
        (
            {
                "attempts": (
                    {"prompt_sha256": "p1", "text": "x\n"},
                    {"prompt_sha256": "p3", "text": "x\n"},
                )
            },
            GAP_VALIDATION_DRIFT,
        ),
        ({"outcome": OUTCOME_NOT_APPLICABLE}, GAP_FIDELITY),
        ({"outcome": OUTCOME_APPLY_RESTORED}, GAP_APPLY_FAILED),
        ({}, GAP_APPLY_VS_SIDECAR),
        # The runtime appends the final newline the offline harness did.
        (
            {"attempts": ({"prompt_sha256": "p1", "text": "x"},)},
            GAP_APPLY_VS_SIDECAR,
        ),
    ],
)
def test_each_gap_is_explained_by_where_the_runs_part(
    changes: dict[str, Any], gap: str
) -> None:
    """The first difference along the request's path is the explanation."""
    assert explain(_record(**changes), _OFFLINE) == gap


def test_the_comparison_pairs_by_sample() -> None:
    """Each run's TaskSuccess, the discordant pairs and McNemar."""
    offline = {
        "gold_001": {**_OFFLINE, "sample_id": "gold_001"},
        "gold_002": {**_OFFLINE, "sample_id": "gold_002"},
        "gold_003": {
            **_OFFLINE,
            "sample_id": "gold_003",
            "task_success": False,
            "final_outcome": "executed_wrong",
        },
    }
    records = [
        _record(sample_id="gold_001", task_success=True),
        _record(sample_id="gold_002", outcome=OUTCOME_NO_PLAN),
        _record(
            sample_id="gold_003",
            task_success=True,
            category="color/chain/single",
        ),
    ]

    block = compare_condition(records, offline)

    assert block["offline"]["k"] == 2
    assert block["integrated"]["k"] == 2
    assert (block["only_offline"], block["only_integrated"]) == (1, 1)
    assert block["mcnemar_exact_p"] == 1.0
    assert [row["sample_id"] for row in block["discordant"]] == [
        "gold_002",
        "gold_003",
    ]
    assert block["outcomes"][OUTCOME_NO_PLAN] == 1
    assert block["breakouts"]["shape"]["single"] == {
        "n": 3,
        "integrated": 2,
        "offline": 2,
    }
    page = render_report({"grammar": block}, title="t")
    assert "| gold_002 | True | False | no_plan |" in page


def test_the_comparison_refuses_different_samples() -> None:
    """Two runs over different samples are not paired."""
    with pytest.raises(ValueError, match="different samples"):
        compare_condition([_record()], {})


def test_a_record_round_trips() -> None:
    """What `to_dict` writes, `from_dict` reads back unchanged."""
    record = _record(live_selection_counts=(("copilot_a", 3),))

    assert IntegratedRecord.from_dict(record.to_dict()) == record


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
