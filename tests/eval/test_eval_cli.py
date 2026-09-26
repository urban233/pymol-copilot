# Copyright 2026 PyMOL Copilot contributors.
"""The eval CLI writes what it claims, and refuses what it cannot trust.

Hermetic: a synthetic repository under a temporary root holds a split
of a few committed gold samples and a config, the model is a reference
model that answers every prompt with the sample's own plan, and the
sidecar reproduces each sample's own verification. The request graph,
the grader and the aggregation between them are the real ones.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from fakes import ReferenceEngine
from fakes import ReferenceExecutor
from pmc_agent.inference.base import ENGINE_UNAVAILABLE
from pmc_agent.inference.base import EngineFailure
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.manifest import DATA_FILES
from pmc_data.manifest import REQUIRED_FIELDS
from pmc_data.manifest import REQUIRED_PROVENANCE
from pmc_data.manifest import compute_split_id
from pmc_data.manifest import file_record
from pmc_data.manifest import write_json
from pmc_data.sample import read_samples
from pmc_data.sample import write_samples
from pmc_eval import eval_cli
from pmc_eval.config import EngineConfig
from pmc_eval.config import PROVENANCE_FIELDS
from pmc_eval.eval_cli import ConnectedEngine

GIT_CLEAN = ("0" * 40, False)
GIT_DIRTY = ("0" * 40, True)

#: Three gold samples on two held-out structures, one of them graded on
#: selection counts only.
SAMPLES = tuple(
    s
    for s in read_samples(DEFAULT_GOLD_SAMPLES_PATH)
    if s.sample_id in {"gold_001", "gold_014", "gold_062"}
)

MODEL_NAME = "user.Llama-3.2-1B-Instruct-Q4_K_M"
CHECKPOINT = "unsloth/Llama-3.2-1B-Instruct-GGUF:Q4_K_M.gguf"
IDENTITY = f"{MODEL_NAME}@{CHECKPOINT}"
LEMONADE_VERSION = "11.9.0"

SPLIT = "data/splits/split-test"


def _config(root: Path, *, provenance: bool = True) -> None:
    """Write the evaluation config under a synthetic root.

    Args:
        root: The synthetic repository root.
        provenance: Whether to fill in every provenance field.
    """
    path = root / "configs" / "evaluation" / "baseline.json"
    path.parent.mkdir(parents=True)
    filled = {name: "recorded" for name in PROVENANCE_FIELDS}
    filled["lemonade_version"] = LEMONADE_VERSION
    path.write_text(
        json.dumps(
            {
                "conditions": ["no-grammar", "grammar"],
                "engine": {
                    "backend": "cpu",
                    "base_url": "http://localhost:13305",
                    "checkpoint": CHECKPOINT,
                    "connect_timeout_seconds": 5.0,
                    "context_size": 16384,
                    "model_name": MODEL_NAME,
                    "read_timeout_seconds": 600.0,
                },
                "engine_provenance": (
                    filled
                    if provenance
                    else {name: None for name in PROVENANCE_FIELDS}
                ),
                "generation": {"deadline_seconds": 600.0, "max_tokens": 256},
                "infra_retries": 1,
                "sets": ["test_gold"],
                "sidecar": {"deadline_seconds": 30.0},
            }
        ),
        encoding="utf-8",
    )


def _split(root: Path) -> Path:
    """Write a split of `SAMPLES` and its committed manifest copy.

    Args:
        root: The synthetic repository root.

    Returns:
        The split directory.
    """
    split = root / SPLIT
    split.mkdir(parents=True)
    write_samples(split / "test_gold.jsonl", SAMPLES)
    for name in DATA_FILES:
        (split / name).touch()
    files = {name: file_record(split / name) for name in DATA_FILES}
    manifest: dict[str, object] = {key: None for key in REQUIRED_FIELDS}
    manifest.update(
        files=files,
        split_id=compute_split_id(files),
        provenance={key: None for key in REQUIRED_PROVENANCE},
    )
    write_json(split / "manifest.json", manifest)
    docs = root / "docs" / "dataset"
    docs.mkdir(parents=True)
    write_json(docs / "manifest.json", manifest)
    return split


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a synthetic repository and point the CLI at it.

    Args:
        tmp_path: The test's temporary directory.
        monkeypatch: Redirects the CLI's repository root.

    Returns:
        The synthetic repository root.
    """
    _config(tmp_path)
    _split(tmp_path)
    monkeypatch.setattr(eval_cli, "REPO_ROOT", tmp_path)
    return tmp_path


def _factory(
    engine: ReferenceEngine,
) -> Callable[[EngineConfig], ConnectedEngine | EngineFailure]:
    """Wrap a reference model as the CLI's engine factory.

    Args:
        engine: The reference model.

    Returns:
        A factory connecting it.
    """

    def connect(_config: EngineConfig) -> ConnectedEngine:
        return ConnectedEngine(
            engine=engine,
            capabilities={"lemonade_version": LEMONADE_VERSION},
            close=lambda: None,
        )

    return connect


def _run(
    *extra: str,
    condition: str = "grammar",
    engine: ReferenceEngine | None = None,
    git: tuple[str, bool] = GIT_CLEAN,
) -> int:
    """Run the CLI's `run` subcommand against the synthetic repository.

    Args:
        *extra: Further arguments.
        condition: The condition to run.
        engine: The model; a healthy reference model when None.
        git: The commit and dirty flag.

    Returns:
        The exit code.
    """
    model = engine or ReferenceEngine(SAMPLES, model_identity=IDENTITY)
    return eval_cli.run(
        [
            "run",
            "--split",
            SPLIT,
            "--set",
            "test_gold",
            "--condition",
            condition,
            *extra,
        ],
        git=git,
        engine_factory=_factory(model),
        executor=ReferenceExecutor(SAMPLES),
    )


def _finished(root: Path, out: str = "results") -> list[Path]:
    """List the finished run directories.

    Args:
        root: The synthetic repository root.
        out: The results directory.

    Returns:
        Every `eval-*` directory.
    """
    return sorted((root / out).glob("eval-*"))


def test_a_clean_run_writes_the_final_directory(repo: Path) -> None:
    """A perfect model scores every sample, and the run lands in place."""
    assert _run() == 0

    (final,) = _finished(repo)
    assert sorted(p.name for p in final.iterdir()) == sorted(eval_cli.RUN_FILES)
    report = json.loads((final / "report.json").read_text("utf-8"))
    assert report["overall"]["task_success"]["k"] == 3
    assert report["condition"] == "grammar"
    run = json.loads((final / "run.json").read_text("utf-8"))
    assert run["identity"]["model_identity"] == IDENTITY
    assert run["identity"]["git_dirty"] is False


def test_refuses_a_dirty_tree(repo: Path) -> None:
    """A modified tracked file refuses the run.

    Args:
        repo: The synthetic repository root.
    """
    assert _run(git=GIT_DIRTY) == 1
    assert not (repo / "results").exists()


def test_refuses_missing_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run whose model cannot be pinned to a file does not start.

    Args:
        tmp_path: The test's temporary directory.
        monkeypatch: Redirects the CLI's repository root.
    """
    _config(tmp_path, provenance=False)
    _split(tmp_path)
    monkeypatch.setattr(eval_cli, "REPO_ROOT", tmp_path)

    assert _run() == 1


def test_refuses_a_split_that_is_not_the_committed_one(repo: Path) -> None:
    """The run must be on the split docs/dataset/ records.

    Args:
        repo: The synthetic repository root.
    """
    committed = repo / "docs" / "dataset" / "manifest.json"
    manifest = json.loads(committed.read_text("utf-8"))
    manifest["split_id"] = "0" * 16
    write_json(committed, manifest)

    assert _run() == 1


def test_refuses_a_split_whose_files_changed(repo: Path) -> None:
    """A split file that no longer matches its manifest refuses the run.

    Args:
        repo: The synthetic repository root.
    """
    with (repo / SPLIT / "train.jsonl").open("a", encoding="utf-8") as f:
        f.write("{}\n")

    assert _run() == 1


def test_refuses_a_model_identity_mismatch(repo: Path) -> None:
    """The engine must be the model the config names.

    Args:
        repo: The synthetic repository root.
    """
    other = ReferenceEngine(SAMPLES, model_identity="another@model")

    assert _run(engine=other) == 1
    assert not (repo / "results").exists()


def test_refuses_a_failed_context_preflight(repo: Path) -> None:
    """A prompt that cannot fit the context refuses the run up front.

    Args:
        repo: The synthetic repository root.
    """
    overflowing = ReferenceEngine(
        SAMPLES,
        model_identity=IDENTITY,
        preflight_failure=EngineFailure(
            ENGINE_UNAVAILABLE, "the request exceeds the context size"
        ),
    )

    assert _run(engine=overflowing) == 1
    assert len(overflowing.calls) == 1
    assert not (repo / "results").exists()


def test_refuses_to_finalize_with_infrastructure_failures(repo: Path) -> None:
    """An unscored sample keeps the run partial; nothing final is written.

    Args:
        repo: The synthetic repository root.
    """
    down = ReferenceEngine(
        SAMPLES,
        model_identity=IDENTITY,
        unavailable_for=frozenset({"gold_014"}),
    )

    assert _run(engine=down) == 1

    assert _finished(repo) == []
    (partial,) = (repo / "results").glob(".eval-*.partial")
    lines = (partial / "samples.partial.jsonl").read_text("utf-8")
    assert "gold_014" not in lines
    assert lines.count("\n") == 2


@pytest.mark.usefixtures("repo")
def test_an_unfinished_run_is_not_silently_restarted() -> None:
    """A partial run is only ever continued deliberately."""
    down = ReferenceEngine(
        SAMPLES,
        model_identity=IDENTITY,
        unavailable_for=frozenset({"gold_014"}),
    )
    assert _run(engine=down) == 1

    assert _run() == 1


def test_resume_skips_finished_samples(repo: Path) -> None:
    """A resumed run asks the model only for what is still unscored.

    Args:
        repo: The synthetic repository root.
    """
    down = ReferenceEngine(
        SAMPLES,
        model_identity=IDENTITY,
        unavailable_for=frozenset({"gold_014"}),
    )
    assert _run(engine=down) == 1
    healthy = ReferenceEngine(SAMPLES, model_identity=IDENTITY)

    assert _run("--resume", engine=healthy) == 0

    prompts = [call.prompt for call in healthy.calls if call.max_tokens > 1]
    gold_014 = next(s for s in SAMPLES if s.sample_id == "gold_014")
    assert prompts == [gold_014.prompt_text]
    (final,) = _finished(repo)
    records = (final / "samples.jsonl").read_text("utf-8").splitlines()
    assert [json.loads(line)["sample_id"] for line in records] == [
        "gold_001",
        "gold_014",
        "gold_062",
    ]


def test_rerun_is_byte_identical(repo: Path) -> None:
    """The same run, written twice, is the same bytes; timings aside.

    Args:
        repo: The synthetic repository root.
    """
    assert _run("--out", "first") == 0
    assert _run("--out", "second") == 0

    (first,) = _finished(repo, "first")
    (second,) = _finished(repo, "second")
    assert first.name == second.name
    for name in ("run.json", "samples.jsonl", "report.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_an_existing_run_is_left_unchanged(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running the same run again reports it exists and writes nothing.

    Args:
        repo: The synthetic repository root.
        capsys: Captures the CLI's output.
    """
    assert _run() == 0
    (final,) = _finished(repo)
    before = (final / "samples.jsonl").read_bytes()

    assert _run() == 0

    assert "UNCHANGED" in capsys.readouterr().out
    assert (final / "samples.jsonl").read_bytes() == before


def _publish(*runs: Path) -> int:
    """Run the CLI's `publish` subcommand.

    Args:
        *runs: The run directories to publish.

    Returns:
        The exit code.
    """
    return eval_cli.run(
        ["publish", "--runs", *(str(run) for run in runs)], git=GIT_CLEAN
    )


def test_publish_writes_the_committed_layout(repo: Path) -> None:
    """Both conditions' runs land under docs/evaluation/baseline/.

    Args:
        repo: The synthetic repository root.
    """
    assert _run(condition="no-grammar") == 0
    assert _run(condition="grammar") == 0

    assert _publish(*_finished(repo)) == 0

    published = repo / "docs" / "evaluation" / "baseline"
    manifest = json.loads((published / "manifest.json").read_text("utf-8"))
    assert sorted((r["set"], r["condition"]) for r in manifest["runs"]) == [
        ("test_gold", "grammar"),
        ("test_gold", "no-grammar"),
    ]
    for name, record in manifest["files"].items():
        assert file_record(published / name) == record
    front = (published / "BASELINE.md").read_text("utf-8")
    assert "| Metric | no-grammar | grammar |" in front
    assert IDENTITY in front


def test_publish_refuses_a_pilot_run(repo: Path) -> None:
    """A limited run is never published as the baseline.

    Args:
        repo: The synthetic repository root.
    """
    assert _run("--limit", "1", condition="no-grammar") == 0
    assert _run("--limit", "1", condition="grammar") == 0

    assert _publish(*_finished(repo)) == 1
    assert not (repo / "docs" / "evaluation").exists()


def test_publish_refuses_an_incomplete_set_of_runs(repo: Path) -> None:
    """Every configured set must be published under every condition.

    Args:
        repo: The synthetic repository root.
    """
    assert _run(condition="grammar") == 0

    assert _publish(*_finished(repo)) == 1


def test_publish_refuses_a_hand_edited_report(repo: Path) -> None:
    """A report that does not follow from its samples is refused.

    Args:
        repo: The synthetic repository root.
    """
    assert _run(condition="no-grammar") == 0
    assert _run(condition="grammar") == 0
    runs = _finished(repo)
    report_path = runs[0] / "report.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["overall"]["task_success"]["k"] = 0
    write_json(report_path, report)

    assert _publish(*runs) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
