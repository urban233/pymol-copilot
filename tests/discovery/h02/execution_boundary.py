# Copyright 2026 PyMOL Copilot contributors.
"""H-02 discovery: the fresh-process hermetic execution boundary prototype.

This module prototypes the accepted design's "Hermetic execution protocol"
contract
([plan and execution](../../design/shared-core/plan-and-execution.md#apis-and-contracts)),
whose stated guarantees are "fresh process, finite resources, command-indexed
outcomes, and deterministic evidence where declared", and whose stated error
behavior is that "timeout, resource, and PyMOL errors terminate the process
with no internal retry". It ships no production API: `ExecutionRequest`,
`ExecutionReport`, and every schema version below are candidate-private
prototype shapes for this discovery task only, not the contract-freeze
checkpoint's accepted contract.

This is deliberately its own process primitive, not an extension of
`harness.run_nested_snapshot_process`: that helper is a nested-pytest runner
with no deadline and no kill path, built for the fresh-process *round-trip*
tests in candidates A/B/C. Slice 2's outer-loop review called out explicitly
that growing it with timeout/kill flags would overload one function and put
this slice's failure modes inside the harness every candidate test depends
on. `execute()` below spawns its own child via a small inline runner script
(`_CHILD_RUNNER_SOURCE`), not pytest, and owns its own deadline enforcement,
hard kill, reap, and scratch-directory cleanup.

Validation of a request happens in this (parent) process, before any child
is spawned: an oversized or malformed snapshot, or one carrying an
incompatible schema version, is rejected with no process ever created and no
scratch data ever written -- "no live child process" and "no scratch data"
hold trivially for those three failure modes. Every other failure mode
(spawn/load failure, timeout, forced crash, a failing PyMOL command, and a
fidelity mismatch between the expected and resulting fingerprints) is
observed from a genuinely spawned child process, whose scratch directory is
always removed in a `finally` clause covering every exit path, including
timeout and crash.

The child runner reuses this module's own `reconstruct()` (a minimal,
candidate-agnostic builder good enough for this slice's own small synthetic
snapshots -- not a full-fidelity contender for slice 4's candidate
selection) and `harness.py`'s existing `from_json`/`to_json`/`extract()`, so
the exact same reconstruction code also runs directly, in-process, wherever
a test wants an independently computed expected value without going through
the boundary at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

from harness import ObjectSnapshot
from harness import from_json

#: This module's own schema versions for the request/report shapes below --
#: candidate-private prototype versions, not a production contract, exactly
#: like harness.SNAPSHOT_SCHEMA_VERSION and candidate B's own manifest
#: schema version.
EXECUTION_REQUEST_SCHEMA_VERSION = 1
EXECUTION_REPORT_SCHEMA_VERSION = 1

#: Top-level report outcomes.
STATUS_OK = "ok"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"

#: Typed, stable failure reasons -- every fail-closed path below sets
#: exactly one of these, never a raw exception string.
REASON_OK = "ok"
REASON_OVERSIZED_INPUT = "oversized_input"
REASON_MALFORMED_INPUT = "malformed_input"
REASON_UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
REASON_SPAWN_OR_LOAD_FAILURE = "spawn_or_load_failure"
REASON_TIMEOUT = "timeout"
REASON_CHILD_CRASH = "child_crash"
REASON_COMMAND_FAILURE = "command_failure"
REASON_FIDELITY_MISMATCH = "fidelity_mismatch"

#: Per-command outcome statuses.
OUTCOME_OK = "ok"
OUTCOME_ERROR = "error"

#: Sentinel command verbs the child runner interprets itself, never
#: forwarded to `cmd`, used only by this slice's own sabotage fixtures to
#: force a wall-clock timeout or a hard child-process crash on demand, or to
#: make a command that always fails while still recording each real
#: invocation it receives (`COUNT_THEN_FAIL_VERB`), so a test can tell
#: "attempted once" apart from "attempted, then silently retried" even
#: though both currently produce exactly one recorded outcome.
CRASH_VERB = "__crash__"
SLEEP_VERB = "__sleep__"
COUNT_THEN_FAIL_VERB = "__count_then_fail__"


@dataclass(frozen=True)
class Command:
    """One command in a request's ordered command list.

    Attributes:
        verb: The `cmd.<verb>` PyMOL API to call, or one of this module's
            own sentinel verbs (`CRASH_VERB`, `SLEEP_VERB`,
            `COUNT_THEN_FAIL_VERB`).
        args: Positional string arguments passed to that verb.
    """

    verb: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandOutcome:
    """The observed outcome of one command, indexed by its position.

    Attributes:
        index: The command's zero-based position in the request's ordered
            command list.
        verb: The verb that was executed.
        status: `OUTCOME_OK` or `OUTCOME_ERROR`.
        error: A bounded error message when status is `OUTCOME_ERROR`, else
            None.
    """

    index: int
    verb: str
    status: str
    error: str | None


@dataclass(frozen=True)
class ExecutionRequest:
    """A request to execute an ordered command list against a snapshot.

    Attributes:
        schema_version: This request shape's own schema version.
        snapshot_json: The candidate snapshot to reconstruct from, as
            `harness.to_json` serialized it -- validated and parsed inside
            `execute()`, never trusted as already-well-formed.
        commands: The ordered commands to execute against the reconstructed
            object.
        max_input_bytes: The maximum allowed size, in bytes, of
            `snapshot_json`'s UTF-8 encoding. A request whose snapshot
            exceeds this limit is rejected before any process is spawned.
        deadline_seconds: The wall-clock deadline for the whole spawned
            child process. Exceeding it causes a hard kill.
        expected_resulting_fingerprint: An optional independently computed
            fingerprint (see `ExecutionReport.resulting_fingerprint`) that
            the boundary must match after a fully successful run. A
            mismatch fails the report closed with
            `REASON_FIDELITY_MISMATCH`, even though every command
            succeeded.
    """

    schema_version: int
    snapshot_json: str
    commands: tuple[Command, ...]
    max_input_bytes: int
    deadline_seconds: float
    expected_resulting_fingerprint: str | None = None


@dataclass(frozen=True)
class ExecutionReport:
    """The result of one `execute()` call.

    Attributes:
        schema_version: This report shape's own schema version.
        status: `STATUS_OK`, `STATUS_REJECTED` (failed before any process
            was spawned), or `STATUS_FAILED` (failed during or after a
            spawned child's run).
        reason: One of this module's `REASON_*` constants; `REASON_OK` iff
            status is `STATUS_OK`.
        input_fingerprint: A fingerprint of the request's own
            `snapshot_json`, computed whenever that snapshot at least parses
            (so it is present even for most rejected requests); None only
            when rejected before that parse (an unsupported request schema
            version, or an oversized snapshot never even attempted to
            parse).
        resulting_fingerprint: A fingerprint of the reconstructed object's
            canonical extraction after every command ran, or None when no
            such extraction was ever produced.
        command_outcomes: Per-command outcomes, indexed by position. Shorter
            than the request's command list whenever execution stopped
            early (a command failure, or a crash).
        elapsed_seconds: Wall-clock time this `execute()` call took.
        warnings: Bounded diagnostic text that does not itself change
            status or reason (for example, captured child stderr after an
            unexplained crash).
    """

    schema_version: int
    status: str
    reason: str
    input_fingerprint: str | None
    resulting_fingerprint: str | None
    command_outcomes: tuple[CommandOutcome, ...]
    elapsed_seconds: float
    warnings: tuple[str, ...] = field(default_factory=tuple)


def fingerprint(text: str) -> str:
    """Compute this module's canonical fingerprint of some JSON text.

    Args:
        text: The text to fingerprint (a snapshot's or an extraction's
            JSON, as produced by `harness.to_json`).

    Returns:
        A stable, deterministic hex digest.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reconstruct(cmd: Any, snapshot: ObjectSnapshot) -> None:
    """Rebuild a live PyMOL object from a canonical structured snapshot.

    A minimal, candidate-agnostic reconstruction good enough for this
    slice's own small synthetic snapshots (see `test_execution_boundary.py`'s
    own fixture, which by construction has no name collisions, altlocs, or
    insertion codes) -- unlike candidate A's own `reconstruct()`, it does not
    need that candidate's tag-based addressing workaround for
    `pseudoatom`'s same-residue name collisions. This function is not a
    fidelity contender for slice 4's candidate selection; it exists only so
    the execution boundary has something real to reconstruct from and run
    commands against.

    Args:
        cmd: The real PyMOL cmd module, in a fresh process with no
            conflicting object of the same name.
        snapshot: The canonical snapshot to reconstruct.
    """
    name = snapshot.name
    first_state = snapshot.states[0]

    for atom in first_state.atoms:
        cmd.pseudoatom(
            name,
            pos=list(atom.coord),
            chain=atom.chain,
            resi=f"{atom.resv}{atom.ins_code}",
            resn=atom.resn,
            name=atom.name,
            elem=atom.elem,
            b=atom.b,
            q=atom.q,
            hetatm=int(atom.hetatm),
            state=1,
        )
    cmd.sync()

    def atom_selection(atom: Any) -> str:
        return (
            f"{name} and name {atom.name} and resi {atom.resv}{atom.ins_code}"
        )

    for bond in snapshot.bonds:
        cmd.bond(
            atom_selection(first_state.atoms[bond.atom_index_a]),
            atom_selection(first_state.atoms[bond.atom_index_b]),
            order=bond.order,
        )
    cmd.sync()

    for atom in first_state.atoms:
        sel = atom_selection(atom)
        cmd.color(str(atom.color), sel)
        cmd.hide("everything", sel)
        for rep_name in atom.reps:
            cmd.show(rep_name, sel)
        if atom.label is not None:
            cmd.label(sel, repr(atom.label))
    cmd.sync()

    cmd.set_view(snapshot.view)
    for setting_name, value in snapshot.settings:
        cmd.set(setting_name, value, name)
    if snapshot.enabled:
        cmd.enable(name)
    else:
        cmd.disable(name)
    cmd.sync()


#: The child's entire program, passed via `python -c`, followed by
#: `snapshot_path`, `commands_path`, and `output_path` in argv. Reuses this
#: module's own `reconstruct()` and harness.py's `from_json`/`extract` --
#: both importable in the child because `execute()` puts this directory on
#: `PYTHONPATH` before spawning. Unlike harness.py's
#: `run_nested_snapshot_process` (which reuses pytest's own automatic
#: sys.path insertion for a real test-file argv path), this child is a bare
#: script with no test-file argument at all, so that automatic insertion
#: does not apply here and PYTHONPATH must be set explicitly.
#:
#: The child always exits through `os._exit` after flushing stdout/stderr,
#: for the same reason every candidate module's own `__main__` block and
#: harness.py's nested pytest runner do: real PyMOL's headless shutdown can
#: otherwise run long enough to interfere with a trustworthy exit code. This
#: child does not rely on its own exit code for pass/fail signaling at all
#: (the parent reads the JSON `output_path` file instead, or treats a
#: missing file as a crash) -- but `os._exit` still matters here, because
#: without it the child could hang past the parent's deadline inside
#: PyMOL's own shutdown sequence instead of actually terminating.
_CHILD_RUNNER_SOURCE = (
    "import hashlib, json, os, sys, time\n"
    "import harness\n"
    "import execution_boundary as eb\n"
    "\n"
    "snapshot_path, commands_path, output_path = sys.argv[1:4]\n"
    "\n"
    "def _write(payload):\n"
    "    with open(output_path, 'w') as fh:\n"
    "        json.dump(payload, fh)\n"
    "        fh.flush()\n"
    "        os.fsync(fh.fileno())\n"
    "\n"
    "snapshot_text = open(snapshot_path).read()\n"
    "commands = json.load(open(commands_path))\n"
    "\n"
    "import pymol\n"
    "from pymol import cmd\n"
    "pymol.finish_launching(['pymol', '-qc'])\n"
    "\n"
    "try:\n"
    "    snapshot = harness.from_json(snapshot_text)\n"
    "    eb.reconstruct(cmd, snapshot)\n"
    "except Exception as exc:\n"
    "    _write({\n"
    "        'status': 'failed',\n"
    "        'reason': eb.REASON_SPAWN_OR_LOAD_FAILURE,\n"
    "        'resulting_fingerprint': None,\n"
    "        'command_outcomes': [],\n"
    "    })\n"
    "    sys.stdout.flush()\n"
    "    sys.stderr.flush()\n"
    "    os._exit(0)\n"
    "\n"
    "command_outcomes = []\n"
    "overall_status = 'ok'\n"
    "overall_reason = eb.REASON_OK\n"
    "for index, (verb, args) in enumerate(commands):\n"
    "    if verb == eb.CRASH_VERB:\n"
    "        os._exit(1)\n"
    "    if verb == eb.SLEEP_VERB:\n"
    "        time.sleep(float(args[0]))\n"
    "        command_outcomes.append(\n"
    "            {'index': index, 'verb': verb, 'status': 'ok', 'error': None}\n"
    "        )\n"
    "        continue\n"
    "    if verb == eb.COUNT_THEN_FAIL_VERB:\n"
    "        counter_path = args[0]\n"
    "        count = 0\n"
    "        if os.path.exists(counter_path):\n"
    "            existing = open(counter_path).read().strip()\n"
    "            count = int(existing) if existing else 0\n"
    "        count += 1\n"
    "        with open(counter_path, 'w') as fh:\n"
    "            fh.write(str(count))\n"
    "            fh.flush()\n"
    "            os.fsync(fh.fileno())\n"
    "        command_outcomes.append(\n"
    "            {\n"
    "                'index': index,\n"
    "                'verb': verb,\n"
    "                'status': 'error',\n"
    "                'error': 'sentinel always fails; counts invocations',\n"
    "            }\n"
    "        )\n"
    "        overall_status = 'failed'\n"
    "        overall_reason = eb.REASON_COMMAND_FAILURE\n"
    "        break\n"
    "    try:\n"
    "        getattr(cmd, verb)(*args)\n"
    "        cmd.sync()\n"
    "        command_outcomes.append(\n"
    "            {'index': index, 'verb': verb, 'status': 'ok', 'error': None}\n"
    "        )\n"
    "    except Exception as exc:\n"
    "        command_outcomes.append(\n"
    "            {\n"
    "                'index': index,\n"
    "                'verb': verb,\n"
    "                'status': 'error',\n"
    "                'error': str(exc),\n"
    "            }\n"
    "        )\n"
    "        overall_status = 'failed'\n"
    "        overall_reason = eb.REASON_COMMAND_FAILURE\n"
    "        break\n"
    "\n"
    "resulting_fingerprint = None\n"
    "if overall_status == 'ok':\n"
    "    try:\n"
    "        extracted = harness.extract(cmd, snapshot.name)\n"
    "        resulting_fingerprint = eb.fingerprint(harness.to_json(extracted))\n"
    "    except Exception as exc:\n"
    "        overall_status = 'failed'\n"
    "        overall_reason = eb.REASON_COMMAND_FAILURE\n"
    "        command_outcomes.append(\n"
    "            {\n"
    "                'index': len(commands),\n"
    "                'verb': '__extract__',\n"
    "                'status': 'error',\n"
    "                'error': str(exc),\n"
    "            }\n"
    "        )\n"
    "\n"
    "_write({\n"
    "    'status': overall_status,\n"
    "    'reason': overall_reason,\n"
    "    'resulting_fingerprint': resulting_fingerprint,\n"
    "    'command_outcomes': command_outcomes,\n"
    "})\n"
    "sys.stdout.flush()\n"
    "sys.stderr.flush()\n"
    "os._exit(0)\n"
)


def _rejected(reason: str, elapsed_seconds: float) -> ExecutionReport:
    """Build a report for a request rejected before any process was spawned.

    Args:
        reason: The typed rejection reason.
        elapsed_seconds: Time spent validating the request.

    Returns:
        A report with `STATUS_REJECTED` and no fingerprints or outcomes.
    """
    return ExecutionReport(
        schema_version=EXECUTION_REPORT_SCHEMA_VERSION,
        status=STATUS_REJECTED,
        reason=reason,
        input_fingerprint=None,
        resulting_fingerprint=None,
        command_outcomes=(),
        elapsed_seconds=elapsed_seconds,
        warnings=(),
    )


def execute(
    request: ExecutionRequest,
    *,
    on_process_spawned: Callable[[subprocess.Popen[str]], None] | None = None,
) -> ExecutionReport:
    """Execute a request's commands against its snapshot in a fresh process.

    Validates the request in this process first: an unsupported request
    schema version, an oversized snapshot, malformed snapshot JSON, or an
    incompatible snapshot schema version is rejected here, with no process
    ever spawned and no scratch data ever written. Only a request that
    passes every check causes a fresh child process to be spawned, given a
    hard wall-clock deadline, and reaped -- on every exit path, including
    timeout and an unhandled child crash -- with its scratch directory
    always removed.

    Args:
        request: The execution request to run.
        on_process_spawned: An optional test-only hook invoked with the
            spawned child's `subprocess.Popen` handle immediately after it
            is created, so a sabotage test can independently confirm the
            process is later reaped and no longer running. Never used by
            `execute()` itself for anything but this notification.

    Returns:
        The execution report. Never raises for any of this module's own
        documented failure modes; every one of them is reported through the
        returned report's `status`/`reason` instead.
    """
    start = time.monotonic()

    if request.schema_version != EXECUTION_REQUEST_SCHEMA_VERSION:
        return _rejected(
            REASON_UNSUPPORTED_SCHEMA_VERSION, time.monotonic() - start
        )

    encoded_snapshot = request.snapshot_json.encode("utf-8")
    if len(encoded_snapshot) > request.max_input_bytes:
        return _rejected(REASON_OVERSIZED_INPUT, time.monotonic() - start)

    try:
        from_json(request.snapshot_json)
    except json.JSONDecodeError:
        return _rejected(REASON_MALFORMED_INPUT, time.monotonic() - start)
    except ValueError:
        return _rejected(
            REASON_UNSUPPORTED_SCHEMA_VERSION, time.monotonic() - start
        )
    except (KeyError, AttributeError, TypeError):
        # Syntactically valid JSON that from_json cannot treat as a
        # snapshot object at all -- a bare scalar/array/string (whose
        # `.get("schema_version")` raises AttributeError) or a JSON object
        # missing a required key (KeyError) -- is malformed input, not an
        # unsupported-but-recognized schema version.
        return _rejected(REASON_MALFORMED_INPUT, time.monotonic() - start)

    input_fingerprint = fingerprint(request.snapshot_json)

    scratch_dir = Path(tempfile.mkdtemp(prefix="h02-execution-boundary-"))
    try:
        snapshot_path = scratch_dir / "snapshot.json"
        snapshot_path.write_text(request.snapshot_json)
        commands_path = scratch_dir / "commands.json"
        commands_path.write_text(
            json.dumps([[c.verb, list(c.args)] for c in request.commands])
        )
        output_path = scratch_dir / "output.json"

        env = os.environ.copy()
        h02_dir = str(Path(__file__).resolve().parent)
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (h02_dir, env.get("PYTHONPATH", "")) if part
        )

        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _CHILD_RUNNER_SOURCE,
                str(snapshot_path),
                str(commands_path),
                str(output_path),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if on_process_spawned is not None:
            on_process_spawned(process)

        try:
            _stdout, stderr = process.communicate(
                timeout=request.deadline_seconds
            )
        except subprocess.TimeoutExpired:
            # Hard kill, then reap: communicate() again both waits for the
            # now-killed child to actually terminate (never leaving a
            # zombie behind) and drains whatever partial output it had
            # already produced.
            process.kill()
            _stdout, stderr = process.communicate()
            return ExecutionReport(
                schema_version=EXECUTION_REPORT_SCHEMA_VERSION,
                status=STATUS_FAILED,
                reason=REASON_TIMEOUT,
                input_fingerprint=input_fingerprint,
                resulting_fingerprint=None,
                command_outcomes=(),
                elapsed_seconds=time.monotonic() - start,
                warnings=(),
            )

        if not output_path.exists():
            # The child never reached its own _write() call -- a crash
            # (this module's own CRASH_VERB sentinel, or a real one) rather
            # than a reported failure. communicate() above already waited
            # for it, so it is reaped either way.
            return ExecutionReport(
                schema_version=EXECUTION_REPORT_SCHEMA_VERSION,
                status=STATUS_FAILED,
                reason=REASON_CHILD_CRASH,
                input_fingerprint=input_fingerprint,
                resulting_fingerprint=None,
                command_outcomes=(),
                elapsed_seconds=time.monotonic() - start,
                warnings=(f"child stderr: {stderr}",) if stderr else (),
            )

        payload = json.loads(output_path.read_text())
        command_outcomes = tuple(
            CommandOutcome(
                index=outcome["index"],
                verb=outcome["verb"],
                status=outcome["status"],
                error=outcome.get("error"),
            )
            for outcome in payload.get("command_outcomes", [])
        )
        resulting_fingerprint = payload.get("resulting_fingerprint")
        status = payload["status"]
        reason = payload["reason"]

        if (
            status == STATUS_OK
            and request.expected_resulting_fingerprint is not None
            and resulting_fingerprint != request.expected_resulting_fingerprint
        ):
            status = STATUS_FAILED
            reason = REASON_FIDELITY_MISMATCH

        return ExecutionReport(
            schema_version=EXECUTION_REPORT_SCHEMA_VERSION,
            status=status,
            reason=reason,
            input_fingerprint=input_fingerprint,
            resulting_fingerprint=resulting_fingerprint,
            command_outcomes=command_outcomes,
            elapsed_seconds=time.monotonic() - start,
            warnings=(),
        )
    finally:
        # Every exit path above -- success, rejection after spawn (there is
        # none), timeout, crash, command failure -- passes through here.
        shutil.rmtree(scratch_dir, ignore_errors=True)
