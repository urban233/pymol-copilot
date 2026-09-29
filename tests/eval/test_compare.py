# Copyright 2026 PyMOL Copilot contributors.
"""Item 17's comparison pairs by sample, tests exactly, and refuses drift.

The candidates here are built from the committed baseline's own
`test_gold` runs, with some samples turned into successes, so the
paired test has discordant pairs to count; the refusals change one
thing the comparison must hold fixed and expect it to be named.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pmc_data.manifest import sha256_of
from pmc_data.manifest import write_json
from pmc_eval import eval_cli
from pmc_eval.compare import ComparisonError
from pmc_eval.compare import compare
from pmc_eval.compare import mcnemar_exact
from pmc_eval.compare import render_markdown
from pmc_eval.eval_cli import read_run
from pmc_eval.metrics import aggregate
from pmc_eval.record import SampleRecord

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "evaluation" / "baseline"
BASELINE_CONFIG = ROOT / "configs" / "evaluation" / "baseline.json"
GIT_CLEAN = ("0" * 40, False)

pytestmark = pytest.mark.skipif(
    not (BASELINE / "manifest.json").is_file(), reason="no baseline published"
)

#: The candidate's model, as its config and runs name it.
MODEL = "pmc-candidate-Q4_K_M"
CHECKPOINT = f"/models/candidate/{MODEL}.gguf"
GGUF = "c" * 64


@pytest.mark.parametrize(
    ("b", "c", "p"),
    [
        (0, 0, 1.0),
        (0, 10, 0.001953125),
        (3, 7, 0.34375),
        (5, 5, 1.0),
        (7, 0, 0.015625),
    ],
)
def test_mcnemar_exact(b: int, c: int, p: float) -> None:
    """The exact two-sided McNemar p-value on known discordant counts."""
    assert mcnemar_exact(b, c) == pytest.approx(p)
    assert mcnemar_exact(c, b) == pytest.approx(p)


def _candidate_config(
    tmp_path: Path, change: Callable[[dict[str, Any]], None] | None = None
) -> Path:
    """Write the candidate's config: the baseline's, but another model.

    Args:
        tmp_path: A scratch directory.
        change: Also changes the config, to test a refusal.

    Returns:
        The config file.
    """
    data = json.loads(BASELINE_CONFIG.read_text(encoding="utf-8"))
    data["engine"]["model_name"] = MODEL
    data["engine"]["checkpoint"] = CHECKPOINT
    data["engine_provenance"]["gguf_sha256"] = GGUF
    data["engine_provenance"]["hf_revision"] = "none (local GGUF)"
    if change is not None:
        change(data)
    path = tmp_path / "candidate.json"
    write_json(path, data)
    return path


def _candidate(
    tmp_path: Path,
    config: Path,
    succeed: dict[str, int],
    *,
    identity: Callable[[dict[str, Any]], None] | None = None,
    reorder: bool = False,
) -> Path:
    """Publish a candidate built from the baseline's test_gold runs.

    Args:
        tmp_path: A scratch directory.
        config: The candidate's config.
        succeed: For each condition, how many leading samples succeed.
        identity: Also changes each run's identity, to test a refusal.
        reorder: Reverse each run's sample order.

    Returns:
        The published candidate's directory.
    """
    out = tmp_path / "candidate"
    manifest = json.loads((BASELINE / "manifest.json").read_text("utf-8"))
    runs = []
    for entry in manifest["runs"]:
        if entry["set"] != "test_gold":
            continue
        source = BASELINE / entry["set"] / entry["condition"]
        target = out / entry["set"] / entry["condition"]
        target.mkdir(parents=True)
        run, records, _ = read_run(source)
        rows = [record.to_dict() for record in records]
        for row in rows[: succeed.get(entry["condition"], 0)]:
            row["attempts"][-1]["outcome"] = "success"
            row["final_outcome"] = "success"
            row["task_success"] = True
        if reorder:
            rows.reverse()
        rebuilt = [SampleRecord.from_dict(row) for row in rows]
        run["identity"]["model_identity"] = f"{MODEL}@{CHECKPOINT}"
        run["identity"]["config_sha256"] = sha256_of(config)
        run["identity"]["engine_provenance"]["gguf_sha256"] = GGUF
        if identity is not None:
            identity(run["identity"])
        write_json(target / "run.json", run)
        (target / "samples.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        write_json(
            target / "report.json",
            aggregate(rebuilt, condition=entry["condition"]),
        )
        shutil.copyfile(source / "timings.jsonl", target / "timings.jsonl")
        runs.append(entry)
    write_json(
        out / "manifest.json",
        {**manifest, "runs": runs, "config_sha256": sha256_of(config)},
    )
    return out


def test_paired_comparison_counts_discordant_pairs(tmp_path: Path) -> None:
    """Seven new successes under the grammar, none without it."""
    config = _candidate_config(tmp_path)
    candidate = _candidate(tmp_path, config, {"grammar": 7})
    result = compare(BASELINE, candidate, BASELINE_CONFIG, config, read_run)
    gold = result["sets"]["test_gold"]
    assert set(result["sets"]) == {"test_gold"}
    grammar = gold["grammar"]["paired_task_success"]
    assert grammar["n"] == 68
    assert grammar["only_candidate_succeeds"] == 7
    assert grammar["only_baseline_succeeds"] == 0
    assert grammar["mcnemar_exact_p"] == pytest.approx(0.015625)
    none = gold["no-grammar"]["paired_task_success"]
    assert none["only_candidate_succeeds"] == 0
    assert none["mcnemar_exact_p"] == 1.0
    overall = gold["grammar"]["overall"]["**TaskSuccess**"]
    assert overall["baseline"]["k"] == 0
    assert overall["candidate"]["k"] == 7
    assert overall["delta"] == pytest.approx(7 / 68, abs=1e-6)


def test_every_category_is_set_side_by_side(tmp_path: Path) -> None:
    """Each category's TaskSuccess appears for both models."""
    config = _candidate_config(tmp_path)
    candidate = _candidate(tmp_path, config, {"grammar": 7})
    result = compare(BASELINE, candidate, BASELINE_CONFIG, config, read_run)
    _, records, _ = read_run(BASELINE / "test_gold" / "grammar")
    categories = result["sets"]["test_gold"]["grammar"]["breakouts"]["category"]
    assert set(categories) == {record.category for record in records}
    succeeded = {record.category for record in records[:7]}
    for category, row in categories.items():
        assert row["baseline"]["k"] == 0
        assert (row["candidate"]["k"] > 0) == (category in succeeded)
    page = render_markdown(result, "A comparison")
    assert "### TaskSuccess by category (descriptive)" in page
    assert "McNemar exact p" in page


@pytest.mark.parametrize(
    ("identity", "reason"),
    [
        (lambda i: i.update(harness_version=99), "harness_version"),
        (lambda i: i.update(split_id="0" * 16), "split_id"),
        (
            lambda i: i["engine_capabilities"].update(context_length=8192),
            "context_length",
        ),
        (lambda i: i.update(git_dirty=True), "dirty"),
        (
            lambda i: i["engine_provenance"].update(lemonade_version="11.10.0"),
            "lemonade_version",
        ),
        (
            lambda i: i["engine_provenance"].update(llama_cpp_build="b1"),
            "llama_cpp_build",
        ),
    ],
)
def test_a_run_differing_beyond_the_model_is_refused(
    tmp_path: Path, identity: Callable[[dict[str, Any]], None], reason: str
) -> None:
    """A run made under another harness, split or engine is refused."""
    config = _candidate_config(tmp_path)
    candidate = _candidate(tmp_path, config, {}, identity=identity)
    with pytest.raises(ComparisonError, match=reason):
        compare(BASELINE, candidate, BASELINE_CONFIG, config, read_run)


def test_another_sample_order_is_refused(tmp_path: Path) -> None:
    """Runs visiting the samples in another order are refused."""
    config = _candidate_config(tmp_path)
    candidate = _candidate(tmp_path, config, {}, reorder=True)
    with pytest.raises(ComparisonError, match="order"):
        compare(BASELINE, candidate, BASELINE_CONFIG, config, read_run)


def test_a_config_differing_beyond_the_model_is_refused(tmp_path: Path) -> None:
    """A candidate run under another token limit is refused."""

    def longer(data: dict[str, Any]) -> None:
        data["generation"]["max_tokens"] = 512

    config = _candidate_config(tmp_path, longer)
    candidate = _candidate(tmp_path, config, {})
    with pytest.raises(ComparisonError, match=r"generation\.max_tokens"):
        compare(BASELINE, candidate, BASELINE_CONFIG, config, read_run)


def test_a_config_not_the_runs_own_is_refused(tmp_path: Path) -> None:
    """Naming a config the candidate was not run under is refused."""
    config = _candidate_config(tmp_path)
    candidate = _candidate(tmp_path, config, {})
    with pytest.raises(ComparisonError, match="was not run under"):
        compare(BASELINE, candidate, BASELINE_CONFIG, BASELINE_CONFIG, read_run)


def test_compare_command_writes_the_comparison(tmp_path: Path) -> None:
    """`eval_cli compare` writes comparison.json and COMPARISON.md."""
    config = _candidate_config(tmp_path)
    candidate = _candidate(tmp_path, config, {"grammar": 3})
    out = tmp_path / "comparison"
    code = eval_cli.run(
        [
            "compare",
            "--baseline",
            str(BASELINE),
            "--baseline-config",
            str(BASELINE_CONFIG),
            "--candidate",
            str(candidate),
            "--candidate-config",
            str(config),
            "--out",
            str(out),
        ],
        git=GIT_CLEAN,
    )
    assert code == 0
    written = json.loads((out / "comparison.json").read_text("utf-8"))
    title = written.pop("title")
    assert written == compare(
        BASELINE, candidate, BASELINE_CONFIG, config, read_run
    )
    assert (out / "COMPARISON.md").read_text("utf-8") == render_markdown(
        written, title
    )
    assert (
        eval_cli.run(
            [
                "compare",
                "--candidate",
                str(candidate),
                "--candidate-config",
                str(config),
                "--out",
                str(out),
            ],
            git=GIT_CLEAN,
        )
        != 0
    )


def _baseline_runs(
    set_name: str | None = None, condition: str | None = None
) -> list[str]:
    """Name the committed baseline's run directories.

    Filters on the manifest rather than the path strings, whose separator
    differs on Windows.

    Args:
        set_name: Keep only this set's runs, if given.
        condition: Keep only this condition's runs, if given.

    Returns:
        Each run directory, as a string.
    """
    manifest = json.loads((BASELINE / "manifest.json").read_text("utf-8"))
    runs = [
        str(BASELINE / entry["set"] / entry["condition"])
        for entry in manifest["runs"]
        if set_name in (None, entry["set"])
        and condition in (None, entry["condition"])
    ]
    assert runs, (set_name, condition)
    return runs


def test_default_publish_still_reproduces_the_baseline(tmp_path: Path) -> None:
    """Publishing the baseline's runs again gives the same bytes."""
    out = tmp_path / "baseline"
    code = eval_cli.run(
        [
            "publish",
            "--runs",
            *_baseline_runs(),
            "--config",
            str(BASELINE_CONFIG),
            "--out",
            str(out),
        ],
        git=GIT_CLEAN,
    )
    assert code == 0
    published = sorted(
        p.relative_to(BASELINE) for p in BASELINE.rglob("*") if p.is_file()
    )
    again = sorted(p.relative_to(out) for p in out.rglob("*") if p.is_file())
    assert again == published
    for relative in published:
        assert (out / relative).read_bytes() == (
            BASELINE / relative
        ).read_bytes(), relative


def test_publish_a_subset_as_another_kind(tmp_path: Path) -> None:
    """The gold-only control publishes as its own kind, under its title."""
    runs = _baseline_runs("test_gold")
    out = tmp_path / "control"
    code = eval_cli.run(
        [
            "publish",
            "--runs",
            *runs,
            "--config",
            str(BASELINE_CONFIG),
            "--out",
            str(out),
            "--kind",
            "export-control",
            "--sets",
            "test_gold",
        ],
        git=GIT_CLEAN,
    )
    assert code == 0
    page = (out / "REPORT.md").read_text("utf-8")
    assert page.startswith("# Export-pipeline control\n")
    assert not (out / "BASELINE.md").exists()
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    assert {run["set"] for run in manifest["runs"]} == {"test_gold"}


def test_publish_refuses_a_missing_run_of_the_named_sets(
    tmp_path: Path,
) -> None:
    """--sets still needs every condition of every named set."""
    runs = _baseline_runs("test_gold", "grammar")
    code = eval_cli.run(
        [
            "publish",
            "--runs",
            *runs,
            "--config",
            str(BASELINE_CONFIG),
            "--out",
            str(tmp_path / "x"),
            "--kind",
            "export-control",
            "--sets",
            "test_gold",
        ],
        git=GIT_CLEAN,
    )
    assert code != 0
    assert not (tmp_path / "x").exists()


def test_publish_refuses_a_partial_baseline(tmp_path: Path) -> None:
    """The baseline is always published over its config's whole grid."""
    runs = _baseline_runs("test_gold")
    code = eval_cli.run(
        [
            "publish",
            "--runs",
            *runs,
            "--config",
            str(BASELINE_CONFIG),
            "--out",
            str(tmp_path / "x"),
            "--sets",
            "test_gold",
        ],
        git=GIT_CLEAN,
    )
    assert code != 0
    assert not (tmp_path / "x").exists()


def test_a_tiny_p_value_is_not_rounded_to_zero() -> None:
    """842 discordant pairs give about 1e-253, not 0."""
    p = mcnemar_exact(0, 842)
    assert 0 < p < 1e-250


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
