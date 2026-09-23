# Copyright 2026 PyMOL Copilot contributors.
"""The label audit: a seeded random draw, judged by hand, scored honestly.

The spec asks for a spot-check of a small labeled sample, with the
observed error rate reported and no pass/fail threshold. This module
draws the sample, writes the sheet a person fills in, and turns the
filled sheet into a number with an interval.

The draw is from the training split only, because that is what could
teach a model wrong behavior; the gold set was already reviewed item
by item. It is uniform and seeded, so anyone can re-draw the same
fifty.

Scoring refuses a sheet with any blank verdict, because a half-judged
sheet silently becomes a smaller sample. An `unsure` verdict is
reported on its own and is never folded into either count: calling it
correct would flatter the labels, and calling it wrong would punish
them for the auditor's doubt. The error rate is over the labels judged
correct or wrong, with a Wilson score interval, and the worst case --
every unsure label wrong -- is reported beside it.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import math
import random
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_data.sample import Sample
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure

VERDICT_CORRECT = "correct"
VERDICT_WRONG = "wrong"
VERDICT_UNSURE = "unsure"
VERDICTS = frozenset((VERDICT_CORRECT, VERDICT_WRONG, VERDICT_UNSURE))

#: The two-sided 95% normal quantile.
_Z_95 = 1.959963984540054

#: What the auditor is asked to judge, written into the sheet itself so
#: the definition travels with the verdicts.
CRITERIA = """\
A label is WRONG when either of these holds:

1. The plan does not do what the intent asks on this structure: the
   wrong atoms, colour or representation, or an effect the intent did
   not ask for, or a requested effect missing.
2. The intent's wording would lead a structural biologist to expect
   something other than what the plan does -- for example `residues 1
   to 4` on a structure where that range spans an insertion code, or
   `hetero atoms` where the reader would not expect water to count.

Mark UNSURE only when you cannot decide; say why in the note.
Otherwise mark CORRECT.
"""


class InvalidAuditError(ValueError):
    """Raised when an audit draw or sheet cannot be trusted."""


def draw(
    train: Sequence[Sample], *, size: int, seed: int
) -> tuple[Sample, ...]:
    """Draw the audit sample uniformly, without replacement.

    The training samples are sorted by id first, so the draw depends on
    the seed and the set of samples and on nothing about file order.

    Args:
        train: The training split.
        size: How many labels to draw.
        seed: The seed the draw derives from.

    Returns:
        The drawn samples, in draw order.

    Raises:
        InvalidAuditError: If the split holds fewer samples than size.
    """
    if size > len(train):
        raise InvalidAuditError(
            f"cannot draw {size} labels from {len(train)} training samples"
        )
    ordered = sorted(train, key=lambda sample: sample.sample_id)
    return tuple(random.Random(seed).sample(ordered, size))


def structure_summary(sample: Sample) -> str:
    """Describe a sample's structure in the terms an auditor needs.

    Args:
        sample: The sample.

    Returns:
        One line per chain listing its residues, then the states,
        alternate locations and insertion codes.
    """
    snapshot = build_structure(StructureSpec.from_dict(sample.structure.spec))
    atoms = snapshot.states[0].atoms
    residues: dict[str, list[str]] = {}
    seen: set[tuple[str, int, str]] = set()
    altlocs: set[str] = set()
    for atom in atoms:
        key = (atom.chain, atom.resv, atom.ins_code)
        label = f"{atom.resv}{atom.ins_code} {atom.resn}"
        if atom.hetatm:
            label += " (het)"
        if key not in seen:
            seen.add(key)
            residues.setdefault(atom.chain, []).append(label)
        if atom.alt:
            altlocs.add(f"{atom.chain}{atom.resv}{atom.ins_code}:{atom.name}")
    lines = [
        f"chain {chain}: {', '.join(labels)}"
        for chain, labels in sorted(residues.items())
    ]
    lines.append(f"states: {len(snapshot.states)}")
    lines.append(
        "alternate locations: " + (", ".join(sorted(altlocs)) or "none")
    )
    return "\n".join(lines)


def sheet_rows(drawn: Iterable[Sample]) -> list[dict[str, Any]]:
    """Build the rows of an unfilled audit sheet.

    Args:
        drawn: The drawn samples.

    Returns:
        One row per sample, with blank verdict and note.
    """
    return [
        {
            "sample_id": sample.sample_id,
            "category": sample.category,
            "intent": sample.intent,
            "structure": structure_summary(sample),
            "plan_pml": sample.plan_pml,
            "selection_counts": [
                list(pair) for pair in sample.verification.selection_counts
            ],
            "not_checked": list(sample.unsupported_assertions),
            "verdict": None,
            "note": None,
        }
        for sample in drawn
    ]


def write_sheet(directory: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write the sheet as JSONL to fill in, and as Markdown to read.

    Args:
        directory: The audit directory; created if absent.
        rows: The sheet rows.
    """
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "sheet.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    parts = [
        "# Label audit sheet\n",
        "Fill in `verdict` (correct, wrong or unsure) and, where useful,",
        "`note` for every line of `sheet.jsonl`. This file is for reading;",
        "only `sheet.jsonl` is scored.\n",
        CRITERIA,
    ]
    for number, row in enumerate(rows, start=1):
        parts += [
            f"## {number}. `{row['sample_id']}`\n",
            f"**Intent:** {row['intent']}\n",
            "**Structure:**\n",
            "```",
            row["structure"],
            "```\n",
            "**Plan:**\n",
            "```",
            row["plan_pml"].rstrip("\n"),
            "```\n",
            f"Selection counts: {row['selection_counts'] or 'none'}\n",
            "Not checked by the oracle: "
            + (", ".join(row["not_checked"]) or "nothing")
            + "\n",
        ]
    (directory / "sheet.md").write_text(
        "\n".join(parts), encoding="utf-8", newline="\n"
    )


def read_sheet(path: Path) -> list[dict[str, Any]]:
    """Read a filled audit sheet.

    Args:
        path: The sheet.jsonl file.

    Returns:
        The rows, in file order.
    """
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """Compute the Wilson score 95% interval for a proportion.

    Args:
        successes: The count observed.
        trials: The number of trials.

    Returns:
        The lower and upper bounds.

    Raises:
        ValueError: If trials is not positive or successes is out of range.
    """
    if trials < 1 or not 0 <= successes <= trials:
        raise ValueError(f"invalid proportion {successes}/{trials}")
    p = successes / trials
    z2 = _Z_95 * _Z_95
    denominator = 1 + z2 / trials
    centre = (p + z2 / (2 * trials)) / denominator
    margin = (
        _Z_95
        * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials * trials))
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


@dataclass(frozen=True)
class AuditResult:
    """A scored audit.

    Attributes:
        sample_size: How many labels were drawn.
        wrong: Labels judged wrong.
        correct: Labels judged correct.
        unsure: Labels the auditor could not decide.
        judged: wrong + correct, the rate's denominator.
        error_rate: wrong / judged.
        wilson_low: Lower bound of the Wilson 95% interval.
        wilson_high: Upper bound of the Wilson 95% interval.
        worst_case_rate: (wrong + unsure) / sample_size.
    """

    sample_size: int
    wrong: int
    correct: int
    unsure: int
    judged: int
    error_rate: float
    wilson_low: float
    wilson_high: float
    worst_case_rate: float

    def to_dict(self) -> dict[str, Any]:
        """Render this result as a JSON-safe mapping.

        Returns:
            A plain dict with this result's fields.
        """
        return {
            "sample_size": self.sample_size,
            "wrong": self.wrong,
            "correct": self.correct,
            "unsure": self.unsure,
            "judged": self.judged,
            "error_rate": self.error_rate,
            "wilson_low": self.wilson_low,
            "wilson_high": self.wilson_high,
            "worst_case_rate": self.worst_case_rate,
        }


def score(
    rows: Sequence[Mapping[str, Any]], *, drawn_ids: Sequence[str]
) -> AuditResult:
    """Score a filled audit sheet.

    Args:
        rows: The filled sheet rows.
        drawn_ids: The sample ids the draw produced, in order; the
            sheet must hold exactly these.

    Returns:
        The scored result.

    Raises:
        InvalidAuditError: If the sheet's ids differ from the draw, a
            verdict is blank or unknown, or nothing was judged.
    """
    if [row.get("sample_id") for row in rows] != list(drawn_ids):
        raise InvalidAuditError(
            "the sheet's sample ids differ from the draw; re-draw rather "
            "than edit the sample"
        )
    blank = [row["sample_id"] for row in rows if row.get("verdict") is None]
    if blank:
        raise InvalidAuditError(
            f"{len(blank)} verdicts are blank: {', '.join(blank)}"
        )
    unknown = [
        row["sample_id"] for row in rows if row["verdict"] not in VERDICTS
    ]
    if unknown:
        raise InvalidAuditError(
            f"verdicts must be one of {sorted(VERDICTS)}: {', '.join(unknown)}"
        )
    verdicts = [row["verdict"] for row in rows]
    wrong = verdicts.count(VERDICT_WRONG)
    correct = verdicts.count(VERDICT_CORRECT)
    unsure = verdicts.count(VERDICT_UNSURE)
    judged = wrong + correct
    if judged == 0:
        raise InvalidAuditError("no label was judged correct or wrong")
    low, high = wilson_interval(wrong, judged)
    return AuditResult(
        sample_size=len(rows),
        wrong=wrong,
        correct=correct,
        unsure=unsure,
        judged=judged,
        error_rate=wrong / judged,
        wilson_low=low,
        wilson_high=high,
        worst_case_rate=(wrong + unsure) / len(rows),
    )
