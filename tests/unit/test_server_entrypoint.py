# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic tests for the production server entrypoint.

docs/master_plan.md item 12: the engine fallback, the handoff file, and
the reader that validates it. No PyMOL, no real Lemonade -- every
Lemonade call goes through `httpx.MockTransport`.
"""

from __future__ import annotations

import inspect
import json
import os
import stat
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

import pmc_server.main as server_main
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.unavailable import UnavailableEngine
from pmc_client.bootstrap import connect_from_handoff
from pmc_client.command import CopilotCommandClient
from pmc_client.recovery import RecoveryStore
from pmc_client.transport import LoopbackPlanClient
from pmc_core.protocol import HealthRequestV1


class _FakeSession:
    """The minimal live-session surface `register_copilot` needs.

    `keyword` mirrors real PyMOL's own attribute, populated by `extend()`
    exactly as `tests/integration/test_command.py`'s own fake does: the
    same shape `register()`'s `cmd.keyword["copilot"][4] = ...` line needs.
    """

    def __init__(self) -> None:
        """Record every registered command name and its keyword entry."""
        self.registered: list[str] = []
        self.keyword: dict[str, list[Any]] = {}

    def extend(self, name: str, callback: Any) -> None:
        """Record a registered command name and its keyword entry.

        Args:
            name: Command name to register.
            callback: The registered callback.
        """
        self.registered.append(name)
        self.keyword[name] = [callback, 0, 0, ",", 11]

    def __getattr__(self, _name: str) -> Any:
        """Never queried by registration or a bootstrap refusal path."""
        raise AssertionError("unexpected live-session query")


def _refusing_client(status: int) -> httpx.Client:
    """Build a client whose every request fails with one HTTP status.

    Args:
        status: The HTTP status every request receives.

    Returns:
        A hermetic client that never reaches a network.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    return httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(handler)
    )


def test_build_engine_returns_unavailable_on_a_failed_probe() -> None:
    """A failed capability probe becomes `UnavailableEngine`, not a crash."""
    engine = server_main.build_engine(
        base_url="http://127.0.0.1", client=_refusing_client(503)
    )

    assert isinstance(engine, UnavailableEngine)
    assert engine.health().state != "ready"


def test_build_engine_never_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """`build_engine` calls `connect_lemonade` exactly once."""
    calls: list[str] = []

    def fake_connect(*, base_url: str, client: Any) -> EngineFailure:
        del client
        calls.append(base_url)
        return EngineFailure("engine_unavailable", "refused")

    monkeypatch.setattr(server_main, "connect_lemonade", fake_connect)

    server_main.build_engine(base_url="http://127.0.0.1")

    assert len(calls) == 1


def test_build_engine_returns_a_real_engine_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful probe returns the connected engine, never wrapped."""
    sentinel = object()

    def fake_connect(*, base_url: str, client: Any) -> Any:
        del base_url, client
        return sentinel

    monkeypatch.setattr(server_main, "connect_lemonade", fake_connect)

    engine = server_main.build_engine(base_url="http://127.0.0.1")

    assert engine is sentinel
    assert not isinstance(engine, UnavailableEngine)


def test_write_handoff_is_private_and_names_the_real_port(
    tmp_path: Path,
) -> None:
    """The handoff file is mode 0600, parses, and names the real port."""
    path = tmp_path / "session.json"

    server_main.write_handoff(path, port=54321, credential="c" * 43, pid=1)

    assert path.exists()
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(path.read_text())
    assert payload["port"] == 54321
    assert payload["host"] == "127.0.0.1"
    assert payload["credential"] == "c" * 43


def test_write_handoff_never_chmods_a_pre_existing_directory(
    tmp_path: Path,
) -> None:
    """A directory `--handoff` already points into is left untouched.

    Martin's own scenario: `--handoff session.json` (the current working
    directory), `--handoff ~/session.json` (the home directory), and
    `--handoff /tmp/pmc.json` (a directory the current user does not own)
    must never have their mode changed -- unconditionally chmodding a
    directory this call did not create either mutates a directory it does
    not own, or, when the current user does not own it, raises
    `PermissionError` and crashes the server right after it started.
    """
    directory = tmp_path / "already-exists"
    directory.mkdir()
    if os.name != "nt":
        directory.chmod(0o751)

    server_main.write_handoff(
        directory / "session.json", port=1, credential="c" * 43, pid=1
    )

    if os.name != "nt":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o751


def test_write_handoff_chmods_a_directory_it_creates_itself(
    tmp_path: Path,
) -> None:
    """A directory `write_handoff` creates fresh is still made private."""
    directory = tmp_path / "brand-new" / "nested"

    server_main.write_handoff(
        directory / "session.json", port=1, credential="c" * 43, pid=1
    )

    if os.name != "nt":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_remove_handoff_if_own_removes_a_file_this_process_wrote(
    tmp_path: Path,
) -> None:
    """A handoff file naming this process's own pid is removed."""
    path = tmp_path / "session.json"
    server_main.write_handoff(path, port=1, credential="c" * 43, pid=4242)

    server_main.remove_handoff_if_own(path, pid=4242)

    assert not path.exists()


def test_remove_handoff_if_own_never_deletes_a_second_servers_handoff(
    tmp_path: Path,
) -> None:
    """A second server overwriting the same path is never deleted.

    Not by the first server's own shutdown. Martin's own scenario:
    server A is running; server B starts and
    overwrites the same (most often default, unspecified `--handoff`)
    path with its own port and credential; A is then stopped. A's own
    shutdown must not delete B's live handoff, or a client reading it
    afterward finds nothing even though a real server is still up.
    """
    path = tmp_path / "session.json"
    server_main.write_handoff(path, port=1, credential="a" * 43, pid=1111)

    server_main.write_handoff(path, port=2, credential="b" * 43, pid=2222)
    server_main.remove_handoff_if_own(path, pid=1111)

    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["pid"] == 2222
    assert payload["port"] == 2


def test_remove_handoff_if_own_tolerates_a_missing_file(
    tmp_path: Path,
) -> None:
    """No file at the path is not an error -- there is nothing to remove."""
    server_main.remove_handoff_if_own(tmp_path / "missing.json", pid=1)


def test_remove_handoff_if_own_tolerates_a_malformed_file(
    tmp_path: Path,
) -> None:
    """A file that is not valid JSON is left alone, never raised on."""
    path = tmp_path / "session.json"
    path.write_text("not json at all")

    server_main.remove_handoff_if_own(path, pid=1)

    assert path.exists()


def test_serve_installs_signal_handlers_before_starting_the_server() -> None:
    """Signal handlers are installed before `server.start()`, not after.

    A SIGTERM arriving between `server.start()`/`write_handoff` and signal
    registration would use Python's default action and kill the process
    without ever running `serve`'s own `finally`, leaving a handoff file
    behind that names a port and credential nothing is listening on
    anymore. A real race like that can't be exercised deterministically
    without introducing timing-dependent flakiness, so this is checked
    structurally instead: `signal.signal` must appear, in source order,
    before `server.start()`.
    """
    source = inspect.getsource(server_main.serve)
    assert source.index("signal.signal(signal.SIGINT") < source.index(
        "server.start()"
    )


def test_serve_waits_on_a_timed_loop_not_an_untimed_wait() -> None:
    """The stop-wait is a timed loop, not a single untimed `Event.wait()`.

    On Windows (Python 3.13), an untimed `Event.wait()` blocks on a lock
    acquire that cannot be interrupted, so the SIGINT handler installed
    above never actually runs while the main thread is parked there, and
    Ctrl+C cannot stop the server. Checked structurally, for the same
    reason as the signal-ordering test above: this is a platform-specific
    behavior difference a hermetic, single-platform suite cannot reproduce
    directly.
    """
    source = inspect.getsource(server_main.serve)
    assert "own_stop.wait()" not in source
    assert "own_stop.wait(timeout=" in source


def test_serve_starts_and_writes_the_handoff_with_an_unavailable_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The server starts (and answers health) even when Lemonade is down.

    SPECIFICATION.md:609: "Server remains available for diagnostics; no
    unconstrained fallback."
    """
    monkeypatch.setattr(
        server_main,
        "connect_lemonade",
        lambda **_kwargs: EngineFailure("engine_unavailable", "refused"),
    )
    handoff = tmp_path / "session.json"
    stop = threading.Event()
    ready = threading.Event()
    ports: list[int] = []

    thread = threading.Thread(
        target=server_main.serve,
        kwargs={
            "handoff_path": handoff,
            "stop": stop,
            "ready": lambda port: (ports.append(port), ready.set()),
        },
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(5.0)
        written = json.loads(handoff.read_text())
        credential = written["credential"]
        assert isinstance(credential, str)
        client = LoopbackPlanClient(ports[0], credential)
        response = client.health(
            HealthRequestV1(
                request_id="11111111-1111-4111-8111-111111111111",
                session_id="22222222-2222-4222-8222-222222222222",
            )
        )
        assert response.engine.state != "ready"
    finally:
        stop.set()
        thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert not handoff.exists()


def test_connect_from_handoff_refuses_a_missing_file(tmp_path: Path) -> None:
    """No handoff file: one bounded line, no registration, `None`."""
    output: list[str] = []
    session = _FakeSession()

    client = connect_from_handoff(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        session,
        output.append,
        path=tmp_path / "missing.json",
    )

    assert client is None
    assert session.registered == []
    assert len(output) == 1
    assert output[0].startswith("copilot:")


_INVALID_HANDOFF_PAYLOADS = [
    {"host": "0.0.0.0", "port": 1, "credential": "c" * 43},
    {"host": "10.0.0.5", "port": 1, "credential": "c" * 43},
    {"host": "localhost", "port": 0, "credential": "c" * 43},
    {"host": "localhost", "port": 70000, "credential": "c" * 43},
    {"host": "localhost", "port": 1, "credential": "short"},
    # 43 characters -- at least `_MIN_CREDENTIAL_LENGTH` -- so this case
    # actually reaches and exercises the alphabet check; a short string
    # with a space in it (the original form of this case) was rejected by
    # the length check first, and would still pass even if the alphabet
    # check were removed entirely.
    {"host": "localhost", "port": 1, "credential": "c" * 42 + "!"},
]
_INVALID_HANDOFF_IDS = [
    "any_host",
    "routable_host",
    "port_low",
    "port_high",
    "short_credential",
    "bad_alphabet",
]


@pytest.mark.parametrize(
    "payload", _INVALID_HANDOFF_PAYLOADS, ids=_INVALID_HANDOFF_IDS
)
def test_connect_from_handoff_refuses_every_invalid_field(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    """Each invalid field is refused, with one bounded line and `None`."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps(payload))
    output: list[str] = []
    session = _FakeSession()

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(session, output.append, path=path)

    assert client is None
    assert session.registered == []
    assert len(output) == 1


def test_connect_from_handoff_refuses_a_non_json_file(tmp_path: Path) -> None:
    """A file that is not JSON is refused, not raised."""
    path = tmp_path / "session.json"
    path.write_text("not json at all")
    output: list[str] = []

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(_FakeSession(), output.append, path=path)

    assert client is None
    assert len(output) == 1


def test_connect_from_handoff_refuses_deeply_nested_json_without_raising(
    tmp_path: Path,
) -> None:
    """Deeply nested JSON is refused, not raised.

    `json.loads`'s own recursive-descent parser raises `RecursionError`
    for input like this -- comfortably under `MAX_HANDOFF_BYTES` -- which
    is not `json.JSONDecodeError` and was not caught here before.
    """
    path = tmp_path / "session.json"
    path.write_text("[" * 3000)
    output: list[str] = []

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(_FakeSession(), output.append, path=path)

    assert client is None
    assert len(output) == 1


def test_connect_from_handoff_refuses_an_oversized_file(
    tmp_path: Path,
) -> None:
    """A file larger than the small cap is refused before it is parsed."""
    from pmc_client.bootstrap import MAX_HANDOFF_BYTES

    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                "host": "localhost",
                "port": 1,
                "credential": "c" * 43,
                "padding": "x" * (MAX_HANDOFF_BYTES + 1),
            }
        )
    )
    output: list[str] = []

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(_FakeSession(), output.append, path=path)

    assert client is None
    assert len(output) == 1


def test_connect_from_handoff_registers_on_a_valid_file(
    tmp_path: Path,
) -> None:
    """A fully valid handoff registers every command and reports success."""
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps({"host": "127.0.0.1", "port": 54321, "credential": "c" * 43})
    )
    output: list[str] = []
    session = _FakeSession()

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(session, output.append, path=path)

    assert isinstance(client, CopilotCommandClient)
    assert "copilot" in session.registered
    assert "copilot_apply" in session.registered
    assert "copilot_health" in session.registered
    assert any("connected" in line for line in output)


def test_connect_from_handoff_forwards_an_injected_recovery_store(
    tmp_path: Path,
) -> None:
    """A caller-supplied recovery store reaches the registered client.

    Without this, a test pointed at a real handoff file has no way to
    root recovery points anywhere but the real user's home directory --
    the same gap Martin's own review found: a regression that wrote one
    would land in `~/.pymol-copilot/recovery`, invisible to a test
    watching its own `tmp_path`.
    """
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps({"host": "127.0.0.1", "port": 54321, "credential": "c" * 43})
    )
    output: list[str] = []
    store = RecoveryStore(tmp_path)

    client = connect_from_handoff(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        _FakeSession(),
        output.append,
        path=path,
        recovery_store=store,
    )

    assert isinstance(client, CopilotCommandClient)
    assert client._recovery_store is store


def test_client_closure_never_reaches_langgraph_or_httpx() -> None:
    """`bootstrap.py` must not widen `pmc_client`'s own forbidden closure.

    Static, not a Bazel query: `pmc_client.bootstrap` imports nothing
    outside `pmc_client`/`pmc_core`, checked directly against its own
    module source rather than trusted by inspection.
    """
    import ast
    import inspect

    import pmc_client.bootstrap as bootstrap_module

    tree = ast.parse(inspect.getsource(bootstrap_module))
    modules = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "langgraph" not in modules
    assert "httpx" not in modules
    assert "pmc_agent" not in modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
