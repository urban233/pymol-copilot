# Copyright 2026 PyMOL Copilot contributors.
"""The live demo's launcher and its rehearsal (docs/demo.md).

docs/master_plan.md item 19: "dry-run the demo: one intent through
apply, one deliberate failure through recovery". The demo has two
beats:

1. an intent through preview, approval (`copilot_apply`) and, to show
   recovery on request, `copilot_rollback`;
2. the same intent with a deliberate failure: with `--fail-on color`,
   the client drives PyMOL through `FailOnVerbProxy`, whose `color`
   raises after the plan's earlier commands have really changed the
   session, and the client restores the whole session automatically.

Nothing in the product can inject a failure, and nothing here adds one:
the proxy wraps the `cmd` object this demo hands the client, it prints
a banner saying so, and without `--fail-on` it is not used at all.

`--headless` rehearses both beats against the running server, in
headless PyMOL, prints the console transcript, and exits non-zero if a
beat did not end as it must. It lives under tests/ because only tests
may depend on `pmc_client`, like `//tests/e2e:record_latency`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import hashlib
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import winstage

from pmc_client.bootstrap import connect_from_handoff
from pmc_client.recovery import RecoveryStore
from pmc_core.snapshot import extract
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import to_json
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_eval.prompt import snapshot_for

#: The gold item the demo runs: an intent the fine-tuned model answered
#: correctly offline, on its own held-out structure, whose plan selects,
#: colours and shows -- so a failing `color` comes after a real change.
DEFAULT_SAMPLE_ID = "gold_056"

#: The verbs `--fail-on` can make fail.
FAILABLE_VERBS = ("color", "show", "hide", "orient", "select")

#: How long one console command may take before the rehearsal gives up.
COMMAND_DEADLINE_SECONDS = 600.0


class FailOnVerbProxy:
    """PyMOL's `cmd`, except that one verb raises when the plan calls it.

    Every other attribute is the real `cmd`'s, so the plan's other
    commands really change the session before the named one fails.
    """

    def __init__(self, cmd: Any, verb: str) -> None:
        """Wrap `cmd`, failing `verb`.

        Args:
            cmd: PyMOL's `cmd`, or another wrapper of it.
            verb: One of `FAILABLE_VERBS`.

        Raises:
            ValueError: If `verb` is not one of them.
        """
        if verb not in FAILABLE_VERBS:
            raise ValueError(f"cannot fail {verb!r}")
        self._cmd = cmd
        self._verb = verb

    def __getattr__(self, name: str) -> Any:
        """Return `cmd`'s attribute, or a failing one for the named verb.

        Args:
            name: The attribute.

        Returns:
            The real attribute, or a function that raises.
        """
        if name == self._verb:

            def fail(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError(
                    f"DEMO: `{self._verb}` failed on purpose (--fail-on)"
                )

            return fail
        return getattr(self._cmd, name)


def banner(verb: str) -> str:
    """Say, before anything runs, that a failure is staged.

    Args:
        verb: The verb that will fail.

    Returns:
        The banner line.
    """
    return (
        f"DEMO: the next plan's `{verb}` will fail on purpose, to show "
        "automatic recovery (--fail-on)."
    )


class ConsoleDriver:
    """Run `copilot*` commands through PyMOL's own dispatch, synchronously.

    The same pattern as `tests/e2e/scenario_support.ConsoleDriver`.
    """

    def __init__(self, cmd: Any, deadline_seconds: float) -> None:
        """Wrap PyMOL's `cmd`.

        Args:
            cmd: PyMOL's `cmd`, or a wrapper of it.
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
        """Forward everything else to the wrapped `cmd`.

        Args:
            name: The attribute.

        Returns:
            Its attribute.
        """
        return getattr(self._cmd, name)

    def run(self, command_line: str) -> None:
        """Dispatch one command line and wait for it to finish.

        Args:
            command_line: What a user would type at PyMOL's prompt.

        Raises:
            TimeoutError: If it did not finish within the deadline.
        """
        finished = self._finished = threading.Event()
        self._cmd.do(command_line)
        if not finished.wait(self._deadline):
            raise TimeoutError(f"{command_line!r} did not finish")


def demo_sample(sample_id: str = DEFAULT_SAMPLE_ID) -> Sample:
    """Read the gold item the demo runs.

    Args:
        sample_id: The gold item.

    Returns:
        The sample.
    """
    return next(
        s
        for s in read_samples(DEFAULT_GOLD_SAMPLES_PATH)
        if s.sample_id == sample_id
    )


def _fingerprint(cmd: Any, name: str) -> str:
    """Fingerprint one live object.

    Args:
        cmd: PyMOL's `cmd`.
        name: The object.

    Returns:
        Its canonical snapshot's SHA-256.
    """
    return hashlib.sha256(
        to_json(extract(cmd, name)).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Rehearsal:
    """What one rehearsed beat printed, and whether it ended as it must.

    Attributes:
        transcript: The console, command by command.
        passed: Whether the beat ended as the demo needs it to.
        problems: What did not, if anything.
    """

    transcript: str
    passed: bool
    problems: tuple[str, ...]


def rehearse(
    cmd: Any,
    *,
    handoff: Path,
    recovery_root: Path,
    fail_on: str | None,
    sample: Sample,
) -> Rehearsal:
    """Rehearse one beat against the running server.

    Without `fail_on`: preview, apply, rollback; the session must change
    on apply and be back where it was after rollback. With it: preview
    and apply through `FailOnVerbProxy`; apply must fail and the whole
    session be restored.

    Args:
        cmd: PyMOL's `cmd`, launched.
        handoff: The server's handoff file.
        recovery_root: Where recovery points are kept.
        fail_on: The verb to fail, or None.
        sample: The gold item to run.

    Returns:
        The rehearsal.
    """
    snapshot = snapshot_for(sample)
    cmd.delete("all")
    reconstruct(cmd, snapshot)
    target = cmd if fail_on is None else FailOnVerbProxy(cmd, fail_on)
    driver = ConsoleDriver(target, COMMAND_DEADLINE_SECONDS)
    output: list[str] = []
    transcript: list[str] = []
    if fail_on is not None:
        transcript.append(banner(fail_on))
    client = connect_from_handoff(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        driver,
        output.append,
        path=handoff,
        recovery_store=RecoveryStore(recovery_root),
    )
    transcript += output
    if client is None:
        return Rehearsal("\n".join(transcript), False, ("did not connect",))
    problems: list[str] = []

    def run(command_line: str) -> str:
        output.clear()
        started = time.monotonic()
        driver.run(command_line)
        text = "\n".join(output)
        transcript.append(f"PyMOL> {command_line}")
        transcript.append(text)
        transcript.append(f"({time.monotonic() - started:.1f} s)")
        return text

    before = _fingerprint(cmd, snapshot.name)
    run("copilot_health")
    preview = run(f"copilot {sample.intent}")
    plan_line = next(
        (
            line
            for line in preview.splitlines()
            if line.startswith("copilot plan ")
        ),
        None,
    )
    if plan_line is None or "apply:     copilot_apply" not in preview:
        return Rehearsal(
            "\n".join(transcript), False, ("no approvable preview",)
        )
    if _fingerprint(cmd, snapshot.name) != before:
        problems.append("the preview changed the session")
    plan_id = plan_line.removeprefix("copilot plan ").split(" ", 1)[0]
    applied = run(f"copilot_apply {plan_id}")
    after = _fingerprint(cmd, snapshot.name)
    if fail_on is None:
        if f"plan {plan_id} applied." not in applied or after == before:
            problems.append("apply did not change the session")
        rolled_back = run(f"copilot_rollback {plan_id}")
        if (
            f"plan {plan_id} rolled back" not in rolled_back
            or _fingerprint(cmd, snapshot.name) != before
        ):
            problems.append("rollback did not restore the session")
    elif (
        "failed and the complete session was restored cleanly" not in applied
        or after != before
    ):
        problems.append("the failed apply was not restored")
    return Rehearsal("\n".join(transcript), not problems, tuple(problems))


def main(argv: Sequence[str] | None = None) -> int:
    """Rehearse the demo's beats headless against the running server.

    Args:
        argv: The arguments, without the program name.

    Returns:
        Zero when every rehearsed beat ended as it must.
    """
    parser = argparse.ArgumentParser(prog="copilot_demo")
    parser.add_argument(
        "--handoff",
        type=Path,
        default=Path.home() / ".pymol-copilot" / "session.json",
    )
    parser.add_argument("--fail-on", choices=FAILABLE_VERBS, default=None)
    parser.add_argument("--sample", default=DEFAULT_SAMPLE_ID)
    parser.add_argument(
        "--headless",
        action="store_true",
        required=True,
        help="Rehearse the beats in headless PyMOL (the only mode yet).",
    )
    arguments = parser.parse_args(argv)
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore[missing-import]
    from pymol import cmd  # pyrefly: ignore[missing-import]

    pymol.finish_launching(["pymol", "-qc"])
    with tempfile.TemporaryDirectory(prefix="pmc-demo-") as scratch:
        result = rehearse(
            cmd,
            handoff=arguments.handoff,
            recovery_root=Path(scratch),
            fail_on=arguments.fail_on,
            sample=demo_sample(arguments.sample),
        )
    print(result.transcript)
    print("REHEARSAL:", "passed" if result.passed else "FAILED")
    for problem in result.problems:
        print("  -", problem)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
