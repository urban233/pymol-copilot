# Copyright 2026 PyMOL Copilot contributors.
"""A minimal production server entrypoint.

docs/master_plan.md item 12. Item 11 built `UnavailableEngine` and the
health seam; nothing before this module ever started a real process,
minted a real per-run credential, or handed PyMOL anything to connect to.
Scope is deliberately minimal, per this item's own plan: process launch,
the Lemonade probe falling back to `UnavailableEngine` when it cannot
connect, and the port and credential hand-off to PyMOL. It is not a
service manager, not multi-session support beyond what
`pmc_agent.session.RequestGraphSession` already gives for free, and there
is no retry loop -- SPECIFICATION.md:554: no remote fallback, no
unconstrained mode.

The credential and port reach PyMOL through a private local file rather
than an environment variable: an environment variable holding a live
credential is visible to every child process and, on some platforms, to
`ps`. `write_handoff` stages, `chmod`s, and verifies the file's mode
before an atomic `os.replace`, the same sequence
`pmc_client.recovery.RecoveryStore.save` already uses for its own
recovery points.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import stat
import threading
import uuid
from collections.abc import Callable
from collections.abc import Sequence
from datetime import UTC
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any

import httpx

from pmc_agent.inference.base import ENGINE_UNKNOWN
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.inference.lemonade import DEFAULT_BASE_URL
from pmc_agent.inference.lemonade import LemonadeEngine
from pmc_agent.inference.lemonade import connect_lemonade
from pmc_agent.inference.lemonade import loaded_llamacpp_args
from pmc_agent.inference.unavailable import UnavailableEngine
from pmc_agent.session import RequestGraphSession
from pmc_core.grammar import build_grammar
from pmc_server.config import PROMPT_BUILDERS
from pmc_server.config import EngineOptions
from pmc_server.config import GenerationOptions
from pmc_server.config import InvalidRuntimeConfigError
from pmc_server.config import RuntimeConfig
from pmc_server.config import engine_mismatch
from pmc_server.config import load_runtime_config
from pmc_server.config import resolve_path
from pmc_server.lifecycle import RequestGraphLifecycle
from pmc_server.trace import TracingEngine
from pmc_server.trace import open_trace
from pmc_server.transport import LOOPBACK_HOST
from pmc_server.transport import LoopbackPlanServer

#: Re-exported: what the server loads and sends is defined beside the
#: config reader that also builds it (`pmc_server.config`).
__all__ = [
    "PROMPT_BUILDERS",
    "EngineOptions",
    "GenerationOptions",
    "build_engine",
    "main",
    "serve",
]

#: Where the handoff file lives by default, relative to a root (the
#: user's home directory unless overridden for a test): the same
#: directory `pmc_client.recovery.RecoveryStore` uses for its own private
#: state, so there is exactly one private PyMOL-Copilot directory per
#: user, not two.
DEFAULT_HANDOFF_PATH = Path(".pymol-copilot") / "session.json"

#: Directory and file permissions for the handoff file and its parent,
#: matching `pmc_client.recovery`'s own constants.
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600


def build_engine(
    *,
    base_url: str = DEFAULT_BASE_URL,
    options: EngineOptions | None = None,
    client: httpx.Client | None = None,
    expected: RuntimeConfig | None = None,
) -> InferenceEngine:
    """Connect to Lemonade, or return an engine that reports why it could not.

    There is no retry and no fallback to a second engine: a failed probe
    is recorded once, in `UnavailableEngine`, and the server starts anyway
    so `copilot_health` can still report it (SPECIFICATION.md:609:
    "Server remains available for diagnostics; no unconstrained fallback").

    Args:
        base_url: The local Lemonade HTTP origin.
        options: Which model to load; the defaults when None.
        client: An optional hermetic transport client, for tests.
        expected: The evaluation config the server was started from, if
            any. An engine that is not the one it records -- another
            model, Lemonade version, or chat-template date -- is refused
            the same way a failed probe is.

    Returns:
        A proven `LemonadeEngine`, or an `UnavailableEngine` recording the
        first capability failure or mismatch.
    """
    options = options or EngineOptions()
    result = connect_lemonade(
        base_url=base_url,
        model_name=options.model_name,
        checkpoint=options.checkpoint,
        backend=options.backend,
        context_size=options.context_size,
        connect_timeout_seconds=options.connect_timeout_seconds,
        read_timeout_seconds=options.read_timeout_seconds,
        client=client,
    )
    if isinstance(result, EngineFailure):
        return UnavailableEngine(result)
    if expected is not None:
        mismatch = _mismatch(result, expected, base_url=base_url, client=client)
        if mismatch is not None:
            result.close()
            return UnavailableEngine(EngineFailure(ENGINE_UNKNOWN, mismatch))
    return result


def _mismatch(
    engine: LemonadeEngine,
    expected: RuntimeConfig,
    *,
    base_url: str,
    client: httpx.Client | None,
) -> str | None:
    """Compare a connected engine with the config it must match.

    Args:
        engine: The proven engine.
        expected: The config the server was started from.
        base_url: The local Lemonade HTTP origin.
        client: An optional hermetic transport client, for tests.

    Returns:
        What differs, or None.
    """
    return engine_mismatch(
        expected,
        model_identity=engine.model_identity,
        lemonade_version=engine.capabilities.lemonade_version,
        llamacpp_args=loaded_llamacpp_args(
            base_url=base_url,
            model_name=expected.engine.model_name,
            timeout_seconds=expected.engine.connect_timeout_seconds,
            client=client,
        ),
    )


def write_handoff(
    path: Path,
    *,
    port: int,
    credential: str,
    pid: int,
    host: str = LOOPBACK_HOST,
) -> None:
    """Write the port and credential PyMOL needs, atomically and private.

    Args:
        path: Where to write the handoff file.
        port: The server's bound loopback port.
        credential: The ephemeral per-run credential.
        pid: This server process's OS process id.
        host: The server's bound loopback address.

    Raises:
        RuntimeError: If the written file cannot be verified to have
            mode 0600 on a platform that enforces POSIX permissions.
    """
    directory = path.parent
    # Only chmod directories this call itself creates: `--handoff` can name
    # any path (the current directory, the user's home directory, `/tmp`),
    # and unconditionally chmodding a pre-existing one would either mutate a
    # directory this process does not own or, when it isn't owned by the
    # current user, raise PermissionError and crash the server right after
    # it started. `mkdir(parents=True)` can create more than one level (e.g.
    # a `--handoff` under a not-yet-existing grandparent), so every level it
    # creates is walked and chmodded, not just the immediate parent.
    created_ancestors = []
    probe = directory
    while not probe.exists():
        created_ancestors.append(probe)
        probe = probe.parent
    directory.mkdir(parents=True, exist_ok=True)
    for created in created_ancestors:
        os.chmod(created, _DIRECTORY_MODE)
    payload = json.dumps(
        {
            "host": host,
            "port": port,
            "credential": credential,
            "pid": pid,
            "startedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    )
    staged = directory / f".{path.name}-{uuid.uuid4().hex}.tmp"
    try:
        # Created already-restricted, via `os.open`'s own `mode` argument,
        # rather than written with `Path.write_text` and chmodded
        # afterward: the latter creates the file at the platform's default
        # (typically world-readable) mode first, leaving a window in
        # which another local user could read the live credential before
        # this process narrows it.
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        if (
            os.name != "nt"
            and stat.S_IMODE(staged.stat().st_mode) != _FILE_MODE
        ):
            raise RuntimeError("handoff file does not have mode 0600")
        os.replace(staged, path)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def remove_handoff_if_own(path: Path, *, pid: int) -> None:
    """Remove the handoff file only if it still names this process.

    Two server processes can point at the same path (most often the
    default, unspecified `--handoff`): a second instance started while
    the first is still running -- or after it crashed without cleaning
    up -- overwrites the file with its own port and credential. If the
    first instance's own shutdown then unlinked the file unconditionally,
    it would delete the second instance's own live handoff instead of its
    own, and a client reading it afterward would find nothing, even
    though a real server is still up.

    Args:
        path: The handoff file to remove.
        pid: This process's own OS process id.
    """
    # Renamed onto a private, pid-named path first, rather than read then
    # unlinked in two separate steps: a second server's own `os.replace`
    # can land in the gap between this function's read and its unlink, and
    # a plain `path.unlink()` afterward would then delete whatever THAT
    # server just installed, not the (already-confirmed) file this process
    # actually read -- exactly the bug this function exists to prevent, one
    # step later than the check for it. `os.replace` (not `os.rename`) is
    # atomic and overwrite-safe on both POSIX and Windows: whichever of
    # this rename and a racing second server's own `os.replace(..., path)`
    # reaches the filesystem first fully wins, so `claimed` always ends up
    # holding one complete, uncorrupted file -- either this process's own,
    # or (if the second server's replace won the race) the second
    # server's, which is then put back untouched.
    claimed = path.with_name(f".{path.name}-{pid}.claim")
    try:
        os.replace(path, claimed)
    except OSError:
        return
    try:
        payload = json.loads(claimed.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        payload = None
    if isinstance(payload, dict) and payload.get("pid") == pid:
        claimed.unlink(missing_ok=True)
    else:
        # Restored via `os.link`, not `os.replace`: a *third* server could
        # have written its own live handoff to `path` in the gap between
        # this function's rename above and the restore here, and
        # `os.replace` would silently clobber it. `os.link` only adds a
        # second directory entry for the same inode and raises
        # `FileExistsError` instead of overwriting, so a third server's
        # fresher handoff is left untouched.
        try:
            os.link(claimed, path)
        except FileExistsError:
            # A third server's own handoff is already live at `path`;
            # this process's rescued copy is now redundant.
            claimed.unlink(missing_ok=True)
        except OSError:
            # Could not restore `path` for some other reason. Leave the
            # rescued copy at `claimed` rather than deleting the only
            # remaining copy of a live server's handoff.
            pass
        else:
            claimed.unlink(missing_ok=True)


def serve(
    *,
    base_url: str = DEFAULT_BASE_URL,
    handoff_path: Path,
    engine_options: EngineOptions | None = None,
    generation: GenerationOptions | None = None,
    expected: RuntimeConfig | None = None,
    trace_path: Path | None = None,
    ready: Callable[[int], None] | None = None,
    stop: threading.Event | None = None,
    engine: InferenceEngine | None = None,
) -> None:
    """Build the real stack, start it, write the handoff, and block.

    Args:
        base_url: The local Lemonade HTTP origin.
        handoff_path: Where to write the port and credential for PyMOL.
        engine_options: Which model to load; the defaults when None.
        generation: What the graph sends the engine; the defaults (the
            training prompt, the grammar) when None.
        expected: The evaluation config the server was started from, if
            any; an engine that does not match it is refused.
        trace_path: A private file to append every completion call to
            (`pmc_server.trace`), or None, the default, to record none.
        ready: Optional callback invoked with the bound port once the
            server has started and the handoff file has been written --
            for a test to synchronize on, never used in production.
        stop: Optional event this function waits on instead of installing
            its own signal handlers -- for a test that wants to stop the
            server deterministically without sending it a real signal.
            Production installs `SIGINT`/`SIGTERM` handlers instead.
        engine: Optional engine used instead of connecting to Lemonade --
            for a test that drives the real server with a scripted
            engine, never used in production.
    """
    generation = generation or GenerationOptions()
    if engine is None:
        engine = build_engine(
            base_url=base_url, options=engine_options, expected=expected
        )
    if trace_path is not None:
        engine = TracingEngine(engine, open_trace(trace_path))
    session = RequestGraphSession(
        engine=engine,
        prompt_builder=PROMPT_BUILDERS[generation.prompt],
        grammar=build_grammar() if generation.grammar else None,
        max_tokens=generation.max_tokens,
        deadline_seconds=generation.deadline_seconds,
    )
    lifecycle = RequestGraphLifecycle(session=session)
    credential = secrets.token_urlsafe(32)
    server = LoopbackPlanServer(
        credential,
        lifecycle,
        reject_handler=lifecycle.reject,
        cancel_handler=lifecycle.cancel,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
        health_handler=lifecycle.health,
    )
    own_stop = stop if stop is not None else threading.Event()
    if stop is None:

        def _handle_signal(signum: int, frame: FrameType | None) -> None:
            del signum, frame
            own_stop.set()

        # Installed before the server actually starts, not after the
        # handoff is written: a SIGTERM arriving in between would
        # otherwise use Python's default action and kill the process
        # without running the `finally` below, leaving a handoff file
        # behind that names a port and credential nothing is listening on
        # anymore.
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    try:
        server.start()
        write_handoff(
            handoff_path,
            host=server.host,
            port=server.port,
            credential=credential,
            pid=os.getpid(),
        )
        print(
            f"pymol-copilot server listening on {server.host}:{server.port}; "
            f"handoff written to {handoff_path}"
        )
        if ready is not None:
            ready(server.port)
        # A timed, looping wait, not a single call with no timeout at all:
        # on Windows (Python 3.13), an untimed `Event.wait` blocks on a
        # lock acquire that cannot be interrupted, so the SIGINT handler
        # above never actually runs while the main thread is parked here,
        # and Ctrl+C cannot stop the server.
        while not own_stop.wait(timeout=0.5):
            pass
    finally:
        server.close()
        remove_handoff_if_own(handoff_path, pid=os.getpid())
        # A proven `LemonadeEngine` owns an `httpx.Client` of its own;
        # `UnavailableEngine` holds nothing to release, and the
        # `InferenceEngine` protocol itself does not declare `close`.
        close_engine = getattr(engine, "close", None)
        if callable(close_engine):
            close_engine()


#: The flags that set what a `--config` also sets, with their types.
_CONFIGURED_FLAGS: tuple[tuple[str, type], ...] = (
    ("--lemonade-base-url", str),
    ("--model-name", str),
    ("--checkpoint", str),
    ("--backend", str),
    ("--context-size", int),
    ("--read-timeout-seconds", float),
    ("--max-tokens", int),
    ("--generation-deadline-seconds", float),
)


def _from_flags(
    args: argparse.Namespace,
) -> tuple[str, EngineOptions, GenerationOptions]:
    """Build the engine and generation settings from individual flags.

    Args:
        args: The parsed command line, without `--config`.

    Returns:
        The Lemonade origin, the engine options and the generation
        options, each flag left alone taking its default.
    """
    engine, generation = EngineOptions(), GenerationOptions()

    def value(name: str, default: object) -> Any:
        given = getattr(args, name)
        return default if given is None else given

    return (
        value("lemonade_base_url", DEFAULT_BASE_URL),
        EngineOptions(
            model_name=value("model_name", engine.model_name),
            checkpoint=value("checkpoint", engine.checkpoint),
            backend=value("backend", engine.backend),
            context_size=value("context_size", engine.context_size),
            read_timeout_seconds=value(
                "read_timeout_seconds", engine.read_timeout_seconds
            ),
        ),
        GenerationOptions(
            prompt=args.prompt,
            grammar=args.grammar,
            max_tokens=value("max_tokens", generation.max_tokens),
            deadline_seconds=value(
                "generation_deadline_seconds", generation.deadline_seconds
            ),
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the server until it is signaled to stop.

    Args:
        argv: Command-line arguments, excluding the program name. Reads
            `sys.argv[1:]` when omitted.

    Returns:
        Zero, once `serve` returns after a clean shutdown.
    """
    parser = argparse.ArgumentParser(
        prog="pymol-copilot-server",
        description="Start the PyMOL-Copilot loopback server.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "An evaluation config (configs/evaluation/*.json) to take the "
            "engine and generation settings from, so the server runs "
            "exactly the configuration that was evaluated. Cannot be "
            "combined with the engine or generation flags below."
        ),
    )
    parser.add_argument(
        "--handoff",
        type=Path,
        default=None,
        help=(
            "Where to write the port/credential handoff file "
            "(default: ~/.pymol-copilot/session.json)."
        ),
    )
    parser.add_argument(
        "--trace-file",
        type=Path,
        default=None,
        help=(
            "Append every completion the server asks for -- its text, stop "
            "reason and timing, and its prompt's SHA-256 -- to this private "
            "file. Off by default: nothing is retained unless asked for."
        ),
    )
    parser.add_argument(
        "--prompt",
        choices=sorted(PROMPT_BUILDERS),
        default=GenerationOptions().prompt,
        help="The prompt builder (default: %(default)s).",
    )
    parser.add_argument(
        "--grammar",
        action=argparse.BooleanOptionalAction,
        default=GenerationOptions().grammar,
        help=(
            "Send pmc_core.grammar.build_grammar() with every completion "
            "(default: on)."
        ),
    )
    # The engine and generation settings a config also sets. Their
    # defaults are applied below, not here, so a flag given alongside
    # --config can be told apart from one left alone.
    for flag, kind in _CONFIGURED_FLAGS:
        parser.add_argument(flag, type=kind, default=None)
    args = parser.parse_args(argv)
    given = [
        flag
        for flag, _ in _CONFIGURED_FLAGS
        if getattr(args, flag[2:].replace("-", "_")) is not None
    ]
    expected: RuntimeConfig | None = None
    try:
        if args.config is not None:
            if given:
                parser.error(
                    f"--config sets the engine and generation; "
                    f"{', '.join(given)} cannot be combined with it"
                )
            expected = load_runtime_config(args.config)
            base_url = expected.base_url
            engine_options = expected.engine
            generation = expected.generation(
                prompt=args.prompt, grammar=args.grammar
            )
        else:
            base_url, engine_options, generation = _from_flags(args)
    except (InvalidRuntimeConfigError, ValueError) as error:
        parser.error(str(error))
    trace_path = None
    if args.trace_file is not None:
        trace_path = resolve_path(args.trace_file)
        try:
            open_trace(trace_path).close()
        except OSError as error:
            parser.error(f"cannot open --trace-file: {error}")
    # Resolved here, not as the argument's own default: Path.home() raises
    # on a platform or sandbox with no resolvable home directory (observed
    # on Windows CI), and that must not happen merely from registering
    # this argument -- only when its value is actually needed, which never
    # happens when a caller supplies --handoff explicitly.
    handoff = (
        args.handoff
        if args.handoff is not None
        else Path.home() / DEFAULT_HANDOFF_PATH
    )
    serve(
        base_url=base_url,
        handoff_path=handoff,
        engine_options=engine_options,
        generation=generation,
        expected=expected,
        trace_path=trace_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
