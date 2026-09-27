# Copyright 2026 PyMOL Copilot contributors.
"""Run the offline evaluation, and publish a finished baseline.

Two subcommands:

    bazel run //src/pmc_eval:eval_cli -- run \\
        --split data/splits/split-<id> --set test_gold --condition grammar
    bazel run //src/pmc_eval:eval_cli -- publish \\
        --runs results/eval-<id> results/eval-<id> ...

`run` evaluates one set under one condition against the model the
config names, and writes `results/eval-<id>/` holding `run.json`,
`samples.jsonl`, `report.json` and `timings.jsonl`. The id is a digest
of everything that decides the run's result -- the harness and grader
versions, the config, the split and set, the condition, the model and
its provenance, the contract versions and the commit -- so the same run
lands in the same directory and an existing one is never overwritten.

A run checkpoints every sample as it finishes, into a hidden partial
directory beside the final one, and `--resume` picks it up again. It
refuses to finalize while any sample is still unscored because of an
infrastructure failure: such a sample says nothing about the model, and
dropping it would bias the result.

`publish` copies a complete set of finished runs -- every set under
every condition the config lists -- into `docs/evaluation/baseline/`,
which is committed, with a digest manifest and `BASELINE.md`.

Both refuse a dirty working tree unless `--allow-dirty` is given, and
`publish` refuses any run that was dirty: a result whose recorded
commit does not contain the code that produced it cannot be reproduced
from that record. Untracked files do not count, as nothing untracked
can reach a Bazel target without a tracked BUILD change.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import dataclasses
import hashlib
import json
import os
import secrets
import shutil
import statistics
import subprocess
import sys
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.inference.lemonade import connect_lemonade
from pmc_core.card import CARD_VERSION
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.executor import execute
from pmc_core.prompt import PROMPT_VERSION
from pmc_data.manifest import InvalidManifestError
from pmc_data.manifest import file_record
from pmc_data.manifest import read_manifest
from pmc_data.manifest import sha256_of
from pmc_data.manifest import validate_manifest
from pmc_data.manifest import write_json
from pmc_data.sample import PINNED_PYMOL_WHEEL
from pmc_data.sample import InvalidSampleError
from pmc_data.sample import Sample
from pmc_data.sample import current_versions
from pmc_data.sample import read_samples
from pmc_eval.config import EngineConfig
from pmc_eval.config import EvalConfig
from pmc_eval.config import InvalidConfigError
from pmc_eval.config import load_config
from pmc_eval.grade import GRADER_VERSION
from pmc_eval.metrics import REPORT_VERSION
from pmc_eval.metrics import aggregate
from pmc_eval.metrics import render_markdown
from pmc_eval.prompt import REPAIR_PROMPT_VERSION
from pmc_eval.prompt import BrokenLineageError
from pmc_eval.prompt import snapshot_for
from pmc_eval.record import InfraFailure
from pmc_eval.record import InvalidRecordError
from pmc_eval.record import SampleRecord
from pmc_eval.runner import HARNESS_VERSION
from pmc_eval.runner import NORMALIZATION
from pmc_eval.runner import Condition
from pmc_eval.runner import VersionDriftError
from pmc_eval.runner import check_versions
from pmc_eval.runner import grammar_text
from pmc_eval.runner import run_sample

#: The repository root, resolved the way Bazel's own `bazel run`
#: convention expects so output lands in the real source tree.
REPO_ROOT = Path(
    os.environ.get(
        "BUILD_WORKSPACE_DIRECTORY", Path(__file__).resolve().parents[2]
    )
)

DEFAULT_CONFIG = Path("configs") / "evaluation" / "baseline.json"
DEFAULT_OUT = Path("results")
DEFAULT_DATASET_MANIFEST = Path("docs") / "dataset" / "manifest.json"
DEFAULT_PUBLISHED = Path("docs") / "evaluation" / "baseline"

#: The files a finished run directory holds.
RUN_FILES = ("run.json", "samples.jsonl", "report.json", "timings.jsonl")

#: The version of the published layout and its manifest.
PUBLISH_VERSION = 1

_PARTIAL_SAMPLES = "samples.partial.jsonl"
_PARTIAL_TIMINGS = "timings.partial.jsonl"

#: The exit code for a refusal, or for a run left incomplete: nothing
#: final was written.
_EXIT_REFUSED = 1


def _resolve(path: Path) -> Path:
    """Resolve a command-line path against the repository root.

    Args:
        path: The path as given.

    Returns:
        The path itself if absolute, else under REPO_ROOT.
    """
    return path if path.is_absolute() else REPO_ROOT / path


def _relative(path: Path) -> str:
    """Render a path relative to the repository root when inside it.

    Args:
        path: The path.

    Returns:
        A repository-relative POSIX path, or the path unchanged.
    """
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _refuse(message: str) -> int:
    """Report a refusal.

    Args:
        message: Why nothing was written.

    Returns:
        The refusal exit code.
    """
    print(f"REFUSED: {message}", file=sys.stderr)
    return _EXIT_REFUSED


def git_state(root: Path) -> tuple[str, bool]:
    """Read the commit and whether any tracked file is modified.

    Args:
        root: The repository root.

    Returns:
        The HEAD commit and True when a tracked file differs from it.
    """
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "-uno"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


@dataclass(frozen=True)
class ConnectedEngine:
    """An engine ready to evaluate, with what its probe proved.

    Attributes:
        engine: The engine.
        capabilities: What its startup probe proved, recorded in the run.
        close: Releases the engine.
    """

    engine: InferenceEngine
    capabilities: Mapping[str, Any]
    close: Callable[[], None]


#: Connects the engine a config names. Injectable so a test evaluates a
#: fake model through the same CLI.
type ENGINE_FACTORY = Callable[[EngineConfig], ConnectedEngine | EngineFailure]


def connect_engine(config: EngineConfig) -> ConnectedEngine | EngineFailure:
    """Connect and prove a local Lemonade engine.

    Args:
        config: The engine to connect.

    Returns:
        The connected engine, or the probe's first failure.
    """
    engine = connect_lemonade(
        base_url=config.base_url,
        model_name=config.model_name,
        checkpoint=config.checkpoint,
        backend=config.backend,
        context_size=config.context_size,
        connect_timeout_seconds=config.connect_timeout_seconds,
        read_timeout_seconds=config.read_timeout_seconds,
    )
    if isinstance(engine, EngineFailure):
        return engine
    capabilities = dataclasses.asdict(engine.capabilities)
    capabilities["llamacpp_args"] = _loaded_llamacpp_args(config)
    return ConnectedEngine(
        engine=engine, capabilities=capabilities, close=engine.close
    )


def _loaded_llamacpp_args(config: EngineConfig) -> str | None:
    """Read the extra llama.cpp arguments the loaded model runs with.

    They carry the pinned chat-template date (configs/evaluation/
    README.md), which the adapter's probe does not check. Read from the
    same local health endpoint the probe just proved, right after it
    loaded the model.

    Args:
        config: The connected engine's config.

    Returns:
        The loaded model's `llamacpp_args`, or None if health does not
        report them.
    """
    try:
        response = httpx.get(
            config.base_url.rstrip("/") + "/api/v1/health",
            timeout=config.connect_timeout_seconds,
            follow_redirects=False,
        )
        health = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(health, dict):
        return None
    loaded = health.get("all_models_loaded")
    for model in loaded if isinstance(loaded, list) else []:
        if isinstance(model, dict) and model.get("model_name") == (
            config.model_name
        ):
            options = model.get("recipe_options")
            if isinstance(options, dict):
                args = options.get("llamacpp_args")
                return args if isinstance(args, str) else None
    return None


def _digest(material: Mapping[str, Any]) -> str:
    """Derive a short identity from a JSON-safe mapping.

    Args:
        material: What the identity is a digest of.

    Returns:
        Sixteen hex digits of its SHA-256.
    """
    text = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _preflight(
    engine: InferenceEngine, samples: Sequence[Sample], condition: Condition
) -> EngineFailure | None:
    """Prove the longest prompt in the set fits the engine's context.

    An overflowing prompt comes back from Lemonade as an HTTP error, the
    same typed failure as an unreachable server, on every retry. Found
    here, before any sample runs, it is one clear refusal rather than a
    run that can never finish.

    Args:
        engine: The engine under evaluation.
        samples: The set about to run.
        condition: The run's condition, for its deadline.

    Returns:
        The engine's failure, or None when the prompt fits.
    """
    longest = max(samples, key=lambda sample: len(sample.prompt_text))
    outcome = engine.complete(
        CompletionRequest(
            prompt=longest.prompt_text,
            grammar=None,
            max_tokens=1,
            deadline_seconds=condition.deadline_seconds,
        ),
        cancel=CancelToken(),
    )
    return outcome if isinstance(outcome, EngineFailure) else None


def _json_line(data: Mapping[str, Any]) -> str:
    """Render one JSONL line deterministically.

    Args:
        data: The mapping.

    Returns:
        The line, newline-terminated.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"


def _append(path: Path, line: str) -> None:
    """Append one line and make it durable before moving on.

    A run killed mid-write can leave the file ending in a torn line with
    no newline; the new line is started on a line of its own, so it is
    never glued onto that fragment and lost with it.

    Args:
        path: The file.
        line: The line to append.
    """
    torn = False
    if path.is_file() and path.stat().st_size > 0:
        with path.open("rb") as existing:
            existing.seek(-1, os.SEEK_END)
            torn = existing.read(1) != b"\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(("\n" if torn else "") + line)
        handle.flush()
        os.fsync(handle.fileno())


def _read_lines(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL checkpoint, tolerating a torn final line.

    A run killed mid-write can leave its last line incomplete; that
    sample is simply run again.

    Args:
        path: The file, which may not exist.

    Returns:
        Every complete record.
    """
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _material(
    *,
    config: EvalConfig,
    config_path: Path,
    manifest: Mapping[str, Any],
    set_name: str,
    condition: Condition,
    limit: int | None,
    connected: ConnectedEngine,
    git: tuple[str, bool],
) -> dict[str, Any]:
    """Assemble everything a run's result depends on.

    Args:
        config: The evaluation config.
        config_path: Its file.
        manifest: The split's validated manifest.
        set_name: The evaluation set.
        condition: The condition.
        limit: The sample limit, if the run is a pilot.
        connected: The connected engine.
        git: The commit and dirty flag.

    Returns:
        The identity material, hashed into the run id.
    """
    return {
        "harness_version": HARNESS_VERSION,
        "grader_version": GRADER_VERSION,
        "repair_prompt_version": REPAIR_PROMPT_VERSION,
        "report_version": REPORT_VERSION,
        "normalization": NORMALIZATION,
        "config_sha256": sha256_of(config_path),
        "split_id": manifest["split_id"],
        "set": set_name,
        "set_sha256": manifest["files"][f"{set_name}.jsonl"]["sha256"],
        "condition": condition.name,
        "limit": limit,
        "model_identity": connected.engine.model_identity,
        "engine_capabilities": dict(connected.capabilities),
        "engine_provenance": dict(config.engine_provenance),
        "versions": dataclasses.asdict(
            current_versions(
                card_version=CARD_VERSION, prompt_version=PROMPT_VERSION
            )
        ),
        "grammar_sha256": hashlib.sha256(
            grammar_text().encode("utf-8")
        ).hexdigest(),
        "pymol_wheel": PINNED_PYMOL_WHEEL,
        "git_commit": git[0],
        "git_dirty": git[1],
    }


def _load_run_inputs(
    args: argparse.Namespace, git: tuple[str, bool]
) -> tuple[EvalConfig, Path, Condition, dict[str, Any], list[Sample]] | str:
    """Validate everything a run reads before any engine is touched.

    Args:
        args: The parsed `run` arguments.
        git: The commit and dirty flag.

    Returns:
        The config, its path, the condition, the split manifest and the
        ordered samples; or why the run is refused.
    """
    config_path = _resolve(args.config)
    try:
        config = load_config(config_path)
        condition = config.condition(args.condition)
    except InvalidConfigError as error:
        return str(error)
    if args.set not in config.sets:
        return f"the config lists no {args.set!r} set"
    missing = config.missing_provenance()
    if missing:
        return (
            f"fill in engine_provenance first; missing {list(missing)} "
            "(see configs/evaluation/README.md)"
        )
    if git[1] and not args.allow_dirty:
        return (
            "a tracked file is modified; commit first, or pass "
            "--allow-dirty for a run that can never be published"
        )
    split = _resolve(args.split)
    try:
        manifest = validate_manifest(split)
        committed = read_manifest(_resolve(args.dataset_manifest))
    except InvalidManifestError as error:
        return str(error)
    if manifest["split_id"] != committed["split_id"]:
        return (
            f"{_relative(split)} is split {manifest['split_id']}, not the "
            f"committed split {committed['split_id']}"
        )
    try:
        samples = read_samples(split / f"{args.set}.jsonl")
    except InvalidSampleError as error:
        return str(error)
    ordered = sorted(samples, key=lambda s: (s.structure.spec_id, s.sample_id))
    if args.limit is not None:
        ordered = ordered[: args.limit]
    if not ordered:
        return f"{args.set} holds no samples"
    try:
        for sample in ordered:
            check_versions(sample)
            snapshot_for(sample)
    except (VersionDriftError, BrokenLineageError) as error:
        return str(error)
    return config, config_path, condition, manifest, ordered


def run_eval(
    args: argparse.Namespace,
    *,
    git: tuple[str, bool],
    engine_factory: ENGINE_FACTORY,
    executor: Callable[[ExecutionRequest], ExecutionReport],
) -> int:
    """Evaluate one set under one condition.

    Args:
        args: The parsed `run` arguments.
        git: The commit and dirty flag.
        engine_factory: Connects the model under evaluation.
        executor: The sidecar executor.

    Returns:
        The process exit code.
    """
    loaded = _load_run_inputs(args, git)
    if isinstance(loaded, str):
        return _refuse(loaded)
    config, config_path, condition, manifest, ordered = loaded

    connected = engine_factory(config.engine)
    if isinstance(connected, EngineFailure):
        return _refuse(
            f"the engine did not connect: {connected.category}: "
            f"{connected.message}"
        )
    try:
        identity = connected.engine.model_identity
        if identity != config.engine.model_identity:
            return _refuse(
                f"the engine is {identity!r}, not the configured "
                f"{config.engine.model_identity!r}"
            )
        for field in ("lemonade_version", "llamacpp_args"):
            reported = connected.capabilities.get(field)
            recorded = config.engine_provenance.get(field)
            if field in connected.capabilities and reported != recorded:
                return _refuse(
                    f"the engine reports {field} {reported!r}, but "
                    f"engine_provenance records {recorded!r}"
                )
        failure = _preflight(connected.engine, ordered, condition)
        if failure is not None:
            return _refuse(
                "the longest prompt does not complete: "
                f"{failure.category}: {failure.message}"
            )
        material = _material(
            config=config,
            config_path=config_path,
            manifest=manifest,
            set_name=args.set,
            condition=condition,
            limit=args.limit,
            connected=connected,
            git=git,
        )
        return _run_samples(
            args,
            config=config,
            condition=condition,
            material=material,
            ordered=ordered,
            engine=connected.engine,
            executor=executor,
        )
    finally:
        connected.close()


def _run_samples(
    args: argparse.Namespace,
    *,
    config: EvalConfig,
    condition: Condition,
    material: Mapping[str, Any],
    ordered: Sequence[Sample],
    engine: InferenceEngine,
    executor: Callable[[ExecutionRequest], ExecutionReport],
) -> int:
    """Run, checkpoint and finalize every sample of one run.

    Args:
        args: The parsed `run` arguments.
        config: The evaluation config.
        condition: The condition.
        material: The run's identity material.
        ordered: The samples, in run order.
        engine: The model under evaluation.
        executor: The sidecar executor.

    Returns:
        The process exit code.
    """
    run_id = _digest(material)
    out = _resolve(args.out)
    final = out / f"eval-{run_id}"
    if final.exists():
        print(f"UNCHANGED {_relative(final)}: this run already exists")
        return 0
    partial = out / f".eval-{run_id}.partial"
    if partial.exists() and not args.resume:
        return _refuse(
            f"{_relative(partial)} holds an unfinished run; pass --resume "
            "to continue it"
        )
    partial.mkdir(parents=True, exist_ok=True)
    write_json(
        partial / "run.json",
        {
            "run_id": run_id,
            "identity": dict(material),
            "samples": len(ordered),
            "regeneration": (
                "bazel run //src/pmc_eval:eval_cli -- run "
                f"--config {args.config.as_posix()} "
                f"--split {args.split.as_posix()} --set {args.set} "
                f"--condition {condition.name}"
                + ("" if args.limit is None else f" --limit {args.limit}")
            ),
        },
    )
    # A sample is done only once both its record and its timings are
    # checkpointed: a run killed between the two appends would otherwise
    # skip the sample forever and `_finalize` would never accept the run.
    done = {
        record["sample_id"]
        for record in _read_lines(partial / _PARTIAL_SAMPLES)
    } & {row["sample_id"] for row in _read_lines(partial / _PARTIAL_TIMINGS)}
    unscored: list[InfraFailure] = []
    for number, sample in enumerate(ordered, start=1):
        if sample.sample_id in done:
            continue
        result: SampleRecord | InfraFailure | None = None
        for _ in range(1 + config.infra_retries):
            result = run_sample(
                sample,
                engine=engine,
                condition=condition,
                executor=executor,
                validation_deadline_seconds=config.sidecar_deadline_seconds,
            )
            if isinstance(result, SampleRecord):
                break
        if isinstance(result, SampleRecord):
            _append(partial / _PARTIAL_SAMPLES, _json_line(result.to_dict()))
            _append(
                partial / _PARTIAL_TIMINGS, _json_line(result.timings_dict())
            )
            # Flushed: under `bazel run` stdout is a pipe, and a run
            # lasts hours, so an unflushed progress line would only
            # appear at the end.
            print(
                f"[{number}/{len(ordered)}] {sample.sample_id} "
                f"{result.final_outcome} ({len(result.attempts)} attempts)",
                flush=True,
            )
        elif isinstance(result, InfraFailure):
            unscored.append(result)
            print(
                f"[{number}/{len(ordered)}] {sample.sample_id} UNSCORED "
                f"{result.category}: {result.message}",
                flush=True,
            )
    if unscored:
        print(
            f"INCOMPLETE: {len(unscored)} samples hit infrastructure "
            f"failures and are unscored; fix the engine or sidecar and "
            f"rerun with --resume ({_relative(partial)})",
            file=sys.stderr,
        )
        return _EXIT_REFUSED
    return _finalize(partial, final, condition, ordered)


def _finalize(
    partial: Path, final: Path, condition: Condition, ordered: Sequence[Sample]
) -> int:
    """Write a finished run's files and move it into place.

    Args:
        partial: The checkpoint directory.
        final: The run's final directory.
        condition: The condition.
        ordered: Every sample the run had to score.

    Returns:
        The process exit code.
    """
    by_id: dict[str, SampleRecord] = {}
    try:
        for data in _read_lines(partial / _PARTIAL_SAMPLES):
            record = SampleRecord.from_dict(data)
            by_id[record.sample_id] = record
    except InvalidRecordError as error:
        return _refuse(f"{_relative(partial)}: {error}")
    timings = {
        row["sample_id"]: row for row in _read_lines(partial / _PARTIAL_TIMINGS)
    }
    expected = {sample.sample_id for sample in ordered}
    if set(by_id) != expected or set(timings) != expected:
        return _refuse(
            f"{_relative(partial)} does not hold exactly this run's samples"
        )
    records = [by_id[key] for key in sorted(by_id)]
    (partial / "samples.jsonl").write_text(
        "".join(_json_line(record.to_dict()) for record in records),
        encoding="utf-8",
        newline="\n",
    )
    (partial / "timings.jsonl").write_text(
        "".join(_json_line(timings[key]) for key in sorted(timings)),
        encoding="utf-8",
        newline="\n",
    )
    write_json(
        partial / "report.json", aggregate(records, condition=condition.name)
    )
    (partial / _PARTIAL_SAMPLES).unlink()
    (partial / _PARTIAL_TIMINGS).unlink()
    partial.replace(final)
    print(f"WROTE {_relative(final)}")
    return 0


class InvalidRunError(ValueError):
    """A run directory is incomplete, or its report does not follow."""


def read_run(
    directory: Path,
) -> tuple[dict[str, Any], list[SampleRecord], dict[str, Any]]:
    """Read a finished run and prove its report follows from its samples.

    Args:
        directory: The run directory.

    Returns:
        Its `run.json`, its records and its report.

    Raises:
        InvalidRunError: If a file is missing or malformed, or the report
            is not exactly what its samples aggregate to.
    """
    for name in RUN_FILES:
        if not (directory / name).is_file():
            raise InvalidRunError(f"{directory}: missing {name}")
    try:
        run = json.loads((directory / "run.json").read_text("utf-8"))
        report = json.loads((directory / "report.json").read_text("utf-8"))
        records = [
            SampleRecord.from_dict(json.loads(line))
            for line in (directory / "samples.jsonl")
            .read_text("utf-8")
            .splitlines()
        ]
        recomputed = aggregate(records, condition=run["identity"]["condition"])
    # ValueError covers a torn JSON line, an invalid record, and
    # `aggregate` refusing a duplicated sample or a foreign condition.
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidRunError(f"{directory}: {error}") from error
    if recomputed != report:
        raise InvalidRunError(
            f"{directory}: report.json is not what its samples aggregate to"
        )
    return run, records, report


def latency(directory: Path) -> dict[str, float | None]:
    """Summarize a run's per-attempt timings.

    Args:
        directory: The run directory.

    Returns:
        The median engine seconds and median sidecar seconds per attempt.
    """
    engine: list[float] = []
    sidecar: list[float] = []
    for row in _read_lines(directory / "timings.jsonl"):
        for attempt in row["attempts"]:
            engine.append(attempt["engine_seconds"])
            if attempt["executor_seconds"] is not None:
                sidecar.append(attempt["executor_seconds"])
    return {
        "engine_p50_seconds": statistics.median(engine) if engine else None,
        "sidecar_p50_seconds": statistics.median(sidecar) if sidecar else None,
    }


def _baseline_markdown(
    runs: Mapping[tuple[str, str], tuple[dict[str, Any], dict[str, Any], Path]],
    config: EvalConfig,
) -> str:
    """Render the published baseline's front page.

    Args:
        runs: Each (set, condition)'s run.json, report and directory.
        config: The evaluation config the runs were made under.

    Returns:
        The Markdown text.
    """
    first = next(iter(runs.values()))[0]["identity"]
    provenance = first["engine_provenance"]
    capabilities = first["engine_capabilities"]
    lines = [
        "# Untuned baseline",
        "",
        "The untuned base model, evaluated by the offline harness "
        "(docs/master_plan.md item 16) before any fine-tuning existed. "
        "Metric definitions: [../README.md](../README.md). Primary "
        "endpoint, fixed before these runs: "
        "[../PREREGISTRATION.md](../PREREGISTRATION.md).",
        "",
        "Generated by `eval_cli publish`; do not edit by hand. "
        "`tests/eval/test_committed_baseline.py` recomputes every report "
        "below from the committed samples.",
        "",
        "## What was run",
        "",
        f"- Model: `{first['model_identity']}`",
        f"- Commit: `{first['git_commit']}`",
        f"- Split: `{first['split_id']}`",
        f"- Harness {first['harness_version']}, grader "
        f"{first['grader_version']}, repair prompt "
        f"{first['repair_prompt_version']}, report "
        f"{first['report_version']}; normalization "
        f"`{first['normalization']}`",
        f"- Generation: at most {config.max_tokens} tokens, temperature 0, "
        f"context {config.engine.context_size}; "
        f"up to {config.infra_retries} retries of an infrastructure failure",
        "",
    ]
    lines += ["| Engine | |", "| --- | --- |"]
    lines += [
        f"| {key} | `{value}` |"
        for key, value in sorted({**capabilities, **provenance}.items())
    ]
    lines += ["", "## Latency (median per attempt)", ""]
    lines += [
        "| Set | Condition | Engine s | Sidecar s |",
        "| --- | --- | --- | --- |",
    ]
    for (set_name, condition), (_, _, directory) in runs.items():
        summary = latency(directory)
        lines.append(
            f"| {set_name} | {condition} | "
            f"{_seconds(summary['engine_p50_seconds'])} | "
            f"{_seconds(summary['sidecar_p50_seconds'])} |"
        )
    lines.append("")
    reports: dict[str, dict[str, Mapping[str, Any]]] = {}
    for (set_name, condition), (_, report, _) in runs.items():
        reports.setdefault(set_name, {})[condition] = report
    return "\n".join(lines) + "\n" + render_markdown(reports)


def _seconds(value: float | None) -> str:
    """Render a duration.

    Args:
        value: Seconds, or None.

    Returns:
        The duration to two decimals, or a dash.
    """
    return "-" if value is None else f"{value:.2f}"


def run_publish(args: argparse.Namespace, git: tuple[str, bool]) -> int:
    """Publish a complete set of finished runs as the committed baseline.

    Args:
        args: The parsed `publish` arguments.
        git: The commit and dirty flag.

    Returns:
        The process exit code.
    """
    if git[1] and not args.allow_dirty:
        return _refuse("a tracked file is modified; commit first")
    try:
        config = load_config(_resolve(args.config))
    except InvalidConfigError as error:
        return _refuse(str(error))
    runs: dict[
        tuple[str, str], tuple[dict[str, Any], dict[str, Any], Path]
    ] = {}
    for given in args.runs:
        directory = _resolve(given)
        try:
            run, _, report = read_run(directory)
        except InvalidRunError as error:
            return _refuse(str(error))
        identity = run["identity"]
        if identity["limit"] is not None:
            return _refuse(f"{_relative(directory)} is a limited pilot run")
        if identity["git_dirty"]:
            return _refuse(f"{_relative(directory)} ran on a dirty tree")
        key = (identity["set"], identity["condition"])
        if key in runs:
            return _refuse(f"two runs of {key[0]} under {key[1]}")
        runs[key] = (run, report, directory)
    expected = {(s, c) for s in config.sets for c in config.conditions}
    if set(runs) != expected:
        return _refuse(
            f"publish needs exactly one run of each of {sorted(expected)}; "
            f"got {sorted(runs)}"
        )
    shared = ("model_identity", "git_commit", "config_sha256", "split_id")
    for field in shared:
        values = {run["identity"][field] for run, _, _ in runs.values()}
        if len(values) != 1:
            return _refuse(f"the runs disagree on {field}: {sorted(values)}")
    # The grid and BASELINE.md's bounds come from this config, so it must
    # be the one the runs were made under.
    config_sha256 = sha256_of(_resolve(args.config))
    recorded = next(iter(runs.values()))[0]["identity"]["config_sha256"]
    if recorded != config_sha256:
        return _refuse(
            f"the runs were made under config {recorded}, not "
            f"{_relative(_resolve(args.config))} ({config_sha256})"
        )
    ordered = dict(sorted(runs.items()))

    out = _resolve(args.out)
    if out.exists():
        return _refuse(
            f"{_relative(out)} already exists; a published baseline is "
            "never replaced in place"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / f".baseline.{secrets.token_hex(4)}.incomplete"
    staging.mkdir()
    try:
        for (set_name, condition), (_, _, directory) in ordered.items():
            target = staging / set_name / condition
            target.mkdir(parents=True)
            for name in RUN_FILES:
                shutil.copyfile(directory / name, target / name)
        files = {
            path.relative_to(staging).as_posix(): file_record(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        first = next(iter(ordered.values()))[0]["identity"]
        write_json(
            staging / "manifest.json",
            {
                "publish_version": PUBLISH_VERSION,
                "model_identity": first["model_identity"],
                "git_commit": first["git_commit"],
                "config_sha256": first["config_sha256"],
                "split_id": first["split_id"],
                "runs": [
                    {
                        "set": set_name,
                        "condition": condition,
                        "run_id": run["run_id"],
                    }
                    for (set_name, condition), (run, _, _) in ordered.items()
                ],
                "files": files,
            },
        )
        (staging / "BASELINE.md").write_text(
            _baseline_markdown(ordered, config),
            encoding="utf-8",
            newline="\n",
        )
        staging.replace(out)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f"WROTE {_relative(out)}")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse this binary's command line.

    Args:
        argv: The arguments after the program name.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="evaluate one set, one condition")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--split", type=Path, required=True)
    run.add_argument("--set", required=True)
    run.add_argument("--condition", required=True)
    run.add_argument("--out", type=Path, default=DEFAULT_OUT)
    run.add_argument(
        "--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST
    )
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--allow-dirty", action="store_true")

    publish = commands.add_parser("publish", help="publish the baseline")
    publish.add_argument("--runs", type=Path, nargs="+", required=True)
    publish.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    publish.add_argument("--out", type=Path, default=DEFAULT_PUBLISHED)
    publish.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run" and args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    return args


def run(
    argv: list[str],
    *,
    git: tuple[str, bool] | None = None,
    engine_factory: ENGINE_FACTORY = connect_engine,
    executor: Callable[[ExecutionRequest], ExecutionReport] = execute,
) -> int:
    """Dispatch one subcommand.

    Args:
        argv: The arguments after the program name.
        git: The commit and dirty flag to record; read from the
            repository when None.
        engine_factory: Connects the model under evaluation.
        executor: The sidecar executor.

    Returns:
        The process exit code.
    """
    args = _parse_args(argv)
    state = git if git is not None else git_state(REPO_ROOT)
    if args.command == "run":
        return run_eval(
            args, git=state, engine_factory=engine_factory, executor=executor
        )
    return run_publish(args, state)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
