# Copyright 2026 PyMOL Copilot contributors.
"""Record p50/p95 latency per stage on this machine.

docs/master_plan.md item 12. Runs the scenario 1 happy path (preview,
approve, apply) `--repetitions` times against real headless PyMOL and a
real loopback server, then the scenario 2 mid-apply-failure path once
more to measure the restore stage, timing each stage through the seams
the client and server already expose for tests. No production code is
edited to make this measurement possible: `preview_client_local` and
`approval_reverify` are each the whole console invocation's own elapsed
time (`ConsoleDriver.run`'s own return value) minus the instrumented
sub-stages within it, not threaded through `pmc_client.command` directly
-- this item's own decision, stated in its plan.

The engine is a scripted `FakeEngine` by default; `generate` is recorded
as "not measured" unless `--lemonade-base-url` names a real, reachable
Lemonade server, in which case one real `generate` call is timed per
repetition instead.

Not a test: writes `results/latency-<platform>-<node>.md` via
`BUILD_WORKSPACE_DIRECTORY`, the same shape as
`tests/integration/capture_color_indices.py`, and prints the same table
to stdout.
"""

from __future__ import annotations

import argparse
import os
import platform
import tempfile
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

from latency import DEFAULT_REPETITIONS
from latency import StageTimer
from latency import render_note
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.lemonade import connect_lemonade
from pmc_client.command import CopilotCommandClient
from pmc_client.command import register_copilot
from pmc_client.recovery import RecoveryStore
from pmc_client.transport import LoopbackPlanClient
from pmc_core.executor import execute
from pmc_core.executor import probe_fidelity
from pmc_server.transport import LoopbackPlanServer
from pmc_sidecar.child import PlanRunResult
from pmc_sidecar.child import run_plan
from preview_support import plan_id_from
from scenario_support import CREDENTIAL
from scenario_support import FIXTURE_PATH
from scenario_support import OBJECT_NAME
from scenario_support import ConsoleDriver
from scenario_support import FailColorProxy
from scenario_support import build_lifecycle

import winstage

INTENT = "Select chain A, color it red, show it as spheres, and orient on it."

_HAPPY_COMPLETION = (
    "select copilot_selection, chain A\n"
    "color red, copilot_selection\n"
    "show spheres, copilot_selection\n"
    "orient copilot_selection\n"
)


def _literal_grammar(text: str) -> str:
    """Build a GBNF grammar that forces exactly one literal completion.

    The same technique the Lemonade capability spike proved
    (`root ::= "Berlin"`) for a real engine's own grammar-canary probe:
    a real model's output is otherwise unpredictable, but `generate`'s
    own timing needs a genuine round trip, and the rest of this harness
    needs the exact scripted plan text to stay deterministic. Forcing the
    grammar, rather than trusting the model's own free output, is what
    makes both true at once.

    Args:
        text: The exact text the grammar must force.

    Returns:
        A one-rule GBNF grammar accepting only `text`.
    """
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )
    return f'root ::= "{escaped}"'


def _time_one_real_generate(timer: StageTimer, base_url: str) -> None:
    """Time exactly one real Lemonade completion.

    Forced to the canonical plan text. Connects fresh, times one
    grammar-forced `complete()` call, and closes
    the connection -- never reused across repetitions, matching every
    other real-process stage this harness measures. Raises loudly rather
    than silently skipping if Lemonade cannot be reached or does not honor
    the forcing grammar: a latency run that claims to have measured
    `generate` must have actually done so.

    Args:
        timer: Where to record `generate`'s own elapsed time.
        base_url: The real, reachable Lemonade origin.

    Raises:
        RuntimeError: If Lemonade cannot be reached, or its own output
            under the forcing grammar does not match the expected text.
    """
    engine = connect_lemonade(base_url=base_url)
    if isinstance(engine, EngineFailure):
        raise RuntimeError(
            f"could not connect to Lemonade at {base_url}: "
            f"{engine.category}: {engine.message}"
        )
    try:
        request = CompletionRequest(
            prompt=INTENT,
            grammar=_literal_grammar(_HAPPY_COMPLETION),
            max_tokens=256,
            deadline_seconds=30.0,
        )
        with timer.measure("generate"):
            result = engine.complete(request, cancel=CancelToken())
    finally:
        engine.close()
    if isinstance(result, EngineFailure) or result.text != _HAPPY_COMPLETION:
        raise RuntimeError(
            "real Lemonade did not reproduce the expected canonical plan "
            f"text under a forcing grammar: {result!r}"
        )


class _TimedTransport:
    """Delegate to a real `LoopbackPlanClient`, timing each own call."""

    def __init__(self, inner: LoopbackPlanClient, timer: StageTimer) -> None:
        """Wrap a real transport for per-call timing.

        Args:
            inner: The real transport to delegate every call to.
            timer: Where to record each call's own elapsed time.
        """
        self._inner = inner
        self._timer = timer

    def submit(self, request: Any) -> Any:
        """Time one plan submission.

        Args:
            request: Forwarded unchanged.

        Returns:
            The real transport's own response.
        """
        with self._timer.measure("submit"):
            return self._inner.submit(request)

    def apply(self, request: Any) -> Any:
        """Time one apply round trip.

        Args:
            request: Forwarded unchanged.

        Returns:
            The real transport's own response.
        """
        with self._timer.measure("apply_round_trip"):
            return self._inner.apply(request)

    def report_apply_outcome(self, request: Any) -> Any:
        """Time one outcome report.

        Args:
            request: Forwarded unchanged.

        Returns:
            The real transport's own response.
        """
        with self._timer.measure("outcome_report"):
            return self._inner.report_apply_outcome(request)

    def __getattr__(self, name: str) -> Any:
        """Forward every other call to the wrapped transport.

        Args:
            name: The attribute name being accessed.

        Returns:
            The wrapped transport's own attribute.
        """
        return getattr(self._inner, name)


class _TimedRecoveryStore(RecoveryStore):
    """A real `RecoveryStore`, timing its own `save`/`restore` calls."""

    def __init__(self, root: Path, timer: StageTimer) -> None:
        """Wrap a real recovery store for per-call timing.

        Args:
            root: Forwarded to `RecoveryStore`.
            timer: Where to record each call's own elapsed time.
        """
        super().__init__(root)
        self._timer = timer

    def save(self, cmd: Any, plan_id: str) -> Path:
        """Time one recovery-point save.

        Args:
            cmd: Forwarded unchanged.
            plan_id: Forwarded unchanged.

        Returns:
            The real store's own saved path.
        """
        with self._timer.measure("recovery_save"):
            return super().save(cmd, plan_id)

    def restore(self, cmd: Any, path: Path) -> None:
        """Time one whole-session restore and its own comparison.

        Args:
            cmd: Forwarded unchanged.
            path: Forwarded unchanged.
        """
        with self._timer.measure("restore_and_compare"):
            super().restore(cmd, path)


class _RestoreOnlyTimedRecoveryStore(RecoveryStore):
    """A real `RecoveryStore`, timing only its own `restore` call.

    Used for the one dedicated failure-path run below, not the happy-path
    repetitions: that run's own `save()` belongs to a different scenario
    (a plan that always fails mid-execution), not one of the
    `recovery_save` stage's `repetitions` normal-apply samples. Recording
    it under that same stage name -- `_TimedRecoveryStore` above times
    both calls -- would silently add one extra sample taken under
    different conditions, so `recovery_save`'s reported p50/p95 would be
    computed over `repetitions` samples while the note claims
    `repetitions - 1`.
    """

    def __init__(self, root: Path, timer: StageTimer) -> None:
        """Wrap a real recovery store for restore-only timing.

        Args:
            root: Forwarded to `RecoveryStore`.
            timer: Where to record `restore`'s own elapsed time.
        """
        super().__init__(root)
        self._timer = timer

    def restore(self, cmd: Any, path: Path) -> None:
        """Time one whole-session restore and its own comparison.

        Args:
            cmd: Forwarded unchanged.
            path: Forwarded unchanged.
        """
        with self._timer.measure("restore_and_compare"):
            super().restore(cmd, path)


def _timed_probe(
    timer: StageTimer, probe: Callable[[Any], Any]
) -> Callable[[Any], Any]:
    """Wrap a fidelity probe to time each call.

    Args:
        timer: Where to record each call's own elapsed time.
        probe: The real probe to delegate to.

    Returns:
        A wrapped probe with the same signature.
    """

    def wrapped(request: Any) -> Any:
        with timer.measure("fidelity_probe"):
            return probe(request)

    return wrapped


def _timed_dispatcher(timer: StageTimer) -> Callable[[Any, Any], PlanRunResult]:
    """Wrap the real live-apply dispatcher to time each call.

    Args:
        timer: Where to record each call's own elapsed time.

    Returns:
        A wrapped dispatcher with `run_plan`'s own signature.
    """

    def wrapped(cmd: Any, plan: Any) -> PlanRunResult:
        with timer.measure("live_dispatch"):
            return run_plan(cmd, plan)

    return wrapped


def _run_happy_path_once(
    cmd: Any, tmp_path: Path, timer: StageTimer, engine_url: str | None
) -> None:
    """Run preview, approve, and apply once, timing every stage.

    Args:
        cmd: The real PyMOL `cmd` module.
        tmp_path: A fresh, private root for this repetition's recovery
            store.
        timer: Where to record each stage's own elapsed time.
        engine_url: A real Lemonade base URL, or None for the scripted
            engine.
    """
    completions = [CompletionResult(_HAPPY_COMPLETION, "m-1", STOP_END)]
    lifecycle = build_lifecycle(completions=completions, executor=execute)
    server = LoopbackPlanServer(
        CREDENTIAL,
        lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )
    driver = ConsoleDriver(cmd)
    output: list[str] = []
    before_count = len(timer.samples)
    try:
        server.start()
        transport = _TimedTransport(
            LoopbackPlanClient(server.port, CREDENTIAL), timer
        )
        store = _TimedRecoveryStore(tmp_path, timer)
        client = CopilotCommandClient(
            transport,  # pyrefly: ignore.
            output.append,
            probe=_timed_probe(timer, probe_fidelity),
            recovery_store=store,
            dispatcher=_timed_dispatcher(timer),
        )
        client.register(driver)  # pyrefly: ignore.
        preview_total = driver.run(f"copilot {INTENT}")
        plan_id = plan_id_from(output)
        apply_total = driver.run(f"copilot_apply {plan_id}")
    finally:
        server.close()
        cmd.delete("all")
        cmd.load(str(FIXTURE_PATH), OBJECT_NAME)

    # This repetition's own instrumented samples, to derive the two
    # client-local remainders from the console totals above.
    this_repetition = timer.samples[before_count:]
    fidelity = sum(s for n, s in this_repetition if n == "fidelity_probe")
    submit = sum(s for n, s in this_repetition if n == "submit")
    apply_parts = sum(
        s
        for n, s in this_repetition
        if n
        in (
            "apply_round_trip",
            "recovery_save",
            "live_dispatch",
            "outcome_report",
        )
    )
    timer.record(
        "preview_client_local", max(0.0, preview_total - fidelity - submit)
    )
    timer.record("approval_reverify", max(0.0, apply_total - apply_parts))
    timer.mark_not_measured("restore_and_compare")
    if engine_url is None:
        timer.mark_not_measured("generate")
    else:
        _time_one_real_generate(timer, engine_url)


def _run_failure_path_once(cmd: Any, tmp_path: Path, timer: StageTimer) -> None:
    """Run one mid-apply failure, to measure `restore_and_compare` once.

    Args:
        cmd: The real PyMOL `cmd` module.
        tmp_path: A fresh, private root for this run's recovery store.
        timer: Where to record `restore_and_compare`'s own elapsed time.
    """
    completions = [
        CompletionResult(
            "select copilot_selection, chain A\ncolor red, copilot_selection\n",
            "m-1",
            STOP_END,
        )
    ]
    lifecycle = build_lifecycle(completions=completions, max_repair_attempts=0)
    server = LoopbackPlanServer(
        CREDENTIAL,
        lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )
    driver = ConsoleDriver(FailColorProxy(cmd))
    output: list[str] = []
    try:
        server.start()
        store = _RestoreOnlyTimedRecoveryStore(tmp_path, timer)
        register_copilot(
            # pyrefly: ignore.  __getattr__ delegates the query surface at
            # runtime, but pyrefly cannot verify that structurally.
            driver,
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
            recovery_store=store,
        )
        driver.run(f"copilot {INTENT}")
        plan_id = plan_id_from(output)
        driver.run(f"copilot_apply {plan_id}")
    finally:
        server.close()
        cmd.delete("all")
        cmd.load(str(FIXTURE_PATH), OBJECT_NAME)


def main(argv: list[str] | None = None) -> int:
    """Run the recorded repetitions and write the note.

    Args:
        argv: Command-line arguments, excluding the program name.

    Returns:
        Zero on success.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--lemonade-base-url", default=None)
    args = parser.parse_args(argv)

    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    timer = StageTimer()
    try:
        cmd.load(str(FIXTURE_PATH), OBJECT_NAME)
        for repetition in range(args.repetitions):
            with tempfile.TemporaryDirectory() as tmp:
                _run_happy_path_once(
                    cmd, Path(tmp), timer, args.lemonade_base_url
                )
            if repetition == 0:
                # The first repetition pays for PyMOL's import and
                # page-cache warm-up; discard it.
                timer.samples.clear()
            timer.next_repetition()
        with tempfile.TemporaryDirectory() as tmp:
            _run_failure_path_once(cmd, Path(tmp), timer)
    finally:
        cmd.do("quit")

    machine = (
        f"{platform.system()} {platform.release()} · "
        f"{platform.machine()} · Python {platform.python_version()}"
    )
    note = render_note(
        timer.samples,
        machine=machine,
        engine=args.lemonade_base_url or "scripted (FakeEngine)",
        repetitions=max(0, args.repetitions - 1),
        date=datetime.now(UTC).date().isoformat(),
    )
    print(note)

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if workspace is not None:
        results_dir = Path(workspace) / "results"
        results_dir.mkdir(exist_ok=True)
        out_path = (
            results_dir
            / f"latency-{platform.system().lower()}-{platform.node()}.md"
        )
        out_path.write_text(note, encoding="utf-8")
        print(f"Written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
