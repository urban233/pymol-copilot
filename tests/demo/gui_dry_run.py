# Copyright 2026 PyMOL Copilot contributors.
"""Drive both demo beats in GUI PyMOL, and record what the window showed.

docs/master_plan.md item 19. This is the demo's scripted dry run: it
runs inside GUI PyMOL (from the demo environment, `requirements-demo.txt`)
against the running server, types each step of docs/demo.md at PyMOL's
command line, waits for the client's answer, checks the session, and
saves a screenshot of the window at every step. It does not replace
the watched dry run: whether a watcher can tell what is about to
change before apply is a person's judgement, and the record says so.

Run it as PyMOL's startup script:

    PYTHONPATH=src:tools/winstage:tests/demo PMC_DRY_RUN_HANDOFF=<handoff> \\
    PMC_DRY_RUN_OUT=<dir> .venv-demo/bin/python -c \\
        "import pymol; pymol.launch(['pymol', 'tests/demo/gui_dry_run.py'])"

It writes `transcript.txt`, `checks.json` and one PNG per step to
`PMC_DRY_RUN_OUT`, then quits PyMOL.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import copilot_demo
from pymol import cmd  # pyrefly: ignore[missing-import]

#: How long one step may take before the dry run gives up.
STEP_SECONDS = 300.0


class _Console:
    """Collect what the client prints, and wait for an answer."""

    def __init__(self) -> None:
        """Start empty."""
        self.lines: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, text: str) -> None:
        """Receive one printed block, and echo it to PyMOL's console.

        Args:
            text: What the client printed.
        """
        print(text)
        with self._lock:
            self.lines.extend(text.splitlines())

    def run(self, command_line: str, done: Callable[[str], bool]) -> str:
        """Type one command and wait until its answer is printed.

        Args:
            command_line: What the presenter types.
            done: Whether a printed line ends the answer.

        Returns:
            Everything printed in answer.

        Raises:
            TimeoutError: If no line ends it in time.
        """
        with self._lock:
            start = len(self.lines)
        cmd.do(command_line)
        deadline = time.monotonic() + STEP_SECONDS
        while time.monotonic() < deadline:
            with self._lock:
                new = self.lines[start:]
            if any(done(line) for line in new):
                time.sleep(0.5)
                with self._lock:
                    return "\n".join(self.lines[start:])
            time.sleep(0.2)
        raise TimeoutError(command_line)


def _shot(out: Path, name: str) -> str:
    """Save the window as it is now.

    Args:
        out: The output directory.
        name: The step's name.

    Returns:
        The file name.
    """
    time.sleep(1.0)
    cmd.png(str(out / f"{name}.png"), width=800, height=600, ray=0)
    time.sleep(1.0)
    return f"{name}.png"


def _dry_run(handoff: Path, out: Path) -> None:
    """Run both beats, then quit PyMOL.

    Args:
        handoff: The server's handoff file.
        out: Where the record is written.
    """
    time.sleep(3.0)
    console = _Console()
    transcript: list[str] = []
    checks: dict[str, Any] = {}
    case = copilot_demo.load_case()
    name = case.snapshot.name

    def step(command_line: str, done: Callable[[str], bool]) -> str:
        text = console.run(command_line, done)
        transcript.append(f"PyMOL> {command_line}\n{text}")
        return text

    def plan_id(text: str) -> str:
        line = next(
            line
            for line in text.splitlines()
            if line.startswith("copilot plan ")
        )
        return line.removeprefix("copilot plan ").split(" ", 1)[0]

    try:
        copilot_demo.prepare_session(cmd, case)
        assert copilot_demo.connect(
            cmd, handoff=handoff, fail_on=None, output=console
        )
        transcript.append("\n".join(console.lines))
        shots = [_shot(out, "0-start")]
        before = copilot_demo._fingerprint(cmd, name)
        step("copilot_health", lambda line: line.startswith("  copilot:"))

        # Beat 1: one intent through apply, then rollback.
        preview = step(
            f"copilot {case.intent}",
            lambda line: line.startswith(("  reject:", "copilot:")),
        )
        shots.append(_shot(out, "1-preview"))
        checks["beat1_preview_changed_nothing"] = (
            copilot_demo._fingerprint(cmd, name) == before
        )
        first = plan_id(preview)
        step(
            f"copilot_apply {first}",
            lambda line: line.startswith("copilot_apply:"),
        )
        shots.append(_shot(out, "2-applied"))
        checks["beat1_apply_changed_the_session"] = (
            copilot_demo._fingerprint(cmd, name) != before
        )
        step(
            f"copilot_rollback {first}",
            lambda line: (
                "rolled back" in line
                or line.startswith("copilot_rollback: recovery")
            ),
        )
        shots.append(_shot(out, "3-rolled-back"))
        checks["beat1_rollback_restored_the_session"] = (
            copilot_demo._fingerprint(cmd, name) == before
        )

        # Beat 2: the staged failure, and automatic recovery.
        console.lines.clear()
        assert copilot_demo.connect(
            cmd, handoff=handoff, fail_on="color", output=console
        )
        transcript.append(
            "PyMOL> copilot_demo_fail color\n" + "\n".join(console.lines)
        )
        preview = step(
            f"copilot {case.intent}",
            lambda line: line.startswith(("  reject:", "copilot:")),
        )
        shots.append(_shot(out, "4-preview-armed"))
        second = plan_id(preview)
        applied = step(
            f"copilot_apply {second}",
            lambda line: line.startswith("copilot_apply:"),
        )
        shots.append(_shot(out, "5-restored"))
        checks["beat2_failed_apply_was_restored"] = (
            "restored cleanly" in applied
            and copilot_demo._fingerprint(cmd, name) == before
        )
        checks["screenshots"] = shots
    except Exception as error:  # Recorded, not raised: PyMOL must still quit.
        checks["error"] = repr(error)
    finally:
        (out / "transcript.txt").write_text(
            "\n".join(transcript) + "\n", encoding="utf-8"
        )
        (out / "checks.json").write_text(
            json.dumps(checks, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        cmd.quit()


threading.Thread(
    target=_dry_run,
    args=(
        Path(os.environ["PMC_DRY_RUN_HANDOFF"]),
        Path(os.environ["PMC_DRY_RUN_OUT"]),
    ),
    daemon=True,
).start()
