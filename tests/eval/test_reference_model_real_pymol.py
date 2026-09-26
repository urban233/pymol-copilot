# Copyright 2026 PyMOL Copilot contributors.
"""The grader, against real PyMOL: a right answer passes, a wrong one fails.

Each gold sample's own reference plan is scripted as the model's answer
and run through the whole harness -- the request graph, a fresh
`pmc_sidecar.child` per attempt, and the grader -- so the one claim a
baseline number rests on is proved against real executions: a model
that answers correctly scores every sample, and a model that answers
wrongly does not. Deliberately wrong answers are drawn from each kind
the grader must catch.

Selection names and the orient view are the two things real PyMOL
produces that a constructed report cannot stand in for, and both are
exercised here. The four `orient` samples whose view differs across
operating systems (`tests/data/test_gold_set_real_pymol.py`) are graded
on selection counts only, so they pass everywhere.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import re
from collections.abc import Sequence

import pytest

from fakes import completion
from pmc_agent.inference.fake import FakeEngine
from pmc_core.executor import execute
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import ASSERTION_SELECTION_COUNTS
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_eval.metrics import category_parts
from pmc_eval.record import OUTCOME_EXECUTED_WRONG
from pmc_eval.record import OUTCOME_SUCCESS
from pmc_eval.record import InfraFailure
from pmc_eval.record import SampleRecord
from pmc_eval.runner import CONDITION_NO_GRAMMAR
from pmc_eval.runner import Condition
from pmc_eval.runner import run_sample

SAMPLES = read_samples(DEFAULT_GOLD_SAMPLES_PATH)

CONDITION = Condition(
    name=CONDITION_NO_GRAMMAR,
    grammar=False,
    max_tokens=256,
    deadline_seconds=600.0,
)


def _answer(sample: Sample, text: str) -> SampleRecord:
    """Evaluate one scripted answer through the real sidecar.

    Args:
        sample: The gold sample.
        text: The model's scripted completion.

    Returns:
        The sample's record.
    """
    result = run_sample(
        sample,
        engine=FakeEngine([completion(text)]),
        condition=CONDITION,
        executor=execute,
    )
    assert not isinstance(result, InfraFailure), result
    return result


def _first_per(key: str, samples: list[Sample]) -> list[Sample]:
    """Pick the first sample of each distinct value of one property.

    Args:
        key: `"spec"` or `"verb_set"`.
        samples: The candidates.

    Returns:
        One sample per distinct value, in the order first seen.
    """
    seen: dict[str, Sample] = {}
    for sample in samples:
        value = (
            sample.structure.spec_id
            if key == "spec"
            else category_parts(sample.category)[0]
        )
        seen.setdefault(value, sample)
    return list(seen.values())


def _ids(samples: Sequence[Sample]) -> list[str]:
    """Name parametrized cases after their samples.

    Args:
        samples: The samples.

    Returns:
        Their ids.
    """
    return [sample.sample_id for sample in samples]


@pytest.mark.parametrize("sample", SAMPLES, ids=_ids(SAMPLES))
def test_the_reference_plan_scores_a_success(sample: Sample) -> None:
    """A model answering with the reference plan scores every gold sample.

    Args:
        sample: The gold sample.
    """
    record = _answer(sample, sample.plan_pml)

    assert record.final_outcome == OUTCOME_SUCCESS, record.assertions
    assert len(record.attempts) == 1


NEWLINE_CASES = _first_per("spec", list(SAMPLES))


@pytest.mark.parametrize("sample", NEWLINE_CASES, ids=_ids(NEWLINE_CASES))
def test_a_plan_missing_its_final_newline_still_scores(sample: Sample) -> None:
    """The harness's normalization lets a chat-style answer through.

    Args:
        sample: The gold sample.
    """
    record = _answer(sample, sample.plan_pml.rstrip("\n"))

    assert record.final_outcome == OUTCOME_SUCCESS
    assert record.attempts[0].newline_appended


COLOR_CASES = _first_per(
    "verb_set", [s for s in SAMPLES if "color " in s.plan_pml]
)


@pytest.mark.parametrize("sample", COLOR_CASES, ids=_ids(COLOR_CASES))
def test_a_wrong_colour_is_executed_wrong(sample: Sample) -> None:
    """A plan that runs cleanly but colours with another colour fails.

    Args:
        sample: The gold sample.
    """
    wrong = re.sub(
        r"^color (\w+),",
        lambda m: "color " + ("blue" if m.group(1) != "blue" else "red") + ",",
        sample.plan_pml,
        flags=re.MULTILINE,
    )
    assert wrong != sample.plan_pml

    record = _answer(sample, wrong)

    assert record.final_outcome == OUTCOME_EXECUTED_WRONG


COUNTED_CASES = _first_per(
    "verb_set",
    [
        s
        for s in SAMPLES
        if any(a.kind == ASSERTION_SELECTION_COUNTS for a in s.assertions)
    ],
)


@pytest.mark.parametrize("sample", COUNTED_CASES, ids=_ids(COUNTED_CASES))
def test_an_extra_selection_is_executed_wrong(sample: Sample) -> None:
    """A selection the reference does not make changes the counts.

    Args:
        sample: The gold sample.
    """
    record = _answer(sample, sample.plan_pml + "select copilot_extra, hetatm\n")

    assert record.final_outcome == OUTCOME_EXECUTED_WRONG


ORIENT_CASES = [s for s in SAMPLES if s.category.startswith("orient+")]


@pytest.mark.parametrize("sample", ORIENT_CASES, ids=_ids(ORIENT_CASES))
def test_a_dropped_orient_passes_but_is_flagged_incomplete(
    sample: Sample,
) -> None:
    """Counts-only grading cannot see a missing camera move, and says so.

    Args:
        sample: A gold `orient+select` sample.
    """
    without_orient = "".join(
        line + "\n"
        for line in sample.plan_pml.splitlines()
        if not line.startswith("orient ")
    )
    assert without_orient != sample.plan_pml

    record = _answer(sample, without_orient)

    assert record.final_outcome == OUTCOME_SUCCESS
    assert not record.grading_complete


def test_the_sabotage_cases_are_not_empty() -> None:
    """Every kind of wrong answer is actually exercised."""
    assert len(NEWLINE_CASES) == 6
    assert len(COLOR_CASES) >= 3
    assert len(COUNTED_CASES) >= 3
    assert len(ORIENT_CASES) == 6


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
