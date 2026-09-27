# Copyright 2026 PyMOL Copilot contributors.
"""Bootstrap the Copilot client from the server's own handoff file.

docs/master_plan.md item 12. `pmc_server.main.write_handoff` is the only
writer; this module is the only reader, and it is deliberately paranoid:
the file names a live credential and a port to connect to, so every field
is validated before a transport or a client is ever built, and a refusal
never raises into PyMOL's own command dispatch -- it prints one bounded
line and returns `None`, the same contract every other registered command
follows (`pmc_client.messages`).

This module must never import `pmc_agent` or anything that pulls in
LangGraph or the training stack: it runs inside PyMOL's own interpreter,
the one process neither may ever reach
(`tools/bazel/check_dependency_boundaries.py`).
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pmc_client.command import CopilotCommandClient
from pmc_client.command import RegisteredPyMOLSession
from pmc_client.command import register_copilot
from pmc_client.messages import bounded
from pmc_client.recovery import RecoveryStore
from pmc_client.transport import LOOPBACK_HOST
from pmc_client.transport import LoopbackPlanClient

#: The largest handoff file this reader will parse. The server writes a
#: few dozen bytes; anything past this is refused before `json.loads` ever
#: sees it, not merely bounded afterward.
MAX_HANDOFF_BYTES = 4096

#: The credential `secrets.token_urlsafe(32)` produces is 43 base64url
#: characters; refuse anything shorter as a defensive floor, not an exact
#: length match -- a future server build widening the token must not
#: break every existing client build.
_MIN_CREDENTIAL_LENGTH = 32
_CREDENTIAL_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


#: Windows error and status codes `_windows_process_is_running` decides on.
#: Named here, rather than as bare literals in that function, so a test can
#: reference the same constants a fake supplies.
_ERROR_ACCESS_DENIED = 5
_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
#: The largest value `OpenProcess`'s `DWORD` pid argument can carry; a
#: larger one would raise `ctypes.ArgumentError` rather than return a
#: liveness answer.
_MAX_WINDOWS_PID = 0xFFFFFFFF


def _windows_process_is_running(
    pid: int,
    *,
    open_process: Callable[[int], int],
    get_exit_code_process: Callable[[int], int | None],
    close_handle: Callable[[int], None],
    get_last_error: Callable[[], int],
) -> bool:
    """Decide process liveness from Windows API results, injected as calls.

    A pure decision, factored out of `_process_is_running`'s Windows
    branch, so its two failure modes -- an access-denied `OpenProcess`
    call is not the same as a genuinely gone process, and a valid handle
    is not by itself proof the process hasn't already exited -- can be
    exercised with fakes from a non-Windows machine, rather than only
    trusted by inspection until it runs on real Windows CI.

    Args:
        pid: The process id to check.
        open_process: Given `pid`, returns a handle (nonzero on success),
            wrapping `OpenProcess`.
        get_exit_code_process: Given a handle, returns the process's exit
            code, or `None` if the call itself failed, wrapping
            `GetExitCodeProcess`.
        close_handle: Closes a handle this function opened.
        get_last_error: Returns the calling thread's last Windows error
            code, wrapping `ctypes.get_last_error()`.

    Returns:
        True if the process still exists and has not exited; False
        otherwise.
    """
    handle = open_process(pid)
    if not handle:
        # A process this account cannot even query still exists --
        # matching the POSIX branch's own `PermissionError` -> True
        # below, not treating every `OpenProcess` failure as "gone". Only
        # ERROR_ACCESS_DENIED means that; anything else (for instance
        # ERROR_INVALID_PARAMETER for an already-recycled pid) means it
        # genuinely does not.
        return get_last_error() == _ERROR_ACCESS_DENIED
    try:
        exit_code = get_exit_code_process(handle)
        if exit_code is None:
            return False
        # A handle staying valid does not by itself mean the process is
        # still running -- another process (a `Popen` launcher, for
        # instance) can keep holding one after its target has already
        # exited, and comparing the exit code against STILL_ACTIVE is
        # what actually tells the two cases apart.
        return exit_code == _STILL_ACTIVE
    finally:
        close_handle(handle)


def _process_is_running(pid: int) -> bool:
    """Return whether a process with this pid currently exists.

    Never signals or otherwise affects the process. On POSIX,
    `os.kill(pid, 0)` is the standard liveness probe -- sending signal 0
    performs no action beyond the existence and permission checks. That
    trick does not carry over to Windows: Windows' `os.kill` only treats
    `signal.CTRL_C_EVENT`/`CTRL_BREAK_EVENT` specially, and every other
    value, including 0, is passed to `TerminateProcess` -- so probing
    liveness that way would kill the very process being checked, or, once
    its pid has been recycled, an unrelated one. `OpenProcess` and
    `GetExitCodeProcess` are the Windows-safe equivalent
    (`_windows_process_is_running`): a handle they return is closed
    immediately and never used to signal or terminate anything.

    Args:
        pid: The process id to check.

    Returns:
        True if a process with this pid currently exists (whether or not
        it is owned by the current user); False otherwise.
    """
    if os.name == "nt":
        if pid > _MAX_WINDOWS_PID:
            return False
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        )
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetExitCodeProcess.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        def _open_process(target_pid: int) -> int:
            return kernel32.OpenProcess(
                _PROCESS_QUERY_LIMITED_INFORMATION, False, target_pid
            )

        def _get_exit_code_process(handle: int) -> int | None:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return None
            return exit_code.value

        return _windows_process_is_running(
            pid,
            open_process=_open_process,
            get_exit_code_process=_get_exit_code_process,
            close_handle=kernel32.CloseHandle,
            get_last_error=ctypes.get_last_error,
        )
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError):
        # OverflowError: a pid past the platform's `pid_t` range (a
        # handoff naming, say, 2**40) cannot name any process, and must
        # not escape into PyMOL's command dispatch.
        return False
    return True


def _valid_credential(value: object) -> bool:
    """Check a handoff credential's shape, never its exact contents.

    Args:
        value: The candidate credential value.

    Returns:
        True iff value is a string of at least `_MIN_CREDENTIAL_LENGTH`
        characters, all drawn from the URL-safe base64 alphabet.
    """
    return (
        isinstance(value, str)
        and len(value) >= _MIN_CREDENTIAL_LENGTH
        and set(value) <= _CREDENTIAL_ALPHABET
    )


def connect_from_handoff(
    cmd: RegisteredPyMOLSession,
    output: Callable[[str], None],
    *,
    path: Path,
    timeout_seconds: float | None = None,
    recovery_store: RecoveryStore | None = None,
) -> CopilotCommandClient | None:
    """Read the server's handoff file and register Copilot if it is valid.

    Args:
        cmd: The live PyMOL session receiving the callbacks.
        output: Callable receiving one bounded diagnostic line, on
            success or refusal alike.
        path: Where to look for the handoff file.
        timeout_seconds: Forwarded to `LoopbackPlanClient`, when given.
        recovery_store: Forwarded to `register_copilot`. Defaults to the
            real per-session recovery lifecycle rooted at the user's own
            home directory; a test injects one rooted elsewhere so a
            recovery point a regression wrote can actually be observed,
            rather than landing in the real `~/.pymol-copilot/recovery`
            where nothing watching a test's own `tmp_path` would ever see
            it.

    Returns:
        The registered command client, or `None` if the handoff could not
        be read or did not validate. Never raises.
    """
    try:
        status = path.stat()
    except OSError:
        output(
            "copilot: no PyMOL-Copilot server handoff found at "
            f"{bounded(str(path))}. Start the server first."
        )
        return None
    oversized = (
        f"copilot: the handoff file at {bounded(str(path))} is larger "
        "than expected and was not read."
    )
    # A FIFO or device node reports a size of 0 and would block (or never
    # end) on read, freezing PyMOL's own command thread.
    if not stat.S_ISREG(status.st_mode) or status.st_size > MAX_HANDOFF_BYTES:
        output(oversized)
        return None
    try:
        # One bounded read from one handle, not `read_text` after the
        # `stat` above: the file can be replaced in between, and
        # `read_text` itself reads without any limit.
        with path.open("rb") as handle:
            raw = handle.read(MAX_HANDOFF_BYTES + 1)
        if len(raw) > MAX_HANDOFF_BYTES:
            output(oversized)
            return None
        payload: Any = json.loads(raw.decode("utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ):
        # RecursionError: json.loads's own recursive-descent parser raises
        # it for deeply nested input (observed with ~3000 levels of `[`,
        # comfortably under MAX_HANDOFF_BYTES) -- this module's own
        # docstring promises never to raise into PyMOL's command dispatch,
        # and that promise must hold for a malformed handoff file, not
        # only for a merely oversized or non-JSON one.
        output(
            f"copilot: the handoff file at {bounded(str(path))} could not "
            "be read. Restart the server."
        )
        return None
    if not isinstance(payload, dict):
        output(
            "copilot: the handoff file did not contain the expected "
            "fields. Restart the server."
        )
        return None

    host = payload.get("host")
    port = payload.get("port")
    credential = payload.get("credential")
    # Exactly the one address `LoopbackPlanClient` actually dials, not
    # merely any loopback name: `localhost`, `::1`, or `127.0.0.2` would
    # each pass a looser "is loopback" check, yet the transport would still
    # connect to 127.0.0.1 and hand this credential to whatever listens
    # there. Non-loopback listening is a configuration error
    # (SPECIFICATION.md:554), and this reader is the last place to catch
    # it, not only the server that wrote the file.
    if host != LOOPBACK_HOST:
        output(
            "copilot: refusing a handoff naming a non-loopback host. "
            "Restart the server."
        )
        return None
    if (
        not isinstance(port, int)
        or isinstance(port, bool)
        or not (1 <= port <= 65535)
    ):
        output(
            "copilot: the handoff file named an invalid port. Restart "
            "the server."
        )
        return None
    if not _valid_credential(credential):
        output(
            "copilot: the handoff file named an invalid credential. "
            "Restart the server."
        )
        return None
    pid = payload.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        output(
            "copilot: the handoff file named an invalid process id. "
            "Restart the server."
        )
        return None
    if not _process_is_running(pid):
        # A handoff a SIGKILLed server, a Windows `terminate()`, or a power
        # loss left behind: without this, its port and credential would
        # still be accepted, and either fail confusingly later or, worse,
        # reach a different, unrelated local process that has since bound
        # the same now-recycled ephemeral port.
        output(
            f"copilot: the server named in the handoff file at "
            f"{bounded(str(path))} is no longer running. Restart the "
            "server."
        )
        return None

    assert isinstance(credential, str)  # narrowed by _valid_credential above
    transport_kwargs: dict[str, Any] = {}
    if timeout_seconds is not None:
        transport_kwargs["timeout_seconds"] = timeout_seconds
    client = register_copilot(
        cmd,
        LoopbackPlanClient(port, credential, **transport_kwargs),
        output,
        recovery_store=recovery_store,
    )
    output(f"copilot: connected to the server on {LOOPBACK_HOST}:{port}.")
    return client
