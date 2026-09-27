# Copyright 2026 PyMOL Copilot contributors.
"""The p50-per-stage record docs/master_plan.md item 12 asks for.

SPECIFICATION.md:157: "Report p50 stage latency; no fixed pass/fail
budget." This module holds the arithmetic and the note-rendering, kept
PyMOL-free so it is checked hermetically and cheaply
(`tests/e2e/test_latency.py`) on every CI run; `record_latency.py` is the
`py_binary` that actually drives a real scenario and writes a real
measurement with it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from time import perf_counter
from typing import Iterator

#: The stages this item's own brief asks to be timed, in the order the
#: rendered table lists them. `StageTimer` treats this as the complete,
#: closed set: an undeclared stage, a stage recorded twice, or a declared
#: stage never recorded are each a programming error in the harness, not
#: a silently missing row in the note.
#: Repetitions `record_latency.py` runs by default: an odd count makes
#: p50 an exact observed sample, and the first repetition (PyMOL's own
#: import and page-cache warm-up) is discarded, leaving an even ten.
DEFAULT_REPETITIONS = 11

DECLARED_STAGES: tuple[str, ...] = (
    "fidelity_probe",
    "submit",
    "preview_client_local",
    "approval_reverify",
    "apply_round_trip",
    "recovery_save",
    "live_dispatch",
    "restore_and_compare",
    "outcome_report",
    "generate",
)


class UndeclaredStageError(ValueError):
    """Raised when a stage name is not one of `DECLARED_STAGES`."""


class DuplicateStageRecordError(ValueError):
    """Raised when one repetition records the same stage twice."""


@dataclass
class StageTimer:
    """Collects one sample per declared stage, once per repetition.

    Attributes:
        samples: Every recorded `(stage, seconds)` pair, across every
            repetition `measure` has been used in.
    """

    samples: list[tuple[str, float]] = field(default_factory=list)
    _seen_this_repetition: set[str] = field(default_factory=set)

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        """Time one stage for the current repetition.

        Args:
            stage: The stage name; must be one of `DECLARED_STAGES`.

        Yields:
            Nothing; the block being timed runs here.

        Raises:
            UndeclaredStageError: If `stage` is not declared.
            DuplicateStageRecordError: If `stage` was already recorded
                since the last call to `next_repetition`.
        """
        if stage not in DECLARED_STAGES:
            raise UndeclaredStageError(stage)
        if stage in self._seen_this_repetition:
            raise DuplicateStageRecordError(stage)
        started = perf_counter()
        try:
            yield
        finally:
            self.samples.append((stage, perf_counter() - started))
            self._seen_this_repetition.add(stage)

    def record(self, stage: str, seconds: float) -> None:
        """Record a directly computed sample, not timed by `measure`.

        Used for a stage this harness derives arithmetically (a whole
        console invocation's own elapsed time, minus the instrumented
        sub-stages within it) rather than measures directly, per this
        item's own decision not to thread a timer through production
        code to isolate it precisely.

        Args:
            stage: The stage name; must be one of `DECLARED_STAGES`.
            seconds: The computed elapsed seconds to record.

        Raises:
            UndeclaredStageError: If `stage` is not declared.
            DuplicateStageRecordError: If `stage` was already recorded
                since the last call to `next_repetition`.
        """
        if stage not in DECLARED_STAGES:
            raise UndeclaredStageError(stage)
        if stage in self._seen_this_repetition:
            raise DuplicateStageRecordError(stage)
        self.samples.append((stage, seconds))
        self._seen_this_repetition.add(stage)

    def next_repetition(self) -> None:
        """Start a fresh repetition: every stage may be recorded once more."""
        self._seen_this_repetition = set()

    def mark_not_measured(self, stage: str) -> None:
        """Record that a declared stage was deliberately not measured.

        Args:
            stage: The stage name; must be one of `DECLARED_STAGES`.

        Raises:
            UndeclaredStageError: If `stage` is not declared.
        """
        if stage not in DECLARED_STAGES:
            raise UndeclaredStageError(stage)
        self._seen_this_repetition.add(stage)


def percentile(values: Sequence[float], q: float) -> float:
    """Compute a percentile by the nearest-rank method.

    Deliberately not `statistics.median`/`quantiles`, which interpolate
    between two samples: a p50 that is not one of the actual observed
    samples is a value nothing ever measured.

    Args:
        values: The samples, in any order.
        q: The percentile to compute, in `[0, 100]`.

    Returns:
        The observed sample at that rank.

    Raises:
        ValueError: If `values` is empty.
    """
    if not values:
        raise ValueError("percentile of an empty sample set is undefined")
    ordered = sorted(values)
    # Nearest-rank is ceil(q/100 * n), not round(): round() rounds a half
    # to even (Python 3's own banker's rounding), which silently returns
    # the wrong sample whenever q/100 * n lands on a half-integer --
    # percentile([1, 2, 3, 4, 5], 50) must be 3 (the true median), but
    # round(2.5) is 2, one rank too low.
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def render_note(
    samples: Sequence[tuple[str, float]],
    *,
    machine: str,
    engine: str,
    repetitions: int,
    date: str,
) -> str:
    """Render the tracked per-machine latency note.

    Args:
        samples: Every `(stage, seconds)` pair recorded, across every
            repetition. A stage recorded zero times is rendered as "not
            measured" rather than a fabricated `0.000`.
        machine: A short description of this machine (OS, CPU, Python,
            PyMOL versions).
        engine: The engine used for this run (a scripted engine, or the
            real Lemonade base URL).
        repetitions: How many repetitions were run (the first, warm-up
            repetition is not included in `samples`).
        date: The date this run was recorded, ISO 8601.

    Returns:
        The complete markdown section for this machine.
    """
    by_stage: dict[str, list[float]] = {name: [] for name in DECLARED_STAGES}
    for name, seconds in samples:
        by_stage[name].append(seconds)

    lines = [
        f"### {machine}",
        "",
        f"Engine: {engine} · Repetitions: {repetitions} · Date: {date}",
        "",
        "| Stage | p50 (ms) | p95 (ms) |",
        "|---|---|---|",
    ]
    for name in DECLARED_STAGES:
        values = by_stage[name]
        if not values:
            lines.append(f"| {name} | not measured | not measured |")
            continue
        p50 = percentile(values, 50) * 1000
        p95 = percentile(values, 95) * 1000
        lines.append(f"| {name} | {p50:.3f} | {p95:.3f} |")
    lines.append("")
    return "\n".join(lines)
