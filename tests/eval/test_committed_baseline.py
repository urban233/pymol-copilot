# Copyright 2026 PyMOL Copilot contributors.
"""The committed baseline is exactly what its committed samples say.

`docs/evaluation/baseline/` is the untuned model's result, measured
before any fine-tuning existed (master plan item 16), and item 17's
comparison rests on it. This suite keeps it, and item 17's own
publications (the export-pipeline control and the fine-tuned model)
and comparisons, honest in five ways:

- every published file still has the digest the manifest recorded;
- every report is recomputed from its samples, so no rate can be edited
  by hand;
- every stored completion still screens, parses and classifies as its
  record says under today's parser and screen, so a later change to
  either shows up here as a stale baseline rather than silently
  re-grading it;
- the baseline was measured on the committed split, under the committed
  config and today's harness, grader, repair-prompt and report versions.
  Changing any of them fails this suite until the base model is run
  again;
- every committed comparison is exactly what its two publications give.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path
from typing import Any

import pytest

from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.screen import SCREEN_HOSTILE
from pmc_core.screen import screen_completion
from pmc_data.manifest import file_record
from pmc_data.manifest import sha256_of
from pmc_eval.compare import compare
from pmc_eval.compare import render_markdown as render_comparison
from pmc_eval.eval_cli import read_run
from pmc_eval.grade import GRADER_VERSION
from pmc_eval.metrics import REPORT_VERSION
from pmc_eval.prompt import REPAIR_PROMPT_VERSION
from pmc_eval.record import OUTCOME_ABSTAINED
from pmc_eval.record import OUTCOME_DENIED_HOSTILE
from pmc_eval.record import OUTCOME_SYNTAX_INVALID
from pmc_eval.record import OUTCOME_TRUNCATED
from pmc_eval.record import AttemptRecord
from pmc_eval.runner import HARNESS_VERSION
from pmc_eval.runner import NORMALIZATION
from pmc_eval.screen_reasons import hostile_reasons

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "docs" / "evaluation"
DATASET_MANIFEST = ROOT / "docs" / "dataset" / "manifest.json"
CONFIGS = ROOT / "configs" / "evaluation"

#: Every published evaluation, and the config it must have been run
#: under: item 16's baseline, and item 17's export-pipeline control and
#: fine-tuned model. Each is checked once `eval_cli publish` has written
#: it; until then its cases are simply absent.
PUBLICATIONS = {
    "baseline": CONFIGS / "baseline.json",
    "export_control": CONFIGS / "export_control.json",
    "finetuned": CONFIGS / "finetuned.json",
}
PUBLISHED = {
    name: EVALUATION / name
    for name in PUBLICATIONS
    if (EVALUATION / name / "manifest.json").is_file()
}
BASELINE = EVALUATION / "baseline"

#: Until `eval_cli publish` writes the baseline there is nothing to
#: check, and every test here skips; from then on each one holds.
pytestmark = pytest.mark.skipif(
    "baseline" not in PUBLISHED,
    reason="no baseline published under docs/evaluation/",
)

#: The pages `eval_cli publish` writes beside the manifest.
PAGES = {"manifest.json", "BASELINE.md", "REPORT.md"}


def _manifest(directory: Path) -> dict[str, Any]:
    """Read a published directory's manifest.

    Args:
        directory: The published directory.

    Returns:
        Its manifest.
    """
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


#: Every published run: its publication's name and its directory.
RUNS = [
    (name, directory / run["set"] / run["condition"])
    for name, directory in PUBLISHED.items()
    for run in _manifest(directory)["runs"]
]
RUN_DIRS = [run for _, run in RUNS]


def _ids(runs: list[Path]) -> list[str]:
    """Name parametrized cases after their publication, set and condition.

    Args:
        runs: The run directories.

    Returns:
        `<publication>/<set>/<condition>` for each.
    """
    return [
        f"{run.parent.parent.name}/{run.parent.name}/{run.name}" for run in runs
    ]


@pytest.mark.parametrize("name", sorted(PUBLISHED))
def test_manifest_digests_hold(name: str) -> None:
    """Every published file is byte for byte what was published.

    Args:
        name: The publication.
    """
    directory = PUBLISHED[name]
    manifest = _manifest(directory)
    assert set(manifest["files"]) == {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name not in PAGES
    }
    for relative, record in manifest["files"].items():
        assert file_record(directory / relative) == record, relative


@pytest.mark.parametrize("run", RUN_DIRS, ids=_ids(RUN_DIRS))
def test_report_recomputes_from_samples(run: Path) -> None:
    """A report is exactly what its samples aggregate to.

    Args:
        run: One published run directory.
    """
    read_run(run)


def _check_attempt(attempt: AttemptRecord) -> None:
    """Re-screen and re-parse one stored completion against its record.

    Args:
        attempt: The stored attempt.
    """
    text = attempt.completion
    assert attempt.newline_appended == (not text.endswith("\n"))
    normalized = text + ("\n" if attempt.newline_appended else "")
    parsed = parse_pml(normalized)
    assert attempt.syntax_valid == isinstance(parsed, ActionPlan)
    if attempt.outcome in {OUTCOME_TRUNCATED, OUTCOME_ABSTAINED}:
        return
    hostile = screen_completion(normalized) == SCREEN_HOSTILE
    assert hostile == (attempt.outcome == OUTCOME_DENIED_HOSTILE)
    if hostile:
        assert hostile_reasons(normalized) == attempt.hostile_reasons
        return
    if attempt.outcome == OUTCOME_SYNTAX_INVALID:
        assert isinstance(parsed, ParseRejection)
        assert parsed.category == attempt.category
    else:
        assert isinstance(parsed, ActionPlan)
        assert parsed.render_pml() == attempt.plan_pml


@pytest.mark.parametrize("run", RUN_DIRS, ids=_ids(RUN_DIRS))
def test_stored_completions_reclassify_identically(run: Path) -> None:
    """Today's screen and parser still read every completion the same way.

    Args:
        run: One published run directory.
    """
    _, records, _ = read_run(run)

    for record in records:
        for attempt in record.attempts:
            _check_attempt(attempt)


@pytest.mark.parametrize(("name", "run"), RUNS, ids=_ids(RUN_DIRS))
def test_baseline_is_on_the_committed_split_and_config(
    name: str, run: Path
) -> None:
    """Each publication was measured on today's split, config and harness.

    Args:
        name: The publication.
        run: One published run directory.
    """
    identity = read_run(run)[0]["identity"]
    dataset = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))

    assert identity["split_id"] == dataset["split_id"]
    assert identity["config_sha256"] == sha256_of(PUBLICATIONS[name])
    assert identity["limit"] is None
    assert identity["git_dirty"] is False
    assert (
        identity["harness_version"],
        identity["grader_version"],
        identity["repair_prompt_version"],
        identity["report_version"],
        identity["normalization"],
    ) == (
        HARNESS_VERSION,
        GRADER_VERSION,
        REPAIR_PROMPT_VERSION,
        REPORT_VERSION,
        NORMALIZATION,
    )


#: Every committed comparison `eval_cli compare` wrote.
COMPARISONS = sorted(
    path.parent for path in EVALUATION.glob("*/comparison.json")
)


@pytest.mark.parametrize(
    "directory", COMPARISONS, ids=[path.name for path in COMPARISONS]
)
def test_comparison_recomputes_from_the_publications(directory: Path) -> None:
    """A comparison is exactly what its two publications give.

    Args:
        directory: A committed comparison.
    """
    committed = json.loads(
        (directory / "comparison.json").read_text(encoding="utf-8")
    )
    title = committed.pop("title")
    sides = committed["baseline"], committed["candidate"]
    recomputed = compare(
        EVALUATION / sides[0]["published"],
        EVALUATION / sides[1]["published"],
        CONFIGS / sides[0]["config"],
        CONFIGS / sides[1]["config"],
        read_run,
    )
    assert recomputed == committed
    page = (directory / "COMPARISON.md").read_text(encoding="utf-8")
    assert page == render_comparison(committed, title)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
