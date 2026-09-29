# Copyright 2026 PyMOL Copilot contributors.
"""The Linux corpus regeneration's report is consistent and correctly made.

`docs/dataset/linux-regeneration/report.json` is the per-category
record of 4,000 oracle-versus-PyMOL differential checks, which the
notebook reports as the oracle's conformance evidence (master plan item
18). It must follow from the committed generation config, and its
totals must be the sum of its categories.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPORT = json.loads(
    (
        ROOT / "docs" / "dataset" / "linux-regeneration" / "report.json"
    ).read_text(encoding="utf-8")
)
CONFIG = json.loads(
    (ROOT / "configs" / "generation" / "corpus.json").read_text(
        encoding="utf-8"
    )
)
KEYS = ("attempted", "kept", "rejected", "unsupported")


def test_it_was_made_under_the_committed_config() -> None:
    """Same seed, and every one of the configured attempts made."""
    assert REPORT["seed"] == CONFIG["seed"]
    assert REPORT["attempted"] == CONFIG["samples_target"]
    assert REPORT["complete"] is True


def test_every_attempt_is_kept_rejected_or_unsupported() -> None:
    """Each attempt ends in exactly one of the three outcomes."""
    assert REPORT["attempted"] == sum(REPORT[k] for k in KEYS[1:])


@pytest.mark.parametrize("key", KEYS)
def test_totals_are_the_sum_of_the_categories(key: str) -> None:
    """No attempt is counted outside a category."""
    assert REPORT[key] == sum(c[key] for c in REPORT["categories"])


def test_every_rejection_was_a_crash_that_passed_when_rerun() -> None:
    """No rejection is an oracle disagreement; each crash passed alone."""
    rerun = json.loads(
        (
            ROOT
            / "docs"
            / "dataset"
            / "linux-regeneration"
            / "crash_rerun.json"
        ).read_text(encoding="utf-8")
    )
    rejected = [
        reason
        for category in REPORT["categories"]
        for reason, count in category["rejected_by_reason"].items()
        for _ in range(count)
    ]
    assert set(rejected) == {"child_crash"}
    assert len(rerun["reruns"]) == REPORT["rejected"]
    assert {r["outcome"] for r in rerun["reruns"]} == {"kept"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
