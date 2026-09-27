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

import ipaddress
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pmc_client.command import CopilotCommandClient
from pmc_client.command import RegisteredPyMOLSession
from pmc_client.command import register_copilot
from pmc_client.messages import bounded
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


def _is_loopback_host(host: str) -> bool:
    """Return whether one host names the local machine only.

    Args:
        host: The hostname or address to check.

    Returns:
        True for `localhost` and a literal loopback IPv4 or IPv6 address;
        False for anything else, including `0.0.0.0` and every routable
        address -- non-loopback listening is a configuration error
        (SPECIFICATION.md:554), and this reader is the last place to
        catch it, not only the server that wrote the file.
    """
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
) -> CopilotCommandClient | None:
    """Read the server's handoff file and register Copilot if it is valid.

    Args:
        cmd: The live PyMOL session receiving the callbacks.
        output: Callable receiving one bounded diagnostic line, on
            success or refusal alike.
        path: Where to look for the handoff file.
        timeout_seconds: Forwarded to `LoopbackPlanClient`, when given.

    Returns:
        The registered command client, or `None` if the handoff could not
        be read or did not validate. Never raises.
    """
    try:
        size = path.stat().st_size
    except OSError:
        output(
            "copilot: no PyMOL-Copilot server handoff found at "
            f"{bounded(str(path))}. Start the server first."
        )
        return None
    if size > MAX_HANDOFF_BYTES:
        output(
            f"copilot: the handoff file at {bounded(str(path))} is larger "
            "than expected and was not read."
        )
        return None
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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
    if not isinstance(host, str) or not _is_loopback_host(host):
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

    assert isinstance(credential, str)  # narrowed by _valid_credential above
    transport_kwargs: dict[str, Any] = {}
    if timeout_seconds is not None:
        transport_kwargs["timeout_seconds"] = timeout_seconds
    client = register_copilot(
        cmd,
        LoopbackPlanClient(port, credential, **transport_kwargs),
        output,
    )
    output(f"copilot: connected to the server on 127.0.0.1:{port}.")
    return client
