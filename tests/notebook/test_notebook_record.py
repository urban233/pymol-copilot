# Copyright 2026 PyMOL Copilot contributors.
"""Every number the committed notebook reports recomputes from the evidence.

The notebook (master plan item 18) is committed executed, so its
outputs are text a reader trusts without running anything. Each number
it reports also goes through `notebook_support.record`, and its last
cell prints them all as one JSON document. This test reads that document
from the committed notebook and recomputes every value from the
committed evidence with the same code the evaluation used, so the
notebook cannot drift from what it describes. It also checks that every
cell ran, in order, without an error, and that the end-user
demonstration was actually executed.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path
from typing import Any

import pytest

from pmc_eval.compare import compare
from pmc_eval.eval_cli import read_run

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "pymol_copilot.ipynb"
EVALUATION = ROOT / "docs" / "evaluation"
CONFIGS = ROOT / "configs" / "evaluation"
RUN_DIR = ROOT / "docs" / "training" / "runs" / "train-e6c6c4dd8f6caaf9"

#: The line that heads the notebook's final record, as
#: `notebooks/notebook_support.py` prints it.
RECORD_HEADER = "pmc-notebook-record"

SETS = ("test_gold", "heldout_synthetic")
CONDITIONS = ("no-grammar", "grammar")


def _read(path: Path) -> Any:
    """Read one JSON file.

    Args:
        path: The file.

    Returns:
        Its decoded JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


NOTEBOOK_JSON: dict[str, Any] = _read(NOTEBOOK)
CODE_CELLS = [c for c in NOTEBOOK_JSON["cells"] if c["cell_type"] == "code"]


def _text(cell: dict[str, Any]) -> str:
    """Join a cell's stream and plain-text outputs.

    Args:
        cell: A code cell.

    Returns:
        Everything it printed or displayed as text.
    """
    parts = []
    for output in cell.get("outputs", []):
        if output["output_type"] == "stream":
            parts.append("".join(output["text"]))
        elif "data" in output:
            parts.append("".join(output["data"].get("text/plain", "")))
    return "".join(parts)


def _record() -> dict[str, Any]:
    """Read the notebook's final record of every reported number.

    Returns:
        The decoded record.
    """
    text = _text(CODE_CELLS[-1])
    assert text.startswith(RECORD_HEADER), "the last cell prints no record"
    return json.loads(text[len(RECORD_HEADER) :])


RECORD = _record()


def test_every_cell_ran_in_order_without_an_error() -> None:
    """The committed notebook is one clean top-to-bottom execution."""
    counts = [cell["execution_count"] for cell in CODE_CELLS]
    assert counts == list(range(1, len(CODE_CELLS) + 1))
    errors = [
        output
        for cell in CODE_CELLS
        for output in cell.get("outputs", [])
        if output["output_type"] == "error"
    ]
    assert errors == []


def test_the_demonstration_ran_against_the_model() -> None:
    """Section 9 was executed: a real preview and a real apply."""
    text = "".join(_text(cell) for cell in CODE_CELLS)
    assert "RUN_DEMO is off" not in text
    assert "copilot plan p-" in text


def test_conformance_is_the_committed_regeneration() -> None:
    """The oracle-versus-PyMOL figures are the committed report's."""
    report = _read(
        ROOT / "docs" / "dataset" / "linux-regeneration" / "report.json"
    )
    for key in ("attempted", "kept", "rejected", "unsupported"):
        assert RECORD[f"conformance.{key}"] == report[key], key
    reasons: dict[str, int] = {}
    for category in report["categories"]:
        for reason, count in category["rejected_by_reason"].items():
            reasons[reason] = reasons.get(reason, 0) + count
    assert RECORD["conformance.rejected_by_reason"] == reasons
    rerun = _read(
        ROOT / "docs" / "dataset" / "linux-regeneration" / "crash_rerun.json"
    )
    assert RECORD["conformance.crashes_kept_on_rerun"] == sum(
        r["outcome"] == "kept" for r in rerun["reruns"]
    )


def test_audit_and_split_are_the_committed_manifest() -> None:
    """The label audit and the split counts are the dataset's own record."""
    audit = _read(ROOT / "docs" / "dataset" / "audit" / "result.json")
    first = _read(
        ROOT
        / "docs"
        / "dataset"
        / "history"
        / "split-f6c24e0f8463359c"
        / "audit"
        / "result.json"
    )
    manifest = _read(ROOT / "docs" / "dataset" / "manifest.json")
    counts = manifest["counts"]
    assert RECORD["audit.v2.wrong"] == audit["wrong"]
    assert RECORD["audit.v2.judged"] == audit["judged"]
    assert RECORD["audit.v1.wrong"] == first["wrong"]
    for name in ("train", "test_gold", "heldout_synthetic"):
        assert RECORD[f"split.{name}"] == counts[name]["total"]
    assert RECORD["split.decontam_dropped"] == counts["decontam_dropped"]
    assert RECORD["split.excluded"] == counts["excluded"]


@pytest.mark.parametrize("set_name", SETS)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_baseline_task_success_recomputes(
    set_name: str, condition: str
) -> None:
    """The baseline figures are what its stored samples aggregate to."""
    _, _, report = read_run(EVALUATION / "baseline" / set_name / condition)
    assert (
        RECORD[f"baseline.{set_name}.{condition}"]
        == report["overall"]["task_success"]["k"]
    )


COMPARISON = compare(
    EVALUATION / "baseline",
    EVALUATION / "finetuned",
    CONFIGS / "baseline.json",
    CONFIGS / "finetuned.json",
    read_run,
)


@pytest.mark.parametrize("set_name", SETS)
@pytest.mark.parametrize("condition", CONDITIONS)
def test_the_comparison_recomputes(set_name: str, condition: str) -> None:
    """Fine-tuned TaskSuccess and the McNemar p are `compare`'s own."""
    block = COMPARISON["sets"][set_name][condition]
    key = f"{set_name}.{condition}"
    assert (
        RECORD[f"finetuned.{key}"]
        == block["overall"]["**TaskSuccess**"]["candidate"]["k"]
    )
    assert (
        RECORD[f"mcnemar.{key}"]
        == block["paired_task_success"]["mcnemar_exact_p"]
    )


@pytest.mark.parametrize("model", ["baseline", "finetuned"])
@pytest.mark.parametrize("condition", CONDITIONS)
def test_repair_success_recomputes(model: str, condition: str) -> None:
    """The repair figures are what the stored samples aggregate to."""
    _, _, report = read_run(EVALUATION / model / "test_gold" / condition)
    assert (
        RECORD[f"repair.{model}.{condition}"]
        == report["overall"]["repair"]["to_success"]["k"]
    )


def test_collapsed_shapes_recompute() -> None:
    """The shapes reported as collapsing have no success in either condition."""
    shapes = COMPARISON["sets"]["test_gold"]
    collapsed = sorted(
        group
        for group, value in shapes["grammar"]["breakouts"]["shape"].items()
        if value["candidate"]["k"] == 0
        and shapes["no-grammar"]["breakouts"]["shape"][group]["candidate"]["k"]
        == 0
    )
    assert RECORD["collapsed.shapes"] == collapsed
    assert collapsed, "a collapse the notebook calls out must exist"


def test_training_record_is_the_committed_run() -> None:
    """Seeds, config hash, steps and the GGUF hash are the run's own."""
    run = _read(RUN_DIR / "run.json")
    timings = _read(RUN_DIR / "timings.json")
    exported = _read(RUN_DIR / "export.json")
    assert RECORD["train.config_sha256"] == run["config_sha256"]
    assert RECORD["train.seeds"] == run["seeds"]
    assert RECORD["train.optimizer_steps"] == timings["optimizer_steps"]
    assert RECORD["train.gguf_sha256"] == exported["gguf_sha256"]
    finetuned = _read(CONFIGS / "finetuned.json")
    assert (
        exported["gguf_sha256"] == finetuned["engine_provenance"]["gguf_sha256"]
    )


def test_versions_are_the_recorded_engine_and_split() -> None:
    """The versions table names the engine and PyMOL the evidence records."""
    provenance = _read(CONFIGS / "finetuned.json")["engine_provenance"]
    manifest = _read(ROOT / "docs" / "dataset" / "manifest.json")
    assert RECORD["versions.lemonade"] == provenance["lemonade_version"]
    assert RECORD["versions.llama_cpp"] == provenance["llama_cpp_build"]
    assert (
        RECORD["versions.pymol_wheel"] == manifest["provenance"]["pymol_wheel"]
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
