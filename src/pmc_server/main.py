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

import httpx

from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.inference.lemonade import DEFAULT_BASE_URL
from pmc_agent.inference.lemonade import connect_lemonade
from pmc_agent.inference.unavailable import UnavailableEngine
from pmc_agent.session import RequestGraphSession
from pmc_server.lifecycle import RequestGraphLifecycle
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


def build_engine(
    *,
    base_url: str = DEFAULT_BASE_URL,
    client: httpx.Client | None = None,
) -> InferenceEngine:
    """Connect to Lemonade, or return an engine that reports why it could not.

    There is no retry and no fallback to a second engine: a failed probe
    is recorded once, in `UnavailableEngine`, and the server starts anyway
    so `copilot_health` can still report it (SPECIFICATION.md:609:
    "Server remains available for diagnostics; no unconstrained fallback").

    Args:
        base_url: The local Lemonade HTTP origin.
        client: An optional hermetic transport client, for tests.

    Returns:
        A proven `LemonadeEngine`, or an `UnavailableEngine` recording the
        first capability failure.
    """
    result = connect_lemonade(base_url=base_url, client=client)
    if isinstance(result, EngineFailure):
        return UnavailableEngine(result)
    return result


def write_handoff(path: Path, *, port: int, credential: str, pid: int) -> None:
    """Write the port and credential PyMOL needs, atomically and private.

    Args:
        path: Where to write the handoff file.
        port: The server's bound loopback port.
        credential: The ephemeral per-run credential.
        pid: This server process's OS process id.

    Raises:
        RuntimeError: If the written file cannot be verified to have
            mode 0600 on a platform that enforces POSIX permissions.
    """
    directory = path.parent
    # Only chmod a directory this call itself creates: `--handoff` can name
    # any path (the current directory, the user's home directory, `/tmp`),
    # and unconditionally chmodding a pre-existing one would either mutate a
    # directory this process does not own or, when it isn't owned by the
    # current user, raise PermissionError and crash the server right after
    # it started.
    directory_already_existed = directory.exists()
    directory.mkdir(parents=True, exist_ok=True)
    if not directory_already_existed:
        os.chmod(directory, _DIRECTORY_MODE)
    payload = json.dumps(
        {
            "host": "127.0.0.1",
            "port": port,
            "credential": credential,
            "pid": pid,
            "startedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    )
    staged = directory / f".{path.name}-{uuid.uuid4().hex}.tmp"
    try:
        staged.write_text(payload, encoding="utf-8")
        os.chmod(staged, _FILE_MODE)
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
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return
    if isinstance(payload, dict) and payload.get("pid") == pid:
        path.unlink(missing_ok=True)


def serve(
    *,
    base_url: str = DEFAULT_BASE_URL,
    handoff_path: Path,
    ready: Callable[[int], None] | None = None,
    stop: threading.Event | None = None,
) -> None:
    """Build the real stack, start it, write the handoff, and block.

    Args:
        base_url: The local Lemonade HTTP origin.
        handoff_path: Where to write the port and credential for PyMOL.
        ready: Optional callback invoked with the bound port once the
            server has started and the handoff file has been written --
            for a test to synchronize on, never used in production.
        stop: Optional event this function waits on instead of installing
            its own signal handlers -- for a test that wants to stop the
            server deterministically without sending it a real signal.
            Production installs `SIGINT`/`SIGTERM` handlers instead.
    """
    engine = build_engine(base_url=base_url)
    session = RequestGraphSession(engine=engine)
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
            port=server.port,
            credential=credential,
            pid=os.getpid(),
        )
        print(
            f"pymol-copilot server listening on 127.0.0.1:{server.port}; "
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
    serve(base_url=args.lemonade_base_url, handoff_path=handoff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
