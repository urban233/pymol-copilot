# Copyright 2026 PyMOL Copilot contributors.
"""The per-category rejection report, aggregated honestly.

Item 14 asks for the rejection rate per category, reported honestly,
with any category the oracle cannot grade marked unsupported rather
than guessed. Three rules follow, and they are what this module exists
to enforce rather than leave to whoever reads the numbers:

- **An unsupported category is not a failure.** A plan naming the
  polymer flag was never gradable, so counting it as a rejection would
  invent a defect rate out of a contract limitation. It is counted in
  its own column and left out of the rate's denominator.
- **A category with nothing kept still appears.** The failure mode
  worth guarding against is a category quietly vanishing from the
  corpus, which produces no error anywhere -- only an absence.
- **A rate over no gradable attempts is None, not zero.** Zero would
  read as "nothing went wrong" for a category where nothing was ever
  measured.

Every rejection keeps the reason the executor actually gave, so a
fidelity mismatch -- real PyMOL disagreeing with the oracle -- stays
distinguishable from a plan PyMOL refused to run.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections import Counter
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_data.generate import STATUS_UNSUPPORTED
from pmc_data.generate import Rejection
from pmc_data.sample import Sample


@dataclass(frozen=True)
class CategoryReport:
    """What happened to every attempt in one taxonomy category.

    Attributes:
        category: The derived category these counts describe.
        attempted: Every attempt, whatever its outcome.
        kept: Attempts that verified and entered the corpus.
        rejected: Attempts that were gradable and failed.
        unsupported: Attempts the oracle could not grade at all.
        rejected_by_reason: How many rejections carried each reason.
        unsupported_assertions: Assertions that kept samples in this
            category could not evaluate, and how often. A kept sample
            can still carry one of these -- an oriented plan is
            verified on its counts while its camera assertion is not
            made at all.
        rejection_rate: rejected / (kept + rejected), or None when no
            attempt in this category was gradable.
    """

    category: str
    attempted: int
    kept: int
    rejected: int
    unsupported: int
    rejected_by_reason: Mapping[str, int]
    unsupported_assertions: Mapping[str, int]
    rejection_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        """Render this category's counts as a JSON-safe mapping.

        Returns:
            A plain dict with this record's fields.
        """
        return {
            "category": self.category,
            "attempted": self.attempted,
            "kept": self.kept,
            "rejected": self.rejected,
            "unsupported": self.unsupported,
            "rejected_by_reason": dict(self.rejected_by_reason),
            "unsupported_assertions": dict(self.unsupported_assertions),
            "rejection_rate": self.rejection_rate,
        }


@dataclass(frozen=True)
class CorpusReport:
    """The whole run's outcome, overall and per category.

    Attributes:
        seed: The seed the run was generated from.
        attempted: Every attempt across every category.
        kept: Verified samples written to the corpus.
        rejected: Gradable attempts that failed.
        unsupported: Attempts no assertion could be made about.
        rejection_rate: rejected / (kept + rejected), or None.
        categories: Per-category counts, ordered by category name.
    """

    seed: int
    attempted: int
    kept: int
    rejected: int
    unsupported: int
    rejection_rate: float | None
    categories: tuple[CategoryReport, ...]

    def to_dict(self) -> dict[str, Any]:
        """Render the whole report as a JSON-safe mapping.

        Returns:
            A plain dict suitable for json.dumps.
        """
        return {
            "seed": self.seed,
            "attempted": self.attempted,
            "kept": self.kept,
            "rejected": self.rejected,
            "unsupported": self.unsupported,
            "rejection_rate": self.rejection_rate,
            "categories": [category.to_dict() for category in self.categories],
        }


def _rate(kept: int, rejected: int) -> float | None:
    """Compute a rejection rate over gradable attempts only.

    Args:
        kept: Verified attempts.
        rejected: Gradable attempts that failed.

    Returns:
        The rate, or None when nothing gradable was attempted -- zero
        would read as "nothing went wrong" where nothing was measured.
    """
    gradable = kept + rejected
    if gradable == 0:
        return None
    return rejected / gradable


def build_report(
    samples: Iterable[Sample],
    rejections: Iterable[Rejection],
    *,
    seed: int,
) -> CorpusReport:
    """Aggregate one run's samples and rejections into a report.

    Args:
        samples: The verified samples.
        rejections: Every attempt that did not become a sample.
        seed: The seed the run used.

    Returns:
        The assembled report.
    """
    kept: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    unsupported: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = {}
    markers: dict[str, Counter[str]] = {}

    for sample in samples:
        kept[sample.category] += 1
        for marker in sample.unsupported_assertions:
            markers.setdefault(sample.category, Counter())[marker] += 1

    for rejection in rejections:
        if rejection.status == STATUS_UNSUPPORTED:
            unsupported[rejection.category] += 1
        else:
            rejected[rejection.category] += 1
        reasons.setdefault(rejection.category, Counter())[rejection.reason] += 1

    categories = sorted(set(kept) | set(rejected) | set(unsupported))
    per_category = tuple(
        CategoryReport(
            category=category,
            attempted=kept[category]
            + rejected[category]
            + unsupported[category],
            kept=kept[category],
            rejected=rejected[category],
            unsupported=unsupported[category],
            rejected_by_reason=dict(
                sorted(reasons.get(category, Counter()).items())
            ),
            unsupported_assertions=dict(
                sorted(markers.get(category, Counter()).items())
            ),
            rejection_rate=_rate(kept[category], rejected[category]),
        )
        for category in categories
    )

    total_kept = sum(kept.values())
    total_rejected = sum(rejected.values())
    total_unsupported = sum(unsupported.values())
    return CorpusReport(
        seed=seed,
        attempted=total_kept + total_rejected + total_unsupported,
        kept=total_kept,
        rejected=total_rejected,
        unsupported=total_unsupported,
        rejection_rate=_rate(total_kept, total_rejected),
        categories=per_category,
    )


def render_table(report: CorpusReport) -> str:
    """Render a report as the table a run prints when it finishes.

    Args:
        report: The report to render.

    Returns:
        The table text, ending in a newline.
    """
    lines = [
        f"{'category':<44} {'att':>6} {'kept':>6} {'rej':>6} "
        f"{'unsup':>6} {'rate':>7}",
        "-" * 79,
    ]
    for category in report.categories:
        rate = (
            "n/a"
            if category.rejection_rate is None
            else f"{category.rejection_rate:.1%}"
        )
        lines.append(
            f"{category.category:<44} {category.attempted:>6} "
            f"{category.kept:>6} {category.rejected:>6} "
            f"{category.unsupported:>6} {rate:>7}"
        )
    overall = (
        "n/a"
        if report.rejection_rate is None
        else f"{report.rejection_rate:.1%}"
    )
    lines.append("-" * 79)
    lines.append(
        f"{'TOTAL':<44} {report.attempted:>6} {report.kept:>6} "
        f"{report.rejected:>6} {report.unsupported:>6} {overall:>7}"
    )
    return "\n".join(lines) + "\n"


def write_report(path: Path, report: CorpusReport) -> None:
    """Write a report as deterministic JSON.

    Args:
        path: The file to write.
        report: The report to serialize.
    """
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_rejections(path: Path, rejections: Iterable[Rejection]) -> int:
    """Write every rejection as JSONL, so none is lost to a summary.

    Args:
        path: The file to write.
        rejections: The rejections to write, in order.

    Returns:
        How many rejections were written.
    """
    written = 0
    with path.open("w", encoding="utf-8") as handle:
        for rejection in rejections:
            handle.write(
                json.dumps(
                    {
                        "sample_id": rejection.sample_id,
                        "category": rejection.category,
                        "difficulty": rejection.difficulty,
                        "status": rejection.status,
                        "reason": rejection.reason,
                        "detail": rejection.detail,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            written += 1
    return written
