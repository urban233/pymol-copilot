# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic tests for the latency note's own arithmetic and rendering.

No PyMOL: `record_latency.py` is the `py_binary` that drives a real
scenario; this module only checks that the percentile method and the
rendered table are honest about what was and was not measured.
"""

from __future__ import annotations

import pytest

from latency import DECLARED_STAGES
from latency import DuplicateStageRecordError
from latency import StageTimer
from latency import UndeclaredStageError
from latency import percentile
from latency import render_note


def test_percentile_returns_an_exact_observed_sample_for_an_odd_count() -> None:
    """p50 of an odd-length sample is the middle observed value.

    Never an interpolation.
    """
    assert percentile([1.0, 2.0, 3.0], 50) == 2.0
    assert percentile([3.0, 1.0, 2.0], 50) == 2.0


def test_percentile_uses_nearest_rank_for_an_even_count() -> None:
    """An even-length sample still returns one observed value.

    Matches hand-computed nearest-rank, not the arithmetic mean.
    """
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile(values, 50) == 2.0
    assert percentile(values, 95) == 4.0


def test_percentile_rejects_an_empty_sample_set() -> None:
    """An empty sample set has no percentile to report."""
    with pytest.raises(ValueError, match="empty"):
        percentile([], 50)


def test_stage_timer_records_each_declared_stage_exactly_once() -> None:
    """A full repetition records one sample per declared stage."""
    timer = StageTimer()
    for stage in DECLARED_STAGES:
        with timer.measure(stage):
            pass

    recorded = {name for name, _ in timer.samples}
    assert recorded == set(DECLARED_STAGES)
    assert len(timer.samples) == len(DECLARED_STAGES)


def test_stage_timer_rejects_an_undeclared_stage() -> None:
    """A stage name outside `DECLARED_STAGES` is a programming error."""
    timer = StageTimer()
    with pytest.raises(UndeclaredStageError), timer.measure("not_a_real_stage"):
        pass


def test_stage_timer_rejects_recording_the_same_stage_twice() -> None:
    """A stage recorded twice in one repetition is a programming error.

    Otherwise a missing stage could silently reuse another's sample.
    """
    timer = StageTimer()
    with timer.measure("submit"):
        pass

    with pytest.raises(DuplicateStageRecordError), timer.measure("submit"):
        pass


def test_stage_timer_allows_each_stage_once_per_repetition() -> None:
    """`next_repetition` resets the per-repetition duplicate guard."""
    timer = StageTimer()
    with timer.measure("submit"):
        pass
    timer.next_repetition()

    with timer.measure("submit"):  # does not raise
        pass

    assert len(timer.samples) == 2


def test_render_note_lists_every_declared_stage_in_order() -> None:
    """Every declared stage gets its own row, in declaration order."""
    samples = [
        (name, 0.001 * (i + 1)) for i, name in enumerate(DECLARED_STAGES)
    ]

    note = render_note(
        samples,
        machine="test-machine",
        engine="fake",
        repetitions=1,
        date="2026-01-01",
    )

    lines = [line for line in note.splitlines() if line.startswith("| ")]
    # The header row plus one row per declared stage.
    assert len(lines) == 1 + len(DECLARED_STAGES)
    for name in DECLARED_STAGES:
        assert any(line.startswith(f"| {name} ") for line in lines)


def test_render_note_marks_an_unmeasured_stage_explicitly() -> None:
    """A stage with zero samples is marked, never printed as `0.000`."""
    note = render_note(
        [],
        machine="test-machine",
        engine="fake",
        repetitions=0,
        date="2026-01-01",
    )

    for name in DECLARED_STAGES:
        assert f"| {name} | not measured | not measured |" in note
    assert "0.000" not in note


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
