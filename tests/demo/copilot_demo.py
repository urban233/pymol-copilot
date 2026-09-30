# Copyright 2026 PyMOL Copilot contributors.
"""The live demo's launcher and its rehearsal (docs/demo.md).

docs/master_plan.md item 19: "dry-run the demo: one intent through
apply, one deliberate failure through recovery". The demo has two
beats, in one PyMOL window:

1. an intent through preview, approval (`copilot_apply`) and, to show
   recovery on request, `copilot_rollback`;
2. `copilot_demo_fail color`, then the same intent again: the client
   now drives PyMOL through `FailOnVerbProxy`, whose `color` raises
   after the plan's earlier commands have really changed the session,
   and the client restores the whole session automatically.

Nothing in the product can inject a failure, and nothing here adds one:
the proxy wraps the `cmd` object this demo hands the client, a banner
says so when it is armed, and `copilot_demo_fail off` removes it.

The structure is gold item `gold_056`'s, read from `demo_case.json`
(checked against its recorded SHA-256) and rebuilt with
`pmc_core.snapshot.reconstruct`, so the PyMOL process holds only what
the product puts there: the client and the shared core. It opens GUI
PyMOL from the pinned demo environment (`requirements-demo.txt`, where
the PyMOL wheel gains a Qt binding); `--headless` instead rehearses one
beat in headless PyMOL, prints the transcript, and exits non-zero if
it did not end as it must.

It lives under tests/ because only tests may depend on `pmc_client`,
like `//tests/e2e:record_latency`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import hashlib
import json
import os
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
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import extract
from pmc_core.snapshot import from_json
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import to_json

#: The demo's gold item: its intent and its held-out structure. The
#: fine-tuned model answered it correctly offline; its plan selects,
#: colours and shows, so a failing `color` comes after a real change.
CASE_PATH = Path(__file__).resolve().with_name("demo_case.json")

#: The verbs `copilot_demo_fail` can make fail.
FAILABLE_VERBS = ("color", "show", "hide", "orient", "select")

#: How long one console command may take before the rehearsal gives up.
COMMAND_DEADLINE_SECONDS = 600.0

DEFAULT_HANDOFF = Path.home() / ".pymol-copilot" / "session.json"

#: Where WSLg keeps its Wayland socket: Qt finds no display otherwise.
_WSLG_RUNTIME_DIR = Path("/mnt/wslg/runtime-dir")


@dataclass(frozen=True)
class DemoCase:
    """The gold item the demo runs.

    Attributes:
        sample_id: The gold item.
        intent: What the presenter types after `copilot`.
        snapshot: Its structure.
        resulting_fingerprint: The state its gold plan leaves.
    """

    sample_id: str
    intent: str
    snapshot: ObjectSnapshot
    resulting_fingerprint: str


def load_case(path: Path = CASE_PATH) -> DemoCase:
    """Read the demo case, and prove its structure is the recorded one.

    Args:
        path: The case file.

    Returns:
        The case.

    Raises:
        ValueError: If the structure's SHA-256 is not the recorded one.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    text = data["snapshot"]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != data["snapshot_sha256"]:
        raise ValueError(f"{path}: the structure is not the recorded one")
    return DemoCase(
        sample_id=data["sample_id"],
        intent=data["intent"],
        snapshot=from_json(text),
        resulting_fingerprint=data["resulting_fingerprint"],
    )


class FailOnVerbProxy:
    """PyMOL's `cmd`, except that one verb raises when the plan calls it.

    Every other attribute is the wrapped object's, so the plan's other
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
                    f"DEMO: `{self._verb}` failed on purpose "
                    "(copilot_demo_fail)"
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
        "automatic recovery. `copilot_demo_fail off` disarms it."
    )


def _fingerprint(cmd: Any, name: str) -> str:
    """Fingerprint one live object the way the sidecar does.

    Args:
        cmd: PyMOL's `cmd`.
        name: The object.

    Returns:
        `sha256:<hex>` of its canonical snapshot.
    """
    text = to_json(extract(cmd, name))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def connect(
    cmd: Any,
    *,
    handoff: Path,
    fail_on: str | None,
    output: Callable[[str], None],
    recovery_store: RecoveryStore | None = None,
) -> bool:
    """Connect the client to the running server, armed or not.

    Registering again replaces the `copilot*` commands, so this also
    arms and disarms the staged failure.

    Args:
        cmd: What the client should drive: PyMOL's `cmd`, or a console
            driver around it.
        handoff: The server's handoff file.
        fail_on: The verb to fail, or None.
        output: Where the client prints.
        recovery_store: Where recovery points go; the user's own when
            None.

    Returns:
        Whether the client connected.
    """
    target = cmd if fail_on is None else FailOnVerbProxy(cmd, fail_on)
    if fail_on is not None:
        output(banner(fail_on))
    client = connect_from_handoff(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        target,
        output,
        path=handoff,
        recovery_store=recovery_store,
    )
    return client is not None


def start_gui(cmd: Any, *, handoff: str, fail_on: str | None = None) -> None:
    """Set up the demo inside GUI PyMOL: the structure, the client.

    Runs in PyMOL's own interpreter, from the launcher's `-d` command.
    Registers `copilot_demo_fail <verb|off>` to arm or disarm the
    staged failure between the beats.

    Args:
        cmd: PyMOL's `cmd`.
        handoff: The server's handoff file.
        fail_on: A verb to arm from the start, or None.
    """
    case = load_case()
    cmd.delete("all")
    reconstruct(cmd, case.snapshot)
    path = Path(handoff)

    def demo_fail(verb: str = "") -> None:
        verb = verb.strip()
        if verb not in (*FAILABLE_VERBS, "off"):
            print(f"copilot_demo_fail: one of {', '.join(FAILABLE_VERBS)}, off")
            return
        armed = None if verb == "off" else verb
        connected = connect(cmd, handoff=path, fail_on=armed, output=print)
        if connected and armed is None:
            print("DEMO: the staged failure is off.")

    cmd.extend("copilot_demo_fail", demo_fail)
    connect(cmd, handoff=path, fail_on=fail_on, output=print)
    print(f"DEMO: {case.sample_id}'s structure is loaded. Try:")
    print(f"  copilot {case.intent}")


class ConsoleDriver:
    """Run `copilot*` commands through PyMOL's own dispatch, synchronously.

    The same pattern as `tests/e2e/scenario_support.ConsoleDriver`.
    """

    def __init__(self, cmd: Any, deadline_seconds: float) -> None:
        """Wrap PyMOL's `cmd`.

        Args:
            cmd: PyMOL's `cmd`.
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
    case: DemoCase,
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
        case: The demo case.

    Returns:
        The rehearsal.
    """
    cmd.delete("all")
    reconstruct(cmd, case.snapshot)
    driver = ConsoleDriver(cmd, COMMAND_DEADLINE_SECONDS)
    output: list[str] = []
    transcript: list[str] = []
    connected = connect(
        driver,
        handoff=handoff,
        fail_on=fail_on,
        output=output.append,
        recovery_store=RecoveryStore(recovery_root),
    )
    transcript += output
    if not connected:
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

    name = case.snapshot.name
    before = _fingerprint(cmd, name)
    run("copilot_health")
    preview = run(f"copilot {case.intent}")
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
    if _fingerprint(cmd, name) != before:
        problems.append("the preview changed the session")
    plan_id = plan_line.removeprefix("copilot plan ").split(" ", 1)[0]
    applied = run(f"copilot_apply {plan_id}")
    after = _fingerprint(cmd, name)
    if fail_on is None:
        if f"plan {plan_id} applied." not in applied or after == before:
            problems.append("apply did not change the session")
        rolled_back = run(f"copilot_rollback {plan_id}")
        if (
            f"plan {plan_id} rolled back" not in rolled_back
            or _fingerprint(cmd, name) != before
        ):
            problems.append("rollback did not restore the session")
    elif (
        "failed and the complete session was restored cleanly" not in applied
        or after != before
    ):
        problems.append("the failed apply was not restored")
    return Rehearsal("\n".join(transcript), not problems, tuple(problems))


def _gui_environment() -> dict[str, str]:
    """Point Qt at WSLg's Wayland socket when running under WSLg.

    Returns:
        The variables set, for the launcher to print.
    """
    if not _WSLG_RUNTIME_DIR.is_dir() or "WAYLAND_DISPLAY" not in os.environ:
        return {}
    chosen = {
        "XDG_RUNTIME_DIR": str(_WSLG_RUNTIME_DIR),
        "QT_QPA_PLATFORM": "wayland",
    }
    for key, value in chosen.items():
        os.environ.setdefault(key, value)
    return {key: os.environ[key] for key in chosen}


def main(argv: Sequence[str] | None = None) -> int:
    """Open the demo in GUI PyMOL, or rehearse one beat headless.

    Args:
        argv: The arguments, without the program name.

    Returns:
        Zero when PyMOL closes, or when the rehearsed beat ended as it
        must.
    """
    parser = argparse.ArgumentParser(prog="copilot_demo")
    parser.add_argument("--handoff", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument("--fail-on", choices=FAILABLE_VERBS, default=None)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Rehearse the beat in headless PyMOL and report it.",
    )
    arguments = parser.parse_args(argv)
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore[missing-import]

    if not arguments.headless:
        for key, value in _gui_environment().items():
            print(f"copilot_demo: {key}={value}")
        pymol.launch(
            [
                "pymol",
                "-d",
                "/import copilot_demo; copilot_demo.start_gui(cmd, "
                f"handoff={str(arguments.handoff)!r}, "
                f"fail_on={arguments.fail_on!r})",
            ]
        )
        return 0
    from pymol import cmd  # pyrefly: ignore[missing-import]

    pymol.finish_launching(["pymol", "-qc"])
    with tempfile.TemporaryDirectory(prefix="pmc-demo-") as scratch:
        result = rehearse(
            cmd,
            handoff=arguments.handoff,
            recovery_root=Path(scratch),
            fail_on=arguments.fail_on,
            case=load_case(),
        )
    print(result.transcript)
    print("REHEARSAL:", "passed" if result.passed else "FAILED")
    for problem in result.problems:
        print("  -", problem)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
