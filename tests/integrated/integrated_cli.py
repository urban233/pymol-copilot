# Copyright 2026 PyMOL Copilot contributors.
"""Run the gold set through the product, and report it against offline.

docs/master_plan.md item 19. Every sample goes through what a user does:

1. its structure is rebuilt in a live, headless PyMOL session;
2. `copilot <intent>` is typed at PyMOL's own command line, and the
   real client (`pmc_client`) sends it to the real server
   (`pmc_server.main`), which asks the model;
3. the preview is approved with `copilot_apply`;
4. the live session is graded, with the offline evaluation's grader.

`bazel run //tests/integrated:integrated_cli -- run ...` writes one
record per sample, and the server's trace of every completion
(`--trace-file`), under `docs/integration/`. `report` pairs
the records with the published offline ones and writes the comparison.

Two engines:

- `--config configs/evaluation/finetuned.json` starts the server as its
  own process, exactly as a user would, against the local model the
  config records. That needs the GPU engine up, and runs only when a
  person has agreed to it.
- `--reference` needs no model: the server runs in this process with a
  scripted engine that answers each sample's own gold plan. A correct
  plan must score every sample through the live path, which proves the
  live grader before any model is measured.

Not a test: a model run is minutes of inference and three PyMOL
processes per sample. It runs by hand through `bazel run` and writes
into the source tree through BUILD_WORKSPACE_DIRECTORY.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

import winstage

from pmc_agent.graph import with_final_newline
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineHealth
from pmc_client.bootstrap import connect_from_handoff
from pmc_client.recovery import RecoveryStore
from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.plan import selection_names
from pmc_core.protocol import HEALTH_ENGINE_READY
from pmc_core.snapshot import extract
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import to_json
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_eval.integrated import INTEGRATED_VERSION
from pmc_eval.integrated import OUTCOME_APPLIED
from pmc_eval.integrated import OUTCOME_NO_PLAN
from pmc_eval.integrated import OUTCOME_NOT_APPLICABLE
from pmc_eval.integrated import OUTCOME_TIMEOUT
from pmc_eval.integrated import IntegratedRecord
from pmc_eval.integrated import compare_condition
from pmc_eval.integrated import grade_live
from pmc_eval.integrated import read_apply
from pmc_eval.integrated import read_offline
from pmc_eval.integrated import previewed_commands
from pmc_eval.integrated import read_preview
from pmc_eval.integrated import read_records
from pmc_eval.integrated import render_report
from pmc_eval.prompt import snapshot_for
from pmc_server.config import GenerationOptions
from pmc_server.main import serve

#: The repository root, resolved the way `bazel run` expects, so output
#: lands in the real source tree.
REPO_ROOT = Path(
    os.environ.get(
        "BUILD_WORKSPACE_DIRECTORY", Path(__file__).resolve().parents[2]
    )
)

DEFAULT_OUT = Path("docs") / "integration"
DEFAULT_OFFLINE = Path("docs") / "evaluation" / "finetuned"
DEFAULT_MANIFEST = Path("docs") / "dataset" / "manifest.json"
CONDITIONS = ("grammar", "no-grammar")
SET_NAME = "test_gold"

#: How long one console command may take before the run stops. The
#: client's own transport timeout (200 s) binds first.
COMMAND_DEADLINE_SECONDS = 900.0

#: How long the server may take to load the model and write its handoff.
SERVER_START_SECONDS = 600.0


class ConsoleDriver:
    """Run `copilot*` commands through PyMOL's own dispatch, synchronously.

    `cmd.do()` only queues a command on PyMOL's thread. The client
    registers its commands through this object's `extend`, which wraps
    each one to signal when it has finished, so `run` can wait for it.
    The same pattern as `tests/e2e/scenario_support.ConsoleDriver`.
    """

    def __init__(self, cmd: Any, deadline_seconds: float) -> None:
        """Wrap PyMOL's `cmd`.

        Args:
            cmd: PyMOL's `cmd` module.
            deadline_seconds: How long one command may take.
        """
        self._cmd = cmd
        self._deadline = deadline_seconds
        self._finished = threading.Event()

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register one command, wrapped to signal completion.

        Args:
            name: The command's name.
            callback: What it runs.
        """

        def synchronized(argument: str = "") -> None:
            finished = self._finished
            try:
                callback(argument)
            finally:
                finished.set()

        self._cmd.extend(name, synchronized)

    def __getattr__(self, name: str) -> Any:
        """Forward everything else to PyMOL's `cmd`.

        Args:
            name: The attribute.

        Returns:
            `cmd`'s attribute.
        """
        return getattr(self._cmd, name)

    def run(self, command_line: str) -> float:
        """Dispatch one command line and wait for it to finish.

        Args:
            command_line: What a user would type at PyMOL's prompt.

        Returns:
            Seconds it took.

        Raises:
            TimeoutError: If it did not finish within the deadline.
        """
        finished = self._finished = threading.Event()
        started = time.monotonic()
        self._cmd.do(command_line)
        if not finished.wait(self._deadline):
            raise TimeoutError(f"{command_line!r} did not finish")
        return time.monotonic() - started


class ReferenceEngine:
    """A scripted engine that answers the current sample's gold plan."""

    def __init__(self) -> None:
        """Start with no plan to answer."""
        self.plan_pml = ""

    @property
    def model_identity(self) -> str:
        """Return a fixed identity naming the reference.

        Returns:
            `reference@gold-plan`.
        """
        return "reference@gold-plan"

    def complete(
        self, request: CompletionRequest, *, cancel: CancelToken
    ) -> CompletionResult:
        """Answer the current plan, whatever was asked.

        Args:
            request: Ignored.
            cancel: Ignored.

        Returns:
            The current sample's gold plan.
        """
        del request, cancel
        return CompletionResult(self.plan_pml, self.model_identity, STOP_END)

    def health(self) -> EngineHealth:
        """Report ready.

        Returns:
            Ready health naming the reference.
        """
        return EngineHealth(
            state=HEALTH_ENGINE_READY,
            engine="reference",
            engine_version="1",
            device="cpu",
            model_identity=self.model_identity,
            failure=None,
        )


def _sha256(text: str) -> str:
    """Hash text.

    Args:
        text: The text.

    Returns:
        Its SHA-256, hex.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resolve(path: Path) -> Path:
    """Resolve a command-line path against the repository root.

    Args:
        path: The path as given.

    Returns:
        An absolute path.
    """
    return path if path.is_absolute() else REPO_ROOT / path


def gold_samples() -> tuple[Sample, ...]:
    """Read the gold set, and prove it is the split's `test_gold`.

    Returns:
        The 68 gold samples.

    Raises:
        SystemExit: If the file is not the one the split manifest records.
    """
    manifest = json.loads(
        _resolve(DEFAULT_MANIFEST).read_text(encoding="utf-8")
    )
    recorded = manifest["files"][f"{SET_NAME}.jsonl"]["sha256"]
    actual = hashlib.sha256(DEFAULT_GOLD_SAMPLES_PATH.read_bytes()).hexdigest()
    if actual != recorded:
        raise SystemExit(
            f"{DEFAULT_GOLD_SAMPLES_PATH} is not the split's {SET_NAME} "
            f"(SHA-256 {actual}, the manifest records {recorded})"
        )
    return read_samples(DEFAULT_GOLD_SAMPLES_PATH)


class Trace:
    """Read what the server appended to its trace since the last read."""

    def __init__(self, path: Path) -> None:
        """Follow `path` from its current end.

        Args:
            path: The server's `--trace-file`.
        """
        self._path = path
        self._offset = path.stat().st_size if path.exists() else 0

    def new_lines(self) -> tuple[dict[str, Any], ...]:
        """Read the lines appended since the last call.

        Returns:
            The decoded trace lines.
        """
        with self._path.open("rb") as handle:
            handle.seek(self._offset)
            data = handle.read()
        self._offset += len(data)
        return tuple(
            json.loads(line) for line in data.decode("utf-8").splitlines()
        )


def _previewed_plan(attempts: Sequence[dict[str, Any]]) -> ActionPlan | None:
    """Parse the plan the server previewed from its last completion.

    Args:
        attempts: This request's trace lines.

    Returns:
        The plan, or None if the last attempt did not parse.
    """
    if not attempts or attempts[-1].get("outcome") != "completion":
        return None
    parsed = parse_pml(with_final_newline(attempts[-1]["text"]))
    return None if isinstance(parsed, ParseRejection) else parsed


def run_sample(
    sample: Sample,
    *,
    condition: str,
    cmd: Any,
    driver: ConsoleDriver,
    output: list[str],
    trace: Trace,
) -> IntegratedRecord:
    """Run one gold sample through the product and grade it live.

    Args:
        sample: The gold sample.
        condition: `grammar` or `no-grammar`.
        cmd: PyMOL's `cmd` module.
        driver: The console driver the client is registered on.
        output: The list the client prints into; drained here.
        trace: The server's trace.

    Returns:
        The sample's record.
    """
    snapshot = snapshot_for(sample)
    cmd.delete("all")
    reconstruct(cmd, snapshot)
    live_sha256 = _sha256(to_json(extract(cmd, snapshot.name)))
    output.clear()
    trace.new_lines()
    base: dict[str, Any] = {
        "sample_id": sample.sample_id,
        "condition": condition,
        "category": sample.category,
        "spec_id": sample.structure.spec_id,
        "live_snapshot_sha256": live_sha256,
        "prompt_skew": live_sha256 != sample.structure.snapshot_sha256,
        "assertions": (),
        "plan_pml": None,
        "live_fingerprint": None,
        "live_selection_counts": (),
        "apply_seconds": None,
        "task_success": False,
    }
    try:
        preview_seconds = driver.run(f"copilot {sample.intent}")
    except TimeoutError:
        return IntegratedRecord(
            **base,
            outcome=OUTCOME_TIMEOUT,
            attempts=trace.new_lines(),
            output=tuple(output),
            preview_seconds=None,
        )
    attempts = trace.new_lines()
    lines = tuple(output)
    output.clear()
    base |= {"attempts": attempts, "preview_seconds": preview_seconds}
    preview = read_preview(lines)
    plan = _previewed_plan(attempts)
    if plan is not None and preview.plan_id is not None:
        base["plan_pml"] = plan.render_pml()
    if preview.plan_id is None or plan is None:
        return IntegratedRecord(**base, outcome=OUTCOME_NO_PLAN, output=lines)
    shown = previewed_commands(lines)
    if shown != tuple(plan.render_pml().splitlines()):
        # The plan graded below is re-parsed from the server's trace; it
        # must be the plan the user was shown and approves.
        raise SystemExit(
            f"{sample.sample_id}: the traced plan {plan.render_pml()!r} is "
            f"not the previewed one {shown!r}"
        )
    if not preview.applicable:
        return IntegratedRecord(
            **base, outcome=OUTCOME_NOT_APPLICABLE, output=lines
        )
    try:
        base["apply_seconds"] = driver.run(f"copilot_apply {preview.plan_id}")
    except TimeoutError:
        return IntegratedRecord(
            **base, outcome=OUTCOME_TIMEOUT, output=lines + tuple(output)
        )
    lines += tuple(output)
    outcome = read_apply(output, preview.plan_id)
    output.clear()
    if outcome != OUTCOME_APPLIED:
        return IntegratedRecord(**base, outcome=outcome, output=lines)
    fingerprint = "sha256:" + _sha256(to_json(extract(cmd, snapshot.name)))
    counts = tuple(
        (name, int(cmd.count_atoms(name))) for name in selection_names(plan)
    )
    graded = grade_live(
        sample, plan, snapshot, fingerprint=fingerprint, selection_counts=counts
    )
    base |= {
        "live_fingerprint": fingerprint,
        "live_selection_counts": counts,
        "assertions": tuple(
            {
                "kind": result.kind,
                "passed": result.passed,
                "expected": result.expected,
                "observed": result.observed,
            }
            for result in graded.assertions
        ),
        "task_success": graded.task_success,
    }
    return IntegratedRecord(**base, outcome=OUTCOME_APPLIED, output=lines)


@contextmanager
def model_server(
    config: Path, *, condition: str, handoff: Path, trace_path: Path
) -> Iterator[list[str]]:
    """Run `pmc_server.main` as its own process, as a user would.

    Args:
        config: The evaluation config to serve from.
        condition: `grammar` or `no-grammar`.
        handoff: Where the server writes its handoff.
        trace_path: The server's trace file.

    Yields:
        The server's command line.

    Raises:
        RuntimeError: If it exits or writes no handoff in time.
    """
    argv = [
        sys.executable,
        "-m",
        "pmc_server.main",
        "--config",
        str(config),
        "--grammar" if condition == "grammar" else "--no-grammar",
        "--trace-file",
        str(trace_path),
        "--handoff",
        str(handoff),
    ]
    log_path = handoff.parent / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + SERVER_START_SECONDS
        while not handoff.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"the server did not start; see {log_path}")
            time.sleep(0.5)
        yield argv[1:]
    finally:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@contextmanager
def reference_server(
    engine: ReferenceEngine,
    *,
    condition: str,
    handoff: Path,
    trace_path: Path,
) -> Iterator[list[str]]:
    """Run the real server in this process with the reference engine.

    Args:
        engine: The scripted engine.
        condition: `grammar` or `no-grammar`.
        handoff: Where the server writes its handoff.
        trace_path: The server's trace file.

    Yields:
        A description of the server.

    Raises:
        RuntimeError: If it does not start in time.
    """
    stop = threading.Event()
    ready = threading.Event()
    thread = threading.Thread(
        target=serve,
        kwargs={
            "handoff_path": handoff,
            "generation": GenerationOptions(grammar=condition == "grammar"),
            "trace_path": trace_path,
            "engine": engine,
            "ready": lambda _port: ready.set(),
            "stop": stop,
        },
        daemon=True,
    )
    thread.start()
    try:
        if not ready.wait(60):
            raise RuntimeError("the reference server did not start")
        yield ["serve(engine=ReferenceEngine())", condition]
    finally:
        stop.set()
        thread.join(timeout=30)


def _git(*arguments: str) -> str:
    """Ask git about the repository.

    Args:
        *arguments: The git arguments.

    Returns:
        Its stripped output, or `unknown` if git is not available.
    """
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _now() -> str:
    """Return the current time, RFC3339 UTC.

    Returns:
        The timestamp.
    """
    return (
        datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _resumed(path: Path, current: dict[str, Any]) -> dict[str, Any]:
    """Continue a run's record, refusing to mix two runs in one.

    Args:
        path: The run's existing `run.json`.
        current: What this invocation would record.

    Returns:
        The original record, with this resume appended.

    Raises:
        SystemExit: If this invocation differs from the original in its
            mode, config, commit or tree.
    """
    original = json.loads(path.read_text(encoding="utf-8"))
    for key in ("mode", "config", "config_sha256", "commit", "dirty"):
        if original.get(key) != current[key]:
            raise SystemExit(
                f"{path}: resuming would mix runs; {key} was "
                f"{original.get(key)!r}, now {current[key]!r}"
            )
    resumes = [*original.get("resumes", []), current["started_at"]]
    return {**original, "resumes": resumes}


def run(arguments: argparse.Namespace) -> int:
    """Run the gold set through the product under each condition.

    Args:
        arguments: The parsed `run` command line.

    Returns:
        Zero once every condition has run.
    """
    # Stage `pymol` to a short path first: a no-op everywhere but
    # Windows (tools/winstage/winstage.py).
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore[missing-import]
    from pymol import cmd  # pyrefly: ignore[missing-import]

    samples = gold_samples()
    if arguments.samples:
        wanted = set(arguments.samples.split(","))
        samples = tuple(s for s in samples if s.sample_id in wanted)
    out = _resolve(arguments.out) / SET_NAME
    config = None if arguments.reference else _resolve(arguments.config)
    pymol.finish_launching(["pymol", "-qc"])
    engine = ReferenceEngine()
    for condition in arguments.conditions.split(","):
        if condition not in CONDITIONS:
            raise SystemExit(f"unknown condition {condition!r}")
        directory = out / condition
        directory.mkdir(parents=True, exist_ok=True)
        samples_path = directory / "samples.jsonl"
        done = (
            {record.sample_id for record in read_records(samples_path)}
            if samples_path.exists()
            else set()
        )
        if done and not arguments.resume:
            raise SystemExit(f"{samples_path} exists; pass --resume")
        todo = [s for s in samples if s.sample_id not in done]
        with tempfile.TemporaryDirectory(prefix="pmc-integrated-") as scratch:
            workdir = Path(scratch)
            handoff = workdir / "session.json"
            trace_path = directory / "trace.jsonl"
            server = (
                reference_server(
                    engine,
                    condition=condition,
                    handoff=handoff,
                    trace_path=trace_path,
                )
                if config is None
                else model_server(
                    config,
                    condition=condition,
                    handoff=handoff,
                    trace_path=trace_path,
                )
            )
            with server as server_argv:
                output: list[str] = []
                driver = ConsoleDriver(cmd, COMMAND_DEADLINE_SECONDS)
                client = connect_from_handoff(
                    # pyrefly: ignore.  __getattr__ delegates the query
                    # surface at runtime, but pyrefly cannot verify that
                    # structurally.
                    driver,
                    output.append,
                    path=handoff,
                    recovery_store=RecoveryStore(workdir),
                )
                if client is None:
                    raise SystemExit("\n".join(output))
                output.clear()
                driver.run("copilot_health")
                health = list(output)
                output.clear()
                run_record = {
                    "integrated_version": INTEGRATED_VERSION,
                    "set": SET_NAME,
                    "condition": condition,
                    "mode": "reference" if config is None else "model",
                    "config": None
                    if config is None
                    else str(config.relative_to(REPO_ROOT)),
                    "config_sha256": None
                    if config is None
                    else hashlib.sha256(config.read_bytes()).hexdigest(),
                    "commit": _git("rev-parse", "HEAD"),
                    "dirty": bool(
                        _git(
                            "status",
                            "--porcelain",
                            "--",
                            "src",
                            "tests",
                            "configs",
                        )
                    ),
                    "server": server_argv,
                    "health": health,
                    "host": f"{platform.platform()} {platform.machine()}",
                    "python": platform.python_version(),
                    "started_at": _now(),
                    "samples": len(samples),
                }
                run_path = directory / "run.json"
                if done:
                    run_record = _resumed(run_path, run_record)
                run_path.write_text(
                    json.dumps(run_record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                trace = Trace(trace_path)
                for index, sample in enumerate(todo, start=1):
                    engine.plan_pml = sample.plan_pml
                    record = run_sample(
                        sample,
                        condition=condition,
                        cmd=cmd,
                        driver=driver,
                        output=output,
                        trace=trace,
                    )
                    with samples_path.open("a", encoding="utf-8") as handle:
                        handle.write(
                            json.dumps(record.to_dict(), sort_keys=True) + "\n"
                        )
                    print(
                        f"{condition} {index}/{len(todo)} {sample.sample_id}: "
                        f"{record.outcome}, task_success={record.task_success}",
                        flush=True,
                    )
                    if record.outcome == OUTCOME_TIMEOUT:
                        raise SystemExit(
                            f"{sample.sample_id} timed out; the PyMOL session "
                            "may be busy. Rerun with --resume."
                        )
    return 0


def report(arguments: argparse.Namespace) -> int:
    """Pair the integrated records with the offline ones and write both.

    Writes `report.json` and `REPORT.md` beside the records. A sample
    the evidence leaves unexplained keeps its hand-written note from
    `notes.json` (`{sample_id: text}`), when there is one.

    Args:
        arguments: The parsed `report` command line.

    Returns:
        Zero.
    """
    out = _resolve(arguments.out)
    offline_root = _resolve(arguments.offline) / SET_NAME
    comparison: dict[str, Any] = {}
    for condition in CONDITIONS:
        path = out / SET_NAME / condition / "samples.jsonl"
        if path.exists():
            comparison[condition] = compare_condition(
                read_records(path),
                read_offline(offline_root / condition / "samples.jsonl"),
            )
    notes_path = out / "notes.json"
    notes = (
        json.loads(notes_path.read_text(encoding="utf-8"))
        if notes_path.exists()
        else {}
    )
    (out / "report.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "REPORT.md").write_text(
        render_report(
            comparison,
            title=arguments.title,
            notes=notes,
        ),
        encoding="utf-8",
    )
    for condition, block in comparison.items():
        print(
            f"{condition}: offline {block['offline']['k']}/{block['n']}, "
            f"integrated {block['integrated']['k']}/{block['n']}, "
            f"McNemar p={block['mcnemar_exact_p']:.4g}"
        )
    return 0


def summarize(arguments: argparse.Namespace) -> int:
    """Print and check a reference run: every sample must succeed.

    Args:
        arguments: The parsed `summarize` command line.

    Returns:
        Zero when every record is a TaskSuccess, one otherwise.
    """
    failed = 0
    for condition in CONDITIONS:
        path = _resolve(arguments.out) / SET_NAME / condition / "samples.jsonl"
        if not path.exists():
            continue
        records = read_records(path)
        wrong = [r.sample_id for r in records if not r.task_success]
        failed += len(wrong)
        print(
            f"{condition}: {len(records) - len(wrong)}/{len(records)} "
            f"TaskSuccess" + (f"; not: {', '.join(wrong)}" if wrong else "")
        )
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line and run the chosen subcommand.

    Args:
        argv: The arguments, without the program name.

    Returns:
        The subcommand's exit status.
    """
    parser = argparse.ArgumentParser(prog="integrated_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help=run.__doc__)
    engine = run_parser.add_mutually_exclusive_group(required=True)
    engine.add_argument("--config", type=Path)
    engine.add_argument("--reference", action="store_true")
    run_parser.add_argument("--conditions", default=",".join(CONDITIONS))
    run_parser.add_argument("--samples", default="")
    run_parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    run_parser.add_argument("--resume", action="store_true")
    report_parser = commands.add_parser("report", help=report.__doc__)
    report_parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    report_parser.add_argument("--offline", type=Path, default=DEFAULT_OFFLINE)
    report_parser.add_argument(
        "--title", default="Integrated TaskSuccess against offline"
    )
    summarize_parser = commands.add_parser("summarize", help=summarize.__doc__)
    summarize_parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    handlers = {"run": run, "report": report, "summarize": summarize}
    return handlers[arguments.command](arguments)


if __name__ == "__main__":
    raise SystemExit(main())
