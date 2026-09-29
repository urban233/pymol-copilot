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
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from types import FrameType

import httpx

from pmc_agent.graph import DEFAULT_GENERATION_DEADLINE_SECONDS
from pmc_agent.graph import DEFAULT_MAX_COMPLETION_TOKENS
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.inference.lemonade import DEFAULT_BACKEND
from pmc_agent.inference.lemonade import DEFAULT_BASE_URL
from pmc_agent.inference.lemonade import DEFAULT_CHECKPOINT
from pmc_agent.inference.lemonade import DEFAULT_CONTEXT_SIZE
from pmc_agent.inference.lemonade import DEFAULT_MODEL_NAME
from pmc_agent.inference.lemonade import DEFAULT_READ_TIMEOUT_SECONDS
from pmc_agent.inference.lemonade import connect_lemonade
from pmc_agent.inference.unavailable import UnavailableEngine
from pmc_agent.prompt import PROMPT_BUILDER
from pmc_agent.prompt import build_default_prompt
from pmc_agent.prompt import build_training_prompt
from pmc_agent.session import RequestGraphSession
from pmc_core.grammar import build_grammar
from pmc_server.lifecycle import RequestGraphLifecycle
from pmc_server.transport import LOOPBACK_HOST
from pmc_server.transport import LoopbackPlanServer

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


#: The prompt builders `--prompt` can select. `placeholder` is the graph's
#: own default; `training` is the prompt the local model was fine-tuned on
#: (master plan item 17), which the offline evaluation sends too.
PROMPT_BUILDERS: dict[str, PROMPT_BUILDER] = {
    "placeholder": build_default_prompt,
    "training": build_training_prompt,
}


@dataclass(frozen=True)
class EngineOptions:
    """Which model the server loads, and how.

    Every default is the adapter's own, so a server started without
    options behaves as it always has. Serving the fine-tuned model takes
    its name, checkpoint and a context large enough for its prompts
    (configs/evaluation/finetuned.json holds the values the evaluation
    used).

    Attributes:
        model_name: The exact Lemonade model identifier.
        checkpoint: The exact checkpoint that identifier must load.
        backend: The llama.cpp backend (`cpu`, `cuda`, `vulkan`, ...).
        context_size: The context size to load the model with.
        read_timeout_seconds: The adapter's HTTP read timeout.
    """

    model_name: str = DEFAULT_MODEL_NAME
    checkpoint: str = DEFAULT_CHECKPOINT
    backend: str = DEFAULT_BACKEND
    context_size: int = DEFAULT_CONTEXT_SIZE
    read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS


@dataclass(frozen=True)
class GenerationOptions:
    """What the request graph sends the engine, and within what bounds.

    Attributes:
        prompt: A `PROMPT_BUILDERS` key.
        grammar: Whether `pmc_core.grammar.build_grammar()` goes with
            every completion.
        max_tokens: The token budget of every completion.
        deadline_seconds: The wall-clock budget of every completion.
    """

    prompt: str = "placeholder"
    grammar: bool = False
    max_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS
    deadline_seconds: float = DEFAULT_GENERATION_DEADLINE_SECONDS


def build_engine(
    *,
    base_url: str = DEFAULT_BASE_URL,
    options: EngineOptions | None = None,
    client: httpx.Client | None = None,
) -> InferenceEngine:
    """Connect to Lemonade, or return an engine that reports why it could not.

    There is no retry and no fallback to a second engine: a failed probe
    is recorded once, in `UnavailableEngine`, and the server starts anyway
    so `copilot_health` can still report it (SPECIFICATION.md:609:
    "Server remains available for diagnostics; no unconstrained fallback").

    Args:
        base_url: The local Lemonade HTTP origin.
        options: Which model to load; the adapter's defaults when None.
        client: An optional hermetic transport client, for tests.

    Returns:
        A proven `LemonadeEngine`, or an `UnavailableEngine` recording the
        first capability failure.
    """
    options = options or EngineOptions()
    result = connect_lemonade(
        base_url=base_url,
        model_name=options.model_name,
        checkpoint=options.checkpoint,
        backend=options.backend,
        context_size=options.context_size,
        read_timeout_seconds=options.read_timeout_seconds,
        client=client,
    )
    if isinstance(result, EngineFailure):
        return UnavailableEngine(result)
    return result


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
    ready: Callable[[int], None] | None = None,
    stop: threading.Event | None = None,
) -> None:
    """Build the real stack, start it, write the handoff, and block.

    Args:
        base_url: The local Lemonade HTTP origin.
        handoff_path: Where to write the port and credential for PyMOL.
        engine_options: Which model to load; the adapter's defaults when
            None.
        generation: What the graph sends the engine; the graph's own
            defaults (placeholder prompt, no grammar) when None.
        ready: Optional callback invoked with the bound port once the
            server has started and the handoff file has been written --
            for a test to synchronize on, never used in production.
        stop: Optional event this function waits on instead of installing
            its own signal handlers -- for a test that wants to stop the
            server deterministically without sending it a real signal.
            Production installs `SIGINT`/`SIGTERM` handlers instead.
    """
    generation = generation or GenerationOptions()
    engine = build_engine(base_url=base_url, options=engine_options)
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
        "--lemonade-base-url",
        default=DEFAULT_BASE_URL,
        help="The local Lemonade HTTP origin (default: %(default)s).",
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
    defaults, generation_defaults = EngineOptions(), GenerationOptions()
    parser.add_argument("--model-name", default=defaults.model_name)
    parser.add_argument("--checkpoint", default=defaults.checkpoint)
    parser.add_argument("--backend", default=defaults.backend)
    parser.add_argument(
        "--context-size", type=int, default=defaults.context_size
    )
    parser.add_argument(
        "--read-timeout-seconds",
        type=float,
        default=defaults.read_timeout_seconds,
    )
    parser.add_argument(
        "--prompt",
        choices=sorted(PROMPT_BUILDERS),
        default=generation_defaults.prompt,
        help="The prompt builder (default: %(default)s).",
    )
    parser.add_argument(
        "--grammar",
        action="store_true",
        help="Send pmc_core.grammar.build_grammar() with every completion.",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=generation_defaults.max_tokens
    )
    parser.add_argument(
        "--generation-deadline-seconds",
        type=float,
        default=generation_defaults.deadline_seconds,
    )
    args = parser.parse_args(argv)
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
        base_url=args.lemonade_base_url,
        handoff_path=handoff,
        engine_options=EngineOptions(
            model_name=args.model_name,
            checkpoint=args.checkpoint,
            backend=args.backend,
            context_size=args.context_size,
            read_timeout_seconds=args.read_timeout_seconds,
        ),
        generation=GenerationOptions(
            prompt=args.prompt,
            grammar=args.grammar,
            max_tokens=args.max_tokens,
            deadline_seconds=args.generation_deadline_seconds,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
